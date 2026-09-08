#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW_CONFIG_DEFAULT="${ROOT_DIR}/src/m20pro_bringup/config/lightning_m20pro_raw_mapping.yaml"

export M20PRO_LIGHTNING_MAPPING_CONFIG="${M20PRO_LIGHTNING_MAPPING_CONFIG:-${RAW_CONFIG_DEFAULT}}"
export M20PRO_LIGHTNING_SOURCE_CLOUD_TOPIC="${M20PRO_LIGHTNING_SOURCE_CLOUD_TOPIC:-/m20pro/lidar_points_dense_ros}"
export M20PRO_LIGHTNING_ENABLE_CLOUD_ADAPTER="${M20PRO_LIGHTNING_ENABLE_CLOUD_ADAPTER:-false}"

exec "${ROOT_DIR}/scripts/104_dddmr_mapping_control.sh" "$@"
