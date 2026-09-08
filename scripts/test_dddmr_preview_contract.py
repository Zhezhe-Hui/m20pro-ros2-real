#!/usr/bin/env python3
"""Source checks for the no-sudo DDDMR read-only preview entrypoint."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRINGUP = ROOT / "src/m20pro_bringup"


def main() -> None:
    launch = (BRINGUP / "launch/m20pro_dddmr_preview.launch.py").read_text(
        encoding="utf-8"
    )
    script = (ROOT / "scripts/104_start_dddmr_preview.sh").read_text(
        encoding="utf-8"
    )
    daemon = (ROOT / "scripts/104_start_dddmr_preview_daemon.sh").read_text(
        encoding="utf-8"
    )
    resolver = (ROOT / "scripts/104_resolve_dddmr_preview_port.sh").read_text(
        encoding="utf-8"
    )
    stop = (ROOT / "scripts/104_stop_dddmr_preview.sh").read_text(
        encoding="utf-8"
    )
    status = (ROOT / "scripts/104_status_dddmr_preview.sh").read_text(
        encoding="utf-8"
    )
    status_104 = (ROOT / "scripts/104_status.sh").read_text(encoding="utf-8")
    scripts_readme = (ROOT / "scripts/README.md").read_text(encoding="utf-8")
    dddmr_doc = (ROOT / "docs/dddmr_navigation_v1.md").read_text(
        encoding="utf-8"
    )

    assert 'default_value="18080"' in launch
    assert 'default_value="~/.m20pro_web_dddmr_preview"' in launch
    assert 'default_value="~/m20pro_maps_dddmr_preview"' in launch
    assert '"navigation_backend"' in launch
    assert 'default_value="dddmr_3d"' in launch
    assert '"enable_dddmr_runtime", default_value="false"' in launch
    assert '"dddmr_motion_enabled", default_value="false"' in launch
    assert '"enable_gnss_adapter", default_value="false"' in launch
    assert 'dddmr_field_test_flat_map' in launch
    assert 'default_value="true"' in launch
    assert 'executable="dddmr_edge_cloud_adapter"' in launch
    assert 'package="m20pro_bringup",\n            executable="dddmr_edge_cloud_adapter"' in launch
    assert 'executable="dddmr_map_asset_server"' in launch
    assert "m20pro_dddmr_bridge.launch.py" in launch
    assert "m20pro_dddmr_runtime.launch.py" in launch
    assert 'require_map_status": "true"' in launch
    assert '"navigation_backend_status_topic": navigation_backend_status_topic' in launch
    assert '"dddmr_edge_cloud_status_topic": dddmr_edge_cloud_status_topic' in launch
    assert '"dddmr_map_cloud_topic": dddmr_map_cloud_topic' in launch
    assert '"dddmr_map_ground_topic": dddmr_map_ground_topic' in launch
    assert '"dddmr_map_status_topic": dddmr_map_status_topic' in launch

    assert "M20PRO_WS" in script
    assert "M20PRO_DDDMR_PREVIEW_PORT" in script
    assert 'navigation_backend:="${NAVIGATION_BACKEND}"' in script
    assert 'if [[ "${NAVIGATION_BACKEND}" != "dddmr_3d" ]]' in script
    assert "m20pro_dddmr_preview.launch.py" in script
    assert "no motion authorization" in script
    assert 'enable_dddmr_runtime:="${ENABLE_DDDMR_RUNTIME}"' in script
    assert 'enable_web_dashboard:="${ENABLE_WEB_DASHBOARD}"' in script
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP" in script
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M" in script
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M" in script
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M" in script

    assert "setsid env" in daemon
    assert 'script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in daemon
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP" in daemon
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M" in daemon
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M" in daemon
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M" in daemon
    assert "preview_${PORT}.pid" in daemon
    assert "preview_${PORT}.log" in daemon
    assert "readlink -f" in daemon
    assert "104_start_dddmr_preview.sh" in daemon
    assert "bridge_seen" in daemon
    assert "navigation_backend_summary.py" in daemon
    assert "provisional" in daemon
    assert "source" in daemon
    assert 'kill -TERM -- -"${pid}"' in daemon
    assert "104_resolve_dddmr_preview_port.sh" in status_104
    assert "104_resolve_dddmr_preview_port.sh" in status
    assert "104_resolve_dddmr_preview_port.sh" in stop
    assert "[104_status] DDDMR:" in status_104
    assert "navigation_backend_summary.py" in status_104
    assert "provisional" in status
    assert "source" in status
    assert "command_mux_seen" in status
    assert "age_s" in status
    assert "preview_*.pid" in resolver
    assert "kill -0" in resolver
    assert "ss -ltnp" in resolver
    assert 'kill -TERM -- -"${pid}"' in stop
    assert "m20pro_web_dashboard_preview" in stop
    assert "navigation_backend" in status
    assert "navigation_backend_summary.py" in status
    assert "recent log" in status

    assert "104_start_dddmr_preview.sh" in scripts_readme
    assert "104_resolve_dddmr_preview_port.sh" in scripts_readme
    assert "104_start_dddmr_preview_daemon.sh" in scripts_readme
    assert "104_status_dddmr_preview.sh" in scripts_readme
    assert "104_stop_dddmr_preview.sh" in scripts_readme
    assert "临时平面" in scripts_readme
    assert "~/.m20pro_dddmr_preview/latest" in scripts_readme
    assert "104_status_dddmr_preview.sh" in status_104
    assert "preview_*.pid" in resolver
    assert "M20PRO_DEPLOY_PREPARE_ONLY=1" in dddmr_doc
    assert "104_start_dddmr_preview.sh" in dddmr_doc
    assert "104_start_dddmr_preview_daemon.sh" in dddmr_doc
    assert "latest" in dddmr_doc
    assert "临时平面" in dddmr_doc
    assert "不放开运动" in dddmr_doc

    print("DDDMR preview contract tests passed")


if __name__ == "__main__":
    main()
