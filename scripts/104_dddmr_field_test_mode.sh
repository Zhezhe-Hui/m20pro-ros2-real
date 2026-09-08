#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
WS_DIR="${M20PRO_WS:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENABLE_SCRIPT="${WS_DIR}/scripts/104_enable_autostart.sh"
ACCEPT_SCRIPT="${WS_DIR}/scripts/104_accept_dddmr_field_test.sh"
WEB_URL="${M20PRO_WEB_URL:-http://127.0.0.1:8080}"

usage() {
  cat <<EOF
Usage: $0 <enable|restart|accept|status>

  enable       Switch systemd to DDDMR 3D mode and restart service.
               This enables motion authority, but sends no task or velocity.
  restart      Restart current m20pro-real.service and show status.
  accept       Read-only DDDMR acceptance check.
  status       Show systemd config, service state, web health, and acceptance.
EOF
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "[104_dddmr_field_test_mode] ${ACTION} must run as root on 104 after su." >&2
    exit 2
  fi
}

require_workspace() {
  if [[ ! -x "${ENABLE_SCRIPT}" ]]; then
    echo "[104_dddmr_field_test_mode] missing ${ENABLE_SCRIPT}" >&2
    exit 20
  fi
}

wait_web() {
  local ready=0
  local state=""
  for _ in $(seq 1 90); do
    state="$(systemctl is-active m20pro-real.service 2>/dev/null || true)"
    if [[ "${state}" == "active" ]] && \
        curl --connect-timeout 1 --max-time 2 -fsS "${WEB_URL%/}/healthz" >/dev/null 2>&1; then
      ready=1
      break
    fi
    [[ "${state}" != "failed" ]]
    sleep 1
  done
  if [[ "${ready}" -ne 1 ]]; then
    echo "[104_dddmr_field_test_mode] FAIL web_not_ready service_state=${state}" >&2
    exit 21
  fi
}

restart_service() {
  systemctl reset-failed m20pro-real.service || true
  systemctl restart m20pro-real.service
  wait_web
}

show_acceptance() {
  if [[ -x "${ACCEPT_SCRIPT}" ]]; then
    "${ACCEPT_SCRIPT}" "${WEB_URL}" || true
  else
    echo "[104_dddmr_field_test_mode] acceptance script unavailable: ${ACCEPT_SCRIPT}"
  fi
}

show_status() {
  echo "[104_dddmr_field_test_mode] workspace=${WS_DIR}"
  echo "[104_dddmr_field_test_mode] web=${WEB_URL}"
  echo
  echo "[104_dddmr_field_test_mode] service:"
  systemctl is-active m20pro-real.service 2>/dev/null || true
  systemctl show m20pro-real.service \
    -p ActiveState -p SubState -p NRestarts -p ExecMainStatus --no-pager 2>/dev/null || true
  echo
  echo "[104_dddmr_field_test_mode] config:"
  if [[ -f /etc/default/m20pro-real ]]; then
    awk -F= '
      /^M20PRO_REAL_MODE=/ ||
      /^M20PRO_NAVIGATION_BACKEND=/ ||
      /^M20PRO_ENABLE_DDDMR/ ||
      /^M20PRO_DDDMR_/ {print}
    ' /etc/default/m20pro-real
  else
    echo "/etc/default/m20pro-real not found"
  fi
  echo
  echo "[104_dddmr_field_test_mode] web health:"
  curl --connect-timeout 1 --max-time 2 -fsS "${WEB_URL%/}/healthz" 2>/dev/null || true
  echo
  echo
  echo "[104_dddmr_field_test_mode] DDDMR acceptance:"
  show_acceptance
}

apply_profile() {
  local real_mode="$1"
  shift
  require_root
  require_workspace
  env "M20PRO_WS=${WS_DIR}" "$@" bash "${ENABLE_SCRIPT}" "${real_mode}"
  restart_service
  show_status
}

case "${ACTION}" in
  enable|dddmr)
    apply_profile move \
      "M20PRO_NAVIGATION_BACKEND=dddmr_3d" \
      "M20PRO_ENABLE_DDDMR_BRIDGE=true" \
      "M20PRO_ENABLE_DDDMR_RUNTIME=true" \
      "M20PRO_ENABLE_DDDMR_MAP_ASSETS=true" \
      "M20PRO_DDDMR_RUNTIME_BACKEND=field_proxy" \
      "M20PRO_DDDMR_RUNTIME_DISTRO=foxy" \
      "M20PRO_DDDMR_RUNTIME_WS=/home/user/m20pro_dddmr_foxy_ws" \
      "M20PRO_DDDMR_MAPPING_LAUNCH=m20pro_lightning_mapping.launch.py" \
      "M20PRO_DDDMR_ALGORITHM_PACKAGE=lightning" \
      "M20PRO_LIGHTNING_MAPPING_WORK_DIR=/root/.m20pro_lightning_mapping/work" \
      "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP=true" \
      "M20PRO_DDDMR_MAPPING_HOST=localhost" \
      "M20PRO_DDDMR_MAPPING_USER=user" \
      "M20PRO_DDDMR_MAPPING_START_COMMAND=${WS_DIR}/scripts/lightning_raw_mapping_control.sh start {floor}" \
      "M20PRO_DDDMR_MAPPING_FINISH_COMMAND=${WS_DIR}/scripts/lightning_raw_mapping_control.sh finish {floor}" \
      "M20PRO_DDDMR_MAPPING_CANCEL_COMMAND=${WS_DIR}/scripts/lightning_raw_mapping_control.sh cancel {floor}" \
      "M20PRO_DDDMR_MAPPING_STATUS_COMMAND=${WS_DIR}/scripts/lightning_raw_mapping_control.sh status {floor}"
    ;;
  restart)
    require_root
    restart_service
    show_status
    ;;
  accept)
    show_acceptance
    ;;
  status)
    show_status
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
