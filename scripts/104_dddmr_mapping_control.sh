#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
FLOOR="${2:-}"
RUN_DIR="${M20PRO_DDDMR_MAPPING_RUN_DIR:-${M20PRO_LIGHTNING_MAPPING_RUN_DIR:-/root/.m20pro_lightning_mapping}}"
ARCHIVE_DIR="${M20PRO_DDDMR_MAPPING_ARCHIVE_DIR:-${M20PRO_LIGHTNING_MAPPING_ARCHIVE_DIR:-/root/lightning_maps}}"
WS_DIR="${M20PRO_WS:-/home/user/m20pro_real_ros2_ws_v4}"
# 104 is Foxy/RK3588/ARM64.  The Lightning runtime must be built natively on
# that host; the Humble/x86 development install tree is never valid here.
LIGHTNING_RUNTIME_DISTRO="${M20PRO_DDDMR_RUNTIME_DISTRO:-${M20PRO_LIGHTNING_RUNTIME_DISTRO:-foxy}}"
LIGHTNING_RUNTIME_WS="${M20PRO_DDDMR_RUNTIME_WS:-${M20PRO_LIGHTNING_RUNTIME_WS:-/home/user/m20pro_real_ros2_ws_v4}}"
LIGHTNING_RUNTIME_SETUP="${M20PRO_DDDMR_RUNTIME_SETUP:-${M20PRO_LIGHTNING_RUNTIME_SETUP:-}}"
MAPPING_PACKAGE="${M20PRO_DDDMR_MAPPING_PACKAGE:-m20pro_bringup}"
MAPPING_LAUNCH="${M20PRO_DDDMR_MAPPING_LAUNCH:-m20pro_lightning_mapping.launch.py}"
LIGHTNING_ALGORITHM_PACKAGE="${M20PRO_DDDMR_ALGORITHM_PACKAGE:-${M20PRO_LIGHTNING_ALGORITHM_PACKAGE:-lightning}}"
LIGHTNING_CONFIG_FILE="${M20PRO_LIGHTNING_MAPPING_CONFIG:-}"
LIGHTNING_WORK_DIR="${M20PRO_LIGHTNING_MAPPING_WORK_DIR:-${RUN_DIR}/work}"
LIGHTNING_ENABLE_CLOUD_ADAPTER="${M20PRO_LIGHTNING_ENABLE_CLOUD_ADAPTER:-false}"
LIGHTNING_SOURCE_CLOUD_TOPIC="${M20PRO_LIGHTNING_SOURCE_CLOUD_TOPIC:-/LIDAR/POINTS}"
LIGHTNING_POINTS_TOPIC="${M20PRO_LIGHTNING_POINTS_TOPIC:-/m20pro/lightning_points}"
LIGHTNING_CLOUD_EXPECTED_FRAME="${M20PRO_LIGHTNING_CLOUD_EXPECTED_FRAME:-m20pro_base_link}"
LIGHTNING_CLOUD_OUTPUT_FRAME="${M20PRO_LIGHTNING_CLOUD_OUTPUT_FRAME:-lidar_link}"
LIGHTNING_GROUND_HEIGHT_M="${M20PRO_LIGHTNING_GROUND_HEIGHT_M:-0.35}"
LIGHTNING_GROUND_LOWER_MARGIN_M="${M20PRO_LIGHTNING_GROUND_LOWER_MARGIN_M:-0.10}"
LIGHTNING_SAVE_WAIT_S="${M20PRO_LIGHTNING_SAVE_WAIT_S:-30}"
PID_FILE="${RUN_DIR}/mapping.pid"
ROS2_WAIT_CALL="${WS_DIR}/scripts/ros2_service_wait_call.py"
STATE_FILE="${RUN_DIR}/state.json"
LOG_DIR="${RUN_DIR}/logs"
ENV_CACHE_FILE="${RUN_DIR}/ros_env.cache"
# DDS profile selected by the caller before any sourcing: the cached ROS
# environment is caller-agnostic and must not override it on replay.
INCOMING_FASTRTPS_PROFILE="${FASTRTPS_DEFAULT_PROFILES_FILE:-}"
INCOMING_PATH="${PATH:-}"
DENSE_CHAIN_HEARTBEAT="${M20PRO_DENSE_CHAIN_HEARTBEAT:-/tmp/m20pro_dense_cloud_publisher.heartbeat}"
# Dense-chain lifetime backstop. Mapping sessions are battery-bound (<2h);
DENSE_CHAIN_WINDOW_S="${M20PRO_DENSE_CHAIN_WINDOW_S:-7200}"
SAVE_SERVICE_MARKER="${RUN_DIR}/save_service_seen"
# 2026-08-21 LIO 发散保护: mapper 以 M20PRO_LIGHTNING_HEALTH_FILE 环境变量
# 接收健康文件路径, 运行期 1Hz 原子写 state=ok/diverged; status/finish 读取。
HEALTH_FILE="${RUN_DIR}/lightning_health.txt"

usage() {
  cat >&2 <<'EOF'
Usage: 104_dddmr_mapping_control.sh {start|finish|cancel|status} [floor]

  v4 keeps the Web/API mapping command contract but replaces the v3
  LeGO-LOAM mapper with DeepRoboticsLab Lightning-LM.  start runs
  lightning/run_slam_online on the raw factory /LIDAR/POINTS + /IMU stream by
  default.  The old /dddmr/edge_cloud -> /m20pro/lightning_points adapter is an
  explicit diagnostic fallback only, enabled with M20PRO_LIGHTNING_ENABLE_CLOUD_ADAPTER=true
  and an adapter profile. finish calls /lightning/save_map, saves
  /lightning/save_path, derives map.pcd, ground.pcd and poses.pcd, then archives
  them for the existing 3D frontend.
EOF
}

env_cache_fingerprint() {
  local ws_mtime foxy_mtime primary_ip
  ws_mtime="$(stat -c %Y "${WS_DIR}/install" 2>/dev/null || echo 0)"
  foxy_mtime="$(stat -c %Y "/opt/ros/${LIGHTNING_RUNTIME_DISTRO}/setup.bash" 2>/dev/null || echo 0)"
  primary_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  printf 'fp=%s:%s:%s:%s:%s\n' "${ws_mtime}" "${foxy_mtime}" "${primary_ip}" "${LIGHTNING_RUNTIME_WS}" "${WS_DIR}"
}

build_env_cache() {
  # Derive the fully-sourced overlay environment once in a clean subshell so
  # the cache does not depend on the caller's inherited environment. Sourcing
  # the vendor script + workspace overlays spawns a python interpreter per
  # ament package hook; under field CPU contention that dominated status
  # latency (30s+ web gate timeouts observed on 104). Replay the cached
  # `export -p` dump instead of re-running the hooks on every call.
  local tmp="${ENV_CACHE_FILE}.tmp.$$"
  if env -i HOME="${HOME:-/root}" USER="$(id -un)" LANG="${LANG:-C.UTF-8}" \
      PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
      bash -c '
        distro="$1"; runtime_ws="$2"; ws="$3"
        set +u
        if [[ -f /opt/robot/scripts/setup_ros2.sh ]]; then
          source /opt/robot/scripts/setup_ros2.sh >/dev/null 2>&1
        elif [[ -f "/opt/ros/${distro}/setup.bash" ]]; then
          source "/opt/ros/${distro}/setup.bash" >/dev/null 2>&1
        fi
        if [[ -n "${runtime_ws}" && "${runtime_ws}" != "${ws}" && -f "${runtime_ws}/install/setup.bash" ]]; then
          source "${runtime_ws}/install/setup.bash" >/dev/null 2>&1
        fi
        if [[ -f "${ws}/install/setup.bash" ]]; then
          source "${ws}/install/setup.bash" >/dev/null 2>&1
        fi
        # `export -p` emits `declare -x` lines; sourced inside a function
        # those would create function-local variables that vanish when
        # source_ros2 returns. Rewrite to `export` assignments so the
        # replay lands in global scope.
        export -p | sed "s/^declare -x /export /"
      ' _ "${LIGHTNING_RUNTIME_DISTRO}" "${LIGHTNING_RUNTIME_WS}" "${WS_DIR}" > "${tmp}" 2>/dev/null \
      && [[ -s "${tmp}" ]]; then
    { env_cache_fingerprint; cat "${tmp}"; } > "${ENV_CACHE_FILE}" 2>/dev/null || true
  fi
  rm -f "${tmp}" 2>/dev/null || true
}

source_ros2() {
  local distro_setup="${LIGHTNING_RUNTIME_SETUP:-/opt/ros/${LIGHTNING_RUNTIME_DISTRO}/setup.bash}"
  local project_setup="${WS_DIR}/install/setup.bash"
  local fp cache_ok=false
  fp="$(env_cache_fingerprint)"
  if [[ -f "${ENV_CACHE_FILE}" && "$(head -n1 "${ENV_CACHE_FILE}" 2>/dev/null)" == "${fp}" ]]; then
    set +u
    # shellcheck disable=SC1090
    source "${ENV_CACHE_FILE}" >/dev/null 2>&1 && cache_ok=true
    set -u
  fi
  if [[ "${cache_ok}" != "true" ]]; then
    build_env_cache
    if [[ -f "${ENV_CACHE_FILE}" ]]; then
      set +u
      # shellcheck disable=SC1090
      source "${ENV_CACHE_FILE}" >/dev/null 2>&1 && cache_ok=true
      set -u
    fi
  fi
  if [[ "${cache_ok}" != "true" ]]; then
    # Slow fallback (e.g. non-root without a writable cache dir).
    if [[ -f /opt/robot/scripts/setup_ros2.sh ]]; then
      set +u
      # shellcheck disable=SC1091
      source /opt/robot/scripts/setup_ros2.sh >/dev/null 2>&1
      set -u
    elif [[ -f "${distro_setup}" ]]; then
      set +u
      # shellcheck disable=SC1091
      source "${distro_setup}" >/dev/null 2>&1
      set -u
    fi
    if [[ "${LIGHTNING_RUNTIME_WS}" != "${WS_DIR}" && -f "${LIGHTNING_RUNTIME_WS}/install/setup.bash" ]]; then
      set +u
      # shellcheck disable=SC1091
      source "${LIGHTNING_RUNTIME_WS}/install/setup.bash" >/dev/null 2>&1
      set -u
    fi
    if [[ -f "${project_setup}" ]]; then
      set +u
      # shellcheck disable=SC1090
      source "${project_setup}" >/dev/null 2>&1
      set -u
    fi
  fi
  if [[ -n "${INCOMING_PATH}" ]]; then
    export PATH="${INCOMING_PATH}:${PATH:-}"
  fi
  # The cached/built environment was derived caller-agnostically; restore the
  # caller's DDS profile selection (vendor profile for bare-DDS LiDAR ingest
  # under the service, project profile in development shells).
  if [[ -n "${INCOMING_FASTRTPS_PROFILE}" && -f "${INCOMING_FASTRTPS_PROFILE}" ]]; then
    export FASTRTPS_DEFAULT_PROFILES_FILE="${INCOMING_FASTRTPS_PROFILE}"
  fi
  # The Lightning runtime owns the upstream `lightning` package only.  The
  # Web/API launch, adapters and mapping config must come from the active
  # M20Pro workspace so v4 edits cannot be shadowed by a stale runtime copy of
  # m20pro_bringup.
  project_package_prefix="${WS_DIR}/install/${MAPPING_PACKAGE}"
  if [[ -d "${project_package_prefix}" ]]; then
    export AMENT_PREFIX_PATH="${project_package_prefix}:${WS_DIR}/install${AMENT_PREFIX_PATH:+:${AMENT_PREFIX_PATH}}"
  elif [[ -d "${WS_DIR}/install" ]]; then
    export AMENT_PREFIX_PATH="${WS_DIR}/install${AMENT_PREFIX_PATH:+:${AMENT_PREFIX_PATH}}"
  fi
  if [[ -d "${WS_DIR}/install" ]]; then
    export COLCON_PREFIX_PATH="${WS_DIR}/install${COLCON_PREFIX_PATH:+:${COLCON_PREFIX_PATH}}"
  fi
  local project_fastdds="${WS_DIR}/install/m20pro_bringup/share/m20pro_bringup/config/m20pro_fastdds_udp.xml"
  # Global handle for discovery-sensitive queries (see ros_query_env).
  PROJECT_FASTDDS_PROFILE="${project_fastdds}"
  # `/opt/robot/scripts/setup_ros2.sh` selects the vendor DDS profile that is
  # known to receive the M20Pro bare-DDS LiDAR streams.  Keep that profile when
  # it exists; only fall back to the project profile for development or hosts
  # that do not provide the vendor setup.
  if [[ (-z "${FASTRTPS_DEFAULT_PROFILES_FILE:-}" || ! -f "${FASTRTPS_DEFAULT_PROFILES_FILE}") && -f "${project_fastdds}" ]]; then
    export FASTRTPS_DEFAULT_PROFILES_FILE="${project_fastdds}"
  fi
}

ros_query_env() {
  # Lightning mapper services are only reliably discoverable from the M20Pro
  # project DDS profile: vendor-profile participants miss them even when
  # long-lived, while project-profile participants converge in ~1s (verified
  # on 104 under boot load). The mapper itself keeps the vendor profile for
  # the bare-DDS LiDAR ingest; only discovery-sensitive queries switch.
  if [[ -n "${PROJECT_FASTDDS_PROFILE:-}" && -f "${PROJECT_FASTDDS_PROFILE}" ]]; then
    FASTRTPS_DEFAULT_PROFILES_FILE="${PROJECT_FASTDDS_PROFILE}" "$@"
  else
    "$@"
  fi
}

source_cloud_chain_alive() {
  # Frame-level heartbeat written by dddmr_dense_cloud_publisher.py after
  # successful publishes (throttled to 2 Hz). A fresh mtime proves the whole
  # dense chain (106 passthrough -> 104 socket bridge -> publisher) delivered
  # a publishable frame within the window. Reading an mtime stays instant
  # under field CPU contention, unlike booting a fresh rclpy participant
  # (python+rclpy import measured at 16s under load 26 on 104), so the Web
  # status gate no longer depends on a one-shot DDS probe.
  # Both proofs are required: right after a stop, the heartbeat mtime stays
  # fresh for up to 5s while the publisher process is already gone — trusting
  # the file alone let a start slip through into a blind mapper (observed in
  # the 2026-08-19 lifecycle test: start 4s after finish). pgrep is a few ms.
  local now_t mtime_t
  [[ -f "${DENSE_CHAIN_HEARTBEAT}" ]] || return 1
  # 2026-08-20 raw chain: the dense publisher is raw_lidar_merge_node.py;
  # accept either it or the legacy dddmr_dense_cloud_publisher.
  if ! pgrep -f "dddmr_dense_cloud_[p]ublisher" >/dev/null 2>&1 \
     && ! pgrep -f "raw_lidar_merge_[n]ode" >/dev/null 2>&1; then
    return 1
  fi
  now_t="$(date +%s)"
  mtime_t="$(stat -c %Y "${DENSE_CHAIN_HEARTBEAT}" 2>/dev/null || echo 0)"
  (( now_t - mtime_t <= 5 ))
}

source_cloud_available_check() {
  # 2026-09-01: keep this probe O(1). The Web mapping-status gate runs this
  # on every frontend poll, and the former rclpy DDS fallback booted a python
  # interpreter per call (measured 16-24s under RK3588 boot load), which blew
  # the frontend's 15s timeout and blocked the mapping-start button.
  # Heartbeat file semantics: present => a chain ran since boot; its mtime
  # freshness is already checked by source_cloud_chain_alive. Absent => the
  # chain never ran this boot, report false instantly instead of probing DDS.
  # This check is informational only: mapping start self-heals the dense
  # chain via ensure_source_cloud_chain, so a false here never strands the
  # operator.
  if source_cloud_chain_alive; then
    return 0
  fi
  return 1
}


ensure_source_cloud_chain() {
  # Self-heal the dense source chain at mapping start so the frontend start
  # button never strands the operator with a manual shell step: chain
  # processes run under `timeout` and expire after their window, which used
  # to surface as "密集数据链未启动或无数据" on the next start click.
  # Budget: the Web start command allows 120s; chain start without its
  # built-in verify costs ~8s and a fresh heartbeat appears well inside 30s.
  local waited=0
  if source_cloud_chain_alive; then
    return 0
  fi
  if pgrep -f "dddmr_dense_cloud_[p]ublisher" >/dev/null 2>&1 \
     || pgrep -f "raw_lidar_merge_[n]ode" >/dev/null 2>&1; then
    # Processes alive but heartbeat stale: grace period, then force a clean
    # restart below (hung chain = alive processes, no frames).
    while (( waited < 8 )); do
      sleep 1
      waited=$((waited + 1))
      if source_cloud_chain_alive; then
        return 0
      fi
    done
    bash "${WS_DIR}/scripts/dense_mapping_chain.sh" stop >&2 || true
  fi
  echo "[mapping_control] dense chain down; auto-starting with ${DENSE_CHAIN_WINDOW_S}s window" >&2
  M20PRO_DENSE_CHAIN_SKIP_VERIFY=1 bash "${WS_DIR}/scripts/dense_mapping_chain.sh" start "${DENSE_CHAIN_WINDOW_S}" >&2 || true
  waited=0
  while (( waited < 30 )); do
    sleep 1
    waited=$((waited + 1))
    if source_cloud_chain_alive; then
      return 0
    fi
  done
  return 1
}


save_service_evidence() {
  # Monotonic, load-tolerant proof that the mapper created its save services
  # (SaveMap/SavePath live for the mapper's whole lifetime once created).
  # One-shot DDS discovery is unreliable under field CPU contention (probe
  # starved past its budget while the service demonstrably exists), so trust:
  #   1. a persisted marker from an earlier observation of this session,
  #   2. the mapper's own log line (slam.cc "SavePath service has been
  #      created.", written at service creation),
  # and let the caller fall back to a live probe only when neither matches.
  local pid_value="${1:-}" map_id_value="${2:-}" log_value="${3:-}"
  if [[ -n "${pid_value}" && -f "${SAVE_SERVICE_MARKER}" ]]; then
    if [[ "$(cat "${SAVE_SERVICE_MARKER}" 2>/dev/null)" == "${pid_value} ${map_id_value}" ]]; then
      return 0
    fi
  fi
  if [[ -n "${log_value}" && -f "${log_value}" ]] && grep -q "SavePath service has been created" "${log_value}" 2>/dev/null; then
    printf '%s %s\n' "${pid_value}" "${map_id_value}" > "${SAVE_SERVICE_MARKER}" 2>/dev/null || true
    return 0
  fi
  return 1
}


check_runtime_distro() {
  if [[ -n "${ROS_DISTRO:-}" && "${ROS_DISTRO}" != "${LIGHTNING_RUNTIME_DISTRO}" ]]; then
    echo "ok=false"
    echo "code=lightning_runtime_distro_mismatch"
    echo "message=Lightning runtime requires ROS 2 ${LIGHTNING_RUNTIME_DISTRO}, found ${ROS_DISTRO}"
    exit 21
  fi
}

default_config_file() {
  if [[ -n "${LIGHTNING_CONFIG_FILE}" ]]; then
    printf '%s\n' "${LIGHTNING_CONFIG_FILE}"
    return 0
  fi
  local prefix
  prefix="$(pkg_prefix "${MAPPING_PACKAGE}")"
  if [[ -n "${prefix}" ]]; then
    printf '%s/share/%s/config/lightning_m20pro_raw_mapping.yaml\n' "${prefix}" "${MAPPING_PACKAGE}"
  fi
}

pkg_prefix() {
  # Resolve a package's ament prefix straight from the on-disk ament index
  # (share/ament_index/resource_index/packages/<pkg>) by walking
  # AMENT_PREFIX_PATH in order, exactly like `ros2 pkg prefix` does, but
  # without booting the ros2 CLI (~1-2s per call, much worse under load).
  # The Web mapping status gate timed out on the RK3588 while spawning the
  # CLI, so status/start reads resolve the index directly.
  local package_name="${1:-}"
  [[ -n "${package_name}" && -n "${AMENT_PREFIX_PATH:-}" ]] || return 0
  local prefixes=() prefix
  IFS=':' read -r -a prefixes <<< "${AMENT_PREFIX_PATH}"
  for prefix in "${prefixes[@]}"; do
    if [[ -n "${prefix}" && -f "${prefix}/share/ament_index/resource_index/packages/${package_name}" ]]; then
      printf '%s\n' "${prefix}"
      return 0
    fi
  done
  return 0
}

path_under() {
  local path_value="${1:-}"
  local root_value="${2:-}"
  [[ -n "${path_value}" && -n "${root_value}" ]] || return 1
  local resolved_path resolved_root
  resolved_path="$(readlink -f "${path_value}" 2>/dev/null || printf '%s' "${path_value}")"
  resolved_root="$(readlink -f "${root_value}" 2>/dev/null || printf '%s' "${root_value}")"
  [[ "${resolved_path}" == "${resolved_root}" || "${resolved_path}" == "${resolved_root}/"* ]]
}

require_project_mapping_overlay() {
  local mapping_prefix="${1:-}"
  local project_install="${WS_DIR}/install"
  if ! path_under "${mapping_prefix}" "${project_install}"; then
    echo "ok=false"
    echo "code=lightning_mapping_overlay_mismatch"
    echo "message=${MAPPING_PACKAGE} resolved outside the active M20Pro workspace; check source order"
    echo "mapping_package_prefix=${mapping_prefix}"
    echo "expected_project_install=${project_install}"
    echo "lightning_runtime_ws=${LIGHTNING_RUNTIME_WS}"
    exit 22
  fi
}

sanitize_tag() {
  printf '%s' "${1:-lightning}" | tr -cs 'A-Za-z0-9._-' '_'
}

mapping_cpu_pin_prefix() {
  # Vendor kernel boots with isolcpus=4,5,6,7 (verified 2026-08-19): PID1 and
  # therefore the whole robot stack inherit little-core (0-3, A55 1.8GHz)
  # affinity while the four big A76 cores (2.35GHz) sit 100% idle. Explicit
  # affinity may still attach to isolated cores — that is their intended use.
  # Pin the mapper there so the official runtime cannot starve it: the
  # 2026-08-19 walk session consumed clouds at 0.22x realtime on the little
  # cores and the chain backlog ballooned to 4.2GB. Override via
  # M20PRO_MAPPING_CPUS; empty value disables pinning.
  local cpus="${M20PRO_MAPPING_CPUS:-4-7}"
  [[ -n "${cpus}" ]] || return 0
  if command -v taskset >/dev/null 2>&1 && taskset -c "${cpus}" true 2>/dev/null; then
    printf 'taskset -c %s ' "${cpus}"
  fi
}

mapping_launch_command() {
  local config_file="${1:-}"
  local run_dir="${2:-${LIGHTNING_WORK_DIR}}"
  if [[ -n "${config_file}" ]]; then
    printf 'exec ros2 launch %q %q config_file:=%q run_dir:=%q rviz:=false enable_cloud_adapter:=%q cloud_adapter_input_topic:=%q lightning_points_topic:=%q cloud_adapter_expected_frame:=%q cloud_adapter_output_frame:=%q\n' \
      "${MAPPING_PACKAGE}" "${MAPPING_LAUNCH}" "${config_file}" "${run_dir}" \
      "${LIGHTNING_ENABLE_CLOUD_ADAPTER}" "${LIGHTNING_SOURCE_CLOUD_TOPIC}" \
      "${LIGHTNING_POINTS_TOPIC}" "${LIGHTNING_CLOUD_EXPECTED_FRAME}" \
      "${LIGHTNING_CLOUD_OUTPUT_FRAME}"
  else
    printf 'exec ros2 launch %q %q run_dir:=%q rviz:=false enable_cloud_adapter:=%q cloud_adapter_input_topic:=%q lightning_points_topic:=%q cloud_adapter_expected_frame:=%q cloud_adapter_output_frame:=%q\n' \
      "${MAPPING_PACKAGE}" "${MAPPING_LAUNCH}" "${run_dir}" \
      "${LIGHTNING_ENABLE_CLOUD_ADAPTER}" "${LIGHTNING_SOURCE_CLOUD_TOPIC}" \
      "${LIGHTNING_POINTS_TOPIC}" "${LIGHTNING_CLOUD_EXPECTED_FRAME}" \
      "${LIGHTNING_CLOUD_OUTPUT_FRAME}"
  fi
}

write_state() {
  mkdir -p "${RUN_DIR}"
  python3 - "${STATE_FILE}" "$@" <<'PY'
import json
import sys

state_file = sys.argv[1]
keys = [
    "action",
    "floor",
    "pid",
    "log",
    "saved_dir",
    "archive_target",
    "mapcloud",
    "mapground",
    "pose_graph_dir",
    "map_id",
    "work_dir",
    "config_file",
]
payload = {"backend": "lightning_lm"}
for index, key in enumerate(keys, start=2):
    payload[key] = sys.argv[index] if len(sys.argv) > index else ""
with open(state_file, "w", encoding="utf-8") as file:
    json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
    file.write("\n")
PY
}

state_value() {
  local key="${1:-}"
  [[ -n "${key}" && -f "${STATE_FILE}" ]] || return 0
  python3 - "${STATE_FILE}" "${key}" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], "r", encoding="utf-8") as file:
        state = json.load(file)
except Exception:
    sys.exit(0)
value = state.get(sys.argv[2], "")
if value is not None:
    print(value)
PY
}

mapping_log_has_child_death() {
  local log_file="${1:-}"
  [[ -n "${log_file}" && -f "${log_file}" ]] || return 1
  grep -Eq 'process has died|exit code -|failed to init slam|Lightning-LM config file not found' "${log_file}"
}

mapping_slam_process_running() {
  local pid="${1:-}"
  [[ -n "${pid}" ]] || return 1
  kill -0 "${pid}" 2>/dev/null || return 1
  local group_id
  group_id="$(ps -o pgid= -p "${pid}" 2>/dev/null | tr -d ' ' || true)"
  [[ -n "${group_id}" ]] || return 1
  while read -r slam_pid; do
    [[ -n "${slam_pid}" ]] || continue
    local slam_group
    slam_group="$(ps -o pgid= -p "${slam_pid}" 2>/dev/null | tr -d ' ' || true)"
    if [[ "${slam_group}" == "${group_id}" ]] && kill -0 "${slam_pid}" 2>/dev/null; then
      return 0
    fi
  done < <(pgrep -x run_slam_online 2>/dev/null || true)
  return 1
}

terminate_mapping_process_group() {
  local pid="${1:-}"
  [[ -n "${pid}" ]] || return 0
  kill -TERM -- "-${pid}" 2>/dev/null || true
  sleep 1
  kill -KILL -- "-${pid}" 2>/dev/null || true
}

cleanup_mapping_runtime() {
  local pid="${1:-}"
  if [[ -z "${pid}" && -f "${PID_FILE}" ]]; then
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  fi
  if [[ -n "${pid}" ]]; then
    terminate_mapping_process_group "${pid}"
  fi
  rm -f "${PID_FILE}" "${HEALTH_FILE}" "${HEALTH_FILE}.tmp"
  timeout 30 bash "${WS_DIR}/scripts/dense_mapping_chain.sh" stop >/dev/null 2>&1 || true
}

start_mapping() {
  source_ros2
  check_runtime_distro
  local algorithm_prefix=""
  local mapping_prefix=""
  mkdir -p "${LOG_DIR}" "${ARCHIVE_DIR}" "${LIGHTNING_WORK_DIR}/data"
  if [[ -f "${PID_FILE}" ]]; then
    old_pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
      old_log="$(state_value log || true)"
      if mapping_log_has_child_death "${old_log}"; then
        terminate_mapping_process_group "${old_pid}"
        rm -f "${PID_FILE}"
      else
        echo "ok=false"
        echo "code=lightning_mapping_busy"
        echo "message=Lightning-LM 3D mapping is already running"
        echo "pid=${old_pid}"
        exit 4
      fi
    else
      rm -f "${PID_FILE}"
    fi
  fi
  algorithm_prefix="$(pkg_prefix "${LIGHTNING_ALGORITHM_PACKAGE}")"
  if [[ -z "${algorithm_prefix}" ]]; then
    echo "ok=false"
    echo "code=lightning_runtime_missing"
    echo "message=${LIGHTNING_ALGORITHM_PACKAGE} package is not installed in the Lightning runtime"
    exit 21
  fi
  mapping_prefix="$(pkg_prefix "${MAPPING_PACKAGE}")"
  if [[ -z "${mapping_prefix}" ]]; then
    echo "ok=false"
    echo "code=lightning_mapping_launch_missing"
    echo "message=${MAPPING_PACKAGE} launch package is not installed in the active M20Pro workspace"
    exit 21
  fi
  require_project_mapping_overlay "${mapping_prefix}"
  config_file="$(default_config_file)"
  if [[ -z "${config_file}" || ! -f "${config_file}" ]]; then
    echo "ok=false"
    echo "code=lightning_config_missing"
    echo "message=Lightning-LM mapping config is missing"
    echo "config_file=${config_file}"
    exit 22
  fi

  # The mapper would run for an entire walk and produce zero keyframes when
  # the dense source chain is down (no data, nothing to save). Gate on the
  # publisher heartbeat (frame-level proof of data flow) — and when the chain
  # is down, auto-start it unattended instead of failing to a manual shell
  # step (chain windows expire by design; the start button must self-heal).
  # 重复发布器防护: 同一话题双发布器会把两条链的帧混投给 mapper
  # (2026-08-21 16:47 会话收到 93k 点异常帧, 起步即发散)。alive 判定只认
  # "有进程+心跳新", 不检查实例数; 这里在 start 入口强制单实例。
  local merge_instances
  merge_instances="$(pgrep -fc 'raw_lidar_merge_[n]ode' 2>/dev/null || true)"
  if [[ "${merge_instances:-0}" -gt 1 ]]; then
    echo "[mapping_control] duplicate dense-chain publishers detected (${merge_instances} merge nodes); restarting chain" >&2
    bash "${WS_DIR}/scripts/dense_mapping_chain.sh" stop >&2 || true
  fi

  local source_chain_auto_started=false
  if ! source_cloud_chain_alive; then
    if ensure_source_cloud_chain; then
      source_chain_auto_started=true
    fi
  fi
  if ! source_cloud_available_check; then
    echo "ok=false"
    echo "code=lightning_source_cloud_missing"
    echo "message=激光雷达密集数据链自动拉起失败或 ${LIGHTNING_SOURCE_CLOUD_TOPIC} 无数据；请检查 106/104 链路（scripts/dense_mapping_chain.sh status）"
    echo "source_cloud_topic=${LIGHTNING_SOURCE_CLOUD_TOPIC}"
    echo "source_chain_auto_started=${source_chain_auto_started}"
    exit 25
  fi

  timestamp="$(date +%Y%m%d_%H%M%S)"
  floor_tag="$(sanitize_tag "${FLOOR:-F_unknown}")"
  map_id="m20pro_${floor_tag}_lightning_${timestamp}"
  log_file="${LOG_DIR}/lightning_mapping_${floor_tag}_${timestamp}.log"
  launch_cmd="$(mapping_launch_command "${config_file}" "${LIGHTNING_WORK_DIR}")"
  # Pin the mapper (and all launch children) onto the isolated big cores.
  local pin_prefix
  pin_prefix="$(mapping_cpu_pin_prefix)"
  if [[ -n "${pin_prefix}" ]]; then
    launch_cmd="exec ${pin_prefix}${launch_cmd#exec }"
  fi
  # 发散健康文件: 清掉上一会话残留, 通过环境变量交给 mapper。
  rm -f "${HEALTH_FILE}" "${HEALTH_FILE}.tmp"
  export M20PRO_LIGHTNING_HEALTH_FILE="${HEALTH_FILE}"
  setsid bash -lc "${launch_cmd}" >"${log_file}" 2>&1 &
  pid=$!
  echo "${pid}" > "${PID_FILE}"
  write_state start "${FLOOR:-}" "${pid}" "${log_file}" "" "" "" "" "" "${map_id}" "${LIGHTNING_WORK_DIR}" "${config_file}"
  echo "ok=true"
  echo "action=start"
  echo "backend=lightning_lm"
  echo "floor=${FLOOR:-}"
  echo "pid=${pid}"
  echo "map_id=${map_id}"
  echo "work_dir=${LIGHTNING_WORK_DIR}"
  echo "config_file=${config_file}"
  echo "algorithm_package_prefix=${algorithm_prefix}"
  echo "mapping_package_prefix=${mapping_prefix}"
  echo "source_cloud_topic=${LIGHTNING_SOURCE_CLOUD_TOPIC}"
  echo "source_chain_auto_started=${source_chain_auto_started}"
  echo "cloud_adapter_enabled=${LIGHTNING_ENABLE_CLOUD_ADAPTER}"
  echo "lightning_points_topic=${LIGHTNING_POINTS_TOPIC}"
  echo "fastdds_profile=${FASTRTPS_DEFAULT_PROFILES_FILE:-}"
  echo "log=${log_file}"
  echo "health_file=${HEALTH_FILE}"
  echo "launch=${launch_cmd}"
}

finish_mapping() {
  source_ros2
  mkdir -p "${LOG_DIR}" "${ARCHIVE_DIR}"
  map_id="$(state_value map_id || true)"
  work_dir="$(state_value work_dir || true)"
  config_file="$(state_value config_file || true)"
  if [[ -z "${map_id}" ]]; then
    timestamp="$(date +%Y%m%d_%H%M%S)"
    map_id="m20pro_$(sanitize_tag "${FLOOR:-F_unknown}")_lightning_${timestamp}"
  fi
  if [[ -z "${work_dir}" ]]; then
    work_dir="${LIGHTNING_WORK_DIR}"
  fi
  saved_dir="${work_dir}/data/${map_id}"
  save_log="${LOG_DIR}/lightning_mapping_save_$(date +%Y%m%d_%H%M%S).log"
  finish_cleanup_armed=true
  trap 'if [[ "${finish_cleanup_armed:-false}" == "true" ]]; then cleanup_mapping_runtime; fi' EXIT

  # 发散门禁(第一道): mapper 已判散时, 全局地图是无意义垃圾点云且
  # GetGlobalMap 会长时间占满 CPU; 直接拒绝并引导取消重建。
  if [[ -f "${HEALTH_FILE}" ]] && grep -q '^state=diverged' "${HEALTH_FILE}" 2>/dev/null; then
    local health_line
    health_line="$(head -n1 "${HEALTH_FILE}" 2>/dev/null || true)"
    pid=""
    if [[ -f "${PID_FILE}" ]]; then
      pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    fi
    cleanup_mapping_runtime "${pid}"
    write_state finish_failed "${FLOOR:-}" "" "${save_log}" "${saved_dir}" "" "" "" "${work_dir}/data" "${map_id}" "${work_dir}" "${config_file}"
    echo "ok=false"
    echo "code=lightning_diverged"
    echo "message=三维建图过程中定位已发散（位姿超出物理可能范围），本次地图无法保存；请取消本次建图并重新开始，建图时请避免长时间停留在无几何特征的区域"
    echo "health=${health_line}"
    exit 27
  fi

  if ! ros_query_env timeout 130 python3 "${ROS2_WAIT_CALL}" call /lightning/save_map lightning/srv/SaveMap "{map_id: '${map_id}'}" --wait 20 --timeout 90 >"${save_log}" 2>&1; then
    pid=""
    if [[ -f "${PID_FILE}" ]]; then
      pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    fi
    cleanup_mapping_runtime "${pid}"
    write_state finish_failed "${FLOOR:-}" "" "${save_log}" "${saved_dir}" "" "" "" "${work_dir}/data" "${map_id}" "${work_dir}" "${config_file}"
    cat "${save_log}" >&2 || true
    echo "ok=false"
    echo "code=lightning_save_failed"
    echo "message=Lightning-LM save_map service failed"
    echo "save_log=${save_log}"
    exit 22
  fi
  # ROS 2 CLI formats service fields differently across Foxy/Humble:
  # Foxy commonly prints `response=0`, while newer versions may print
  # `response: 0`. Accept both representations and require the actual
  # successful response value.
  # 发散门禁(第二道): mapper 侧在收到存档请求瞬间判散时返回 response=4。
  if grep -Eiq 'response[=:][[:space:]]*4([[:space:],]|$|\))' "${save_log}"; then
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    cleanup_mapping_runtime "${pid}"
    write_state finish_failed "${FLOOR:-}" "" "${save_log}" "${saved_dir}" "" "" "" "${work_dir}/data" "${map_id}" "${work_dir}" "${config_file}"
    cat "${save_log}" >&2 || true
    echo "ok=false"
    echo "code=lightning_diverged"
    echo "message=三维建图过程中定位已发散（位姿超出物理可能范围），本次地图无法保存；请取消本次建图并重新开始"
    echo "save_log=${save_log}"
    exit 27
  fi
  if ! grep -Eiq 'response[=:][[:space:]]*0([[:space:],]|$|\))' "${save_log}"; then
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    cleanup_mapping_runtime "${pid}"
    write_state finish_failed "${FLOOR:-}" "" "${save_log}" "${saved_dir}" "" "" "" "${work_dir}/data" "${map_id}" "${work_dir}" "${config_file}"
    cat "${save_log}" >&2 || true
    echo "ok=false"
    echo "code=lightning_save_rejected"
    echo "message=Lightning-LM rejected map save because the map health gate failed"
    echo "save_log=${save_log}"
    exit 22
  fi

  global_pcd="${saved_dir}/global.pcd"
  for _ in $(seq 1 "${LIGHTNING_SAVE_WAIT_S}"); do
    [[ -s "${global_pcd}" ]] && break
    sleep 1
  done
  if [[ ! -s "${global_pcd}" ]]; then
    pid=""
    if [[ -f "${PID_FILE}" ]]; then
      pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    fi
    cleanup_mapping_runtime "${pid}"
    write_state finish_failed "${FLOOR:-}" "" "${save_log}" "${saved_dir}" "" "" "" "${saved_dir}" "${map_id}" "${work_dir}" "${config_file}"
    echo "ok=false"
    echo "code=lightning_global_map_missing"
    echo "message=Lightning-LM save_map returned but global.pcd is missing or empty"
    echo "saved_dir=${saved_dir}"
    echo "save_log=${save_log}"
    echo "pid=${pid}"
    exit 23
  fi

  path_txt="${saved_dir}/path.txt"
  if ! ros_query_env timeout 70 python3 "${ROS2_WAIT_CALL}" call /lightning/save_path lightning/srv/SavePath "{file_path: '${path_txt}'}" --wait 10 --timeout 30 >>"${save_log}" 2>&1; then
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    cleanup_mapping_runtime "${pid}"
    write_state finish_failed "${FLOOR:-}" "" "${save_log}" "${saved_dir}" "" "" "" "${work_dir}/data" "${map_id}" "${work_dir}" "${config_file}"
    cat "${save_log}" >&2 || true
    echo "ok=false"
    echo "code=lightning_save_path_failed"
    echo "message=Lightning-LM save_path service failed; poses.pcd cannot be generated from real trajectory"
    echo "saved_dir=${saved_dir}"
    echo "save_log=${save_log}"
    exit 24
  fi
  if ! grep -Eiq 'success[=:][[:space:]]*true([[:space:],]|$|\))' "${save_log}"; then
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    cleanup_mapping_runtime "${pid}"
    write_state finish_failed "${FLOOR:-}" "" "${save_log}" "${saved_dir}" "" "" "" "${work_dir}/data" "${map_id}" "${work_dir}" "${config_file}"
    cat "${save_log}" >&2 || true
    echo "ok=false"
    echo "code=lightning_save_path_rejected"
    echo "message=Lightning-LM rejected trajectory save"
    echo "saved_dir=${saved_dir}"
    echo "save_log=${save_log}"
    exit 24
  fi

  asset_log="${LOG_DIR}/lightning_asset_adapter_$(date +%Y%m%d_%H%M%S).log"
  mapcloud="${saved_dir}/map.pcd"
  mapground="${saved_dir}/ground.pcd"
  poses="${saved_dir}/poses.pcd"
  if ! timeout 120 ros2 run m20pro_bringup lightning_pcd_asset_adapter \
      --input "${global_pcd}" \
      --map "${mapcloud}" \
      --ground "${mapground}" \
      --poses "${poses}" \
      --path "${path_txt}" \
      --ground-height "${LIGHTNING_GROUND_HEIGHT_M}" \
      --ground-lower-margin "${LIGHTNING_GROUND_LOWER_MARGIN_M}" \
      >"${asset_log}" 2>&1; then
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    cleanup_mapping_runtime "${pid}"
    write_state finish_failed "${FLOOR:-}" "" "${save_log}" "${saved_dir}" "" "" "" "${work_dir}/data" "${map_id}" "${work_dir}" "${config_file}"
    cat "${asset_log}" >&2 || true
    echo "ok=false"
    echo "code=lightning_asset_adaptation_failed"
    echo "message=Lightning-LM global.pcd could not be converted into v4 frontend assets"
    echo "saved_dir=${saved_dir}"
    echo "asset_log=${asset_log}"
    exit 25
  fi

  if [[ ! -s "${mapcloud}" || ! -s "${mapground}" || ! -s "${poses}" ]]; then
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    cleanup_mapping_runtime "${pid}"
    write_state finish_failed "${FLOOR:-}" "" "${save_log}" "${saved_dir}" "" "" "" "${work_dir}/data" "${map_id}" "${work_dir}" "${config_file}"
    echo "ok=false"
    echo "code=lightning_assets_missing"
    echo "message=Lightning-LM asset adapter did not produce map.pcd, ground.pcd and poses.pcd"
    echo "saved_dir=${saved_dir}"
    echo "mapcloud=${mapcloud}"
    echo "mapground=${mapground}"
    echo "poses=${poses}"
    echo "asset_log=${asset_log}"
    exit 26
  fi

  archive_target="${ARCHIVE_DIR}/${map_id}"
  if [[ -e "${archive_target}" ]]; then
    archive_target="${archive_target}_$(date +%Y%m%d_%H%M%S)"
  fi
  mv "${saved_dir}" "${archive_target}"
  cleanup_mapping_runtime "$(cat "${PID_FILE}" 2>/dev/null || true)"
  mapcloud="${archive_target}/map.pcd"
  mapground="${archive_target}/ground.pcd"
  poses="${archive_target}/poses.pcd"
  pose_graph_dir="${archive_target}"
  write_state finish "${FLOOR:-}" "" "${save_log}" "${saved_dir}" "${archive_target}" "${mapcloud}" "${mapground}" "${pose_graph_dir}" "${map_id}" "${work_dir}" "${config_file}"
  echo "ok=true"
  echo "action=finish"
  echo "backend=lightning_lm"
  echo "floor=${FLOOR:-}"
  echo "map_id=${map_id}"
  echo "saved_dir=${saved_dir}"
  echo "archive_dir=${ARCHIVE_DIR}"
  echo "archive_target=${archive_target}"
  echo "mapcloud=${mapcloud}"
  echo "mapground=${mapground}"
  echo "poses=${poses}"
  echo "pose_graph_dir=${pose_graph_dir}"
  echo "save_log=${save_log}"
  echo "asset_log=${asset_log}"

  # Auto-register the finished map with the local Web dashboard so the 3D
  # view picks it up without a manual POST.  Disable with
  # M20PRO_DDDMR_MAPPING_AUTO_REGISTER=0.
  if [[ "${M20PRO_DDDMR_MAPPING_AUTO_REGISTER:-true}" == "true" ]]; then
    local web_api_base="${M20PRO_WEB_API_BASE:-http://127.0.0.1:8080}"
    # Label carries the map id's time suffix so repeated runs on the same
    # floor stay distinguishable in the frontend (registration is keyed by
    # floor, so the latest run replaces the previous one as the active map).
    local register_label="${FLOOR:-}_$(echo "${map_id}" | grep -oE '[0-9]{6}$' || true)"
    local register_response
    register_response="$(
      curl -s --max-time 15 -X POST "${web_api_base}/api/dddmr/map_assets" \
        -H "Content-Type: application/json" \
        -d "{\"floor\": \"${FLOOR:-}\", \"label\": \"${register_label}\", \"mapcloud\": [\"${mapcloud}\"], \"mapground\": [\"${mapground}\"], \"source\": \"lightning_lm_mapping\", \"note\": \"Lightning-LM auto-registered ${map_id}\"}" \
        2>/dev/null || true
    )"
    if [[ "${register_response}" == *"dddmr_map_asset_registered"* ]]; then
      echo "asset_registered=true"
      echo "asset_registered_code=dddmr_map_asset_registered"
      echo "asset_registered_label=${register_label}"
    else
      echo "asset_registered=false"
      echo "asset_registered_response=${register_response}"
    fi
  fi

  # The session is over: stop the dense chain immediately instead of letting
  # it idle ~1 CPU core + 23MB/s of point-cloud traffic until the window
  # expires. Best effort — a stop failure never fails a successful save.
  local dense_chain_stopped=false
  if bash "${WS_DIR}/scripts/dense_mapping_chain.sh" stop >/dev/null 2>&1; then
    dense_chain_stopped=true
  fi
  echo "dense_chain_stopped=${dense_chain_stopped}"
  finish_cleanup_armed=false
}

cancel_mapping() {
  cleanup_mapping_runtime "$(cat "${PID_FILE}" 2>/dev/null || true)"
  write_state cancel "${FLOOR:-}" "" "" "" "" "" "" "" "" "${LIGHTNING_WORK_DIR}" ""
  echo "ok=true"
  echo "action=cancel"
  echo "backend=lightning_lm"
  echo "floor=${FLOOR:-}"
  # Same rationale as finish: the session ended, so the high-cost dense chain
  # stops now; the next start self-heals it again.
  local dense_chain_stopped=false
  if bash "${WS_DIR}/scripts/dense_mapping_chain.sh" stop >/dev/null 2>&1; then
    dense_chain_stopped=true
  fi
  echo "dense_chain_stopped=${dense_chain_stopped}"
}

status_mapping() {
  source_ros2
  check_runtime_distro
  local package_available=false
  local mapping_launch_available=false
  local save_service_available=false
  local source_cloud_available=false
  local pid=""
  local log_file=""
  local map_id_value=""
  local algorithm_prefix=""
  local mapping_prefix=""
  local config_file=""
  algorithm_prefix="$(pkg_prefix "${LIGHTNING_ALGORITHM_PACKAGE}")"
  if [[ -n "${algorithm_prefix}" ]]; then
    package_available=true
  fi
  mapping_prefix="$(pkg_prefix "${MAPPING_PACKAGE}")"
  if [[ -n "${mapping_prefix}" ]] && path_under "${mapping_prefix}" "${WS_DIR}/install"; then
    mapping_launch_available=true
    config_file="$(default_config_file)"
  fi
  if [[ -f "${PID_FILE}" ]]; then
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  fi
  log_file="$(state_value log || true)"
  map_id_value="$(state_value map_id || true)"
  # The mapper silently records nothing when the dense source chain is down
  # (production case: a 35-minute session produced zero keyframes because the
  # socket bridge had died). Surface the chain state via the publisher
  # heartbeat before an operator starts walking.
  if source_cloud_available_check; then
    source_cloud_available=true
  fi
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null \
     && [[ -f "${HEALTH_FILE}" ]] \
     && grep -q '^state=diverged' "${HEALTH_FILE}" 2>/dev/null; then
    health_line="$(head -n1 "${HEALTH_FILE}" 2>/dev/null || true)"
    cleanup_mapping_runtime "${pid}"
    # Terminal marker: later finish/status requests must keep reporting the
    # divergence instead of degrading to "idle -> not running" (2026-08-31
    # field incident: operator pressed save after divergence and got the
    # misleading "mapping is not running" message).
    write_state diverged "${FLOOR:-}" "" "${log_file}" "" "" "" "" "" "${map_id_value}" "$(state_value work_dir || true)" "${config_file}"
    echo "ok=true"
    echo "action=status"
    echo "backend=lightning_lm"
    echo "state=error"
    echo "code=lightning_diverged"
    echo "message=三维建图定位已发散，后台建图已停止，本次地图无法保存"
    echo "mapping_health=diverged"
    echo "mapping_health_detail=${health_line}"
    echo "pid="
    echo "state_file=${STATE_FILE}"
    echo "log=${log_file}"
    echo "package_available=${package_available}"
    echo "mapping_launch_available=${mapping_launch_available}"
    echo "save_service_available=false"
    echo "source_cloud_available=${source_cloud_available}"
    echo "config_file=${config_file}"
    exit 0
  fi
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    # The launch parent can survive an OOM-killed run_slam_online child.  Do
    # this check before ROS graph discovery so status returns immediately and
    # the Web finish request never waits on a dead mapper.
    if mapping_log_has_child_death "${log_file}" || ! mapping_slam_process_running "${pid}"; then
      echo "ok=true"
      echo "action=status"
      echo "backend=lightning_lm"
      echo "state=error"
      echo "code=lightning_mapping_process_died"
      echo "message=Lightning-LM mapping process exited; the capture cannot be saved"
      echo "pid=${pid}"
      echo "state_file=${STATE_FILE}"
      echo "log=${log_file}"
      echo "package_available=${package_available}"
      echo "mapping_launch_available=${mapping_launch_available}"
      echo "save_service_available=false"
      echo "source_cloud_available=${source_cloud_available}"
      echo "algorithm_package_prefix=${algorithm_prefix}"
      echo "mapping_package_prefix=${mapping_prefix}"
      echo "config_file=${config_file}"
      exit 0
    fi
    # Save-service readiness is proven by monotonic evidence (marker or the
    # mapper's own creation log line); the bounded live probe is only a
    # first-time best effort because one-shot discovery under field CPU
    # contention can miss an existing service and misreport `starting`.
    if save_service_evidence "${pid}" "${map_id_value}" "${log_file}"; then
      save_service_available=true
    elif ros_query_env timeout 15 python3 "${ROS2_WAIT_CALL}" exists /lightning/save_map --wait 8 >/dev/null 2>&1; then
      save_service_available=true
      printf '%s %s\n' "${pid}" "${map_id_value}" > "${SAVE_SERVICE_MARKER}" 2>/dev/null || true
    fi
    echo "ok=true"
    echo "action=status"
    echo "backend=lightning_lm"
    if [[ "${save_service_available}" == "true" ]]; then
      echo "state=running"
    else
      echo "state=starting"
    fi
    # LIO 发散健康上报: 前端据此在建图界面给出告警, 避免用户在发散后继续
    # 无效建图数十分钟。
    if [[ -f "${HEALTH_FILE}" ]]; then
      local health_line health_state health_age_s
      health_line="$(head -n1 "${HEALTH_FILE}" 2>/dev/null || true)"
      health_state="$(printf '%s' "${health_line}" | sed -n 's/^state=\([^ ]*\).*/\1/p')"
      health_age_s=$(( $(date +%s) - $(stat -c %Y "${HEALTH_FILE}" 2>/dev/null || date +%s) ))
      echo "mapping_health=${health_state:-unknown}"
      echo "mapping_health_age_s=${health_age_s}"
      if [[ "${health_state}" == "diverged" ]]; then
        echo "mapping_health_detail=${health_line}"
        echo "code=lightning_diverged"
        echo "message=三维建图定位已发散，本次地图无法保存；请取消本次建图并重新开始"
      fi
    fi
    echo "pid=${pid}"
    echo "state_file=${STATE_FILE}"
    echo "log=${log_file}"
    echo "package_available=${package_available}"
    echo "mapping_launch_available=${mapping_launch_available}"
    echo "save_service_available=${save_service_available}"
    echo "source_cloud_available=${source_cloud_available}"
    echo "algorithm_package_prefix=${algorithm_prefix}"
    echo "mapping_package_prefix=${mapping_prefix}"
    echo "config_file=${config_file}"
    echo "source_cloud_topic=${LIGHTNING_SOURCE_CLOUD_TOPIC}"
    echo "lightning_points_topic=${LIGHTNING_POINTS_TOPIC}"
    echo "fastdds_profile=${FASTRTPS_DEFAULT_PROFILES_FILE:-}"
    if [[ -n "${mapping_prefix}" && "${mapping_launch_available}" != "true" ]]; then
      echo "code=lightning_mapping_overlay_mismatch"
      echo "message=${MAPPING_PACKAGE} resolved outside the active M20Pro workspace; check source order"
    fi
    exit 0
  fi
  if [[ "$(state_value action || true)" == "diverged" ]]; then
    echo "ok=true"
    echo "action=status"
    echo "backend=lightning_lm"
    echo "state=error"
    echo "code=lightning_diverged"
    echo "message=上一次建图定位已发散并停止，本次采集无法保存；请重新开始建图"
    echo "mapping_health=diverged"
    echo "package_available=${package_available}"
    echo "mapping_launch_available=${mapping_launch_available}"
    echo "save_service_available=false"
    echo "source_cloud_available=${source_cloud_available}"
    echo "config_file=${config_file}"
    exit 0
  fi
  echo "ok=true"
  echo "action=status"
  echo "backend=lightning_lm"
  echo "state=idle"
  echo "archive_dir=${ARCHIVE_DIR}"
  echo "package_available=${package_available}"
  echo "mapping_launch_available=${mapping_launch_available}"
  echo "save_service_available=${save_service_available}"
  echo "source_cloud_available=${source_cloud_available}"
  echo "algorithm_package_prefix=${algorithm_prefix}"
  echo "mapping_package_prefix=${mapping_prefix}"
  echo "config_file=${config_file}"
  echo "source_cloud_topic=${LIGHTNING_SOURCE_CLOUD_TOPIC}"
  echo "cloud_adapter_enabled=${LIGHTNING_ENABLE_CLOUD_ADAPTER}"
  echo "lightning_points_topic=${LIGHTNING_POINTS_TOPIC}"
  echo "fastdds_profile=${FASTRTPS_DEFAULT_PROFILES_FILE:-}"
  if [[ "${package_available}" != "true" ]]; then
    echo "code=lightning_runtime_missing"
    echo "message=${LIGHTNING_ALGORITHM_PACKAGE} package is not installed in the Lightning runtime"
  elif [[ -n "${mapping_prefix}" && "${mapping_launch_available}" != "true" ]]; then
    echo "code=lightning_mapping_overlay_mismatch"
    echo "message=${MAPPING_PACKAGE} resolved outside the active M20Pro workspace; check source order"
  elif [[ "${source_cloud_available}" != "true" ]]; then
    echo "code=lightning_source_cloud_missing"
    echo "message=激光雷达密集数据链未运行或 ${LIGHTNING_SOURCE_CLOUD_TOPIC} 无数据；请先执行 scripts/dense_mapping_chain.sh start"
  fi
}

case "${ACTION}" in
  start)
    start_mapping
    ;;
  finish)
    finish_mapping
    ;;
  cancel)
    cancel_mapping
    ;;
  status)
    status_mapping
    ;;
  *)
    usage
    exit 2
    ;;
esac
