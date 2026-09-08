#!/usr/bin/env bash
set -euo pipefail

WS_DIR="${M20PRO_WS:-/home/user/m20pro_real_ros2_ws_v4}"
PORT="${1:-8080}"
NAVIGATION_BACKEND="${M20PRO_NAVIGATION_BACKEND:-dddmr_3d}"
DDDMR_MAPPING_HOST="${M20PRO_DDDMR_MAPPING_HOST:-localhost}"
DDDMR_MAPPING_USER="${M20PRO_DDDMR_MAPPING_USER:-user}"
DDDMR_MAPPING_START_COMMAND="${M20PRO_DDDMR_MAPPING_START_COMMAND:-}"
DDDMR_MAPPING_FINISH_COMMAND="${M20PRO_DDDMR_MAPPING_FINISH_COMMAND:-}"
DDDMR_MAPPING_CANCEL_COMMAND="${M20PRO_DDDMR_MAPPING_CANCEL_COMMAND:-}"
DDDMR_MAPPING_STATUS_COMMAND="${M20PRO_DDDMR_MAPPING_STATUS_COMMAND:-}"
DDDMR_MAP_ASSET_RELOAD_PERIOD_S="${M20PRO_DDDMR_MAP_ASSET_RELOAD_PERIOD_S:-1.0}"
DDDMR_MAP_ASSET_MANIFEST="${M20PRO_DDDMR_MAP_ASSET_MANIFEST:-/home/user/.m20pro_web/dddmr_map_assets.yaml}"
NAVIGATION_BACKEND_STATUS_TOPIC="${M20PRO_NAVIGATION_BACKEND_STATUS_TOPIC:-/m20pro/navigation_backend/status}"
DDDMR_RUNTIME_STATUS_TOPIC="${M20PRO_DDDMR_RUNTIME_STATUS_TOPIC:-/m20pro/dddmr/runtime/status}"
ENABLE_GNSS_ADAPTER="${M20PRO_ENABLE_GNSS_ADAPTER:-false}"
GNSS_STATUS_TOPIC="${M20PRO_GNSS_STATUS_TOPIC:-/m20pro/gnss/status}"
WEB_DASHBOARD_DATA_DIR="${M20PRO_WEB_DASHBOARD_DATA_DIR:-/home/user/.m20pro_web}"
RUNTIME_FLOOR_CONFIG="${M20PRO_RUNTIME_FLOOR_CONFIG:-${WEB_DASHBOARD_DATA_DIR}/runtime_navigation.yaml}"

cat >&2 <<'EOF'
[m20pro_real_web] 仅用于开发预览网页界面。
[m20pro_real_web] 真机测试请使用 m20pro_real_full.sh shadow/move 全量启动。
[m20pro_real_web] 单独网页不会拉起 tcp_bridge、三维运行时或点云融合。
EOF

set +u
source /opt/robot/scripts/setup_ros2.sh
set -u
cd "${WS_DIR}"
set +u
source install/setup.bash
set -u

LAUNCH_ARGS=(
  port:="${PORT}"
  navigation_backend:="${NAVIGATION_BACKEND}"
  navigation_backend_status_topic:="${NAVIGATION_BACKEND_STATUS_TOPIC}"
  dddmr_runtime_status_topic:="${DDDMR_RUNTIME_STATUS_TOPIC}"
  enable_gnss_adapter:="${ENABLE_GNSS_ADAPTER}"
  gnss_status_topic:="${GNSS_STATUS_TOPIC}"
  dddmr_map_asset_manifest:="${DDDMR_MAP_ASSET_MANIFEST}"
  dddmr_map_asset_reload_period_s:="${DDDMR_MAP_ASSET_RELOAD_PERIOD_S}"
  dddmr_mapping_host:="${DDDMR_MAPPING_HOST}"
  dddmr_mapping_user:="${DDDMR_MAPPING_USER}"
  data_dir:="${WEB_DASHBOARD_DATA_DIR}"
  floor_config:="${RUNTIME_FLOOR_CONFIG}"
  enable_camera_proxy:=false
)
if [[ -n "${DDDMR_MAPPING_START_COMMAND}" ]]; then
  LAUNCH_ARGS+=(dddmr_mapping_start_command:="${DDDMR_MAPPING_START_COMMAND}")
fi
if [[ -n "${DDDMR_MAPPING_FINISH_COMMAND}" ]]; then
  LAUNCH_ARGS+=(dddmr_mapping_finish_command:="${DDDMR_MAPPING_FINISH_COMMAND}")
fi
if [[ -n "${DDDMR_MAPPING_CANCEL_COMMAND}" ]]; then
  LAUNCH_ARGS+=(dddmr_mapping_cancel_command:="${DDDMR_MAPPING_CANCEL_COMMAND}")
fi
if [[ -n "${DDDMR_MAPPING_STATUS_COMMAND}" ]]; then
  LAUNCH_ARGS+=(dddmr_mapping_status_command:="${DDDMR_MAPPING_STATUS_COMMAND}")
fi

exec ros2 launch m20pro_bringup m20pro_web_dashboard.launch.py "${LAUNCH_ARGS[@]}"
