#!/usr/bin/env bash
set -euo pipefail

explicit_port="${1:-}"
default_port="${M20PRO_DDDMR_PREVIEW_DEFAULT_PORT:-18080}"
run_dir="${M20PRO_DDDMR_PREVIEW_RUN_DIR:-${HOME}/.m20pro_dddmr_preview}"

resolve_from_pid_file() {
  local pid_file="$1"
  local pid port

  port="${pid_file##*/preview_}"
  port="${port%.pid}"
  pid="$(cat "${pid_file}" 2>/dev/null || true)"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
    printf '%s\n' "${port}"
    return 0
  fi
  return 1
}

resolve_from_listening_socket() {
  local pid port

  if ! command -v ps >/dev/null 2>&1 || ! command -v ss >/dev/null 2>&1; then
    return 1
  fi

  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    if ! ps -p "${pid}" -o args= 2>/dev/null \
      | grep -Eq 'm20pro_dddmr_preview\.launch\.py|104_start_dddmr_preview|m20pro_web_dashboard_preview'; then
      continue
    fi

    port="$(
      ss -ltnp 2>/dev/null \
        | awk -v pid="${pid}" '
            index($0, "pid=" pid ",") {
              if (match($4, /:([0-9]+)$/, m)) {
                print m[1]
                exit
              }
            }
          '
    )"
    if [[ -n "${port}" ]]; then
      printf '%s\n' "${port}"
      return 0
    fi
  done < <(ps -eo pid,args | awk '/m20pro_dddmr_preview\.launch\.py|104_start_dddmr_preview|m20pro_web_dashboard_preview/ && !/awk/ {print $1}')

  return 1
}

if [[ -n "${explicit_port}" ]]; then
  printf '%s\n' "${explicit_port}"
  exit 0
fi

if [[ -n "${M20PRO_DDDMR_PREVIEW_PORT:-}" ]]; then
  printf '%s\n' "${M20PRO_DDDMR_PREVIEW_PORT}"
  exit 0
fi

if [[ -d "${run_dir}" ]]; then
  while IFS= read -r pid_file; do
    [[ -n "${pid_file}" ]] || continue
    if resolve_from_pid_file "${pid_file}"; then
      exit 0
    fi
  done < <(find "${run_dir}" -maxdepth 1 -type f -name 'preview_*.pid' -printf '%T@ %p\n' 2>/dev/null | sort -nr | awk '{print $2}')
fi

if resolve_from_listening_socket; then
  exit 0
fi

printf '%s\n' "${default_port}"
