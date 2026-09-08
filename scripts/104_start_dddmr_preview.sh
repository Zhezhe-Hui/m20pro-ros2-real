#!/usr/bin/env bash
set -euo pipefail

WS_DIR="${M20PRO_WS:-/home/user/m20pro_real_ros2_ws_v4}"
PORT="${M20PRO_DDDMR_PREVIEW_PORT:-${1:-18080}}"
DATA_DIR="${M20PRO_DDDMR_PREVIEW_DATA_DIR:-~/.m20pro_web_dddmr_preview}"
MAP_ARCHIVE_DIR="${M20PRO_DDDMR_PREVIEW_MAP_ARCHIVE_DIR:-~/m20pro_maps_dddmr_preview}"
DDDMR_MAP_ASSET_MANIFEST="${M20PRO_DDDMR_MAP_ASSET_MANIFEST:-/home/user/.m20pro_web/dddmr_map_assets.yaml}"
NAVIGATION_BACKEND="${M20PRO_NAVIGATION_BACKEND:-dddmr_3d}"
ENABLE_EDGE_CLOUD_ADAPTER="${M20PRO_ENABLE_DDDMR_EDGE_CLOUD_ADAPTER:-true}"
ENABLE_MAP_ASSET_SERVER="${M20PRO_ENABLE_DDDMR_MAP_ASSET_SERVER:-true}"
ENABLE_DDDMR_BRIDGE="${M20PRO_ENABLE_DDDMR_BRIDGE:-true}"
ENABLE_DDDMR_RUNTIME="${M20PRO_ENABLE_DDDMR_RUNTIME:-false}"
ENABLE_GNSS_ADAPTER="${M20PRO_ENABLE_GNSS_ADAPTER:-false}"
ENABLE_WEB_DASHBOARD="${M20PRO_ENABLE_WEB_DASHBOARD:-true}"
DDDMR_FIELD_TEST_FLAT_MAP="${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP:-true}"
DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M="${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M:-2.0}"
DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M="${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M:-0.25}"
DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M="${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M:-0.0}"
DDDMR_MAPPING_HOST="${M20PRO_DDDMR_MAPPING_HOST:-localhost}"
DDDMR_MAPPING_USER="${M20PRO_DDDMR_MAPPING_USER:-user}"
DDDMR_MAPPING_START_COMMAND="${M20PRO_DDDMR_MAPPING_START_COMMAND:-}"
DDDMR_MAPPING_FINISH_COMMAND="${M20PRO_DDDMR_MAPPING_FINISH_COMMAND:-}"
DDDMR_MAPPING_CANCEL_COMMAND="${M20PRO_DDDMR_MAPPING_CANCEL_COMMAND:-}"

if [[ "${NAVIGATION_BACKEND}" != "dddmr_3d" ]]; then
  echo "[104_start_dddmr_preview] preview is DDDMR 3D read-only; refusing backend=${NAVIGATION_BACKEND}" >&2
  exit 2
fi

if [[ ! -f "${WS_DIR}/install/setup.bash" ]]; then
  echo "[104_start_dddmr_preview] install/setup.bash not found in ${WS_DIR}" >&2
  echo "[104_start_dddmr_preview] run local_deploy_to_test_robot.sh with M20PRO_DEPLOY_PREPARE_ONLY=1 first." >&2
  exit 3
fi

cat >&2 <<EOF
[104_start_dddmr_preview] DDDMR 3D read-only preview; no systemd cutover, no motion authorization.
[104_start_dddmr_preview] workspace=${WS_DIR}
[104_start_dddmr_preview] web=http://0.0.0.0:${PORT}/
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
  data_dir:="${DATA_DIR}"
  map_archive_dir:="${MAP_ARCHIVE_DIR}"
  navigation_backend:="${NAVIGATION_BACKEND}"
  dddmr_map_asset_manifest:="${DDDMR_MAP_ASSET_MANIFEST}"
  enable_edge_cloud_adapter:="${ENABLE_EDGE_CLOUD_ADAPTER}"
  enable_map_asset_server:="${ENABLE_MAP_ASSET_SERVER}"
  enable_bridge:="${ENABLE_DDDMR_BRIDGE}"
  enable_dddmr_runtime:="${ENABLE_DDDMR_RUNTIME}"
  enable_gnss_adapter:="${ENABLE_GNSS_ADAPTER}"
  enable_web_dashboard:="${ENABLE_WEB_DASHBOARD}"
  dddmr_field_test_flat_map:="${DDDMR_FIELD_TEST_FLAT_MAP}"
  dddmr_field_test_flat_map_extent_m:="${DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M}"
  dddmr_field_test_flat_map_spacing_m:="${DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M}"
  dddmr_field_test_flat_map_height_m:="${DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M}"
  dddmr_mapping_host:="${DDDMR_MAPPING_HOST}"
  dddmr_mapping_user:="${DDDMR_MAPPING_USER}"
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

exec ros2 launch m20pro_bringup m20pro_dddmr_preview.launch.py "${LAUNCH_ARGS[@]}"
