#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
base_url="${1:-${M20PRO_WEB_URL:-http://127.0.0.1:8080}}"
base_url="${base_url%/}"
curl_timeout_s="${M20PRO_ACCEPT_CURL_TIMEOUT_S:-3}"

echo "[104_accept_dddmr_field_test] target=${base_url}"
echo "[104_accept_dddmr_field_test] read-only acceptance; no task, teleop, gait, or localization command will be sent"

payload_source="/api/dddmr/field_test"
payload_json="$(
  curl -fsS --max-time "${curl_timeout_s}" \
    "${base_url}${payload_source}" 2>/dev/null || true
)"

if [[ -z "${payload_json}" ]]; then
  payload_source="/api/state?debug=0"
  payload_json="$(
    curl -fsS --max-time "${curl_timeout_s}" \
      "${base_url}${payload_source}" 2>/dev/null || true
  )"
fi

if [[ -z "${payload_json}" ]]; then
  echo "[104_accept_dddmr_field_test] FAIL web_state_unavailable"
  echo "  cannot read ${base_url}/api/dddmr/field_test or ${base_url}/api/state?debug=0"
  exit 10
fi

summary_json="$(
  printf '%s' "${payload_json}" | python3 "${script_dir}/navigation_backend_summary.py"
)"

if [[ "${summary_json}" == "unavailable" ]]; then
  if [[ "${payload_source}" != "/api/state?debug=0" ]]; then
    payload_source="/api/state?debug=0"
    payload_json="$(
      curl -fsS --max-time "${curl_timeout_s}" \
        "${base_url}${payload_source}" 2>/dev/null || true
    )"
    summary_json="$(
      printf '%s' "${payload_json}" | python3 "${script_dir}/navigation_backend_summary.py"
    )"
  fi
  if [[ -z "${payload_json}" || "${summary_json}" == "unavailable" ]]; then
    echo "[104_accept_dddmr_field_test] FAIL web_state_unavailable"
    echo "  cannot parse ${base_url}/api/dddmr/field_test or ${base_url}/api/state?debug=0"
    exit 10
  fi
fi

echo "[104_accept_dddmr_field_test] source=${payload_source}"
echo "[104_accept_dddmr_field_test] navigation_backend_summary=${summary_json}"

SUMMARY_JSON="${summary_json}" PAYLOAD_JSON="${payload_json}" python3 - <<'PY'
import json
import os
import sys


def _as_dict(value):
    return value if isinstance(value, dict) else {}

summary = _as_dict(json.loads(os.environ.get("SUMMARY_JSON", "") or "{}"))
payload = _as_dict(json.loads(os.environ.get("PAYLOAD_JSON", "") or "{}"))
field_test = _as_dict(summary.get("field_test"))
acceptance = _as_dict(field_test.get("acceptance"))
runtime_detail = _as_dict(summary.get("runtime"))
command_mux = _as_dict(acceptance.get("command_mux"))


def _next_steps_from_payload(payload):
    candidates = [
        payload.get("next_steps"),
        _as_dict(payload.get("field_test")).get("next_steps"),
        _as_dict(_as_dict(payload.get("navigation_backend")).get("field_test")).get("next_steps"),
    ]
    for value in candidates:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
    return []


def _print_next_steps(payload):
    steps = _next_steps_from_payload(payload)
    if not steps:
        return
    print("  next_steps:")
    for step in steps[:8]:
        print("    - %s" % step)

ready = bool(acceptance.get("ready"))
if not ready:
    reason = (
        acceptance.get("reason")
        or field_test.get("reason")
        or summary.get("reason")
        or "field_test_not_ready"
    )
    notes = "%s/%s" % (
        field_test.get("notes_ready", summary.get("notes_ready", 0)),
        field_test.get("notes_total", summary.get("notes_total", 0)),
    )
    blocked_by = acceptance.get("blocked_by") or []
    blocked_text = ",".join(str(item) for item in blocked_by) if blocked_by else "unknown"
    print("[104_accept_dddmr_field_test] FAIL %s" % reason)
    print("  field_test.ready=%s acceptance.ready=false notes=%s blocked_by=%s" % (
        bool(field_test.get("ready")),
        notes,
        blocked_text,
    ))
    if runtime_detail:
        print(
            "  runtime.backend=%s ready=%s state=%s code=%s tf_ready=%s tf_code=%s"
            % (
                runtime_detail.get("backend") or "",
                runtime_detail.get("ready"),
                runtime_detail.get("state") or "",
                runtime_detail.get("code") or "",
                runtime_detail.get("tf_ready"),
                runtime_detail.get("tf_code") or "",
            )
        )
    if command_mux:
        print(
            "  command_mux.seen=%s mode=%s output_nonzero=%s stale=%s age_s=%s reason=%s"
            % (
                command_mux.get("seen"),
                command_mux.get("mode") or "",
                command_mux.get("output_nonzero"),
                command_mux.get("stale"),
                command_mux.get("age_s"),
                command_mux.get("reason") or "",
            )
        )
    _print_next_steps(payload)
    if not acceptance.get("field_test_ready", False):
        sys.exit(11)
    if "active_task" in blocked_by:
        sys.exit(12)
    if "command_mux" in blocked_by:
        sys.exit(13)
    sys.exit(11)

backend = summary.get("backend") or ""
runtime = summary.get("runtime_backend") or field_test.get("runtime_backend") or ""
mode = field_test.get("mode") or summary.get("mode") or ""
notes = "%s/%s" % (
    field_test.get("notes_ready", summary.get("notes_ready", 0)),
    field_test.get("notes_total", summary.get("notes_total", 0)),
)
gnss = _as_dict(summary.get("gnss"))
edge = _as_dict(summary.get("edge_cloud"))
map_3d = _as_dict(summary.get("map_3d"))
assets = _as_dict(summary.get("assets"))
asset_status = _as_dict(assets.get("status"))
print("[104_accept_dddmr_field_test] PASS field_test_ready")
print(
    "  backend=%s mode=%s runtime=%s notes=%s acceptance=%s"
    % (backend, mode, runtime, notes, acceptance.get("reason") or "")
)
print(
    "  edge_cloud.ready=%s finite_points=%s frame=%s"
    % (edge.get("ready"), edge.get("finite_points"), edge.get("frame_id") or "")
)
if runtime_detail:
    print(
        "  runtime.ready=%s state=%s code=%s tf_ready=%s tf_code=%s"
        % (
            runtime_detail.get("ready"),
            runtime_detail.get("state") or "",
            runtime_detail.get("code") or "",
            runtime_detail.get("tf_ready"),
            runtime_detail.get("tf_code") or "",
        )
    )
print(
    "  map_3d.ready=%s mapcloud=%s mapground=%s"
    % (map_3d.get("ready"), map_3d.get("mapcloud_points"), map_3d.get("mapground_points"))
)
print(
    "  assets.ready_floors=%s/%s provisional=%s source=%s code=%s"
    % (
        assets.get("ready_floor_count"),
        assets.get("floor_count"),
        asset_status.get("provisional"),
        asset_status.get("source") or "",
        asset_status.get("code") or "",
    )
)
print(
    "  gnss.ready=%s anchor=%s satellites=%s hdop=%s"
    % (
        gnss.get("ready"),
        gnss.get("anchor_usable"),
        gnss.get("num_satellites"),
        gnss.get("hdop"),
    )
)
if command_mux:
    print(
        "  command_mux.seen=%s mode=%s output_nonzero=%s stale=%s age_s=%s reason=%s"
        % (
            command_mux.get("seen"),
            command_mux.get("mode") or "",
            command_mux.get("output_nonzero"),
            command_mux.get("stale"),
            command_mux.get("age_s"),
            command_mux.get("reason") or "",
        )
    )
_print_next_steps(payload)
PY
