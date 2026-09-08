#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[104_status] disk:"
df -h /home/user 2>/dev/null || df -h .

echo
echo "[104_status] web/real processes:"
ps -eo pid,args | awk '/web_dashboard|m20pro_real_full|m20pro.launch.py/ && !/awk/ {print}'

echo
echo "[104_status] listening on 8080:"
ss -ltnp 2>/dev/null | grep ':8080' || true

echo
echo "[104_status] lidar sample check:"
if command -v ros2 >/dev/null 2>&1; then
  M20PRO_LIDAR_WAIT_S="${M20PRO_LIDAR_STATUS_WAIT_S:-6}" ros2 run m20pro_bringup m20pro_lidar_guard.sh check || true
else
  echo "ros2 not found; run after the fixed 104 source -> su environment"
fi

echo
echo "[104_status] quick health:"
curl -fsS http://127.0.0.1:8080/healthz 2>/dev/null || true
echo

echo
echo "[104_status] DDDMR:"
state_json="$(curl -fsS http://127.0.0.1:8080/api/state?debug=0 2>/dev/null || true)"
if [[ -n "${state_json}" ]]; then
  summary_json="$(printf '%s' "${state_json}" | python3 "${script_dir}/navigation_backend_summary.py" || true)"
  if [[ -n "${summary_json}" && "${summary_json}" != "unavailable" ]]; then
    printf '%s\n' "${summary_json}"
    SUMMARY_JSON="${summary_json}" python3 - <<'PY' || true
import json
import os

summary = json.loads(os.environ.get("SUMMARY_JSON", "") or "{}")
field_test = summary.get("field_test") or {}
field_test_mode = summary.get("field_test_mode") or {}
acceptance = field_test.get("acceptance") or {}
gnss = summary.get("gnss") or {}
command_mux = acceptance.get("command_mux") or {}
print(
    "[104_status] field_test_mode: current=%s label=%s available=%s motion_enabled=%s acceptance=%s reason=%s"
    % (
        field_test_mode.get("current_mode") or "unknown",
        field_test_mode.get("current_label") or "unknown",
        "yes" if field_test_mode.get("available") else "no",
        "yes" if field_test_mode.get("current_motion_enabled") else "no",
        "yes" if acceptance.get("ready") else "no",
        acceptance.get("reason") or field_test.get("reason") or "",
    )
)
print(
    "[104_status] gnss: ready=%s source=%s fix=%s anchor=%s code=%s"
    % (
        "yes" if gnss.get("ready") else "no",
        gnss.get("source_topic") or "/GPS",
        gnss.get("fix_topic") or "/m20pro/gnss/fix",
        "yes" if gnss.get("anchor_usable") else "no",
        gnss.get("code") or "",
    )
)
print(
    "[104_status] command_mux: seen=%s mode=%s output_nonzero=%s stale=%s age_s=%s reason=%s"
    % (
        "yes" if command_mux.get("seen") else "no",
        command_mux.get("mode") or "",
        "yes" if command_mux.get("output_nonzero") else "no",
        "yes" if command_mux.get("stale") else "no",
        command_mux.get("age_s"),
        command_mux.get("reason") or "",
    )
)
PY
  else
    echo "unavailable"
  fi
else
  echo "unavailable"
fi

echo
echo "[104_status] DDDMR preview:"
preview_run_dir="${HOME}/.m20pro_dddmr_preview"
preview_resolver="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/104_resolve_dddmr_preview_port.sh"
preview_script="${preview_run_dir}/latest/scripts/104_status_dddmr_preview.sh"
preview_port="$("${preview_resolver}")"
if [[ -x "${preview_script}" ]]; then
  "${preview_script}" "${preview_port:-18080}" || true
else
  echo "not prepared; run scripts/104_prepare_staged_workspace.sh via local_deploy_to_test_robot.sh with M20PRO_DEPLOY_PREPARE_ONLY=1"
fi

echo
echo "[104_status] active web task:"
tasks_json="$(curl -fsS http://127.0.0.1:8080/api/tasks 2>/dev/null || true)"
TASKS_JSON="${tasks_json}" python3 - <<'PY' || true
import json
import os
import sys

try:
    text = os.environ.get("TASKS_JSON", "")
    if not text:
        sys.exit(0)
    payload = json.loads(text)
except Exception:
    sys.exit(0)
active = payload.get("active_task")
if not active:
    print("none")
else:
    print(json.dumps(active, ensure_ascii=False, separators=(",", ":")))
PY

echo
echo "[104_status] latest tcp bridge motion mode:"
search_dirs=()
if [[ -d "${HOME}/.ros/log" && -r "${HOME}/.ros/log" ]]; then
  search_dirs+=("${HOME}/.ros/log")
fi
if [[ -d /root/.ros/log && -r /root/.ros/log ]]; then
  search_dirs+=("/root/.ros/log")
fi
latest_log="$(
  {
    if [[ "${#search_dirs[@]}" -gt 0 ]]; then
      find "${search_dirs[@]}" -type f -name '*.log' -printf '%T@ %p\n' 2>/dev/null
    fi
  } \
    | sort -nr \
    | awk '{print $2}' \
    | while read -r file; do
        if grep -qE 'axis command enabled|shadow mode; axis command disabled' "$file" 2>/dev/null; then
          echo "$file"
          break
        fi
      done
)" || true
if [[ -n "${latest_log}" ]]; then
  grep -E 'axis command enabled|shadow mode; axis command disabled' "${latest_log}" | tail -1
else
  echo "unknown; start real first, or run this script after su to read root launch logs"
fi
