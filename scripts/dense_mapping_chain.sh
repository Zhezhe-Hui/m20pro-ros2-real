#!/usr/bin/env bash
set -euo pipefail

# Dense full-field cloud chain for Lightning-LM raw mapping on 104.
#
#   start   Start 106 passthrough + 104 passthrough/socket + 104 ROS2 publisher
#   stop    Stop the three chain processes
#   status  Show chain process state and the native dense topic rate
#
# The vendor /LIDAR/POINTS DDS locators live on the 33-network segment only,
# so 104 cannot subscribe it directly (verified 2026-08-13).  106 reads the
# DrDDS channel and republishes as /m20pro/lidar_points_dense; a second
# passthrough on 104 forwards each frame over a unix socket with ALL native
# fields; dddmr_dense_cloud_publisher.py then republishes it as the native
# ROS2 topic /m20pro/lidar_points_dense_ros that Lightning subscribes.
#
# Chain processes run with timeout and die on their own; use this script to
# start them explicitly before a mapping run (walking recommended for real
# map quality), then scripts/lightning_raw_mapping_control.sh start/finish.
#
# This script runs on 104.

ACTION="${1:-status}"
DURATION_S="${2:-1200}"          # default 20 minutes
if [[ "$(id -u)" != "0" && "${ACTION}" != "status" ]]; then
  # Chain processes run as root (raw DDS + privileged socket); stop must be
  # able to kill them, so start/stop are root-only instead of re-sudoing
  # internally with fragile stdin password plumbing.
  echo "run as root: sudo bash $0 ${ACTION} ${DURATION_S}" >&2
  exit 1
fi
TOPIC_106="/m20pro/lidar_points_dense"
TOPIC_104_ROS="/m20pro/lidar_points_dense_ros"
SOCKET_104="/tmp/lidar_points_dense.sock"
BIN="m20pro_dense_passthrough"
WS_DIR="${M20PRO_WS:-/home/user/m20pro_real_ros2_ws_v4}"
PUB_PY="${WS_DIR}/src/m20pro_navigation/m20pro_navigation/dddmr_dense_cloud_publisher.py"
SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)

# 2026-08-20 raw lidar chain: rslidar_sdk parses the factory MSOP packets
# (already forwarded to the 31 segment by 106 multicast.py) into rigid
# uncompensated XYZIRT clouds; raw_lidar_merge_node merges front+rear into
# ${TOPIC_104_ROS}.  M20PRO_DENSE_CHAIN_SOURCE selects the chain:
#   raw     - root-cause input (default since 2026-08-20)
#   vendor  - legacy /LIDAR/POINTS passthrough + attitude de-leveling
SOURCE_MODE="${M20PRO_DENSE_CHAIN_SOURCE:-raw}"
RAW_SDK_WS="${M20PRO_RAW_SDK_WS:-/home/user/m20pro_lidar_sdk_ws}"
RAW_SDK_CONFIG="${RAW_SDK_WS}/src/rslidar_sdk/config/config.yaml"
MERGE_PY="${WS_DIR}/src/m20pro_navigation/m20pro_navigation/raw_lidar_merge_node.py"

# 2026-08-21 root cause: the ROS2 chain members (rslidar_sdk, merge node,
# dense publisher) must run with the project UDP-only FastDDS profile like
# every other m20pro-real node. /opt/robot/fastdds.xml (force-set by
# setup_ros2.sh) enables the SHM transport; SIGKILLed participants leak
# /dev/shm segments and stale SHM ports isolate vendor-profile participants
# from the graph (topics exist in-process but nobody can discover/receive
# them - observed after the 22:00 crash loop; the 21:51 mapping session only
# worked because the service entrypoint had just cleaned stale SHM).
PROJECT_FASTDDS_PROFILE="${WS_DIR}/install/m20pro_bringup/share/m20pro_bringup/config/m20pro_fastdds_udp.xml"
# Expansion for the unquoted heredocs below: keep the vendor profile when the
# project profile is missing (e.g. staged workspace without bringup install).
PROJECT_PROFILE_EXPORT="[[ -f '${PROJECT_FASTDDS_PROFILE}' ]] && export FASTRTPS_DEFAULT_PROFILES_FILE='${PROJECT_FASTDDS_PROFILE}' || true"

start_raw() {
  if [[ ! -f "${RAW_SDK_CONFIG}" ]]; then
    echo "[dense_chain] raw mode: config missing: ${RAW_SDK_CONFIG}" >&2
    return 1
  fi
  echo "[dense_chain] starting raw lidar chain (${DURATION_S}s)"
  local pin
  pin="$(mapping_cpu_pin_prefix)"
  setsid bash -s <<EOF >/dev/null 2>&1 &
export ROS_DOMAIN_ID=0
source /opt/robot/scripts/setup_ros2.sh >/dev/null 2>&1
${PROJECT_PROFILE_EXPORT}
source ${RAW_SDK_WS}/install/setup.bash >/dev/null 2>&1
${pin}timeout ${DURATION_S} ros2 run rslidar_sdk rslidar_sdk_node --ros-args -p config_path:=${RAW_SDK_CONFIG} > /tmp/rslidar_sdk.log 2>&1
EOF
  sleep 5
  setsid bash -s <<EOF >/dev/null 2>&1 &
export ROS_DOMAIN_ID=0
source /opt/robot/scripts/setup_ros2.sh >/dev/null 2>&1
${PROJECT_PROFILE_EXPORT}
source ${WS_DIR}/install/setup.bash >/dev/null 2>&1
${pin}timeout ${DURATION_S} python3 ${MERGE_PY} --ros-args \
  -p output_topic:=${TOPIC_104_ROS} > /tmp/raw_lidar_merge.log 2>&1
EOF
  if [[ "${M20PRO_DENSE_CHAIN_SKIP_VERIFY:-0}" == "1" ]]; then
    echo "[dense_chain] started (data-flow verification delegated to caller)"
    return 0
  fi
  echo "[dense_chain] started; verifying data flow..."
  sleep 8
  export ROS_DOMAIN_ID=0
  source_vendor_ros
  local rate_line
  rate_line="$(timeout 10 ros2 topic hz ${TOPIC_104_ROS} 2>/dev/null | grep -m1 "average rate" || true)"
  if [[ -n "${rate_line}" ]]; then
    echo "[dense_chain] OK: ${rate_line}"
  else
    echo "[dense_chain] WARNING: no dense frames measured yet; check: $0 status" >&2
  fi
}

mapping_cpu_pin_prefix() {
  # Mirror of the control-script helper: vendor kernel isolcpus=4,5,6,7 leaves
  # the big A76 cores idle while the robot stack is pinned to little cores.
  # Run the 104-side chain there so point-cloud transport is not starved
  # (2026-08-19: publisher fell to 2.4Hz under load; passthrough buffered
  # 4.2GB). 106 is a different host/topology and is intentionally not pinned.
  local cpus="${M20PRO_MAPPING_CPUS:-4-7}"
  [[ -n "${cpus}" ]] || return 0
  if command -v taskset >/dev/null 2>&1 && taskset -c "${cpus}" true 2>/dev/null; then
    printf 'taskset -c %s ' "${cpus}"
  fi
}

source_vendor_ros() {
  # The vendor setup script references unset variables and is not safe under
  # `set -u`; source it with the strict flags temporarily off so chain
  # control never aborts on a cosmetic vendor-script failure.
  set +eu
  # shellcheck disable=SC1091
  source /opt/robot/scripts/setup_ros2.sh >/dev/null 2>&1 || true
  set -eu
  # Probe must share the chain's DDS world (see PROJECT_FASTDDS_PROFILE note).
  if [[ -f "${PROJECT_FASTDDS_PROFILE}" ]]; then
    export FASTRTPS_DEFAULT_PROFILES_FILE="${PROJECT_FASTDDS_PROFILE}"
  fi
}

start() {
  if [[ "${SOURCE_MODE}" == "raw" ]]; then
    start_raw
    return $?
  fi
  # Self-healing start: if chain processes linger without a fresh heartbeat
  # (hung or half-dead chain), clean them first instead of stacking duplicate
  # passthroughs (duplicates previously accumulated on repeated starts).
  local hb="/tmp/m20pro_dense_cloud_publisher.heartbeat" hb_age=999999
  if [[ -f "${hb}" ]]; then
    hb_age=$(( $(date +%s) - $(stat -c %Y "${hb}" 2>/dev/null || echo 0) ))
  fi
  if pgrep -f "dddmr_dense_cloud_[p]ublisher" >/dev/null 2>&1 || pgrep -f "m20pro_dense_[p]assthrough" >/dev/null 2>&1; then
    if (( hb_age <= 10 )); then
      echo "[dense_chain] already running with fresh data flow; nothing to do"
      return 0
    fi
    echo "[dense_chain] stale chain processes present (heartbeat ${hb_age}s old); stopping before start"
    stop >/dev/null
  fi
  echo "[dense_chain] starting 106 passthrough (${DURATION_S}s)"
  ssh "${SSH_OPTS[@]}" user@10.21.31.106 "echo \"'\" | sudo -S bash -c '
    export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/robot/fastdds.xml
    source /opt/robot/scripts/setup_ros2.sh >/dev/null 2>&1
    setsid timeout ${DURATION_S} /usr/local/lib/m20pro/${BIN} /LIDAR/POINTS ${TOPIC_106} 0 0 rt \"\" 0 $((DURATION_S - 20)) > /tmp/dense_passthrough106.log 2>&1 &
  '"
  sleep 3
  echo "[dense_chain] starting 104 passthrough + publisher"
  local pin
  pin="$(mapping_cpu_pin_prefix)"
  # Unquoted here-docs so the outer shell expands the chain variables;
  # single-quoted sudo/setsid payloads would lose them (sudo env_reset and
  # non-exported globals), leaving `timeout <empty> ...` behind.
  bash -s <<EOF
export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/robot/fastdds.xml
source /opt/robot/scripts/setup_ros2.sh >/dev/null 2>&1
setsid ${pin}timeout ${DURATION_S} /usr/local/lib/m20pro/${BIN} ${TOPIC_106} /m20pro/lidar_points_dense_dds 0 0 rt "" 0 $((DURATION_S - 20)) ${SOCKET_104} > /tmp/dense_passthrough104.log 2>&1 &
EOF
  sleep 3
  # Redirect the wrapper's own stdout/stderr: an inherited caller pipe left
  # open here keeps the caller's `| tail`/ssh channel waiting for EOF until
  # the whole 2400s chain expires (observed twice in production).
  # 2026-08-20: attitude de-leveling (dense_cloud_delevel.py) restores rigid
# body-frame geometry before Lightning; M20PRO_DENSE_CHAIN_DELEVEL=off is the
# field kill switch that falls back to raw passthrough (e.g. for forensics).
DELEVEL_FLAG="${M20PRO_DENSE_CHAIN_DELEVEL:-on}"
setsid bash -s <<EOF >/dev/null 2>&1 &
export ROS_DOMAIN_ID=0
source /opt/robot/scripts/setup_ros2.sh >/dev/null 2>&1
${PROJECT_PROFILE_EXPORT}
source ${WS_DIR}/install/setup.bash >/dev/null 2>&1
${pin}timeout ${DURATION_S} python3 ${PUB_PY} --ros-args \
  -p socket_path:=${SOCKET_104} \
  -p output_topic:=${TOPIC_104_ROS} \
  -p attitude_delevel_enabled:=$([ "${DELEVEL_FLAG}" = "off" ] && echo false || echo true) > /tmp/dense_publisher.log 2>&1
EOF
  if [[ "${M20PRO_DENSE_CHAIN_SKIP_VERIFY:-0}" == "1" ]]; then
    # Mapping-start auto-recovery verifies via the publisher heartbeat instead
    # of the slow sleep+ros2-hz probe, keeping Web start latency bounded.
    echo "[dense_chain] started (data-flow verification delegated to caller)"
    return 0
  fi
  echo "[dense_chain] started; verifying data flow..."
  sleep 8
  export ROS_DOMAIN_ID=0
  source_vendor_ros
  local rate_line
  rate_line="$(timeout 10 ros2 topic hz ${TOPIC_104_ROS} 2>/dev/null | grep -m1 "average rate" || true)"
  if [[ -n "${rate_line}" ]]; then
    echo "[dense_chain] OK: ${rate_line}"
  else
    echo "[dense_chain] WARNING: no dense frames measured yet; check: $0 status" >&2
  fi
}

stop() {
  # [x]-bracket patterns keep pkill from matching the shell whose own command
  # line carries the literal pattern: on 106 that self-match killed the
  # remote shell, ssh returned 255, and `set -e` aborted stop before the
  # local cleanup ever ran (observed: three duplicate chains accumulated).
  # The 106 hop is best-effort; local cleanup must always run.
  ssh "${SSH_OPTS[@]}" user@10.21.31.106 "echo \"'\" | sudo -S pkill -f m20pro_dense_[p]assthrough 2>/dev/null || true" || true
  pkill -f m20pro_dense_[p]assthrough 2>/dev/null || true
  pkill -f dddmr_dense_cloud_[p]ublisher 2>/dev/null || true
  pkill -f rslidar_sdk_[n]ode 2>/dev/null || true
  pkill -f raw_lidar_merge_[n]ode 2>/dev/null || true
  sleep 1
  pkill -9 -f m20pro_dense_[p]assthrough 2>/dev/null || true
  pkill -9 -f dddmr_dense_cloud_[p]ublisher 2>/dev/null || true
  pkill -9 -f rslidar_sdk_[n]ode 2>/dev/null || true
  pkill -9 -f raw_lidar_merge_[n]ode 2>/dev/null || true
  echo "[dense_chain] stopped"
}

status() {
  echo "== 106 passthrough =="
  ssh "${SSH_OPTS[@]}" user@10.21.31.106 "ps -eo pid,args | grep ${BIN} | grep -v grep | head -2"
  echo "== 104 passthrough + publisher =="
  ps -eo pid,args | grep -E "${BIN}|dddmr_dense_cloud_publisher|rslidar_sdk_node|raw_lidar_merge" | grep -v grep | head -4
  echo "== native dense topic rate =="
  export ROS_DOMAIN_ID=0
  source_vendor_ros
  timeout 10 ros2 topic hz ${TOPIC_104_ROS} 2>&1 | head -2
}

case "${ACTION}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *) echo "usage: $0 [start|stop|status] [duration_s]"; exit 2 ;;
esac
