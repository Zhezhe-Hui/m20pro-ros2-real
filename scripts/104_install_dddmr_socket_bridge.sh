#!/usr/bin/env bash
set -euo pipefail

# Build this on the RK3588/Foxy host. DrDDS headers and ABI are target-only;
# never copy an x86/Humble binary into 104.
WS_DIR="${M20PRO_WS:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SOURCE="${WS_DIR}/tools/edge_scan_feasibility/drdds_edge_cloud_socket_source.cpp"
MOTION_SOURCE="${WS_DIR}/tools/edge_scan_feasibility/drdds_motion_info_socket_source.cpp"
UNIT_SOURCE="${WS_DIR}/systemd/m20pro-dddmr-socket-source.service"
MOTION_UNIT_SOURCE="${WS_DIR}/systemd/m20pro-dddmr-motion-source.service"
TARGET="/usr/local/lib/m20pro/drdds_edge_cloud_socket_source"
MOTION_TARGET="/usr/local/lib/m20pro/drdds_motion_info_socket_source"
UNIT_TARGET="/etc/systemd/system/m20pro-dddmr-socket-source.service"
MOTION_UNIT_TARGET="/etc/systemd/system/m20pro-dddmr-motion-source.service"
BUILD_DIR="$(mktemp -d /tmp/m20pro-dddmr-socket-build.XXXXXX)"

cleanup() {
  rm -rf -- "${BUILD_DIR}"
}
trap cleanup EXIT

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root on 104: sudo M20PRO_WS=${WS_DIR} $0" >&2
  exit 2
fi
if [[ ! -f "${SOURCE}" || ! -f "${MOTION_SOURCE}" || ! -f "${UNIT_SOURCE}" || ! -f "${MOTION_UNIT_SOURCE}" ]]; then
  echo "missing v4 socket bridge source under ${WS_DIR}" >&2
  exit 1
fi
if [[ ! -f /usr/local/include/dridl/drdds/core/common_type.h && ! -f /usr/local/include/drdds/core/common_type.h ]]; then
  echo "DrDDS development headers are missing on this host" >&2
  exit 1
fi

g++ -std=c++17 -DGEN_API_VER=2 \
  -I/usr/local/include -I/usr/local/include/dridl \
  "${SOURCE}" -o "${BUILD_DIR}/drdds_edge_cloud_socket_source" \
  -L/usr/local/lib -Wl,-rpath,/usr/local/lib \
  -ldrdds -lfastcdr -lfastrtps -lfoonathan_memory-0.7.3 -lpthread
g++ -std=c++17 -DGEN_API_VER=2 \
  -I/usr/local/include -I/usr/local/include/dridl \
  "${MOTION_SOURCE}" -o "${BUILD_DIR}/drdds_motion_info_socket_source" \
  -L/usr/local/lib -Wl,-rpath,/usr/local/lib \
  -ldrdds -lfastcdr -lfastrtps -lfoonathan_memory-0.7.3 -lpthread

install -D -m 0755 "${BUILD_DIR}/drdds_edge_cloud_socket_source" "${TARGET}"
install -D -m 0755 "${BUILD_DIR}/drdds_motion_info_socket_source" "${MOTION_TARGET}"
install -m 0644 "${UNIT_SOURCE}" "${UNIT_TARGET}"
install -m 0644 "${MOTION_UNIT_SOURCE}" "${MOTION_UNIT_TARGET}"
systemctl daemon-reload
systemctl enable m20pro-dddmr-socket-source.service
systemctl enable m20pro-dddmr-motion-source.service

echo "[104_install_dddmr_socket_bridge] installed ${TARGET}"
echo "[104_install_dddmr_socket_bridge] enabled m20pro-dddmr-socket-source.service"
echo "[104_install_dddmr_socket_bridge] enabled m20pro-dddmr-motion-source.service"
