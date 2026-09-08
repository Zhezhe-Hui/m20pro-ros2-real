#!/usr/bin/env bash
set -euo pipefail

SOURCE_WS="${M20PRO_3D_WS:-/home/user/m20pro_real_ros2_ws_v4}"
TARGET_WS="${M20PRO_2D_WS:-/home/user/m20pro_2d_ros2_ws}"

if [[ "$(id -un)" != "user" ]]; then
  echo "Run as user on 104, not root: $0" >&2
  exit 2
fi
if [[ ! -d "${SOURCE_WS}/src" ]]; then
  echo "3D source workspace missing: ${SOURCE_WS}" >&2
  exit 1
fi

mkdir -p "${TARGET_WS}/src"
if [[ ! -d "${SOURCE_WS}/src_2d/m20pro_2d_bringup" ]]; then
  echo "missing 2D source package: ${SOURCE_WS}/src_2d/m20pro_2d_bringup" >&2
  exit 1
fi
if [[ ! -d "${SOURCE_WS}/src_2d/m20pro_2d_navigation" ||
      ! -d "${SOURCE_WS}/src_2d/m20pro_2d_cloud_bridge" ]]; then
  echo "missing independent 2D navigation/cloud packages under ${SOURCE_WS}/src_2d" >&2
  exit 1
fi
if [[ ! -d "${SOURCE_WS}/src_2d/m20pro_2d_description" ]]; then
  echo "missing independent 2D description package: ${SOURCE_WS}/src_2d/m20pro_2d_description" >&2
  exit 1
fi

# Copy only the independent 2D package sources.  The target must not contain
# symlinks into the 3D source tree or any 3D package names in its colcon graph.
for package in \
  m20pro_2d_bringup \
  m20pro_2d_navigation \
  m20pro_2d_cloud_bridge \
  m20pro_2d_description; do
  rm -rf "${TARGET_WS}/src/${package}"
  cp -a "${SOURCE_WS}/src_2d/${package}" "${TARGET_WS}/src/${package}"
done
rm -f "${TARGET_WS}/src/m20pro_description" "${TARGET_WS}/src/m20pro_navigation" \
  "${TARGET_WS}/src/m20pro_cloud_bridge" "${TARGET_WS}/src/m20pro_bringup"
printf '%s\n' 'm20pro_2d_ros2_ws' > "${TARGET_WS}/.workspace_kind"

set +u
source /opt/robot/scripts/setup_ros2.sh
set -u
cd "${TARGET_WS}"
colcon build --symlink-install --packages-select \
  m20pro_2d_description \
  m20pro_2d_navigation \
  m20pro_2d_cloud_bridge \
  m20pro_2d_bringup

echo "[104_prepare_2d_workspace] ready=${TARGET_WS}"
echo "[104_prepare_2d_workspace] independent 2D source copies are under ${TARGET_WS}/src"
echo "[104_prepare_2d_workspace] install=${TARGET_WS}/install/setup.bash"
