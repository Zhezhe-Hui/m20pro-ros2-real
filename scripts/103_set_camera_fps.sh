#!/usr/bin/env bash
set -euo pipefail

TARGET_FPS="${1:-30}"
CAPTURE_FPS="${M20PRO_CAMERA_CAPTURE_FPS:-30}"
SERVICE_DIR="${M20PRO_CAMERA_SERVICE_DIR:-/opt/robot/scripts/board_resources/rtsp_service}"
CONFIG_NAMES=(
  SM_USB_107X_0.json
  SM_USB_107X_1.json
  SM_USB_107X_2.json
  SM_USB_107X_3.json
)

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root on 103." >&2
  exit 2
fi
if [[ ! "${TARGET_FPS}" =~ ^[0-9]+$ ]] || (( TARGET_FPS < 1 || TARGET_FPS > 30 )); then
  echo "Output FPS must be an integer from 1 to 30." >&2
  exit 2
fi
if [[ ! "${CAPTURE_FPS}" =~ ^[0-9]+$ ]] || (( CAPTURE_FPS < 1 || CAPTURE_FPS > 30 )); then
  echo "Capture FPS must be an integer from 1 to 30." >&2
  exit 2
fi
if (( TARGET_FPS > CAPTURE_FPS )); then
  echo "Output FPS cannot exceed capture FPS." >&2
  exit 2
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required on 103." >&2
  exit 1
fi

for name in "${CONFIG_NAMES[@]}" push_video.sh; do
  if [[ ! -f "${SERVICE_DIR}/${name}" ]]; then
    echo "Missing camera configuration: ${SERVICE_DIR}/${name}" >&2
    exit 1
  fi
done

TMP_DIR="$(mktemp -d /tmp/m20pro-camera-fps.XXXXXX)"
trap 'rm -rf -- "${TMP_DIR}"' EXIT

install_preserving_metadata() {
  local source_path="$1"
  local target_path="$2"
  install \
    -o "$(stat -c '%u' "${target_path}")" \
    -g "$(stat -c '%g' "${target_path}")" \
    -m "$(stat -c '%a' "${target_path}")" \
    "${source_path}" "${target_path}"
}

for name in "${CONFIG_NAMES[@]}"; do
  source_path="${SERVICE_DIR}/${name}"
  backup_path="${source_path}.m20pro-fps30-backup"
  output_path="${TMP_DIR}/${name}"
  if [[ ! -e "${backup_path}" ]]; then
    cp -a -- "${source_path}" "${backup_path}"
  fi
  jq --argjson capture_fps "${CAPTURE_FPS}" --argjson output_fps "${TARGET_FPS}" '
    .fps = $capture_fps
    | .pipeline_template |= (
        gsub(" ! videorate drop-only=true ! video/x-raw,framerate=[0-9]+/1"; "")
        | gsub("framerate=[0-9]+/1"; "framerate=\($capture_fps)/1")
        | if $output_fps < $capture_fps then
            sub(
              " ! videoconvert";
              " ! videorate drop-only=true ! video/x-raw,framerate=\($output_fps)/1 ! videoconvert"
            )
          else . end
      )
  ' "${source_path}" >"${output_path}"
  jq -e --argjson capture_fps "${CAPTURE_FPS}" --argjson output_fps "${TARGET_FPS}" '
    (.fps == $capture_fps)
    and (.pipeline_template | contains("framerate=\($capture_fps)/1"))
    and (
      if $output_fps < $capture_fps then
        (.pipeline_template | contains("videorate drop-only=true"))
        and (.pipeline_template | contains("framerate=\($output_fps)/1"))
      else
        (.pipeline_template | contains("videorate drop-only=true") | not)
      end
    )
  ' "${output_path}" >/dev/null
  install_preserving_metadata "${output_path}" "${source_path}"
done

push_script="${SERVICE_DIR}/push_video.sh"
push_backup="${push_script}.m20pro-fps30-backup"
push_base="${TMP_DIR}/push_video.base.sh"
push_output="${TMP_DIR}/push_video.sh"
if [[ ! -e "${push_backup}" ]]; then
  cp -a -- "${push_script}" "${push_backup}"
fi
sed -E \
  -e 's/ ! videorate drop-only=true ! video\/x-raw,framerate=[0-9]+\/1//g' \
  -e "s/framerate=[0-9]+\/1/framerate=${CAPTURE_FPS}\/1/g" \
  "${push_script}" >"${push_base}"
if (( TARGET_FPS < CAPTURE_FPS )); then
  sed \
    "s| ! jpegdec ! videoconvert| ! jpegdec ! videorate drop-only=true ! video/x-raw,framerate=${TARGET_FPS}/1 ! videoconvert|g" \
    "${push_base}" >"${push_output}"
else
  cp -- "${push_base}" "${push_output}"
fi
bash -n "${push_output}"
grep -q "framerate=${CAPTURE_FPS}/1" "${push_output}"
if (( TARGET_FPS < CAPTURE_FPS )); then
  grep -q "videorate drop-only=true ! video/x-raw,framerate=${TARGET_FPS}/1" "${push_output}"
fi
install_preserving_metadata "${push_output}" "${push_script}"

echo "Configured 103 camera capture at ${CAPTURE_FPS} fps and H.264 output at ${TARGET_FPS} fps."
echo "Camera processes were not restarted; run the vendor restart procedure to apply it."
