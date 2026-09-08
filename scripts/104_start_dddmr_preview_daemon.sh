#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PREVIEW_WS="${M20PRO_DDDMR_PREVIEW_WS:-${HOME}/.m20pro_dddmr_preview/latest}"
if [[ -n "${M20PRO_WS:-}" ]]; then
  WS_DIR="${M20PRO_WS}"
elif [[ -e "${DEFAULT_PREVIEW_WS}" ]]; then
  WS_DIR="$(readlink -f "${DEFAULT_PREVIEW_WS}")"
else
  WS_DIR="/home/user/m20pro_real_ros2_ws_v4"
fi
PORT="${M20PRO_DDDMR_PREVIEW_PORT:-${1:-18080}}"
RUN_DIR="${M20PRO_DDDMR_PREVIEW_RUN_DIR:-${HOME}/.m20pro_dddmr_preview}"
PID_FILE="${RUN_DIR}/preview_${PORT}.pid"
LOG_FILE="${RUN_DIR}/preview_${PORT}.log"
URL="http://127.0.0.1:${PORT}"

if [[ ! -x "${WS_DIR}/scripts/104_start_dddmr_preview.sh" ]]; then
  echo "[104_start_dddmr_preview_daemon] preview script not found in ${WS_DIR}" >&2
  exit 3
fi

mkdir -p "${RUN_DIR}"

if [[ -f "${PID_FILE}" ]]; then
  old_pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" >/dev/null 2>&1; then
    echo "[104_start_dddmr_preview_daemon] already running pid=${old_pid} url=${URL}"
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

cat >&2 <<EOF
[104_start_dddmr_preview_daemon] starting no-sudo DDDMR read-only preview
[104_start_dddmr_preview_daemon] workspace=${WS_DIR}
[104_start_dddmr_preview_daemon] url=${URL}
[104_start_dddmr_preview_daemon] log=${LOG_FILE}
EOF

: > "${LOG_FILE}"
setsid env \
  M20PRO_WS="${WS_DIR}" \
  M20PRO_DDDMR_PREVIEW_PORT="${PORT}" \
  M20PRO_DDDMR_FIELD_TEST_FLAT_MAP="${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP:-true}" \
  M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M="${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M:-2.0}" \
  M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M="${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M:-0.25}" \
  M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M="${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M:-0.0}" \
  "${WS_DIR}/scripts/104_start_dddmr_preview.sh" "${PORT}" \
  >>"${LOG_FILE}" 2>&1 < /dev/null &
pid="$!"
printf '%s\n' "${pid}" > "${PID_FILE}"

ready=0
for _ in $(seq 1 60); do
  if curl --connect-timeout 1 --max-time 2 -fsS "${URL}/healthz" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "${pid}" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if [[ "${ready}" -ne 1 ]]; then
  echo "[104_start_dddmr_preview_daemon] preview failed to become ready" >&2
  tail -n 80 "${LOG_FILE}" >&2 || true
  kill -TERM -- -"${pid}" >/dev/null 2>&1 || true
  sleep 1
  kill -KILL -- -"${pid}" >/dev/null 2>&1 || true
  rm -f "${PID_FILE}"
  exit 14
fi

echo "[104_start_dddmr_preview_daemon] ready pid=${pid} url=http://10.21.31.104:${PORT}"
curl --connect-timeout 1 --max-time 3 -fsS "${URL}/api/state" \
  | python3 "${script_dir}/navigation_backend_summary.py" \
  | python3 -c '
import json
import sys

state = json.load(sys.stdin)
nav = state
assets = state.get("assets") or {}
asset_status = assets.get("status") or {}
print(
    "[104_start_dddmr_preview_daemon] backend=%s bridge_seen=%s reason=%s assets=%s/%s provisional=%s source=%s"
    % (
        nav.get("backend"),
        nav.get("bridge_seen"),
        nav.get("reason"),
        assets.get("ready_floor_count"),
        assets.get("floor_count"),
        asset_status.get("provisional"),
        asset_status.get("source"),
    )
)
'
