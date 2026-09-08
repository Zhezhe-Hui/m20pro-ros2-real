#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-${M20PRO_BUNDLE_OUTPUT_DIR:-${ROOT_DIR}/dist}}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BRANCH="$(git -C "${ROOT_DIR}" branch --show-current 2>/dev/null || echo worktree)"
SAFE_BRANCH="$(printf '%s' "${BRANCH:-worktree}" | tr -c 'A-Za-z0-9._-' '_')"
REVISION="$(git -C "${ROOT_DIR}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
if [[ -n "$(git -C "${ROOT_DIR}" status --porcelain 2>/dev/null)" ]]; then
  REVISION="${REVISION}-worktree"
fi
BASENAME="m20pro_real_ros2_ws_${SAFE_BRANCH}_${STAMP}"
BUNDLE="${OUT_DIR}/${BASENAME}.tgz"
SHA256_FILE="${BUNDLE}.sha256"
REVISION_FILE="${BUNDLE}.revision"
INSTALLER_COPY="${OUT_DIR}/104_install_source_bundle.sh"
WINDOWS_DEPLOY_COPY="${OUT_DIR}/windows_deploy_104_bundle.ps1"

for command_name in git tar sha256sum cp chmod mkdir; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "${command_name} is required to create the 104 source bundle." >&2
    exit 2
  fi
done

mkdir -p "${OUT_DIR}"

tar -C "${ROOT_DIR}" -czf "${BUNDLE}" \
  --exclude='.git/' \
  --exclude='./.git' \
  --exclude='build/' \
  --exclude='./build' \
  --exclude='./build/*' \
  --exclude='install/' \
  --exclude='./install' \
  --exclude='./install/*' \
  --exclude='log/' \
  --exclude='./log' \
  --exclude='./log/*' \
  --exclude='__pycache__/' \
  --exclude='__pycache__' \
  --exclude='*/__pycache__/' \
  --exclude='*/__pycache__' \
  --exclude='*/__pycache__/*' \
  --exclude='*.pyc' \
  --exclude='bags/' \
  --exclude='./bags' \
  --exclude='./bags/*' \
  --exclude='.colcon/' \
  --exclude='./.colcon' \
  --exclude='dist/' \
  --exclude='./dist' \
  --exclude='./dist/*' \
  --exclude='*.bag' \
  --exclude='*.db3' \
  --exclude='*.mcap' \
  --exclude='杂项/' \
  --exclude='./杂项' \
  --exclude='./杂项/*' \
  --exclude='dddmr_navigation/' \
  --exclude='./dddmr_navigation' \
  --exclude='./dddmr_navigation/*' \
  --transform "s#^\\./#${BASENAME}/#" \
  .

sha256sum "${BUNDLE}" > "${SHA256_FILE}"
printf '%s\n' "${REVISION}" > "${REVISION_FILE}"
cp "${ROOT_DIR}/scripts/104_install_source_bundle.sh" "${INSTALLER_COPY}"
chmod +x "${INSTALLER_COPY}"
cp "${ROOT_DIR}/scripts/windows_deploy_104_bundle.ps1" "${WINDOWS_DEPLOY_COPY}"

cat <<EOF
[local_make_104_source_bundle] bundle=${BUNDLE}
[local_make_104_source_bundle] sha256=${SHA256_FILE}
[local_make_104_source_bundle] revision_file=${REVISION_FILE}
[local_make_104_source_bundle] installer=${INSTALLER_COPY}
[local_make_104_source_bundle] windows_deploy=${WINDOWS_DEPLOY_COPY}
[local_make_104_source_bundle] revision=${REVISION}

Copy the bundle, sha256 file, and installer to 104, then run on 104:
  sha256sum -c $(basename "${SHA256_FILE}")
  M20PRO_BUNDLE_REVISION='${REVISION}' bash ./104_install_source_bundle.sh ./$(basename "${BUNDLE}") /home/user/m20pro_real_ros2_ws move
  /home/user/m20pro_real_ros2_ws/scripts/104_verify_dddmr_field_test_deploy.sh
  /home/user/m20pro_real_ros2_ws/scripts/104_accept_dddmr_field_test.sh
  /home/user/m20pro_real_ros2_ws/scripts/104_dddmr_field_test_report.sh

Or from Windows PowerShell with OpenSSH:
  powershell -ExecutionPolicy Bypass -File ./windows_deploy_104_bundle.ps1 -Host user@10.21.31.104
  powershell -ExecutionPolicy Bypass -File ./windows_deploy_104_bundle.ps1 -Host user@10.21.31.104 -RestartEdge106
EOF
