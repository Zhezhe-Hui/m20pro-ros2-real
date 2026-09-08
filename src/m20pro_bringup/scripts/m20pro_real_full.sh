#!/usr/bin/env bash
set -euo pipefail

# The production service runs as root while field builds run as user. Avoid
# root-owned __pycache__ files inside the symlink install tree blocking rebuilds.
export PYTHONDONTWRITEBYTECODE=1

WS_DIR="${M20PRO_WS:-/home/user/m20pro_real_ros2_ws_v4}"
MODE="${1:-shadow}"
RADAR_ENABLED="${M20PRO_ENABLE_RADAR_INSPECTION:-false}"
RADAR_BACKEND="${M20PRO_RADAR_BACKEND:-dry_run}"
RADAR_SCAN_MODE="${M20PRO_RADAR_SCAN_MODE:-measuring}"
RADAR_DEVICE_URL="${M20PRO_RADAR_DEVICE_URL:-http://192.168.107.72:8080}"
RADAR_OUTPUT_DIR="${M20PRO_RADAR_OUTPUT_DIR:-/home/user/m20pro_radar_results}"
RADAR_RELEASE_ON_ANALYSIS="${M20PRO_RADAR_RELEASE_ON_ANALYSIS:-true}"
RADAR_START_RETRY_TIMEOUT_S="${M20PRO_RADAR_START_RETRY_TIMEOUT_S:-120.0}"
RADAR_START_RETRY_INTERVAL_S="${M20PRO_RADAR_START_RETRY_INTERVAL_S:-5.0}"
RADAR_RESULT_RETRY_COUNT="${M20PRO_RADAR_RESULT_RETRY_COUNT:-5}"
RADAR_RESULT_RETRY_INTERVAL_S="${M20PRO_RADAR_RESULT_RETRY_INTERVAL_S:-2.0}"
RADAR_QUERY_ERROR_TIMEOUT_S="${M20PRO_RADAR_QUERY_ERROR_TIMEOUT_S:-120.0}"
DEFAULT_NAVIGATION_BACKEND="dddmr_3d"
DEFAULT_ENABLE_DDDMR_BRIDGE="true"
DEFAULT_ENABLE_DDDMR_RUNTIME="false"
DEFAULT_DDDMR_RUNTIME_BACKEND="official"
if [[ "${MODE}" == "move" ]]; then
  DEFAULT_ENABLE_DDDMR_RUNTIME="true"
fi
NAVIGATION_BACKEND="${M20PRO_NAVIGATION_BACKEND:-${DEFAULT_NAVIGATION_BACKEND}}"
ENABLE_DDDMR_BRIDGE="${M20PRO_ENABLE_DDDMR_BRIDGE:-${DEFAULT_ENABLE_DDDMR_BRIDGE}}"
ENABLE_DDDMR_RUNTIME="${M20PRO_ENABLE_DDDMR_RUNTIME:-${DEFAULT_ENABLE_DDDMR_RUNTIME}}"
DDDMR_RUNTIME_BACKEND="${M20PRO_DDDMR_RUNTIME_BACKEND:-${DEFAULT_DDDMR_RUNTIME_BACKEND}}"
ENABLE_DDDMR_SOCKET_BRIDGE="${M20PRO_ENABLE_DDDMR_SOCKET_BRIDGE:-true}"
DDDMR_SOCKET_CLOUD_PATH="${M20PRO_DDDMR_SOCKET_CLOUD_PATH:-/run/m20pro/dddmr_edge_cloud.sock}"
DDDMR_SOCKET_CLOUD_TOPIC="${M20PRO_DDDMR_SOCKET_CLOUD_TOPIC:-/m20pro/dddmr/edge_cloud_socket}"
ENABLE_DDDMR_MAP_ASSETS="${M20PRO_ENABLE_DDDMR_MAP_ASSETS:-}"
if [[ -z "${ENABLE_DDDMR_MAP_ASSETS}" ]]; then
  ENABLE_DDDMR_MAP_ASSETS="true"
  echo "[m20pro_real_full] auto-enable 3D map assets for backend ${NAVIGATION_BACKEND}" >&2
fi
ENABLE_GNSS_ADAPTER="${M20PRO_ENABLE_GNSS_ADAPTER:-true}"
GNSS_SOURCE_TOPIC="${M20PRO_GNSS_SOURCE_TOPIC:-/GPS}"
GNSS_FIX_TOPIC="${M20PRO_GNSS_FIX_TOPIC:-/m20pro/gnss/fix}"
GNSS_STATUS_TOPIC="${M20PRO_GNSS_STATUS_TOPIC:-/m20pro/gnss/status}"
DDDMR_MAP_ASSET_MANIFEST="${M20PRO_DDDMR_MAP_ASSET_MANIFEST:-}"
DDDMR_MAP_ASSET_RELOAD_PERIOD_S="${M20PRO_DDDMR_MAP_ASSET_RELOAD_PERIOD_S:-1.0}"
DDDMR_MAPCLOUD_FILE="${M20PRO_DDDMR_MAPCLOUD_FILE:-}"
DDDMR_MAPGROUND_FILE="${M20PRO_DDDMR_MAPGROUND_FILE:-}"
DDDMR_FIELD_TEST_FLAT_MAP="${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP:-}"
DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M="${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M:-2.0}"
DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M="${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M:-0.25}"
DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M="${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M:-0.0}"
DDDMR_MAPPING_HOST="${M20PRO_DDDMR_MAPPING_HOST:-localhost}"
DDDMR_MAPPING_USER="${M20PRO_DDDMR_MAPPING_USER:-user}"
DDDMR_MAPPING_START_COMMAND="${M20PRO_DDDMR_MAPPING_START_COMMAND:-}"
DDDMR_MAPPING_FINISH_COMMAND="${M20PRO_DDDMR_MAPPING_FINISH_COMMAND:-}"
DDDMR_MAPPING_CANCEL_COMMAND="${M20PRO_DDDMR_MAPPING_CANCEL_COMMAND:-}"
DDDMR_MAPPING_STATUS_COMMAND="${M20PRO_DDDMR_MAPPING_STATUS_COMMAND:-}"
DDDMR_MAPPING_CONTROL_SCRIPT="${WS_DIR}/scripts/lightning_raw_mapping_control.sh"

case "${NAVIGATION_BACKEND}" in
  dddmr_3d) ;;
  *)
    echo "[m20pro_real_full] invalid M20PRO_NAVIGATION_BACKEND=${NAVIGATION_BACKEND}" >&2
    exit 2
    ;;
esac
case "${DDDMR_RUNTIME_BACKEND}" in
  official|field_proxy) ;;
  *)
    echo "[m20pro_real_full] invalid M20PRO_DDDMR_RUNTIME_BACKEND=${DDDMR_RUNTIME_BACKEND}" >&2
    exit 2
    ;;
esac
if [[ -z "${DDDMR_FIELD_TEST_FLAT_MAP}" ]]; then
  if [[ "${DDDMR_RUNTIME_BACKEND}" == "field_proxy" ]]; then
    DDDMR_FIELD_TEST_FLAT_MAP="true"
    echo "[m20pro_real_full] enable temporary flat map fallback for ${NAVIGATION_BACKEND}/${DDDMR_RUNTIME_BACKEND}" >&2
  else
    DDDMR_FIELD_TEST_FLAT_MAP="false"
  fi
fi
if [[ "${MODE}" == "move" && "${NAVIGATION_BACKEND}" == "dddmr_3d" ]]; then
  if [[ -z "${DDDMR_MAPPING_START_COMMAND}" ]]; then
    DDDMR_MAPPING_START_COMMAND="${DDDMR_MAPPING_CONTROL_SCRIPT} start {floor}"
  fi
  if [[ -z "${DDDMR_MAPPING_FINISH_COMMAND}" ]]; then
    DDDMR_MAPPING_FINISH_COMMAND="${DDDMR_MAPPING_CONTROL_SCRIPT} finish {floor}"
  fi
  if [[ -z "${DDDMR_MAPPING_CANCEL_COMMAND}" ]]; then
    DDDMR_MAPPING_CANCEL_COMMAND="${DDDMR_MAPPING_CONTROL_SCRIPT} cancel {floor}"
  fi
  if [[ -z "${DDDMR_MAPPING_STATUS_COMMAND}" ]]; then
    DDDMR_MAPPING_STATUS_COMMAND="${DDDMR_MAPPING_CONTROL_SCRIPT} status {floor}"
  fi
fi

if [[ "${EUID}" -ne 0 ]]; then
  cat >&2 <<'EOF'
m20pro_real_full.sh must be run after the known-good 104 root sequence:

  ssh user@10.21.31.104
  source /opt/robot/scripts/setup_ros2.sh
  su
  cd /home/user/m20pro_real_ros2_ws_v4
  source install/setup.bash
  ros2 run m20pro_bringup m20pro_real_full.sh shadow

Use "move" only when the site is safe and motion control is allowed.
EOF
  exit 2
fi

if [[ -z "${ROS_DISTRO:-}" || ! -x "$(command -v ros2)" ]]; then
  set +u
  source /opt/robot/scripts/setup_ros2.sh
  set -u
fi

cd "${WS_DIR}"
set +u
DDDMR_RUNTIME_SETUP="${M20PRO_DDDMR_RUNTIME_SETUP:-${M20PRO_DDDMR_RUNTIME_WS:-${WS_DIR}}/install/setup.bash}"
if [[ "${ENABLE_DDDMR_RUNTIME}" == "true" && "${DDDMR_RUNTIME_BACKEND}" == "official" && ! -f "${DDDMR_RUNTIME_SETUP}" ]]; then
  echo "[m20pro_real_full] official DDDMR runtime is missing: ${DDDMR_RUNTIME_SETUP}" >&2
  echo "[m20pro_real_full] build it natively on 104 with scripts/prepare_dddmr_foxy_runtime.sh" >&2
  exit 24
fi
if [[ -f "${DDDMR_RUNTIME_SETUP}" && "$(realpath -m "${DDDMR_RUNTIME_SETUP}")" != "$(realpath -m "${WS_DIR}/install/setup.bash")" ]]; then
  source "${DDDMR_RUNTIME_SETUP}"
fi
source install/setup.bash
set -u
BRINGUP_PREFIX="$(ros2 pkg prefix m20pro_bringup)"
if [[ -z "${DDDMR_MAP_ASSET_MANIFEST}" ]]; then
  DDDMR_MAP_ASSET_MANIFEST="/home/user/.m20pro_web/dddmr_map_assets.yaml"
fi
mkdir -p "$(dirname "${DDDMR_MAP_ASSET_MANIFEST}")"

PROJECT_FASTDDS="${WS_DIR}/install/m20pro_bringup/share/m20pro_bringup/config/m20pro_fastdds_udp.xml"
FACTORY_FASTDDS="/opt/robot/fastdds.xml"

cleanup_stale_fastdds_shm() {
  if [[ "${M20PRO_CLEAN_STALE_FASTDDS_SHM:-1}" != "1" ]]; then
    return
  fi
  local stale=0
  local kept=0
  local file
  shopt -s nullglob
  for file in /dev/shm/fastrtps_*; do
    if fuser "${file}" >/dev/null 2>&1; then
      kept=$((kept + 1))
    else
      rm -f -- "${file}" && stale=$((stale + 1))
    fi
  done
  shopt -u nullglob
  if [[ "${stale}" -gt 0 || "${kept}" -gt 0 ]]; then
    echo "[m20pro_real_full] stale FastDDS SHM cleanup: removed=${stale} kept_open=${kept}" >&2
  fi
}

cleanup_stale_fastdds_shm

case "${M20PRO_FASTDDS_PROFILE:-factory}" in
  project_udp|udp)
    if [[ -f "${PROJECT_FASTDDS}" ]]; then
      export FASTRTPS_DEFAULT_PROFILES_FILE="${PROJECT_FASTDDS}"
    elif [[ -f "${FACTORY_FASTDDS}" ]]; then
      export FASTRTPS_DEFAULT_PROFILES_FILE="${FACTORY_FASTDDS}"
    fi
    ;;
  factory)
    if [[ -f "${FACTORY_FASTDDS}" ]]; then
      export FASTRTPS_DEFAULT_PROFILES_FILE="${FACTORY_FASTDDS}"
    fi
    ;;
  auto)
    if [[ "${M20PRO_USE_PROJECT_FASTDDS:-1}" == "1" && -f "${PROJECT_FASTDDS}" ]]; then
      export FASTRTPS_DEFAULT_PROFILES_FILE="${PROJECT_FASTDDS}"
    elif [[ -n "${FASTRTPS_DEFAULT_PROFILES_FILE:-}" ]]; then
      :
    elif [[ -f "${FACTORY_FASTDDS}" ]]; then
      export FASTRTPS_DEFAULT_PROFILES_FILE="${FACTORY_FASTDDS}"
    fi
    ;;
  inherit)
    ;;
  *)
    echo "[m20pro_real_full] invalid M20PRO_FASTDDS_PROFILE=${M20PRO_FASTDDS_PROFILE}; expected project_udp, factory, auto, or inherit" >&2
    exit 2
    ;;
esac

if [[ -n "${FASTRTPS_DEFAULT_PROFILES_FILE:-}" ]]; then
  echo "[m20pro_real_full] FASTRTPS_DEFAULT_PROFILES_FILE=${FASTRTPS_DEFAULT_PROFILES_FILE}" >&2
fi

if ps -eo pid,args | awk '
  /ros2 launch m20pro_bringup m20pro.launch.py/ &&
  /mode:=real/ &&
  !/awk/ {print}
' >/tmp/m20pro_real_existing_stack.out && [[ -s /tmp/m20pro_real_existing_stack.out ]]; then
  cat >&2 <<'EOF'
[m20pro_real_full] another M20Pro real launch is already running.

Do not start multiple real stacks on 104. Stop the existing stack first:

  ./scripts/104_stop_real.sh
  # or
  systemctl stop m20pro-real.service
EOF
  cat /tmp/m20pro_real_existing_stack.out >&2 || true
  exit 70
fi

SCAN_TOPIC="${M20PRO_SCAN_TOPIC:-/scan}"
WEB_DASHBOARD_DATA_DIR="${M20PRO_WEB_DASHBOARD_DATA_DIR:-/home/user/.m20pro_web}"
WEB_DASHBOARD_MAP_ARCHIVE_DIR="${M20PRO_WEB_DASHBOARD_MAP_ARCHIVE_DIR:-/home/user/m20pro_maps}"
RUNTIME_FLOOR_CONFIG="${M20PRO_RUNTIME_FLOOR_CONFIG:-${WEB_DASHBOARD_DATA_DIR}/runtime_navigation.yaml}"
INSPECTION_MODEL_PATH="${M20PRO_INSPECTION_MODEL_PATH:-${WS_DIR}/install/m20pro_inspection/share/m20pro_inspection/models/best_rk3588_fp16.rknn}"
INSPECTION_CLASS_NAMES_PATH="${M20PRO_INSPECTION_CLASS_NAMES_PATH:-${WS_DIR}/install/m20pro_inspection/share/m20pro_inspection/models/labels_zh.txt}"
echo "[m20pro_real_full] perception=/scan from 106 edge scan" >&2

selected_map_floor_for_launch() {
  python3 - "${WEB_DASHBOARD_DATA_DIR}" <<'PY'
import json
import os
import sys

data_dir = sys.argv[1]
settings_path = os.path.join(data_dir, "settings.json")
maps_path = os.path.join(data_dir, "maps.json")

try:
    with open(settings_path, "r", encoding="utf-8") as file:
        settings = json.load(file) or {}
        selected_map_id = str(settings.get("selected_map_id") or "").strip()
        working_map_id = str(settings.get("working_map_id") or "").strip()
except Exception:
    selected_map_id = ""
    working_map_id = ""

launch_map_ids = []
for value in (selected_map_id, working_map_id):
    if value and value not in launch_map_ids:
        launch_map_ids.append(value)
if not launch_map_ids:
    sys.exit(0)

try:
    with open(maps_path, "r", encoding="utf-8") as file:
        records = json.load(file) or []
except Exception:
    records = []

if not isinstance(records, list):
    records = []

for launch_map_id in launch_map_ids:
    for record in records:
        if str(record.get("id") or "").strip() != launch_map_id:
            continue
        print(str(record.get("floor") or "").strip())
        sys.exit(0)
        break
PY
}

SELECTED_MAP_FLOOR="$(selected_map_floor_for_launch || true)"
if [[ -n "${SELECTED_MAP_FLOOR}" ]]; then
  echo "[m20pro_real_full] initial floor from web working map: ${SELECTED_MAP_FLOOR}" >&2
fi

COMMON_ARGS=(
  mode:=real
  rviz:=false
  enable_web_dashboard:=true
  enable_initialpose_relocalization:=true
  navigation_backend:="${NAVIGATION_BACKEND}"
  enable_dddmr_bridge:="${ENABLE_DDDMR_BRIDGE}"
  enable_dddmr_runtime:="${ENABLE_DDDMR_RUNTIME}"
  dddmr_runtime_backend:="${DDDMR_RUNTIME_BACKEND}"
  enable_dddmr_socket_bridge:="${ENABLE_DDDMR_SOCKET_BRIDGE}"
  dddmr_socket_cloud_path:="${DDDMR_SOCKET_CLOUD_PATH}"
  dddmr_socket_cloud_topic:="${DDDMR_SOCKET_CLOUD_TOPIC}"
  enable_dddmr_map_assets:="${ENABLE_DDDMR_MAP_ASSETS}"
  enable_gnss_adapter:="${ENABLE_GNSS_ADAPTER}"
  gnss_source_topic:="${GNSS_SOURCE_TOPIC}"
  gnss_fix_topic:="${GNSS_FIX_TOPIC}"
  gnss_status_topic:="${GNSS_STATUS_TOPIC}"
  dddmr_map_asset_manifest:="${DDDMR_MAP_ASSET_MANIFEST}"
  dddmr_map_asset_reload_period_s:="${DDDMR_MAP_ASSET_RELOAD_PERIOD_S}"
  dddmr_field_test_flat_map:="${DDDMR_FIELD_TEST_FLAT_MAP}"
  dddmr_field_test_flat_map_extent_m:="${DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M}"
  dddmr_field_test_flat_map_spacing_m:="${DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M}"
  dddmr_field_test_flat_map_height_m:="${DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M}"
  dddmr_mapping_host:="${DDDMR_MAPPING_HOST}"
  dddmr_mapping_user:="${DDDMR_MAPPING_USER}"
  floor_config:="${RUNTIME_FLOOR_CONFIG}"
  web_dashboard_data_dir:="${WEB_DASHBOARD_DATA_DIR}"
  web_dashboard_map_archive_dir:="${WEB_DASHBOARD_MAP_ARCHIVE_DIR}"
  enable_initialpose_3d_adapter:=true
  enable_camera_proxy:=false
  camera_proxy_backend:=ffmpeg_mjpeg
  camera_proxy_fps:=10.0
  camera_proxy_jpeg_quality:=45
  camera_proxy_ffmpeg_mjpeg_qscale:=5
  camera_proxy_max_width:=480
  enable_inspection:="${M20PRO_ENABLE_INSPECTION:-false}"
  inspection_backend:="${M20PRO_INSPECTION_BACKEND:-rknn}"
  inspection_source_type:="${M20PRO_INSPECTION_SOURCE_TYPE:-rtsp}"
  inspection_rtsp_url:="${M20PRO_INSPECTION_RTSP_URL:-rtsp://10.21.31.103:8554/video1}"
  inspection_camera_name:="${M20PRO_INSPECTION_CAMERA_NAME:-front_wide}"
  inspection_model_path:="${INSPECTION_MODEL_PATH}"
  inspection_class_names_path:="${INSPECTION_CLASS_NAMES_PATH}"
  scan_topic:="${SCAN_TOPIC}"
  enable_radar_inspection:="${RADAR_ENABLED}"
  radar_backend:="${RADAR_BACKEND}"
  radar_scan_mode:="${RADAR_SCAN_MODE}"
  radar_device_url:="${RADAR_DEVICE_URL}"
  radar_output_dir:="${RADAR_OUTPUT_DIR}"
  radar_release_on_analysis:="${RADAR_RELEASE_ON_ANALYSIS}"
  radar_start_retry_timeout_s:="${RADAR_START_RETRY_TIMEOUT_S}"
  radar_start_retry_interval_s:="${RADAR_START_RETRY_INTERVAL_S}"
  radar_result_retry_count:="${RADAR_RESULT_RETRY_COUNT}"
  radar_result_retry_interval_s:="${RADAR_RESULT_RETRY_INTERVAL_S}"
  radar_query_error_timeout_s:="${RADAR_QUERY_ERROR_TIMEOUT_S}"
)
if [[ -n "${DDDMR_MAPCLOUD_FILE}" ]]; then
  COMMON_ARGS+=(dddmr_mapcloud_file:="${DDDMR_MAPCLOUD_FILE}")
fi
if [[ -n "${DDDMR_MAPGROUND_FILE}" ]]; then
  COMMON_ARGS+=(dddmr_mapground_file:="${DDDMR_MAPGROUND_FILE}")
fi
if [[ -n "${DDDMR_MAPPING_START_COMMAND}" ]]; then
  COMMON_ARGS+=(dddmr_mapping_start_command:="${DDDMR_MAPPING_START_COMMAND}")
fi
if [[ -n "${DDDMR_MAPPING_FINISH_COMMAND}" ]]; then
  COMMON_ARGS+=(dddmr_mapping_finish_command:="${DDDMR_MAPPING_FINISH_COMMAND}")
fi
if [[ -n "${DDDMR_MAPPING_CANCEL_COMMAND}" ]]; then
  COMMON_ARGS+=(dddmr_mapping_cancel_command:="${DDDMR_MAPPING_CANCEL_COMMAND}")
fi
if [[ -n "${DDDMR_MAPPING_STATUS_COMMAND}" ]]; then
  COMMON_ARGS+=(dddmr_mapping_status_command:="${DDDMR_MAPPING_STATUS_COMMAND}")
fi
if [[ -n "${SELECTED_MAP_FLOOR}" ]]; then
  COMMON_ARGS+=(initial_floor:="${SELECTED_MAP_FLOOR}")
fi
echo "[m20pro_real_full] navigation_backend=${NAVIGATION_BACKEND} local_dddmr_bridge=${ENABLE_DDDMR_BRIDGE} local_dddmr_runtime=${ENABLE_DDDMR_RUNTIME} dddmr_runtime_backend=${DDDMR_RUNTIME_BACKEND} socket_bridge=${ENABLE_DDDMR_SOCKET_BRIDGE} map_assets=${ENABLE_DDDMR_MAP_ASSETS}" >&2

case "${MODE}" in
  shadow|safe)
    AXIS_ENABLED=false
    ;;
  move)
    AXIS_ENABLED=true
    ;;
  *)
    echo "Usage: $0 [shadow|move]" >&2
    exit 2
    ;;
esac

FIELD_PROFILE="${BRINGUP_PREFIX}/share/m20pro_bringup/config/m20pro_field_profile.yaml"
BASE_REAL_PARAMS="${BRINGUP_PREFIX}/share/m20pro_bringup/config/m20pro_real.yaml"
PROFILE_TOOL="${WS_DIR}/scripts/m20pro_field_profile.py"
RUNTIME_PARAMS=""
cleanup_runtime_params() {
  [[ -z "${RUNTIME_PARAMS}" ]] || rm -f -- "${RUNTIME_PARAMS}"
}
trap cleanup_runtime_params EXIT

RUNTIME_PARAMS="$(mktemp "/tmp/m20pro_real_params_${MODE}.XXXXXX.yaml")"
"${PROFILE_TOOL}" render-real-yaml \
  --profile "${FIELD_PROFILE}" \
  --input "${BASE_REAL_PARAMS}" \
  --output "${RUNTIME_PARAMS}" \
  --axis-enabled "${AXIS_ENABLED}"
ros2 launch m20pro_bringup m20pro.launch.py \
  "${COMMON_ARGS[@]}" \
  real_params_file:="${RUNTIME_PARAMS}" \
  enable_axis_command:="${AXIS_ENABLED}" \
  enable_stair_connector:="${AXIS_ENABLED}"
