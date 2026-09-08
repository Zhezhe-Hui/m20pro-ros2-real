#!/usr/bin/env bash
set -euo pipefail

# Compatibility helper for desktop-only Humble Lightning-LM experiments.  The
# 104 target is Foxy/RK3588 ARM and must use prepare_dddmr_foxy_runtime.sh on
# the robot.
echo "[prepare_lightning_humble_runtime] desktop reference only; do not deploy its x86 install/ to 104" >&2
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
M20PRO_DDDMR_RUNTIME_DISTRO=humble \
M20PRO_LIGHTNING_TARGET_ARCH="$(uname -m)" \
M20PRO_DDDMR_RUNTIME_WS="${M20PRO_DDDMR_RUNTIME_WS:-/home/user/m20pro_dddmr_humble_ws}" \
  exec "${ROOT_DIR}/scripts/prepare_dddmr_foxy_runtime.sh" "$@"
