#!/usr/bin/env bash
set -euo pipefail

WS_DIR="${M20PRO_WS:-/home/user/m20pro_real_ros2_ws_v4}"
MEDIAMTX_BIN_SRC="${M20PRO_MEDIAMTX_BIN_SRC:-/tmp/mediamtx}"
BIN_DST="/usr/local/lib/m20pro/mediamtx"
CONFIG_SRC="${WS_DIR}/systemd/m20pro-camera-webrtc-104.yml"
CONFIG_DST="/etc/m20pro-camera-webrtc-104.yml"
UNIT_SRC="${WS_DIR}/systemd/m20pro-camera-webrtc-104.service"
UNIT_DST="/etc/systemd/system/m20pro-camera-webrtc-104.service"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root on 104" >&2
  exit 2
fi
for path in "${MEDIAMTX_BIN_SRC}" "${CONFIG_SRC}" "${UNIT_SRC}"; do
  if [[ ! -e "${path}" ]]; then
    echo "missing required file: ${path}" >&2
    exit 1
  fi
done
version_output="$("${MEDIAMTX_BIN_SRC}" --version 2>/dev/null || true)"
if [[ ! "${version_output}" =~ ^v([0-9]+)\.([0-9]+)\. ]] \
  || (( BASH_REMATCH[1] < 1 )) \
  || (( BASH_REMATCH[1] == 1 && BASH_REMATCH[2] < 20 )); then
  echo "MediaMTX v1.20.0 or newer is required for the WebRTC gateway config; got: ${version_output:-unknown}" >&2
  exit 1
fi

install -d -m 0755 "$(dirname "${BIN_DST}")"
install -m 0755 "${MEDIAMTX_BIN_SRC}" "${BIN_DST}"
install -m 0644 "${CONFIG_SRC}" "${CONFIG_DST}"
install -m 0644 "${UNIT_SRC}" "${UNIT_DST}"
systemctl daemon-reload
systemctl enable --now m20pro-camera-webrtc-104.service

echo "[104_enable_camera_webrtc] installed and started m20pro-camera-webrtc-104.service"
echo "[104_enable_camera_webrtc] ${version_output}; WebRTC 8889, ICE 8189 UDP/TCP, HLS fallback 8888"
