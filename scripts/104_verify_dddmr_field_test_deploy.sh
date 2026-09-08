#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-${M20PRO_WEB_URL:-http://127.0.0.1:8080}}"
CURL_TIMEOUT="${M20PRO_VERIFY_CURL_TIMEOUT_S:-5}"

fetch() {
  local url="$1"
  curl --connect-timeout 1 --max-time "${CURL_TIMEOUT}" -fsS "${url}"
}

fail() {
  echo "[104_verify_dddmr_field_test_deploy] FAIL $*" >&2
  exit 10
}

echo "[104_verify_dddmr_field_test_deploy] base=${BASE_URL}"

health="$(fetch "${BASE_URL}/healthz")" || fail "healthz unavailable"
html="$(fetch "${BASE_URL}/")" || fail "frontend html unavailable"
script="$(fetch "${BASE_URL}/static/dashboard.js")" || fail "frontend js unavailable"
field_test="$(fetch "${BASE_URL}/api/dddmr/field_test")" || fail "DDDMR API unavailable"
near_task="$(fetch "${BASE_URL}/api/dddmr/field_test_task?distance_m=1.0")" || fail "DDDMR near-task API unavailable"
tasks="$(fetch "${BASE_URL}/api/tasks?map_id=live_map&include_all=true")" || fail "tasks API unavailable"

grep -q 'dddmrCreateFieldTestTaskBtn' <<<"${html}" || fail "frontend html missing DDDMR near-task button"
grep -q '生成 DDDMR 近点任务' <<<"${html}" || fail "frontend html missing near-task label"
grep -q 'createDddmrFieldTestTask' <<<"${script}" || fail "frontend js missing near-task handler"
grep -q '"/api/dddmr/field_test_task"' <<<"${script}" || fail "frontend js missing near-task API"
grep -q '不会启动任务' <<<"${script}" || fail "frontend js missing no-autostart wording"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

health_json_file="${tmp_dir}/health.json"
field_test_json_file="${tmp_dir}/field_test.json"
near_task_json_file="${tmp_dir}/near_task.json"
tasks_json_file="${tmp_dir}/tasks.json"

printf '%s' "${health}" > "${health_json_file}"
printf '%s' "${field_test}" > "${field_test_json_file}"
printf '%s' "${near_task}" > "${near_task_json_file}"
printf '%s' "${tasks}" > "${tasks_json_file}"

python3 - "${health_json_file}" "${field_test_json_file}" "${near_task_json_file}" "${tasks_json_file}" <<'PY'
import json
import os
import sys
from pathlib import Path


def load_file(path: str) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except Exception as exc:
        print(f"[104_verify_dddmr_field_test_deploy] FAIL {path} is not JSON: {exc}", file=sys.stderr)
        sys.exit(11)
    if not isinstance(payload, dict):
        print(f"[104_verify_dddmr_field_test_deploy] FAIL {path} root is not object", file=sys.stderr)
        sys.exit(11)
    return payload


health = load_file(sys.argv[1])
field = load_file(sys.argv[2])
near = load_file(sys.argv[3])
tasks = load_file(sys.argv[4])

if health.get("ok") is not True:
    print("[104_verify_dddmr_field_test_deploy] FAIL healthz ok is not true", file=sys.stderr)
    sys.exit(12)

if field.get("ok") is not True or field.get("api") != "/api/dddmr/field_test":
    print("[104_verify_dddmr_field_test_deploy] FAIL DDDMR API contract missing", file=sys.stderr)
    sys.exit(13)
acceptance = field.get("acceptance")
if not isinstance(acceptance, dict) or "ready" not in acceptance or "reason" not in acceptance:
    print("[104_verify_dddmr_field_test_deploy] FAIL DDDMR acceptance missing ready/reason", file=sys.stderr)
    sys.exit(13)
if not isinstance(field.get("next_steps"), list):
    print("[104_verify_dddmr_field_test_deploy] FAIL DDDMR next_steps missing", file=sys.stderr)
    sys.exit(13)

if "ok" not in near:
    print("[104_verify_dddmr_field_test_deploy] FAIL near-task API did not return an API payload", file=sys.stderr)
    sys.exit(14)
if near.get("ok") is True:
    if near.get("api") != "/api/dddmr/field_test_task" or near.get("created") is not False:
        print("[104_verify_dddmr_field_test_deploy] FAIL near-task preview contract invalid", file=sys.stderr)
        sys.exit(14)
    near_code = str((near.get("field_test_task_gate") or {}).get("code") or "ready")
else:
    near_code = str(near.get("code") or (near.get("field_test_task_gate") or {}).get("code") or "blocked")

task_list = tasks.get("tasks")
if not isinstance(task_list, list):
    print("[104_verify_dddmr_field_test_deploy] FAIL tasks list missing", file=sys.stderr)
    sys.exit(15)
missing_gate = [
    str(item.get("id") or "")
    for item in task_list
    if isinstance(item, dict) and "field_test_task_gate" not in item
]
if missing_gate:
    print(
        "[104_verify_dddmr_field_test_deploy] FAIL tasks missing field_test_task_gate: "
        + ",".join(missing_gate[:5]),
        file=sys.stderr,
    )
    sys.exit(15)

blocked_by = acceptance.get("blocked_by") or []
print(
    "[104_verify_dddmr_field_test_deploy] field_test ready=%s reason=%s blocked_by=%s"
    % (
        "true" if acceptance.get("ready") is True else "false",
        str(acceptance.get("reason") or ""),
        ",".join(str(item) for item in blocked_by) if blocked_by else "-",
    )
)
print(
    "[104_verify_dddmr_field_test_deploy] near_task_endpoint ok=%s code=%s"
    % ("true" if near.get("ok") is True else "false", near_code)
)
print(
    "[104_verify_dddmr_field_test_deploy] tasks=%d gates_checked=%d"
    % (len(task_list), len(task_list))
)
PY

echo "[104_verify_dddmr_field_test_deploy] PASS deploy contract is present on 8080"
echo "[104_verify_dddmr_field_test_deploy] read-only: no task, mode, mapping, localization, teleop, action, or velocity command was sent"
