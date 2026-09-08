#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE=""
RUN_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      CONFIG_FILE="${2:-}"
      shift 2
      ;;
    --run-dir)
      RUN_DIR="${2:-}"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "${CONFIG_FILE}" || ! -f "${CONFIG_FILE}" ]]; then
  echo "Lightning-LM config file not found: ${CONFIG_FILE}" >&2
  exit 21
fi
if [[ -z "${RUN_DIR}" ]]; then
  echo "Lightning-LM run directory is required" >&2
  exit 22
fi
if ! command -v ros2 >/dev/null 2>&1; then
  echo "ros2 is not available in the current runtime" >&2
  exit 23
fi

# thirdparty_install lives at the workspace root, not inside install/.
# Derive the root from this script (src/m20pro_bringup/scripts -> root).
# Do not gate on `ros2 pkg prefix`: the launch env may not have the v4
# install sourced, and run_slam_online needs libpango/glog from these
# directories regardless.
# ros2 run resolves this script through the install symlink, so resolve the
# real source path first or the ../.. walk lands in install/ instead of the
# workspace root.
LIGHTNING_WS="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../.." && pwd)"
for lib_dir in \
  "${LIGHTNING_WS}/thirdparty_install/lib" \
  "${LIGHTNING_WS}/thirdparty_install/lib64" \
  "${LIGHTNING_WS}/build_pangolin" \
  "${LIGHTNING_WS}/build_glog"; do
  if [[ -d "${lib_dir}" ]]; then
    case ":${LD_LIBRARY_PATH:-}:" in
      *":${lib_dir}:"*) ;;
      *) export LD_LIBRARY_PATH="${lib_dir}:${LD_LIBRARY_PATH:-}" ;;
    esac
  fi
done

mkdir -p "${RUN_DIR}/data" "${RUN_DIR}/logs"
cd "${RUN_DIR}"

exec ros2 run lightning run_slam_online --config "${CONFIG_FILE}"
