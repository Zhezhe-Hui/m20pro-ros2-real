#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
ROOT_WS="${M20PRO_3D_WS:-/home/user/m20pro_real_ros2_ws_v4}"
WS_2D="${M20PRO_2D_WS:-/home/user/m20pro_2d_ros2_ws}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root on 104 after su." >&2
  exit 2
fi

status() {
  echo "workspace_mode=$(grep -E '^M20PRO_WORKSPACE_MODE=' /etc/default/m20pro-real 2>/dev/null | cut -d= -f2- || echo unknown)"
  echo "workspace=$(grep -E '^M20PRO_WS=' /etc/default/m20pro-real 2>/dev/null | cut -d= -f2- || echo unknown)"
  echo "2d_install=$([[ -f "${WS_2D}/install/setup.bash" ]] && echo ready || echo missing)"
  echo "3d_install=$([[ -f "${ROOT_WS}/install/setup.bash" ]] && echo ready || echo missing)"
  systemctl is-active m20pro-real.service m20pro-dddmr-socket-source.service \
    m20pro-dddmr-motion-source.service m20pro-2d-motion-source.service 2>/dev/null || true
}

switch_to() {
  local mode="$1" ws real_mode enable_runtime enable_bridge enable_socket navigation_backend dddmr_runtime_ws dddmr_runtime_setup
  case "${mode}" in
    2d)
      ws="${WS_2D}"
      real_mode=shadow
      enable_runtime=false
      enable_bridge=false
      enable_socket=false
      navigation_backend=nav2_2d
      dddmr_runtime_ws=""
      dddmr_runtime_setup=""
      ;;
    3d)
      ws="${ROOT_WS}"
      real_mode=move
      enable_runtime=true
      enable_bridge=true
      enable_socket=true
      navigation_backend=dddmr_3d
      dddmr_runtime_ws="${ROOT_WS}"
      dddmr_runtime_setup="${ROOT_WS}/install/setup.bash"
      ;;
    *)
      echo "Usage: $0 {2d|3d|status}" >&2
      exit 2
      ;;
  esac
  if [[ ! -f "${ws}/install/setup.bash" ]]; then
    echo "workspace is not built: ${ws}" >&2
    if [[ "${mode}" == 2d ]]; then
      echo "Run as user first: ${ROOT_WS}/scripts/104_prepare_2d_workspace.sh" >&2
    fi
    exit 3
  fi

  M20PRO_WS="${ws}" \
  M20PRO_WORKSPACE_MODE="${mode}" \
  M20PRO_NAVIGATION_BACKEND="${navigation_backend}" \
  M20PRO_REAL_MODE="${real_mode}" \
  M20PRO_ENABLE_DDDMR_RUNTIME="${enable_runtime}" \
  M20PRO_ENABLE_DDDMR_BRIDGE="${enable_bridge}" \
  M20PRO_ENABLE_DDDMR_SOCKET_BRIDGE="${enable_socket}" \
  M20PRO_DDDMR_RUNTIME_WS="${dddmr_runtime_ws}" \
  M20PRO_DDDMR_RUNTIME_SETUP="${dddmr_runtime_setup}" \
    "${ROOT_WS}/scripts/104_enable_autostart.sh" "${real_mode}"
  systemctl restart m20pro-real.service
  if [[ "${mode}" == 3d ]]; then
    systemctl stop m20pro-2d-motion-source.service 2>/dev/null || true
    systemctl restart m20pro-dddmr-motion-source.service
    systemctl restart m20pro-dddmr-socket-source.service
  else
    systemctl stop m20pro-dddmr-motion-source.service 2>/dev/null || true
    systemctl restart m20pro-2d-motion-source.service
    systemctl stop m20pro-dddmr-socket-source.service 2>/dev/null || true
  fi
  sleep 3
  echo "[104_switch_workspace] active=${mode} workspace=${ws}"
  status
}

case "${ACTION}" in
  status) status ;;
  2d|3d) switch_to "${ACTION}" ;;
  *) echo "Usage: $0 {2d|3d|status}" >&2; exit 2 ;;
esac
