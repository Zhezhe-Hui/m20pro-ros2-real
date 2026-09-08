#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="$("${script_dir}/104_resolve_dddmr_preview_port.sh" "${M20PRO_DDDMR_PREVIEW_PORT:-${1:-}}")"
RUN_DIR="${M20PRO_DDDMR_PREVIEW_RUN_DIR:-${HOME}/.m20pro_dddmr_preview}"
PID_FILE="${RUN_DIR}/preview_${PORT}.pid"
LOG_FILE="${RUN_DIR}/preview_${PORT}.log"
URL="http://127.0.0.1:${PORT}"

echo "[104_status_dddmr_preview] port=${PORT}"
if [[ -f "${PID_FILE}" ]]; then
  pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
    echo "pid=${pid} running=true"
  else
    echo "pid=${pid:-} running=false"
  fi
else
  echo "pid= running=false"
fi

echo
echo "[104_status_dddmr_preview] health:"
curl --connect-timeout 1 --max-time 2 -fsS "${URL}/healthz" 2>/dev/null || true
echo

echo
echo "[104_status_dddmr_preview] navigation backend:"
curl --connect-timeout 1 --max-time 3 -fsS "${URL}/api/state" 2>/dev/null \
  | python3 "${script_dir}/navigation_backend_summary.py" \
  | python3 -c '
import json
import sys

try:
    state = json.load(sys.stdin)
except Exception:
    sys.exit(0)
nav = state.get("field_test") or {}
acceptance = nav.get("acceptance") or {}
command_mux = acceptance.get("command_mux") or {}
assets = state.get("assets") or {}
asset_status = assets.get("status") or {}
gnss = state.get("gnss") or {}
edge_cloud = state.get("edge_cloud") or {}
map_3d = state.get("map_3d") or {}
print(
    "backend=%s bridge_seen=%s ready=%s reason=%s field_test=%s assets=%s/%s provisional=%s source=%s gnss=%s edge=%s map3d=%s command_mux_seen=%s stale=%s age_s=%s"
    % (
        state.get("backend"),
        state.get("bridge_seen"),
        state.get("ready"),
        state.get("reason"),
        nav.get("ready"),
        assets.get("ready_floor_count"),
        assets.get("floor_count"),
        asset_status.get("provisional"),
        asset_status.get("source"),
        gnss.get("ready"),
        edge_cloud.get("ready"),
        map_3d.get("ready"),
        command_mux.get("seen"),
        command_mux.get("stale"),
        command_mux.get("age_s"),
    )
)
'

echo
echo "[104_status_dddmr_preview] processes:"
ps -eo pid,ppid,args | awk '/m20pro_dddmr_preview|104_start_dddmr_preview|m20pro_web_dashboard_preview/ && !/awk/ {print}' || true

echo
echo "[104_status_dddmr_preview] recent log:"
tail -n 40 "${LOG_FILE}" 2>/dev/null || true
