#!/usr/bin/env python3
"""Source checks for the DDDMR mode API and frontend wiring."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/m20pro_cloud_bridge/m20pro_cloud_bridge/static"


def main() -> None:
    backend = (
        ROOT / "src/m20pro_cloud_bridge/m20pro_cloud_bridge/web_dashboard_node.py"
    ).read_text(encoding="utf-8")
    html = (STATIC / "dashboard.html").read_text(encoding="utf-8")
    script = (STATIC / "dashboard.js").read_text(encoding="utf-8")
    summary = (ROOT / "scripts" / "navigation_backend_summary.py").read_text(
        encoding="utf-8"
    )
    docs = (ROOT / "docs" / "frontend_api_contract.md").read_text(encoding="utf-8")

    assert re.search(
        r'self\.declare_parameter\(\s*["\']dddmr_field_test_mode_script["\']',
        backend,
    )
    assert "dddmr_field_test_mode" in backend
    assert "_dddmr_field_test_mode_payload_from_snapshot" in backend
    assert "_dddmr_field_test_mode_command" in backend
    assert 'elif parsed.path == "/api/dddmr/field_test_mode":' in backend
    assert 'self._send_json(node._dddmr_field_test_mode_payload())' in backend
    assert 'self._send_api(node._dddmr_field_test_mode_command(payload))' in backend
    assert "systemd-run" in backend
    assert '"queued": True' in backend
    assert '"target_navigation_backend": target_map[action]["navigation_backend"]' in backend
    assert '"target": target_map[action]' in backend
    assert '"navigation_backend": "dddmr_3d"' in backend
    assert '"dddmr_motion_enabled": True' in backend
    assert '"field_test_mode": snapshot.get("dddmr_field_test_mode")' in backend
    assert 'if backend_mode == "dddmr_3d":' in backend
    assert 'current_mode = "dddmr_3d"' in backend
    assert '"restore-nav2"' not in backend

    for removed_element_id in (
        "dddmrFieldTestModeStatus",
        "dddmrFieldTestModeSteps",
        "dddmrEnableFieldTestModeBtn",
    ):
        assert f'id="{removed_element_id}"' not in html

    for token in (
        "dddmrFieldTestModePayload",
        "renderDddmrFieldTestMode",
        "submitDddmrFieldTestMode",
        '"/api/dddmr/field_test_mode"',
        "state.dddmrFieldTestMode",
        "dddmrFieldTestModeText",
        'loadState(true).catch(() => {});',
    ):
        assert token in script
    assert "restore-nav2" not in script

    assert '"field_test_mode": {' in summary
    assert "current_mode" in summary
    assert "_navigation_backend_mode" in summary
    assert "available_actions" not in summary

    assert "GET `/api/dddmr/field_test_mode`" in docs
    assert "POST `/api/dddmr/field_test_mode`" in docs
    assert "action` 只接受 `enable`" in docs
    assert "target.navigation_backend" in docs
    assert "target.axis_command_enabled" in docs

    print("DDDMR mode API contract tests passed")


if __name__ == "__main__":
    main()
