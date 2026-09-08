#!/usr/bin/env python3
"""Source checks for the 104-side DDDMR mode switcher."""

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    script_path = ROOT / "scripts/104_dddmr_field_test_mode.sh"
    script = script_path.read_text(encoding="utf-8")
    autostart = (ROOT / "scripts/104_enable_autostart.sh").read_text(
        encoding="utf-8"
    )
    deploy = (ROOT / "scripts/local_deploy_to_test_robot.sh").read_text(
        encoding="utf-8"
    )
    install = (ROOT / "scripts/104_install_staged_workspace.sh").read_text(
        encoding="utf-8"
    )
    default_file = (ROOT / "systemd" / "m20pro-real.default").read_text(
        encoding="utf-8"
    )

    assert os.access(script_path, os.X_OK)
    assert "enable|dddmr" in script
    assert 'WS_DIR="${M20PRO_WS:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"' in script
    assert "M20PRO_NAVIGATION_BACKEND=dddmr_3d" in script
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP=true" in script
    assert "104_enable_autostart.sh" in script
    assert "104_accept_dddmr_field_test.sh" in script
    assert "command_mux" not in script
    assert "start_mapping()" not in script
    assert "start now:" not in script
    assert "restart_service" in script
    assert "show_status" in script
    assert "show_acceptance" in script
    assert "Usage: $0 <enable|restart|accept|status>" in script
    assert "restore-nav2" not in script

    assert "M20PRO_DEPLOY_REAL_MODE" in deploy
    assert 'DEPLOY_REAL_MODE="${M20PRO_DEPLOY_REAL_MODE:-move}"' in deploy
    assert 'real_mode=${DEPLOY_REAL_MODE}' in deploy
    assert 'invalid M20PRO_DEPLOY_REAL_MODE' in deploy
    assert '\"${DEPLOY_REAL_MODE}\"' in deploy

    assert "REAL_MODE=\"${5:-move}\"" in install
    assert "invalid real mode:" in install
    assert 'bash "${TARGET}/scripts/104_enable_autostart.sh" "${REAL_MODE}"' in install

    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP=true" in default_file
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M=2.0" in default_file
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M=0.25" in default_file
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M=0.0" in default_file
    assert "M20PRO_DDDMR_FIELD_TEST_MODE_SCRIPT=/home/user/m20pro_real_ros2_ws_v4/scripts/104_dddmr_field_test_mode.sh" in default_file

    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP" in autostart
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M" in autostart
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M" in autostart
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M" in autostart
    assert "M20PRO_DDDMR_FIELD_TEST_MODE_SCRIPT=${M20PRO_DDDMR_FIELD_TEST_MODE_SCRIPT:-${DEFAULT_DDDMR_FIELD_TEST_MODE_SCRIPT}}" in autostart
    assert 'WS_DIR="${M20PRO_WS:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"' in autostart

    print("DDDMR mode contract tests passed")


if __name__ == "__main__":
    main()
