#!/usr/bin/env bash
set -euo pipefail

# Start the v4 3D RViz view on the 104 desktop session (gdm autologin).
#
#   bash scripts/104_start_rviz_desktop.sh            # start on the desktop
#   bash scripts/104_start_rviz_desktop.sh status     # check rviz2 process
#
# RViz shows the normalized live DDDMR edge cloud (/dddmr/edge_cloud, purple) plus
# the DDDMR map clouds; the dense mapping cloud layer
# (/m20pro/lidar_points_dense_ros, green) appears while the dense chain runs.
# The visualization launch also publishes the robot model TF for the 3D view.

WS_DIR="${M20PRO_WS:-/home/user/m20pro_real_ros2_ws_v4}"
ACTION="${1:-start}"

status() {
  ps -eo pid,user,args | grep rviz2 | grep -v grep || true
}

case "${ACTION}" in
  status)
    status
    exit 0
    ;;
  start) ;;
  *)
    echo "usage: $0 [start|status]" >&2
    exit 2
    ;;
esac

if status | grep -q rviz2; then
  echo "[rviz] rviz2 is already running; use '$0 status' to inspect" >&2
  exit 0
fi

sudo -u user setsid bash -c '
  export DISPLAY=:0
  export XAUTHORITY=/home/user/.Xauthority
  export ROS_DOMAIN_ID=0
  export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/robot/fastdds.xml
  source /opt/robot/scripts/setup_ros2.sh >/dev/null 2>&1
  source '"${WS_DIR}"'/install/setup.bash >/dev/null 2>&1
  exec /opt/ros/foxy/bin/ros2 launch m20pro_bringup m20pro_visualization.launch.py
' > /tmp/rviz_launch.log 2>&1 &
sleep 6
if status | grep -q rviz2; then
  echo "[rviz] started on desktop session (DISPLAY=:0), log=/tmp/rviz_launch.log"
else
  echo "[rviz] startup failed; check /tmp/rviz_launch.log" >&2
  exit 1
fi
