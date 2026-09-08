#!/usr/bin/env bash
set -euo pipefail

# Install the on-demand RTMP push units used by the cloud SRS WebRTC relay.
# The units are NOT enabled at boot: the web dashboard starts/stops them on
# demand via /api/remote_stream so the robot uplink stays idle when nobody
# watches remotely. Start manually for testing:
#   sudo systemctl start m20pro-rtmp-push@video1.service

WS_DIR="${M20PRO_WS:-/home/user/m20pro_real_ros2_ws_v4}"
UNIT_SRC="${WS_DIR}/systemd/m20pro-rtmp-push@.service"
UNIT_DST="/etc/systemd/system/m20pro-rtmp-push@.service"
ENV_SRC="${WS_DIR}/systemd/m20pro-rtmp-push.env"
ENV_DST="/etc/m20pro-rtmp-push.env"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root on 104" >&2
  exit 2
fi
for path in "${UNIT_SRC}" "${ENV_SRC}"; do
  if [[ ! -e "${path}" ]]; then
    echo "missing required file: ${path}" >&2
    exit 1
  fi
done

install -m 0644 "${ENV_SRC}" "${ENV_DST}"
install -m 0644 "${UNIT_SRC}" "${UNIT_DST}"
systemctl daemon-reload

echo "[104_enable_rtmp_push] installed m20pro-rtmp-push@.service (on-demand; not auto-started)"
