#!/usr/bin/env bash
set -euo pipefail

# Remove Fast-DDS/Fast-RTPS shared-memory segments that no live process uses.
#
# SIGKILLed DDS participants (service restarts under KillMode=control-group,
# dense-chain stops, cancelled mapping runs) leak their /dev/shm segments;
# they accumulate across sessions (6.2 GB observed on 104). This restores the
# documented `M20PRO_CLEAN_STALE_FASTDDS_SHM=1` behaviour (see m20pro日志.md,
# 2026-07-07 fuser-protected cleanup): never touch a segment that any live
# process still maps or holds open.
#
# Note: `fuser -m` is NOT usable for per-file decisions on tmpfs - it lists
# every user of the whole /dev/shm mount. Detection here scans /proc maps and
# fd links for the exact segment path instead.
#
# Usage: clean_stale_fastdds_shm.sh [grace_seconds]   (default 60)

GRACE_S="${1:-60}"
now="$(date +%s)"
# One dump of every live mapping/fd instead of re-reading /proc per segment.
maps_dump="$(cat /proc/[0-9]*/maps 2>/dev/null | grep -F '/dev/shm/' || true)"
fd_dump="$(find "/proc/[0-9]"*/fd -maxdepth 1 -type l -printf '%l\n' 2>/dev/null | grep -F '/dev/shm/' || true)"

segment_in_use() {
  local seg="${1}"
  grep -qF "${seg}" <<< "${maps_dump}" && return 0
  grep -qF "${seg}" <<< "${fd_dump}" && return 0
  return 1
}

removed=0
kept=0
freed_kb=0
for seg in /dev/shm/fastrtps_* /dev/shm/fast_datasharing_*; do
  [[ -e "${seg}" ]] || continue
  if segment_in_use "${seg}"; then
    kept=$((kept + 1))
    continue
  fi
  mtime="$(stat -c %Y "${seg}" 2>/dev/null || echo "${now}")"
  if (( now - mtime < GRACE_S )); then
    kept=$((kept + 1))
    continue
  fi
  size_kb="$(du -k "${seg}" 2>/dev/null | cut -f1 || echo 0)"
  if rm -f "${seg}" 2>/dev/null; then
    removed=$((removed + 1))
    freed_kb=$((freed_kb + size_kb))
  fi
done
echo "[clean_stale_fastdds_shm] removed=${removed} kept=${kept} freed_kb=${freed_kb}"
