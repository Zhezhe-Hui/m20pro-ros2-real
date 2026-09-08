#!/usr/bin/env python3
"""Runtime checks for the 104-side Lightning-LM mapping control wrapper."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "104_dddmr_mapping_control.sh"


def _write_fake_ros2(fakebin: Path) -> None:
    fakebin.mkdir(parents=True, exist_ok=True)
    ros2 = fakebin / "ros2"
    ros2.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "service" && "${2:-}" == "call" ]]; then
  if [[ "${3:-}" == "/lightning/save_map" ]]; then
    if [[ "${FAKE_LIGHTNING_SAVE_FAIL:-0}" == "1" ]]; then
      echo "save service unavailable" >&2
      exit 1
    fi
    if [[ "${FAKE_LIGHTNING_CREATE_SAVE_DIR:-0}" == "1" ]]; then
      all_args="$*"
      map_id=""
      if [[ "${all_args}" =~ map_id:[[:space:]]\\'([^\\']+)\\' ]]; then
        map_id="${BASH_REMATCH[1]}"
      fi
      if [[ -z "${map_id}" ]]; then
        map_id="fake_lightning_map"
      fi
      mkdir -p "${M20PRO_LIGHTNING_MAPPING_WORK_DIR}/data/${map_id}"
      if [[ "${FAKE_LIGHTNING_WRITE_GLOBAL:-0}" == "1" ]]; then
        printf 'global\\n' > "${M20PRO_LIGHTNING_MAPPING_WORK_DIR}/data/${map_id}/global.pcd"
      fi
    fi
    if [[ "${FAKE_LIGHTNING_FOXY_OUTPUT:-0}" == "1" ]]; then
      echo "response=0"
    else
      echo "response: 0"
    fi
    exit 0
  fi
  if [[ "${3:-}" == "/lightning/save_path" ]]; then
    all_args="$*"
    path_file=""
    if [[ "${all_args}" =~ file_path:[[:space:]]\\'([^\\']+)\\' ]]; then
      path_file="${BASH_REMATCH[1]}"
    fi
    if [[ -n "${path_file}" ]]; then
      mkdir -p "$(dirname "${path_file}")"
      printf 'timestamp px py pz qx qy qz qw\\n1.0 0 0 0 0 0 0 1\\n' > "${path_file}"
    fi
    if [[ "${FAKE_LIGHTNING_FOXY_OUTPUT:-0}" == "1" ]]; then
      echo "success=True, message='Path saved successfully'"
    else
      echo "success: true"
    fi
    exit 0
  fi
fi
if [[ "${1:-}" == "run" && "${2:-}" == "m20pro_bringup" && "${3:-}" == "lightning_pcd_asset_adapter" ]]; then
  map=""
  ground=""
  poses=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --map) map="${2:-}"; shift 2 ;;
      --ground) ground="${2:-}"; shift 2 ;;
      --poses) poses="${2:-}"; shift 2 ;;
      *) shift ;;
    esac
  done
  printf 'map\\n' > "${map}"
  printf 'ground\\n' > "${ground}"
  printf 'poses\\n' > "${poses}"
  echo "map_points=1"
  echo "ground_points=1"
  echo "poses=1"
  exit 0
fi
if [[ "${1:-}" == "service" && "${2:-}" == "list" ]]; then
  if [[ "${FAKE_LIGHTNING_SAVE_SERVICE:-0}" == "1" ]]; then
    echo "/lightning/save_map"
  fi
  exit 0
fi
if [[ "${1:-}" == "pkg" && "${2:-}" == "prefix" ]]; then
  if [[ "${FAKE_LIGHTNING_PKG_PREFIX:-1}" != "1" ]]; then
    exit 1
  fi
  if [[ "${3:-}" == "m20pro_bringup" ]]; then
    echo "${FAKE_M20PRO_PREFIX}"
  else
    echo "/tmp/fake_lightning_prefix"
  fi
  exit 0
fi
echo "fake ros2: unsupported $*" >&2
exit 2
""",
        encoding="utf-8",
    )
    ros2.chmod(0o755)


def _base_env(root: Path, fakebin: Path) -> dict:
    env = dict(os.environ)
    env.pop("ROS_DISTRO", None)
    fake_prefix = root / "workspace" / "install"
    (fake_prefix / "share" / "m20pro_bringup" / "config").mkdir(
        parents=True, exist_ok=True
    )
    (fake_prefix / "share" / "m20pro_bringup" / "config" / "lightning_m20pro_raw_mapping.yaml").write_text(
        "common:\n  lidar_topic: /m20pro/lidar_points_dense_ros\n",
        encoding="utf-8",
    )
    resource_dir = fake_prefix / "share" / "ament_index" / "resource_index" / "packages"
    resource_dir.mkdir(parents=True, exist_ok=True)
    (resource_dir / "lightning").write_text("", encoding="utf-8")
    (resource_dir / "m20pro_bringup").write_text("", encoding="utf-8")
    env.update(
        {
            "PATH": "%s:%s" % (fakebin, env.get("PATH", "")),
            "M20PRO_WS": str(root / "workspace"),
            # Keep the sandbox hermetic on hosts where the default runtime
            # workspace (/home/user/m20pro_real_ros2_ws_v4) really exists and
            # would leak the real lightning package into the "missing
            # workspace" scenario.
            "M20PRO_DDDMR_RUNTIME_WS": str(root / "missing_runtime_ws"),
            "M20PRO_DDDMR_MAPPING_RUN_DIR": str(root / "run"),
            "M20PRO_DDDMR_MAPPING_ARCHIVE_DIR": str(root / "archive"),
            "M20PRO_LIGHTNING_MAPPING_WORK_DIR": str(root / "work"),
            "M20PRO_LIGHTNING_SAVE_WAIT_S": "1",
            # The control script auto-registers finished maps with the Web
            # dashboard at http://127.0.0.1:8080 by default.  On 104 that is
            # the LIVE frontend, and the sandbox finish flow would overwrite
            # the real floor binding with fake assets (observed 2026-08-29).
            "M20PRO_DDDMR_MAPPING_AUTO_REGISTER": "0",
            "FAKE_M20PRO_PREFIX": str(fake_prefix),
            "AMENT_PREFIX_PATH": str(fake_prefix),
        }
    )
    (root / "work" / "data").mkdir(parents=True, exist_ok=True)
    helper = root / "workspace" / "scripts" / "ros2_service_wait_call.py"
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text(
        "#!/usr/bin/env python3\n"
        "import subprocess\n"
        "import sys\n"
        "raise SystemExit(subprocess.call(['ros2', 'service', *sys.argv[1:]]))\n",
        encoding="utf-8",
    )
    helper.chmod(0o755)
    return env


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="m20pro_lightning_mapping_runtime_"))
    try:
        fakebin = root / "fakebin"
        _write_fake_ros2(fakebin)
        env = _base_env(root, fakebin)

        missing = subprocess.run(
            [str(SCRIPT), "finish", "F20"],
            cwd=str(ROOT),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert missing.returncode == 23, missing.stdout + missing.stderr
        assert "ok=false" in missing.stdout
        assert "code=lightning_global_map_missing" in missing.stdout
        assert "archive_target=" not in missing.stdout

        mapper = subprocess.Popen(["setsid", "sleep", "60"])
        try:
            (root / "run" / "mapping.pid").write_text(str(mapper.pid), encoding="utf-8")
            (root / "run" / "state.json").write_text(
                '{"action":"start","floor":"F20","pid":"%s",'
                '"map_id":"failed_map","work_dir":"%s"}\n'
                % (mapper.pid, root / "work"),
                encoding="utf-8",
            )
            env_failed = dict(env)
            env_failed["FAKE_LIGHTNING_SAVE_FAIL"] = "1"
            failed = subprocess.run(
                [str(SCRIPT), "finish", "F20"],
                cwd=str(ROOT),
                env=env_failed,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            assert failed.returncode == 22, failed.stdout + failed.stderr
            assert "code=lightning_save_failed" in failed.stdout
            assert not (root / "run" / "mapping.pid").exists()
            assert mapper.poll() is not None
        finally:
            if mapper.poll() is None:
                mapper.kill()
                mapper.wait()

        env_success = dict(env)
        env_success["FAKE_LIGHTNING_CREATE_SAVE_DIR"] = "1"
        env_success["FAKE_LIGHTNING_WRITE_GLOBAL"] = "1"
        env_success["FAKE_LIGHTNING_FOXY_OUTPUT"] = "1"
        success = subprocess.run(
            [str(SCRIPT), "finish", "F20"],
            cwd=str(ROOT),
            env=env_success,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert success.returncode == 0, success.stdout + success.stderr
        assert "ok=true" in success.stdout
        assert "backend=lightning_lm" in success.stdout
        assert "action=finish" in success.stdout
        assert "archive_target=%s" % (root / "archive") in success.stdout
        assert "mapcloud=" in success.stdout
        assert "mapground=" in success.stdout
        assert "poses=" in success.stdout

        status_missing_env = dict(env)
        status_missing_env["M20PRO_WS"] = str(root / "missing_workspace")
        status_missing_env["AMENT_PREFIX_PATH"] = str(root / "missing_workspace" / "install")
        status_missing = subprocess.run(
            [str(SCRIPT), "status", "F20"],
            cwd=str(ROOT),
            env=status_missing_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert status_missing.returncode == 0, status_missing.stdout + status_missing.stderr
        assert "ok=true" in status_missing.stdout
        assert "backend=lightning_lm" in status_missing.stdout
        assert "state=idle" in status_missing.stdout
        assert "package_available=false" in status_missing.stdout
        assert "save_service_available=false" in status_missing.stdout
        assert "source_cloud_topic=/LIDAR/POINTS" in status_missing.stdout
        assert "cloud_adapter_enabled=false" in status_missing.stdout
        assert "lightning_points_topic=/m20pro/lightning_points" in status_missing.stdout
        assert "code=lightning_runtime_missing" in status_missing.stdout

        status_ready_env = dict(env)
        status_ready_env["FAKE_LIGHTNING_SAVE_SERVICE"] = "1"
        status_ready = subprocess.run(
            [str(SCRIPT), "status", "F20"],
            cwd=str(ROOT),
            env=status_ready_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert status_ready.returncode == 0, status_ready.stdout + status_ready.stderr
        assert "ok=true" in status_ready.stdout
        assert "backend=lightning_lm" in status_ready.stdout
        assert "state=idle" in status_ready.stdout
        assert "package_available=true" in status_ready.stdout
        assert "save_service_available=false" in status_ready.stdout
        assert "source_cloud_topic=/LIDAR/POINTS" in status_ready.stdout
        assert "cloud_adapter_enabled=false" in status_ready.stdout
        assert "lightning_points_topic=/m20pro/lightning_points" in status_ready.stdout
        assert "code=lightning_runtime_missing" not in status_ready.stdout
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("Lightning-LM mapping control runtime tests passed")


if __name__ == "__main__":
    main()
