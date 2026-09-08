#!/usr/bin/env bash
set -euo pipefail

WS_DIR="${M20PRO_WS:-/home/user/m20pro_real_ros2_ws_v4}"
MODE="${1:-safe}"
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
DEFAULT_ENABLE_DDDMR_RUNTIME="false"
if [[ "${MODE}" == "move" ]]; then
  DEFAULT_ENABLE_DDDMR_RUNTIME="true"
fi
NAVIGATION_BACKEND="${M20PRO_NAVIGATION_BACKEND:-dddmr_3d}"
ENABLE_DDDMR_BRIDGE="${M20PRO_ENABLE_DDDMR_BRIDGE:-true}"
ENABLE_DDDMR_RUNTIME="${M20PRO_ENABLE_DDDMR_RUNTIME:-${DEFAULT_ENABLE_DDDMR_RUNTIME}}"
DDDMR_RUNTIME_BACKEND="${M20PRO_DDDMR_RUNTIME_BACKEND:-official}"
ENABLE_DDDMR_MAP_ASSETS="${M20PRO_ENABLE_DDDMR_MAP_ASSETS:-}"
if [[ -z "${ENABLE_DDDMR_MAP_ASSETS}" ]]; then
  ENABLE_DDDMR_MAP_ASSETS="true"
  echo "[m20pro_real_nav] auto-enable 3D map assets for backend ${NAVIGATION_BACKEND}" >&2
fi
ENABLE_GNSS_ADAPTER="${M20PRO_ENABLE_GNSS_ADAPTER:-true}"
GNSS_SOURCE_TOPIC="${M20PRO_GNSS_SOURCE_TOPIC:-/GPS}"
GNSS_FIX_TOPIC="${M20PRO_GNSS_FIX_TOPIC:-/m20pro/gnss/fix}"
GNSS_STATUS_TOPIC="${M20PRO_GNSS_STATUS_TOPIC:-/m20pro/gnss/status}"
DDDMR_MAPPING_HOST="${M20PRO_DDDMR_MAPPING_HOST:-localhost}"
DDDMR_MAPPING_USER="${M20PRO_DDDMR_MAPPING_USER:-user}"
DDDMR_MAP_ASSET_RELOAD_PERIOD_S="${M20PRO_DDDMR_MAP_ASSET_RELOAD_PERIOD_S:-1.0}"
DDDMR_MAPPING_START_COMMAND="${M20PRO_DDDMR_MAPPING_START_COMMAND:-}"
DDDMR_MAPPING_FINISH_COMMAND="${M20PRO_DDDMR_MAPPING_FINISH_COMMAND:-}"
DDDMR_MAPPING_CANCEL_COMMAND="${M20PRO_DDDMR_MAPPING_CANCEL_COMMAND:-}"
DDDMR_MAPPING_STATUS_COMMAND="${M20PRO_DDDMR_MAPPING_STATUS_COMMAND:-}"
DDDMR_MAPPING_CONTROL_SCRIPT="${WS_DIR}/scripts/lightning_raw_mapping_control.sh"
WEB_DASHBOARD_DATA_DIR="${M20PRO_WEB_DASHBOARD_DATA_DIR:-/home/user/.m20pro_web}"
RUNTIME_FLOOR_CONFIG="${M20PRO_RUNTIME_FLOOR_CONFIG:-${WEB_DASHBOARD_DATA_DIR}/runtime_navigation.yaml}"

case "${NAVIGATION_BACKEND}" in
  dddmr_3d) ;;
  *)
    echo "[m20pro_real_nav] invalid M20PRO_NAVIGATION_BACKEND=${NAVIGATION_BACKEND}" >&2
    exit 2
    ;;
esac
case "${DDDMR_RUNTIME_BACKEND}" in
  official|field_proxy) ;;
  *)
    echo "[m20pro_real_nav] invalid M20PRO_DDDMR_RUNTIME_BACKEND=${DDDMR_RUNTIME_BACKEND}" >&2
    exit 2
    ;;
esac
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

set +u
source /opt/robot/scripts/setup_ros2.sh
set -u
cd "${WS_DIR}"
set +u
DDDMR_RUNTIME_SETUP="${M20PRO_DDDMR_RUNTIME_SETUP:-${M20PRO_DDDMR_RUNTIME_WS:-${WS_DIR}}/install/setup.bash}"
if [[ "${ENABLE_DDDMR_RUNTIME}" == "true" && "${DDDMR_RUNTIME_BACKEND}" == "official" && ! -f "${DDDMR_RUNTIME_SETUP}" ]]; then
  echo "[m20pro_real_nav] official DDDMR runtime is missing: ${DDDMR_RUNTIME_SETUP}" >&2
  exit 24
fi
if [[ -f "${DDDMR_RUNTIME_SETUP}" && "$(realpath -m "${DDDMR_RUNTIME_SETUP}")" != "$(realpath -m "${WS_DIR}/install/setup.bash")" ]]; then
  source "${DDDMR_RUNTIME_SETUP}"
fi
source install/setup.bash
set -u
DDDMR_MAP_ASSET_MANIFEST="${M20PRO_DDDMR_MAP_ASSET_MANIFEST:-/home/user/.m20pro_web/dddmr_map_assets.yaml}"
mkdir -p "$(dirname "${DDDMR_MAP_ASSET_MANIFEST}")"

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
  echo "[m20pro_real_nav] initial floor from web working map: ${SELECTED_MAP_FLOOR}" >&2
fi

COMMON_ARGS=(
  mode:=real
  rviz:=false
  enable_web_dashboard:=false
  navigation_backend:="${NAVIGATION_BACKEND}"
  enable_dddmr_bridge:="${ENABLE_DDDMR_BRIDGE}"
  enable_dddmr_runtime:="${ENABLE_DDDMR_RUNTIME}"
  dddmr_runtime_backend:="${DDDMR_RUNTIME_BACKEND}"
  enable_dddmr_map_assets:="${ENABLE_DDDMR_MAP_ASSETS}"
  enable_gnss_adapter:="${ENABLE_GNSS_ADAPTER}"
  gnss_source_topic:="${GNSS_SOURCE_TOPIC}"
  gnss_fix_topic:="${GNSS_FIX_TOPIC}"
  gnss_status_topic:="${GNSS_STATUS_TOPIC}"
  dddmr_map_asset_manifest:="${DDDMR_MAP_ASSET_MANIFEST}"
  dddmr_map_asset_reload_period_s:="${DDDMR_MAP_ASSET_RELOAD_PERIOD_S}"
  dddmr_mapping_host:="${DDDMR_MAPPING_HOST}"
  dddmr_mapping_user:="${DDDMR_MAPPING_USER}"
  floor_config:="${RUNTIME_FLOOR_CONFIG}"
  enable_camera_proxy:=false
  enable_inspection:=false
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
if [[ -n "${M20PRO_DDDMR_MAPCLOUD_FILE:-}" ]]; then
  COMMON_ARGS+=(dddmr_mapcloud_file:="${M20PRO_DDDMR_MAPCLOUD_FILE}")
fi
if [[ -n "${M20PRO_DDDMR_MAPGROUND_FILE:-}" ]]; then
  COMMON_ARGS+=(dddmr_mapground_file:="${M20PRO_DDDMR_MAPGROUND_FILE}")
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
COMMON_ARGS+=(enable_initialpose_3d_adapter:=true)

case "${MODE}" in
  safe|shadow)
    exec ros2 launch m20pro_bringup m20pro.launch.py \
      "${COMMON_ARGS[@]}" \
      enable_axis_command:=false
    ;;
  move)
    exec ros2 launch m20pro_bringup m20pro.launch.py \
      "${COMMON_ARGS[@]}" \
      enable_axis_command:=true
    ;;
  rviz)
    exec ros2 launch m20pro_bringup m20pro.launch.py \
      "${COMMON_ARGS[@]}" \
      rviz:=true \
      enable_axis_command:=false
    ;;
  *)
    echo "Usage: $0 [safe|shadow|move|rviz]" >&2
    exit 2
    ;;
esac
