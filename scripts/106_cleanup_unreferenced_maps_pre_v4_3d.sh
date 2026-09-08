#!/usr/bin/env bash
set -euo pipefail

# Run on 106 only, after the paired 104/106 pre-v4-3D map archives exist.
# Default is dry-run. Set M20PRO_CONFIRM_DELETE_UNREFERENCED_106_MAPS=1 to delete.

MAP_ROOT="${M20PRO_106_MAP_ROOT:-/var/opt/robot/data/maps}"
ARCHIVE_ROOT="${M20PRO_106_MAP_ARCHIVE_ROOT:-/var/opt/robot/data/map_archives}"
CONFIRM="${M20PRO_CONFIRM_DELETE_UNREFERENCED_106_MAPS:-0}"

keep_paths=(
  "${MAP_ROOT}/F20_20260713_100749-20260713-100821"
  "${MAP_ROOT}/F20_20260713_105002-20260713-105038"
  "${MAP_ROOT}/F20_20260713_105002-20260713-130638"
  "${MAP_ROOT}/map-20260625-164234"
  "${MAP_ROOT}/test-20260709-163256"
  "${MAP_ROOT}/工地-20260713-135704"
  "${MAP_ROOT}/工地1-20260713-154222"
  "${MAP_ROOT}/工地2-20260713-154854"
  "${MAP_ROOT}/工地3_F20-20260713-155257"
  "${MAP_ROOT}/演示_F20-20260713-155735"
)

delete_paths=(
  "${MAP_ROOT}/active-20260413-193811"
  "${MAP_ROOT}/m20pro_desk_20260622_204142-20260622-204702"
  "${MAP_ROOT}/m20pro_frontend_desk_20260622_211145-20260622-211525"
  "${MAP_ROOT}/map-20260413-193811"
  "${MAP_ROOT}/map-20260414-113940"
  "${MAP_ROOT}/map-20260427-160356"
  "${MAP_ROOT}/map-20260427-161031"
  "${MAP_ROOT}/map-20260519-204926"
  "${MAP_ROOT}/map-20260520-205606"
  "${MAP_ROOT}/test_field-20260709-152308"
  "${MAP_ROOT}/working_1-20260429-162852"
)

if [[ "$(hostname)" != "host" ]]; then
  echo "[106_cleanup] warning: hostname is $(hostname); expected factory host name 'host'" >&2
fi
if [[ ! -d "${MAP_ROOT}" ]]; then
  echo "[106_cleanup] map root missing: ${MAP_ROOT}" >&2
  exit 2
fi
if ! find "${ARCHIVE_ROOT}" -maxdepth 2 -name '106_var_opt_robot_data_maps.tar.sha256' -print -quit 2>/dev/null | grep -q .; then
  echo "[106_cleanup] refusing cleanup: 106 archive sha256 not found under ${ARCHIVE_ROOT}" >&2
  exit 3
fi

active_target="$(readlink -f "${MAP_ROOT}/active" 2>/dev/null || true)"
echo "[106_cleanup] map_root=${MAP_ROOT}"
echo "[106_cleanup] archive_root=${ARCHIVE_ROOT}"
echo "[106_cleanup] active_target=${active_target:-none}"
echo "[106_cleanup] confirm=${CONFIRM}"

for keep in "${keep_paths[@]}"; do
  if [[ ! -d "${keep}" ]]; then
    echo "[106_cleanup] refusing cleanup: keep path missing: ${keep}" >&2
    exit 4
  fi
done
for delete_path in "${delete_paths[@]}"; do
  case "${delete_path}" in
    "${MAP_ROOT}"/*) ;;
    *) echo "[106_cleanup] refusing unsafe path: ${delete_path}" >&2; exit 5 ;;
  esac
  if [[ "${delete_path}" == "${MAP_ROOT}/active" ]]; then
    echo "[106_cleanup] refusing active symlink target: ${delete_path}" >&2
    exit 5
  fi
  for keep in "${keep_paths[@]}"; do
    if [[ "${delete_path}" == "${keep}" ]]; then
      echo "[106_cleanup] refusing keep path in delete list: ${delete_path}" >&2
      exit 5
    fi
  done
  if [[ -n "${active_target}" && "$(readlink -f "${delete_path}" 2>/dev/null || true)" == "${active_target}" ]]; then
    echo "[106_cleanup] refusing active target in delete list: ${delete_path}" >&2
    exit 5
  fi
done

echo "[106_cleanup] before:"
df -h "${MAP_ROOT}" || true
du -sh "${MAP_ROOT}" || true
printf '%s\n' "${delete_paths[@]}" | sed 's/^/[106_cleanup] candidate /'

if [[ "${CONFIRM}" != "1" ]]; then
  echo "[106_cleanup] dry-run only; set M20PRO_CONFIRM_DELETE_UNREFERENCED_106_MAPS=1 to delete."
  exit 0
fi

report_dir="${ARCHIVE_ROOT}/pre_v4_3d_cleanup_reports"
mkdir -p "${report_dir}"
report="${report_dir}/deleted_paths_$(date +%Y%m%d_%H%M%S).txt"
printf '%s\n' "${delete_paths[@]}" > "${report}"

for delete_path in "${delete_paths[@]}"; do
  if [[ -e "${delete_path}" ]]; then
    echo "[106_cleanup] deleting ${delete_path}"
    rm -rf -- "${delete_path}"
  else
    echo "[106_cleanup] already missing ${delete_path}"
  fi
done

echo "[106_cleanup] after:"
df -h "${MAP_ROOT}" || true
du -sh "${MAP_ROOT}" || true
ls -la "${MAP_ROOT}/active" || true
echo "[106_cleanup] report=${report}"
