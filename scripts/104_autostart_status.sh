#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[104_autostart_status] unit file:"
systemctl list-unit-files m20pro-real.service --no-pager 2>/dev/null || true

echo
echo "[104_autostart_status] service state:"
systemctl --no-pager --full status m20pro-real.service 2>/dev/null || true

echo
echo "[104_autostart_status] config:"
if [[ -f /etc/default/m20pro-real ]]; then
  cat /etc/default/m20pro-real
else
  echo "/etc/default/m20pro-real not found"
fi

echo
echo "[104_autostart_status] web health:"
curl -fsS http://127.0.0.1:8080/healthz 2>/dev/null || true
echo

echo
echo "[104_autostart_status] DDDMR:"
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
    "[104_autostart_status] field_test_mode: current=%s label=%s available=%s motion_enabled=%s acceptance=%s reason=%s"
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
    "[104_autostart_status] gnss: ready=%s source=%s fix=%s anchor=%s code=%s"
    % (
        "yes" if gnss.get("ready") else "no",
        gnss.get("source_topic") or "/GPS",
        gnss.get("fix_topic") or "/m20pro/gnss/fix",
        "yes" if gnss.get("anchor_usable") else "no",
        gnss.get("code") or "",
    )
)
print(
    "[104_autostart_status] command_mux: seen=%s mode=%s output_nonzero=%s stale=%s age_s=%s reason=%s"
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
echo "[104_autostart_status] listening on 8080:"
ss -ltnp 2>/dev/null | grep ':8080' || true

echo
echo "[104_autostart_status] recent logs:"
journalctl -u m20pro-real.service -n 80 --no-pager 2>/dev/null || true
