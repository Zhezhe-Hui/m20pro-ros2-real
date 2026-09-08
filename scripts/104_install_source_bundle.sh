#!/usr/bin/env bash
set -euo pipefail

BUNDLE="${1:?source bundle .tgz is required}"
TARGET="${2:-/home/user/m20pro_real_ros2_ws_v4}"
REAL_MODE="${3:-move}"
BACKUP_ROOT="${M20PRO_DEPLOY_BACKUP_DIR:-/home/user/m20pro_deploy_backups}"
EXTRACT_ROOT="${M20PRO_BUNDLE_EXTRACT_ROOT:-/home/user/m20pro_bundle_extracts}"
STAMP="$(date +%Y%m%d_%H%M%S)"
STAGE="${TARGET}.bundle.${STAMP}"
BACKUP="${BACKUP_ROOT}/$(basename "${TARGET}")_${STAMP}"
TMP_EXTRACT="${EXTRACT_ROOT}/extract.${STAMP}.$$"

case "${REAL_MODE}" in
  move|shadow) ;;
  *)
    echo "invalid real mode: ${REAL_MODE}; expected move or shadow" >&2
    exit 22
    ;;
esac

if [[ ! -f "${BUNDLE}" ]]; then
  echo "source bundle not found: ${BUNDLE}" >&2
  exit 20
fi
if [[ -e "${STAGE}" || -e "${BACKUP}" || -e "${BACKUP}.systemd" ]]; then
  echo "deployment path already exists; choose a new timestamp" >&2
  exit 21
fi

for command_name in tar mkdir mv chmod; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "${command_name} is required on 104." >&2
    exit 2
  fi
done

cleanup_extract() {
  if [[ -n "${TMP_EXTRACT}" && -d "${TMP_EXTRACT}" ]]; then
    rm -rf "${TMP_EXTRACT}"
  fi
}
trap cleanup_extract EXIT

mkdir -p "${TMP_EXTRACT}" "${BACKUP_ROOT}"
bundle_listing="$(tar -tzf "${BUNDLE}")"
top_level=""
while IFS= read -r entry; do
  entry="${entry#./}"
  top_level="${entry%%/*}"
  if [[ -n "${top_level}" && "${top_level}" != "." ]]; then
    break
  fi
done <<< "${bundle_listing}"
if [[ -z "${top_level}" ]]; then
  echo "source bundle has no top-level workspace directory: ${BUNDLE}" >&2
  exit 20
fi
tar -xzf "${BUNDLE}" -C "${TMP_EXTRACT}"
SOURCE_DIR="${TMP_EXTRACT}/${top_level}"
if [[ ! -d "${SOURCE_DIR}/src" || ! -f "${SOURCE_DIR}/scripts/104_install_staged_workspace.sh" ]]; then
  echo "invalid source bundle: missing src/ or scripts/104_install_staged_workspace.sh" >&2
  exit 20
fi

mv "${SOURCE_DIR}" "${STAGE}"
chmod +x "${STAGE}"/scripts/*.sh "${STAGE}"/src/m20pro_bringup/scripts/*.sh 2>/dev/null || true
REVISION="${M20PRO_BUNDLE_REVISION:-$(basename "${BUNDLE}")-bundle}"

echo "[104_install_source_bundle] stage=${STAGE}"
echo "[104_install_source_bundle] target=${TARGET}"
echo "[104_install_source_bundle] backup=${BACKUP}"
echo "[104_install_source_bundle] revision=${REVISION}"
echo "[104_install_source_bundle] real_mode=${REAL_MODE}"

bash "${STAGE}/scripts/104_install_staged_workspace.sh" \
  "${STAGE}" "${TARGET}" "${BACKUP}" "${REVISION}" "${REAL_MODE}"

echo "[104_install_source_bundle] installed; run:"
echo "  ${TARGET}/scripts/104_verify_dddmr_field_test_deploy.sh"
echo "  ${TARGET}/scripts/104_accept_dddmr_field_test.sh"
echo "  ${TARGET}/scripts/104_dddmr_field_test_report.sh"
