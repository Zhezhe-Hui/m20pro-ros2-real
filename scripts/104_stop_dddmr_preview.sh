#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="$("${script_dir}/104_resolve_dddmr_preview_port.sh" "${M20PRO_DDDMR_PREVIEW_PORT:-${1:-}}")"
RUN_DIR="${M20PRO_DDDMR_PREVIEW_RUN_DIR:-${HOME}/.m20pro_dddmr_preview}"
PID_FILE="${RUN_DIR}/preview_${PORT}.pid"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "[104_stop_dddmr_preview] no pid file for port ${PORT}"
else
  pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
    echo "[104_stop_dddmr_preview] stopping preview pid=${pid} port=${PORT}"
    kill -TERM -- -"${pid}" >/dev/null 2>&1 || true
    sleep 1
    kill -KILL -- -"${pid}" >/dev/null 2>&1 || true
  else
    echo "[104_stop_dddmr_preview] stale pid file for port ${PORT}"
  fi
  rm -f "${PID_FILE}"
fi

echo "[104_stop_dddmr_preview] remaining preview processes:"
ps -eo pid,ppid,args | awk '/m20pro_dddmr_preview|104_start_dddmr_preview|m20pro_web_dashboard_preview/ && !/awk/ {print}' || true

echo "[104_stop_dddmr_preview] port ${PORT}:"
ss -ltnp 2>/dev/null | grep ":${PORT}" || true
