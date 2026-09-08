#!/usr/bin/env bash
set -euo pipefail

MODE="${M20PRO_WORKSPACE_MODE:-3d}"
WS_DIR="${M20PRO_WS:-/home/user/m20pro_real_ros2_ws_v4}"
REAL_MODE="${M20PRO_REAL_MODE:-move}"

if [[ ! -f "${WS_DIR}/install/setup.bash" ]]; then
  echo "workspace install missing: ${WS_DIR}/install/setup.bash" >&2
  exit 3
fi

if [[ "${M20PRO_CLEAN_STALE_FASTDDS_SHM:-1}" == "1" ]]; then
  # Leaked /dev/shm DDS segments accumulate across restarts and slow down
  # participant startup; clean the stale ones before launching the runtime.
  bash "${WS_DIR}/scripts/clean_stale_fastdds_shm.sh" 60 || true
fi

set +u
source /opt/robot/scripts/setup_ros2.sh
source "${WS_DIR}/install/setup.bash"
set -u

case "${MODE}" in
  2d)
    two_d_profile="${WS_DIR}/install/m20pro_2d_bringup/share/m20pro_2d_bringup/config/m20pro_2d_fastdds_udp.xml"
    if [[ -f "${two_d_profile}" ]]; then
      export FASTRTPS_DEFAULT_PROFILES_FILE="${two_d_profile}"
    fi
    exec ros2 launch m20pro_2d_bringup m20pro_2d_mapping.launch.py \
      rviz:="${M20PRO_2D_RVIZ:-false}"
    ;;
  3d)
    exec ros2 run m20pro_bringup m20pro_real_full.sh "${REAL_MODE}"
    ;;
  *)
    echo "invalid M20PRO_WORKSPACE_MODE=${MODE}; expected 2d or 3d" >&2
    exit 2
    ;;
esac
