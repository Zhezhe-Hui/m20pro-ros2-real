#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-user@10.21.31.106}"
REMOTE_WS="${2:-/home/user/m20pro_real_ros2_ws}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
STAGE="${REMOTE_WS}.edge_stage.${STAMP}"

EDGE_SSH_OPTIONS=()
if [[ -n "${M20PRO_DEPLOY_EDGE_SSH_KEY:-${M20PRO_DEPLOY_SSH_KEY:-}}" ]]; then
  EDGE_KEY="${M20PRO_DEPLOY_EDGE_SSH_KEY:-${M20PRO_DEPLOY_SSH_KEY}}"
  EDGE_SSH_OPTIONS=(
    -i "${EDGE_KEY}"
    -o IdentitiesOnly=yes
  )
fi
edge_ssh() { ssh "${EDGE_SSH_OPTIONS[@]}" "$@"; }
EDGE_RSYNC_SSH_COMMAND="ssh"
if [[ -n "${M20PRO_DEPLOY_EDGE_SSH_KEY:-${M20PRO_DEPLOY_SSH_KEY:-}}" ]]; then
  EDGE_KEY="${M20PRO_DEPLOY_EDGE_SSH_KEY:-${M20PRO_DEPLOY_SSH_KEY}}"
  printf -v EDGE_RSYNC_SSH_COMMAND 'ssh -i %q -o IdentitiesOnly=yes' "${EDGE_KEY}"
fi

cleanup_stage() {
  edge_ssh "${HOST}" "rm -rf '${STAGE}'" >/dev/null 2>&1 || true
}
trap cleanup_stage EXIT

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required on the upper computer." >&2
  exit 2
fi

echo "[local_deploy_edge_scan_to_106] remote=${HOST}:${REMOTE_WS}"

edge_ssh "${HOST}" "rm -rf '${STAGE}'; mkdir -p \
  '${STAGE}/scripts' \
  '${STAGE}/tools/edge_scan_feasibility' \
  '${STAGE}/src/m20pro_bringup/config' \
  '${STAGE}/src/m20pro_navigation/m20pro_navigation'"

rsync -e "${EDGE_RSYNC_SSH_COMMAND}" -az --delete --no-owner --no-group \
  --exclude='__pycache__/' \
  "${ROOT_DIR}/tools/edge_scan_feasibility/" \
  "${HOST}:${STAGE}/tools/edge_scan_feasibility/"
rsync -e "${EDGE_RSYNC_SSH_COMMAND}" -az --no-owner --no-group \
  "${ROOT_DIR}/scripts/106_enable_edge_scan_service.sh" \
  "${ROOT_DIR}/scripts/m20pro_field_profile.py" \
  "${HOST}:${STAGE}/scripts/"
rsync -e "${EDGE_RSYNC_SSH_COMMAND}" -az --no-owner --no-group \
  "${ROOT_DIR}/src/m20pro_bringup/config/m20pro_field_profile.yaml" \
  "${HOST}:${STAGE}/src/m20pro_bringup/config/"
rsync -e "${EDGE_RSYNC_SSH_COMMAND}" -az --no-owner --no-group \
  "${ROOT_DIR}/src/m20pro_navigation/m20pro_navigation/field_profile_contract.py" \
  "${ROOT_DIR}/src/m20pro_navigation/m20pro_navigation/__init__.py" \
  "${HOST}:${STAGE}/src/m20pro_navigation/m20pro_navigation/"

edge_ssh -tt "${HOST}" "bash -lc '
set -e
sudo -v
sudo -n install -d -m 0755 "${REMOTE_WS}/scripts" \
  "${REMOTE_WS}/tools/edge_scan_feasibility" \
  "${REMOTE_WS}/src/m20pro_bringup/config" \
  "${REMOTE_WS}/src/m20pro_navigation/m20pro_navigation"
sudo -n rsync -a --delete \
  "${STAGE}/tools/edge_scan_feasibility/" \
  "${REMOTE_WS}/tools/edge_scan_feasibility/"
sudo -n install -m 0755 \
  "${STAGE}/scripts/106_enable_edge_scan_service.sh" \
  "${REMOTE_WS}/scripts/106_enable_edge_scan_service.sh"
sudo -n install -m 0755 \
  "${STAGE}/scripts/m20pro_field_profile.py" \
  "${REMOTE_WS}/scripts/m20pro_field_profile.py"
sudo -n install -m 0644 \
  "${STAGE}/src/m20pro_bringup/config/m20pro_field_profile.yaml" \
  "${REMOTE_WS}/src/m20pro_bringup/config/m20pro_field_profile.yaml"
sudo -n install -m 0644 \
  "${STAGE}/src/m20pro_navigation/m20pro_navigation/field_profile_contract.py" \
  "${STAGE}/src/m20pro_navigation/m20pro_navigation/__init__.py" \
  "${REMOTE_WS}/src/m20pro_navigation/m20pro_navigation/"
sudo -n chown -R \"\$(id -u):\$(id -g)\" \
  "${REMOTE_WS}/scripts/106_enable_edge_scan_service.sh" \
  "${REMOTE_WS}/scripts/m20pro_field_profile.py" \
  "${REMOTE_WS}/src/m20pro_bringup/config/m20pro_field_profile.yaml" \
  "${REMOTE_WS}/src/m20pro_navigation/m20pro_navigation" \
  "${REMOTE_WS}/tools/edge_scan_feasibility"
sudo -n env M20PRO_WS="${REMOTE_WS}" \
  bash "${REMOTE_WS}/scripts/106_enable_edge_scan_service.sh"
sudo -n systemctl is-enabled --quiet m20pro-edge-scan-106.service
sudo -n systemctl is-active --quiet m20pro-edge-scan-106.service
'"

trap - EXIT
cleanup_stage
echo "[local_deploy_edge_scan_to_106] edge scan is installed, enabled, and active"
