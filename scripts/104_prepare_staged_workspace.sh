#!/usr/bin/env bash
set -eo pipefail

STAGE="${1:?staged workspace is required}"
REVISION="${2:-unknown}"
RUN_DIR="${M20PRO_DDDMR_PREVIEW_RUN_DIR:-${HOME}/.m20pro_dddmr_preview}"
LATEST_LINK="${RUN_DIR}/latest"

source_ros2_and_dddmr_runtime() {
  set +u
  source /opt/robot/scripts/setup_ros2.sh
  local runtime_setup="${M20PRO_DDDMR_RUNTIME_SETUP:-${M20PRO_DDDMR_RUNTIME_WS:-${STAGE}}/install/setup.bash}"
  if [[ -f "${runtime_setup}" ]]; then
    source "${runtime_setup}" >/dev/null 2>&1
  fi
}

if [[ ! -d "${STAGE}/src" || ! -x "${STAGE}/scripts/104_enable_autostart.sh" ]]; then
  echo "invalid staged workspace: ${STAGE}" >&2
  exit 20
fi

# A symlink install embeds absolute build paths, so it must be built only after
# the staged source has reached its final target directory.
rm -rf "${STAGE}/build" "${STAGE}/install" "${STAGE}/log"
source_ros2_and_dddmr_runtime
cd "${STAGE}"
colcon build --symlink-install
chmod +x scripts/*.sh src/m20pro_bringup/scripts/*.sh 2>/dev/null || true
test -f install/m20pro_bringup/share/m20pro_bringup/local_setup.bash
printf '%s\n' "${REVISION}" > .m20pro_deploy_revision
date --iso-8601=seconds > .m20pro_deploy_time
mkdir -p "${RUN_DIR}"
ln -sfn "${STAGE}" "${LATEST_LINK}"

echo "[104_prepare_staged_workspace] stage=${STAGE}"
echo "[104_prepare_staged_workspace] revision=${REVISION}"
echo "[104_prepare_staged_workspace] latest=${LATEST_LINK}"
echo "[104_prepare_staged_workspace] ready for cutover"
