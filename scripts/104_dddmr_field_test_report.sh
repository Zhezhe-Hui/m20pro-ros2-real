#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
base_url="${1:-${M20PRO_WEB_URL:-http://127.0.0.1:8080}}"
base_url="${base_url%/}"
curl_timeout_s="${M20PRO_REPORT_CURL_TIMEOUT_S:-3}"

echo "[104_dddmr_field_test_report] target=${base_url}"
echo "[104_dddmr_field_test_report] read-only report; no task, teleop, gait, localization, mode-switch, mapping, or velocity command will be sent"

fetch_json() {
  local path="$1"
  curl -fsS --max-time "${curl_timeout_s}" "${base_url}${path}" 2>/dev/null || true
}

field_json="$(fetch_json "/api/dddmr/field_test")"
state_json="$(fetch_json "/api/state?debug=0")"
tasks_json="$(fetch_json "/api/tasks")"
annotations_json="$(fetch_json "/api/annotations?map_id=live_map")"
health_json="$(fetch_json "/healthz")"

summary_source="${field_json}"
if [[ -z "${summary_source}" ]]; then
  summary_source="${state_json}"
fi
if [[ -z "${summary_source}" ]]; then
  echo "[104_dddmr_field_test_report] FAIL web_state_unavailable"
  echo "  cannot read ${base_url}/api/dddmr/field_test or ${base_url}/api/state?debug=0"
  exit 10
fi

summary_json="$(
  printf '%s' "${summary_source}" | python3 "${script_dir}/navigation_backend_summary.py"
)"
if [[ -z "${summary_json}" || "${summary_json}" == "unavailable" ]]; then
  echo "[104_dddmr_field_test_report] FAIL web_state_unparseable"
  echo "  cannot parse navigation_backend from ${base_url}"
  exit 10
fi

echo "[104_dddmr_field_test_report] health=${health_json:-unavailable}"
echo "[104_dddmr_field_test_report] navigation_backend_summary=${summary_json}"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

summary_json_file="${tmp_dir}/summary.json"
field_json_file="${tmp_dir}/field.json"
state_json_file="${tmp_dir}/state.json"
tasks_json_file="${tmp_dir}/tasks.json"
annotations_json_file="${tmp_dir}/annotations.json"

printf '%s' "${summary_json}" > "${summary_json_file}"
printf '%s' "${field_json}" > "${field_json_file}"
printf '%s' "${state_json}" > "${state_json_file}"
printf '%s' "${tasks_json}" > "${tasks_json_file}"
printf '%s' "${annotations_json}" > "${annotations_json_file}"

python3 - "${summary_json_file}" "${field_json_file}" "${state_json_file}" "${tasks_json_file}" "${annotations_json_file}" <<'PY'
import json
import math
import os
import sys
from pathlib import Path


def _load(path):
    text = Path(path).read_text(encoding="utf-8")
    if not text:
        return {}
    try:
        value = json.loads(text)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _short(value, limit=110):
    text = str(value or "").replace("\n", " ").strip()
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


summary = _load(sys.argv[1])
field_payload = _load(sys.argv[2])
state_payload = _load(sys.argv[3])
tasks_payload = _load(sys.argv[4])
annotations_payload = _load(sys.argv[5])
field_test = _as_dict(summary.get("field_test"))
acceptance = _as_dict(field_test.get("acceptance"))
runtime = _as_dict(summary.get("runtime"))
edge = _as_dict(summary.get("edge_cloud"))
map_3d = _as_dict(summary.get("map_3d"))
assets = _as_dict(summary.get("assets"))
asset_status = _as_dict(assets.get("status"))
gnss = _as_dict(summary.get("gnss"))
command_mux = _as_dict(acceptance.get("command_mux"))
selected_map_status = _as_dict(state_payload.get("selected_map_status"))
localization_status = _as_dict(state_payload.get("localization_status"))
map_relocalization_required = state_payload.get("map_relocalization_required")
map_relocalization_required = (
    map_relocalization_required
    if isinstance(map_relocalization_required, dict)
    else None
)
pose = _as_dict(state_payload.get("pose"))


def _finite_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _xy_distance(a, b):
    ax = _finite_float(_as_dict(a).get("x"))
    ay = _finite_float(_as_dict(a).get("y"))
    bx = _finite_float(_as_dict(b).get("x"))
    by = _finite_float(_as_dict(b).get("y"))
    if ax is None or ay is None or bx is None or by is None:
        return None
    return math.hypot(ax - bx, ay - by)


def _pose_text(value):
    item = _as_dict(value)
    x = _finite_float(item.get("x"))
    y = _finite_float(item.get("y"))
    z = _finite_float(item.get("z"))
    yaw = _finite_float(item.get("yaw"))
    if x is None or y is None:
        return "unavailable"
    parts = ["x=%.2f" % x, "y=%.2f" % y]
    if z is not None:
        parts.append("z=%.2f" % z)
    if yaw is not None:
        parts.append("yaw=%.2f" % yaw)
    return " ".join(parts)

print("[104_dddmr_field_test_report] mode:")
print(
    "  backend=%s mode=%s runtime=%s ready=%s reason=%s"
    % (
        summary.get("backend") or "",
        field_test.get("mode") or summary.get("mode") or "",
        field_test.get("runtime_backend") or summary.get("runtime_backend") or "",
        acceptance.get("ready"),
        acceptance.get("reason") or field_test.get("reason") or summary.get("reason") or "",
    )
)
blocked_by = acceptance.get("blocked_by") or []
print("  blocked_by=%s" % (",".join(str(item) for item in blocked_by) if blocked_by else "-"))
print(
    "  runtime.ready=%s state=%s code=%s tf_ready=%s max_goal_distance_m=%s"
    % (
        runtime.get("ready"),
        runtime.get("state") or "",
        runtime.get("code") or "",
        runtime.get("tf_ready"),
        runtime.get("max_goal_distance_m"),
    )
)
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
print("[104_dddmr_field_test_report] map/localization:")
print(
    "  selected_map_id=%s effective_map_id=%s working_map_id=%s floor=%s reported_floor=%s"
    % (
        state_payload.get("selected_map_id") or "",
        state_payload.get("effective_map_id") or "",
        state_payload.get("working_map_id") or "",
        state_payload.get("floor") or "",
        state_payload.get("reported_floor") or "",
    )
)
print(
    "  selected_map_status.ready=%s code=%s message=%s"
    % (
        selected_map_status.get("ready"),
        selected_map_status.get("code") or "",
        _short(selected_map_status.get("message"), 140),
    )
)
if map_relocalization_required:
    print(
        "  map_relocalization_required=true map_id=%s reason=%s message=%s"
        % (
            map_relocalization_required.get("map_id") or "",
            map_relocalization_required.get("reason") or "",
            _short(map_relocalization_required.get("message"), 140),
        )
    )
else:
    print("  map_relocalization_required=false")
print(
    "  localization.confirmed=%s code=%s message=%s"
    % (
        localization_status.get("confirmed"),
        localization_status.get("code") or "",
        _short(localization_status.get("message"), 140),
    )
)
print(
    "  pose_fresh=%s pose_age_sec=%s pose_timeout_s=%s current_pose=%s"
    % (
        state_payload.get("pose_fresh"),
        state_payload.get("pose_age_sec"),
        state_payload.get("pose_timeout_s"),
        _pose_text(pose),
    )
)
print(
    "  edge_cloud.ready=%s finite_points=%s frame=%s code=%s"
    % (
        edge.get("ready"),
        edge.get("finite_points"),
        edge.get("frame_id") or "",
        edge.get("code") or "",
    )
)
print(
    "  map_3d.ready=%s mapcloud=%s mapground=%s assets.provisional=%s source=%s code=%s"
    % (
        map_3d.get("ready"),
        map_3d.get("mapcloud_points"),
        map_3d.get("mapground_points"),
        asset_status.get("provisional"),
        asset_status.get("source") or "",
        asset_status.get("code") or "",
    )
)
print(
    "  gnss.ready=%s anchor=%s sats=%s hdop=%s source=%s fix=%s"
    % (
        gnss.get("ready"),
        gnss.get("anchor_usable"),
        gnss.get("num_satellites"),
        gnss.get("hdop"),
        gnss.get("source_topic") or "/GPS",
        gnss.get("fix_topic") or "/m20pro/gnss/fix",
    )
)

steps = field_payload.get("next_steps")
if not isinstance(steps, list):
    steps = _as_dict(field_payload.get("field_test")).get("next_steps")
if not isinstance(steps, list):
    steps = []
if steps:
    print("[104_dddmr_field_test_report] next_steps:")
    for step in steps[:8]:
        print("  - %s" % _short(step, 160))

tasks = tasks_payload.get("tasks")
if not isinstance(tasks, list):
    tasks = []
active_task = tasks_payload.get("active_task") or state_payload.get("active_task")
print("[104_dddmr_field_test_report] tasks:")
if active_task:
    print("  active=%s" % json.dumps(active_task, ensure_ascii=False, separators=(",", ":")))
else:
    print("  active=none")
field_gates = []
for task in tasks:
    if not isinstance(task, dict):
        continue
    gate = task.get("field_test_task_gate")
    if isinstance(gate, dict) and gate.get("applies"):
        field_gates.append((task, gate))
ready_count = sum(1 for _task, gate in field_gates if gate.get("ready"))
print(
    "  field_test_task_gate applicable=%s ready=%s blocked=%s total_tasks=%s"
    % (len(field_gates), ready_count, len(field_gates) - ready_count, len(tasks))
)
if not tasks:
    print("  no tasks returned by /api/tasks")
elif not field_gates:
    print("  no DDDMR field_proxy task gates apply in current mode")
else:
    field_gates_sorted = sorted(
        field_gates,
        key=lambda item: (
            _finite_float(item[1].get("distance_m")) is None,
            _finite_float(item[1].get("distance_m")) or float("inf"),
            str(item[0].get("id") or ""),
        ),
    )
    for task, gate in field_gates_sorted[:12]:
        print(
            "  - id=%s name=%s status=%s waypoints=%s gate.ready=%s code=%s distance=%s max=%s message=%s"
            % (
                task.get("id") or "",
                _short(task.get("name") or task.get("task_name") or "", 32),
                task.get("status") or "",
                len(task.get("annotation_ids") or []),
                gate.get("ready"),
                gate.get("code") or "",
                gate.get("distance_m"),
                gate.get("max_goal_distance_m"),
                _short(gate.get("message"), 120),
            )
        )
    if len(field_gates_sorted) > 12:
        print("  ... %s more gated tasks omitted" % (len(field_gates_sorted) - 12))

annotations = annotations_payload.get("annotations")
if not isinstance(annotations, list):
    annotations = []
same_map = str(state_payload.get("effective_map_id") or "")
near = []
for item in annotations:
    if not isinstance(item, dict):
        continue
    item_map = str(item.get("map_id") or "")
    if same_map and item_map and item_map != same_map:
        continue
    distance = _xy_distance(pose, item.get("pose"))
    if distance is None:
        continue
    near.append((distance, item))
near.sort(key=lambda pair: (pair[0], str(pair[1].get("id") or "")))
print("[104_dddmr_field_test_report] nearest_annotations:")
if not annotations:
    print("  no annotations returned by /api/annotations?map_id=live_map")
elif not pose:
    print("  current pose unavailable; cannot rank annotations")
elif not near:
    print("  no same-map annotations with finite pose distance")
else:
    max_goal = _finite_float(runtime.get("max_goal_distance_m"))
    for distance, item in near[:8]:
        within = None if max_goal is None else distance <= max_goal + 0.05
        print(
            "  - id=%s label=%s floor=%s type=%s distance=%.2f within_field_limit=%s pose=%s"
            % (
                item.get("id") or "",
                _short(item.get("label") or "", 32),
                item.get("floor") or "",
                item.get("type") or "",
                distance,
                within,
                _pose_text(item.get("pose")),
            )
        )
    if len(near) > 8:
        print("  ... %s more annotations omitted" % (len(near) - 8))

print(
    "[104_dddmr_field_test_report] result acceptance_ready=%s task_gate_ready=%s/%s"
    % (acceptance.get("ready"), ready_count, len(field_gates))
)
PY
