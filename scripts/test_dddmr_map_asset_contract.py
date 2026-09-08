#!/usr/bin/env python3
"""Offline checks for DDDMR PCD asset loading and runtime wiring."""

from __future__ import annotations

import struct
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/m20pro_navigation"))

from m20pro_navigation.dddmr_map_asset_io import (  # noqa: E402
    _finite_xyz,
    _parse_pcd,
    _split_paths,
)
from m20pro_navigation.dddmr_map_asset_contract import (  # noqa: E402
    dddmr_map_asset_workspace,
    generate_dddmr_field_test_flat_map_points,
    normalize_dddmr_map_asset_record,
    remove_dddmr_map_asset_record,
    upsert_dddmr_map_asset,
)


def pcd_header(mode: str, points: int) -> bytes:
    return (
        "VERSION .7\n"
        "FIELDS x y z intensity\n"
        "SIZE 4 4 4 4\n"
        "TYPE F F F F\n"
        "COUNT 1 1 1 1\n"
        f"WIDTH {points}\n"
        "HEIGHT 1\n"
        f"POINTS {points}\n"
        f"DATA {mode}\n"
    ).encode("ascii")


def main() -> None:
    assert _finite_xyz([(1, 2, 3), (float("nan"), 2, 3), (4, 5, 6)], 1) == [
        (1.0, 2.0, 3.0)
    ]
    assert _split_paths("a.pcd, b.pcd") == [Path("a.pcd"), Path("b.pcd")]
    normalized_record = normalize_dddmr_map_asset_record(
        "F20", {"mapcloud": "a.pcd", "mapground": "b.pcd", "z": 1.25}
    )
    assert normalized_record["label"] == "F20"
    assert normalized_record["z"] == 1.25
    manifest = {
        "floors": {
            "F20": {
                "floor": "F20",
                "mapcloud": ["a.pcd"],
                "mapground": ["b.pcd"],
            }
        }
    }
    workspace = dddmr_map_asset_workspace(manifest)
    assert workspace["floor_count"] == 1
    assert workspace["ready_floor_count"] == 1
    assert workspace["floors"][0]["ready"] is True
    first_asset_id = workspace["floors"][0]["asset_id"]
    updated_manifest = upsert_dddmr_map_asset(
        manifest,
        {
            "floor": "F20",
            "label": "second",
            "mapcloud": ["second_map.pcd"],
            "mapground": ["second_ground.pcd"],
        },
    )
    updated_workspace = dddmr_map_asset_workspace(updated_manifest)
    assert updated_workspace["floor_count"] == 1
    assert updated_workspace["asset_count"] == 2
    assert updated_workspace["ready_asset_count"] == 2
    assert updated_workspace["floors"][0]["label"] == "second"
    assert any(item["asset_id"] == first_asset_id and not item["active"] for item in updated_workspace["assets"])
    assert any(item["label"] == "second" and item["active"] for item in updated_workspace["assets"])
    removed = remove_dddmr_map_asset_record(updated_manifest, first_asset_id)
    assert removed["ok"] is True
    assert removed["asset_id"] == first_asset_id
    assert removed["removed_floors"] == []
    assert first_asset_id not in removed["manifest"]["assets"]

    # Re-registering the same archive (identical mapcloud paths) under a new
    # label must update the existing asset record, not add a duplicate that
    # shares the archive directory and deadlocks deletion of both records.
    duplicate_manifest = upsert_dddmr_map_asset(
        updated_manifest,
        {
            "floor": "F20",
            "label": "auto-register",
            "mapcloud": ["second_map.pcd"],
            "mapground": ["second_ground.pcd"],
            "source": "lightning_lm_mapping",
        },
    )
    duplicate_workspace = dddmr_map_asset_workspace(duplicate_manifest)
    assert duplicate_workspace["asset_count"] == 2
    second_ids = [
        item["asset_id"]
        for item in duplicate_workspace["assets"]
        if item["label"] == "auto-register"
    ]
    assert second_ids == [
        item["asset_id"]
        for item in updated_workspace["assets"]
        if item["label"] == "second"
    ]
    flat_points = generate_dddmr_field_test_flat_map_points(extent_m=0.5, spacing_m=0.5, height_m=0.0)
    assert flat_points[0] == (-0.5, -0.5, 0.0)
    assert flat_points[-1] == (0.5, 0.5, 0.0)
    assert len(flat_points) == 9

    with tempfile.TemporaryDirectory(prefix="m20pro_dddmr_map_test_") as tmp:
        root = Path(tmp)
        ascii_path = root / "ascii.pcd"
        ascii_path.write_bytes(
            pcd_header("ascii", 3)
            + b"1 2 3 9\nnan 2 3 9\n4 5 6 9\n"
        )
        assert _parse_pcd(ascii_path, 0) == [
            (1.0, 2.0, 3.0),
            (4.0, 5.0, 6.0),
        ]
        assert _parse_pcd(ascii_path, 1) == [(1.0, 2.0, 3.0)]

        binary_path = root / "binary.pcd"
        binary_path.write_bytes(
            pcd_header("binary", 2)
            + struct.pack("<ffff", 1.5, 2.5, 3.5, 7.0)
            + struct.pack("<ffff", 4.5, 5.5, 6.5, 8.0)
        )
        assert _parse_pcd(binary_path, 0) == [
            (1.5, 2.5, 3.5),
            (4.5, 5.5, 6.5),
        ]

    params = yaml.safe_load(
        (
            ROOT
            / "src/m20pro_bringup/config/dddmr_m20pro_navigation.yaml"
        ).read_text(encoding="utf-8")
    )
    for node in (
        "p2p_move_base",
        "global_plan_manager",
        "local_planner",
        "perception_3d_local",
        "perception_3d_global",
    ):
        assert node in params
    local = params["perception_3d_local"]["ros__parameters"]
    global_perception = params["perception_3d_global"]["ros__parameters"]
    assert local["robot_base_frame"] == "m20pro_base_link"
    assert local["lidar"]["topic"] == "/dddmr/edge_cloud"
    # DDDMR planners consume the pose-graph namespace. The M20Pro dashboard
    # remains on /mapcloud and /mapground, which are published as a mirror.
    assert local["map"]["map_topic"] == "map1/mapcloud"
    assert local["map"]["ground_topic"] == "map1/mapground"
    assert global_perception["map"]["map_topic"] == "map1/mapcloud"
    assert global_perception["map"]["ground_topic"] == "map1/mapground"
    assert params["local_planner"]["ros__parameters"]["odom_topic"] == "/odom"

    source = (
        ROOT
        / "src/m20pro_navigation/m20pro_navigation/dddmr_map_asset_server_node.py"
    ).read_text(encoding="utf-8")
    web_source = (
        ROOT
        / "src/m20pro_cloud_bridge/m20pro_cloud_bridge/web_dashboard_node.py"
    ).read_text(encoding="utf-8")
    real_launch = (ROOT / "src/m20pro_bringup/launch/m20pro_real.launch.py").read_text(
        encoding="utf-8"
    )
    top_launch = (ROOT / "src/m20pro_bringup/launch/m20pro.launch.py").read_text(
        encoding="utf-8"
    )
    assert "DurabilityPolicy.TRANSIENT_LOCAL" in source
    assert "self._publish_empty()" in source
    assert "from .dddmr_map_asset_io import _finite_xyz, _parse_pcd, _split_paths" in source
    assert "field_test_fallback_enabled" in source
    assert "field_test_flat_map_ready" in source
    assert '"map_assets_ready"' in source
    assert 'self.declare_parameter("mapcloud_topic", "/mapcloud")' in source
    assert '"%s/mapcloud" % self._pg_name' in source
    assert '"%s/mapground" % self._pg_name' in source
    assert "config = augment_floor_config(config, self._projects, manifest)" in web_source
    assert web_source.count("floor_config_sync = self._sync_runtime_floor_config()") >= 4
    assert "_select_dddmr_map_asset" in web_source
    assert '"/api/dddmr/map_assets/select"' in web_source
    html = (
        ROOT / "src/m20pro_cloud_bridge/m20pro_cloud_bridge/static/dashboard.html"
    ).read_text(encoding="utf-8")
    js = (
        ROOT / "src/m20pro_cloud_bridge/m20pro_cloud_bridge/static/dashboard.js"
    ).read_text(encoding="utf-8")
    assert "mapDddmrAssetWorkspace" in html
    assert "mapDddmrRefreshAssetsBtn" in html
    assert "status-popover-map" in html
    assert 'id="mapStatusDetail" class="map-current-summary"' in html
    assert 'id="mapStatusDetail" class="compact-status"' not in html
    assert "dddmrAssetWorkspace" not in html
    assert "dddmrMapAssetsSummary" not in html
    assert "dddmrRegisterAssetBtn" not in html
    assert "dddmrFillAssetFromMapBtn" not in html
    assert "data-dddmr-select-asset" in js
    assert "data-dddmr-delete-asset" in js
    assert "map-asset-card" in js
    assert "map-asset-badge" in js
    assert "map-current-summary" in html
    assert "buildSpatialRenderModel" in js
    assert "drawSpatialRenderCells3d" in js
    assert "drawSpatialRenderCellsTopdown" in js
    assert "draw3dGrid(map, view);" not in js
    assert "drawCanvasBackground" in js
    assert "syncMapCanvasBackingStore" in js
    assert "clearMapCanvasPixels" in js
    assert "resetMapCanvasTransform" in js
    assert "ResizeObserver" in js
    assert "ctx.setTransform(1, 0, 0, 1, 0, 0)" in js
    assert "const py = ry * cp + dz * sp" in js
    assert "const depth = ry * sp - dz * cp" in js
    assert "Math.max(0.45, Math.min(1.25" in js
    assert 'ctx.fillStyle = "rgba(15, 23, 42, 0.22)"' not in js
    assert "createRadialGradient" not in js
    assert "shadowBlur" not in js
    assert "orbiting" in js
    css = (ROOT / "src/m20pro_cloud_bridge/m20pro_cloud_bridge/static/dashboard.css").read_text(encoding="utf-8")
    assert "image-rendering: auto" in css
    assert "#mapCanvas" in css
    assert "position: absolute" in css
    assert "data-dddmr-load-asset" not in js
    assert "dddmr-asset-meta" not in js
    assert "mapcloud_count" not in js
    assert "groundCount" not in js
    assert "cloudCount" not in js
    assert "空间地图：" not in js
    assert "地面地图：" not in js
    assert "map.mapcloud.length" not in js
    assert "map.mapground.length" not in js
    assert "空间点 /" not in js
    assert "地面点 /" not in js
    assert 'const viewText = effectiveMapViewMode()' not in js
    assert "map.assetRecord.source" not in js
    assert "renderDddmrAssetWorkspace" in js
    assert "/api/dddmr/map_assets/select" in js
    assert "/api/dddmr/map_assets/delete" in js
    # Deleting a record must never be vetoed by file-side safety checks: the
    # old all-or-nothing rejection made shared-archive duplicates undeletable.
    assert "dddmr_map_asset_file_delete_unsafe" not in web_source
    assert "三维地图归档目录无法安全删除" not in web_source
    assert "file_skip_reason" in web_source
    assert "from .spatial_view_contract import (" in web_source
    assert "/api/3d/spatial_map" in web_source
    assert "dddmr_field_test_flat_map" in real_launch
    assert "dddmr_field_test_flat_map" in top_launch

    print("DDDMR map asset contract tests passed")


if __name__ == "__main__":
    main()
