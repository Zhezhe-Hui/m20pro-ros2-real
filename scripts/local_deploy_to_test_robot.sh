#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-user@10.21.31.104}"
REMOTE_WS="${2:-/home/user/m20pro_real_ros2_ws}"
EDGE_HOST="${M20PRO_EDGE_HOST:-user@10.21.31.106}"
EDGE_WS="${M20PRO_EDGE_WS:-/home/user/m20pro_real_ros2_ws}"
DEPLOY_REAL_MODE="${M20PRO_DEPLOY_REAL_MODE:-move}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
STAGE="${REMOTE_WS}.deploy.${STAMP}"
BACKUP_ROOT="${M20PRO_DEPLOY_BACKUP_DIR:-/home/user/m20pro_deploy_backups}"
BACKUP="${BACKUP_ROOT}/$(basename "${REMOTE_WS}")_${STAMP}"
REVISION="$(git -C "${ROOT_DIR}" rev-parse HEAD 2>/dev/null || echo unknown)"
if [[ -n "$(git -C "${ROOT_DIR}" status --porcelain 2>/dev/null)" ]]; then
  REVISION="${REVISION}-worktree"
fi
PREPARE_ONLY="${M20PRO_DEPLOY_PREPARE_ONLY:-0}"
WEB_HOST="${HOST#*@}"
WEB_URL="${M20PRO_WEB_URL:-http://${WEB_HOST}:8080}"

HOST_SSH_OPTIONS=()
EDGE_SSH_OPTIONS=()
if [[ -n "${M20PRO_DEPLOY_SSH_KEY:-}" ]]; then
  HOST_SSH_OPTIONS=(
    -i "${M20PRO_DEPLOY_SSH_KEY}"
    -o IdentitiesOnly=yes
  )
fi
if [[ -n "${M20PRO_DEPLOY_EDGE_SSH_KEY:-}" ]]; then
  EDGE_SSH_OPTIONS=(
    -i "${M20PRO_DEPLOY_EDGE_SSH_KEY}"
    -o IdentitiesOnly=yes
  )
fi
host_ssh() { ssh "${HOST_SSH_OPTIONS[@]}" "$@"; }
edge_ssh() { ssh "${EDGE_SSH_OPTIONS[@]}" "$@"; }
RSYNC_SSH_COMMAND="ssh"
if [[ -n "${M20PRO_DEPLOY_SSH_KEY:-}" ]]; then
  printf -v RSYNC_SSH_COMMAND 'ssh -i %q -o IdentitiesOnly=yes' \
    "${M20PRO_DEPLOY_SSH_KEY}"
fi

echo "[local_deploy_to_test_robot] local=${ROOT_DIR}"
echo "[local_deploy_to_test_robot] remote=${HOST}:${REMOTE_WS}"
echo "[local_deploy_to_test_robot] edge=${EDGE_HOST}:${EDGE_WS}"
echo "[local_deploy_to_test_robot] real_mode=${DEPLOY_REAL_MODE}"

case "${DEPLOY_REAL_MODE}" in
  move|shadow) ;;
  *)
    echo "invalid M20PRO_DEPLOY_REAL_MODE=${DEPLOY_REAL_MODE}; expected move or shadow" >&2
    exit 2
    ;;
esac

for command_name in ssh rsync curl python3; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "${command_name} is required on the upper computer." >&2
    exit 2
  fi
done

edge_was_active=1
edge_was_enabled=1
if [[ "${M20PRO_DEPLOY_SKIP_EDGE:-0}" != "1" && "${PREPARE_ONLY}" != "1" ]]; then
  edge_previous_state="$(edge_ssh "${EDGE_HOST}" '
active=0
enabled=0
systemctl is-active --quiet m20pro-edge-scan-106.service 2>/dev/null && active=1
systemctl is-enabled --quiet m20pro-edge-scan-106.service 2>/dev/null && enabled=1
printf "%s %s\n" "${active}" "${enabled}"
')"
  read -r edge_was_active edge_was_enabled <<<"${edge_previous_state}"
  "${ROOT_DIR}/scripts/local_deploy_edge_scan_to_106.sh" "${EDGE_HOST}" "${EDGE_WS}"
fi

host_ssh "${HOST}" "mkdir -p '${STAGE}' '${BACKUP_ROOT}'"

rsync -e "${RSYNC_SSH_COMMAND}" -az --delete \
  --exclude='.git/' \
  --exclude='build/' \
  --exclude='install/' \
  --exclude='log/' \
  --exclude='__pycache__/' \
  --exclude='*/__pycache__/' \
  --exclude='*.pyc' \
  --exclude='bags/' \
  --exclude='.colcon/' \
  --exclude='dist/' \
  --exclude='*.bag' \
  --exclude='*.db3' \
  --exclude='*.mcap' \
  --exclude='杂项/' \
  --exclude='dddmr_navigation/' \
  "${ROOT_DIR}/" "${HOST}:${STAGE}/"

if ! host_ssh -tt "${HOST}" "bash -lc '
if [[ "${PREPARE_ONLY}" == "1" ]]; then
  exec bash \"${STAGE}/scripts/104_prepare_staged_workspace.sh\" \
  \"${STAGE}\" \"${REVISION}\"
else
  exec bash \"${STAGE}/scripts/104_install_staged_workspace.sh\" \
  \"${STAGE}\" \"${REMOTE_WS}\" \"${BACKUP}\" \"${REVISION}\" \"${DEPLOY_REAL_MODE}\"
fi
'"; then
  if [[ "${M20PRO_DEPLOY_SKIP_EDGE:-0}" != "1" ]] && \
      { [[ "${edge_was_active}" -ne 1 ]] || [[ "${edge_was_enabled}" -ne 1 ]]; }; then
    edge_ssh -tt "${EDGE_HOST}" "bash -lc '
set -e
sudo -v
if [[ ${edge_was_active} -ne 1 ]]; then
  sudo -n systemctl stop m20pro-edge-scan-106.service
fi
if [[ ${edge_was_enabled} -ne 1 ]]; then
  sudo -n systemctl disable m20pro-edge-scan-106.service
fi
'" || true
  fi
  exit 14
fi

if [[ "${PREPARE_ONLY}" == "1" ]]; then
  echo "[local_deploy_to_test_robot] prepared stage only; cutover skipped"
  echo "[local_deploy_to_test_robot] stage=${STAGE}"
  echo "[local_deploy_to_test_robot] revision=${REVISION}"
  exit 0
fi

# The 106 publisher is a bare DDS application. Restart it after the new 104
# subscribers exist so discovery is deterministic, unless this deployment was
# explicitly scoped to 104 only.
if [[ "${M20PRO_DEPLOY_SKIP_EDGE:-0}" != "1" ]]; then
  edge_ssh -tt "${EDGE_HOST}" "bash -lc '
  set -e
  sudo -v
  sudo -n systemctl restart m20pro-edge-scan-106.service
  sudo -n systemctl is-active --quiet m20pro-edge-scan-106.service
  '"
fi

edge_ready=0
for _ in $(seq 1 90); do
  payload="$(curl --connect-timeout 1 --max-time 3 -fsS "${WEB_URL}/api/state" 2>/dev/null || true)"
  if [[ -n "${payload}" ]] && PAYLOAD="${payload}" python3 -c '
import json
import os
import sys

state = json.loads(os.environ["PAYLOAD"])
perception = state.get("perception_status") or {}
scan = perception.get("scan") or {}
ready = (
    perception.get("ready") is True
    and perception.get("mode") == "edge_scan"
    and scan.get("frame_id") == "m20pro_base_link"
    and int(scan.get("finite_ranges") or 0) >= 20
)
sys.exit(0 if ready else 1)
'; then
    edge_ready=1
    break
  fi
  sleep 1
done

if [[ "${edge_ready}" -ne 1 ]]; then
  echo "104 web is up, but 106 edge scan did not pass API acceptance at ${WEB_URL}." >&2
  echo "Previous 104 workspace is retained at ${BACKUP}." >&2
  exit 15
fi

dddmr_field_test_ready=0
dddmr_payload="$(curl --connect-timeout 1 --max-time 3 -fsS "${WEB_URL}/api/dddmr/field_test" 2>/dev/null || true)"
if [[ -n "${dddmr_payload}" ]]; then
  dddmr_summary="$(
    PAYLOAD="${dddmr_payload}" python3 -c '
import json
import os
import sys

try:
    payload = json.loads(os.environ["PAYLOAD"])
except Exception:
    print("ready=false reason=field_test_api_parse_error blocked_by=api")
    sys.exit(1)
acceptance = payload.get("acceptance") or {}
assets = payload.get("dddmr_map_assets") or {}
asset_status = assets.get("status") or {}
if isinstance(asset_status.get("parsed"), dict):
    asset_status = asset_status.get("parsed") or asset_status
blocked_by = acceptance.get("blocked_by") or []
ready = acceptance.get("ready") is True
reason = str(acceptance.get("reason") or "")
print("ready=%s reason=%s blocked_by=%s provisional=%s source=%s" % (
    "true" if ready else "false",
    reason or "unknown",
    ",".join(str(item) for item in blocked_by) if blocked_by else "-",
    "true" if asset_status.get("provisional") is True else "false",
    str(asset_status.get("source") or "-"),
))
sys.exit(0 if ready else 1)
' 2>/dev/null
  )" && dddmr_field_test_ready=1 || dddmr_field_test_ready=0
else
  dddmr_summary="ready=false reason=field_test_api_unavailable blocked_by=api"
fi

echo "[local_deploy_to_test_robot] done revision=${REVISION}"
echo "[local_deploy_to_test_robot] API=${WEB_URL} edge_scan=ready"
echo "[local_deploy_to_test_robot] DDDMR field_test ${dddmr_summary}"

if [[ "${dddmr_field_test_ready}" -ne 1 && "${M20PRO_DEPLOY_REQUIRE_DDDMR_FIELD_TEST:-0}" == "1" ]]; then
  echo "DDDMR acceptance did not pass at ${WEB_URL}/api/dddmr/field_test." >&2
  echo "Previous 104 workspace is retained at ${BACKUP}." >&2
  exit 16
fi

if [[ "${M20PRO_DEPLOY_KEEP_BACKUP:-0}" != "1" ]]; then
  host_ssh "${HOST}" "rm -rf '${BACKUP}' '${BACKUP}.systemd'"
  echo "[local_deploy_to_test_robot] removed successful-deployment backup"
else
  echo "[local_deploy_to_test_robot] kept backup=${BACKUP}"
fi
