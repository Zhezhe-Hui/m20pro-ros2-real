#!/usr/bin/env python3
"""Offline tests for m20pro_cloud_bridge.map_contract."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/m20pro_cloud_bridge"))
sys.path.insert(0, str(ROOT / "src/m20pro_navigation"))

from m20pro_cloud_bridge.map_contract import (  # noqa: E402
    all_map_records,
    apply_map_delete_state,
    apply_map_cell_edits,
    build_imported_map_record,
    default_map_id,
    ensure_map_yaml_uses_local_image,
    find_map_record,
    find_map_yaml,
    load_builtin_maps_from_manifest,
    load_map_file_payload,
    map_navigation_capability,
    map_file_fingerprint,
    map_file_metadata_payload,
    read_pgm,
    read_pgm_header,
    removable_map_archive_directory,
    stable_factory_map_path,
)
from m20pro_navigation.map_manifest import load_manifest as load_navigation_manifest  # noqa: E402


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def write_p2(path: Path) -> None:
    path.write_text(
        "P2\n"
        "# tiny map\n"
        "2 2\n"
        "100\n"
        "0 50\n"
        "100 20\n",
        encoding="ascii",
    )


def write_p5(path: Path) -> None:
    path.write_bytes(b"P5\n2 1\n255\n\x00\xff")


def test_find_map_yaml_prefers_known_names() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        nested = root / "nested"
        nested.mkdir()
        (nested / "other.yaml").write_text("image: other.pgm\n", encoding="utf-8")
        (root / "occ_grid.yaml").write_text("image: occ_grid.pgm\n", encoding="utf-8")
        assert_equal(find_map_yaml(root), root / "occ_grid.yaml", "preferred yaml")


def test_load_builtin_maps_from_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        manifest = root / "map_manifest.yaml"
        f19 = root / "F19"
        f20 = root / "F20"
        f19.mkdir()
        f20.mkdir()
        (f19 / "occ_grid.yaml").write_text("image: occ_grid.pgm\n", encoding="utf-8")
        (f20 / "occ_grid.yaml").write_text("image: occ_grid.pgm\n", encoding="utf-8")
        manifest.write_text(
            "map_set:\n"
            "  default_floor: F20\n"
            "  global_pcd: package://m20pro_bringup/maps/full_cloud.pcd\n"
            "  source_note: note\n"
            "floors:\n"
            "  F20:\n"
            "    level: 20\n"
            "    label: 20楼\n"
            "    map_yaml: package://m20pro_bringup/maps/F20/occ_grid.yaml\n"
            "  F19:\n"
            "    level: 19\n"
            "    label: 19楼\n"
            "    map_yaml: package://m20pro_bringup/maps/F19/occ_grid.yaml\n"
            "    pcd_map: /tmp/custom_f19.pcd\n",
            encoding="utf-8",
        )

        def resolve_path(value: str) -> str:
            return value.replace("package://m20pro_bringup/maps", str(root))

        result = load_builtin_maps_from_manifest(
            manifest,
            resolve_path=resolve_path,
            derived_payload=lambda yaml_path, pcd_path: {"yaml": str(yaml_path), "pcd": pcd_path},
        )
        maps = result["maps"]
        assert_equal(result["default_floor"], "F20", "default floor")
        assert_equal(result["default_map_id"], "builtin_F20", "default map id")
        assert_equal([item["id"] for item in maps], ["builtin_F19", "builtin_F20"], "sorted maps")
        assert_equal(maps[0]["name"], "19楼", "label")
        assert_equal(maps[0]["pcd_path"], "/tmp/custom_f19.pcd", "explicit pcd")
        assert_equal(maps[1]["source_note"], "note", "source note")
        assert_equal(maps[1]["derived"]["pcd"], str(root / "full_cloud.pcd"), "global pcd")


def test_map_asset_manifest_uses_explicit_map_ids() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "f19.yaml").write_text("image: f19.pgm\n", encoding="utf-8")
        (root / "f20.yaml").write_text("image: f20.pgm\n", encoding="utf-8")
        manifest = root / "map_manifest.yaml"
        manifest.write_text(
            "map_set:\n"
            "  default_map_id: builtin_F20\n"
            "maps:\n"
            "  - id: builtin_F19\n"
            "    floor: F19\n"
            "    map_yaml: f19.yaml\n"
            "  - id: builtin_F20\n"
            "    floor: F20\n"
            "    map_yaml: f20.yaml\n",
            encoding="utf-8",
        )
        result = load_builtin_maps_from_manifest(
            manifest,
            resolve_path=lambda value: str(root / value),
            derived_payload=lambda yaml_path, pcd_path: {},
        )
        assert_equal([item["id"] for item in result["maps"]], ["builtin_F19", "builtin_F20"], "explicit map ids")
        assert_equal(result["default_floor"], None, "no default floor semantic")
        assert_equal(result["default_map_id"], "builtin_F20", "explicit map default")


def test_map_record_merge_find_and_default() -> None:
    builtin = [
        {"id": "builtin_F19", "floor": "F19"},
        {"id": "builtin_F20", "floor": "F20"},
    ]
    archived = [
        {"id": "builtin_F19", "floor": "F19", "source": "106_active_map"},
        {"id": "map_custom", "floor": "F21"},
    ]
    merged = all_map_records(builtin, archived)
    assert_equal([item["id"] for item in merged], ["builtin_F20", "builtin_F19", "map_custom"], "merged order")
    assert_equal(find_map_record(builtin, archived, "builtin_F19")["source"], "106_active_map", "archived wins")
    assert_equal(default_map_id(builtin, archived, "builtin_F19"), "builtin_F19", "default id if present")
    assert_equal(default_map_id(builtin, archived, "missing"), "builtin_F19", "fallback first ordinary map")
    assert_equal(default_map_id([], archived, None), "builtin_F19", "fallback archived")
    real_archived = [{"id": "map_office", "floor": "F7", "source": "106_active_map"}]
    assert_equal(
        default_map_id([], real_archived, "builtin_F20"),
        "map_office",
        "removed builtin default falls back to archived map",
    )


def test_repository_has_no_legacy_builtin_floor_assets() -> None:
    manifest_path = ROOT / "src" / "m20pro_bringup" / "config" / "map_manifest.yaml"
    result = load_builtin_maps_from_manifest(
        manifest_path,
        resolve_path=lambda value: value,
        derived_payload=lambda yaml_path, pcd_path: {},
    )
    assert_equal(result["maps"], [], "repository manifest has no preset floor maps")
    assert_equal(result["default_map_id"], None, "repository manifest has no preset default map")
    assert_equal(
        load_navigation_manifest(str(manifest_path))["maps"],
        [],
        "navigation config audit accepts an explicit empty project manifest",
    )

    bringup = ROOT / "src" / "m20pro_bringup"
    for floor in ("F19", "F20", "F21"):
        assert_true(not (bringup / "maps" / floor).exists(), f"legacy {floor} map directory removed")
    assert_true(
        not (bringup / "maps" / "DESK_20260625_164234_edit").exists(),
        "retired 104-only desk map asset removed",
    )
    assert_true(
        not (
            ROOT
            / "docs"
            / "archived_route_profiles"
            / "legacy_inspection_waypoints_f19_f20_f21.yaml"
        ).exists(),
        "legacy fixed-floor route profile removed",
    )

    runtime_files = [
        manifest_path,
        bringup / "config" / "runtime_navigation.yaml",
        bringup / "launch" / "m20pro_real.launch.py",
        bringup / "launch" / "m20pro.launch.py",
    ]
    runtime_text = "\n".join(path.read_text(encoding="utf-8") for path in runtime_files)
    for legacy_id in ("builtin_F19", "builtin_F20", "builtin_F21"):
        assert_true(legacy_id not in runtime_text, f"legacy map id {legacy_id} absent from runtime config")
    for legacy_path in ('"F19", "occ_grid.yaml"', '"F20", "occ_grid.yaml"', '"F21", "occ_grid.yaml"'):
        assert_true(legacy_path not in runtime_text, f"legacy launch path {legacy_path} absent")

    bootstrap_map = bringup / "maps" / "Original_map" / "occ_grid.yaml"
    assert_true(bootstrap_map.exists(), "technical launch map exists")
    for launch_path in (runtime_files[2], runtime_files[3]):
        launch_text = launch_path.read_text(encoding="utf-8")
        assert_true(
            '"Original_map", "occ_grid.yaml"' in launch_text,
            f"{launch_path.name} uses the non-registered technical launch map",
        )


def test_navigation_map_requires_stable_factory_binding_and_edits_inherit_it() -> None:
    parent = {
        "id": "map_parent",
        "factory_apply_path": "/var/opt/robot/data/maps/site-f20-001",
    }
    edited = {"id": "map_edited", "parent_map_id": "map_parent", "source": "web_map_editor"}
    orphan = {"id": "map_orphan", "source": "manual_sync_upper_computer"}
    active_alias = {"id": "map_active", "source_path": "/var/opt/robot/data/maps/active"}
    records = [parent, edited, orphan, active_alias]
    assert_equal(
        stable_factory_map_path(edited, records),
        "/var/opt/robot/data/maps/site-f20-001",
        "edited map inherits its parent factory package",
    )
    assert_true(map_navigation_capability(edited, records)["ready"], "edited map is navigable")
    assert_equal(
        map_navigation_capability(orphan, records)["code"],
        "factory_map_binding_missing",
        "104-only map is not navigable",
    )
    assert_true(not map_navigation_capability(active_alias, records)["ready"], "active alias is not stable")


def test_ensure_map_yaml_repairs_to_local_relative_image() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        yaml_path = root / "map.yaml"
        pgm_path = root / "occ_grid.pgm"
        write_p2(pgm_path)
        yaml_path.write_text(
            "image: /tmp/not-this-map/old.pgm\n"
            "resolution: 0.1\n"
            "origin: [1.0, 2.0, 0.5]\n",
            encoding="utf-8",
        )
        result = ensure_map_yaml_uses_local_image(yaml_path)
        assert_true(result["ok"], "repair ok")
        assert_true(result["repaired"], "repaired")
        assert_equal(result["image"], "occ_grid.pgm", "relative image")
        assert_true("image: occ_grid.pgm" in yaml_path.read_text(encoding="utf-8"), "yaml rewritten")


def test_ensure_map_yaml_reports_missing_image() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_path = Path(tmpdir) / "map.yaml"
        yaml_path.write_text("image: missing.pgm\n", encoding="utf-8")
        result = ensure_map_yaml_uses_local_image(yaml_path)
        assert_equal(result["ok"], False, "not ok")
        assert_equal(result["code"], "map_image_missing", "missing image code")


def test_read_pgm_p2_and_p5() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        p2 = root / "map_p2.pgm"
        p5 = root / "map_p5.pgm"
        write_p2(p2)
        write_p5(p5)
        assert_equal(read_pgm(p2), (2, 2, 100, [0, 50, 100, 20]), "p2 parsed")
        assert_equal(read_pgm(p5), (2, 1, 255, [0, 255]), "p5 parsed")
        assert_equal(read_pgm_header(p2), (2, 2, 100), "p2 header parsed")
        assert_equal(read_pgm_header(p5), (2, 1, 255), "p5 header parsed")


def test_map_file_metadata_payload_is_lightweight() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        yaml_path = root / "map.yaml"
        pgm_path = root / "map.pgm"
        write_p2(pgm_path)
        yaml_path.write_text(
            "image: map.pgm\n"
            "resolution: 0.1\n"
            "origin: [1.0, 2.0, 0.5]\n",
            encoding="utf-8",
        )
        record = {"id": "map_a", "name": "Desk", "floor": "F20", "source": "106_active_map"}
        metadata = map_file_metadata_payload(record, yaml_path)
        full = load_map_file_payload(record, yaml_path)
        assert_true(metadata["available"], "metadata available")
        assert_equal(metadata["map_id"], "map_a", "metadata map id")
        assert_equal(metadata["width"], 2, "metadata width")
        assert_equal(metadata["height"], 2, "metadata height")
        assert_equal(metadata["resolution"], 0.1, "metadata resolution")
        assert_equal(metadata["origin"]["yaw"], 0.5, "metadata yaw")
        assert_true("data" not in metadata, "metadata omits occupancy data")
        assert_true("data" in full, "full payload keeps occupancy data")


def test_map_file_fingerprint_tracks_yaml_and_image() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        yaml_path = root / "map.yaml"
        pgm_path = root / "map.pgm"
        write_p2(pgm_path)
        yaml_path.write_text("image: map.pgm\nresolution: 0.1\n", encoding="utf-8")
        first = map_file_fingerprint(yaml_path)
        assert_true(first is not None, "fingerprint exists")
        pgm_path.write_text("P2\n1 1\n100\n0\n", encoding="ascii")
        second = map_file_fingerprint(yaml_path)
        assert_true(second is not None, "second fingerprint exists")
        assert_true(first != second, "fingerprint changes when image changes")


def test_load_map_file_payload_builds_nav_occupancy_grid() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        yaml_path = root / "map.yaml"
        pgm_path = root / "map.pgm"
        write_p2(pgm_path)
        yaml_path.write_text(
            "image: map.pgm\n"
            "resolution: 0.1\n"
            "origin: [1.0, 2.0, 0.5]\n"
            "occupied_thresh: 0.65\n"
            "free_thresh: 0.196\n"
            "negate: 0\n",
            encoding="utf-8",
        )
        payload = load_map_file_payload(
            {"id": "map_a", "name": "Desk", "floor": "F20", "source": "106_active_map"},
            yaml_path,
        )
        assert_true(payload["available"], "available")
        assert_equal(payload["map_id"], "map_a", "map id")
        assert_equal(payload["map_source"], "106_active_map", "map source")
        assert_equal(payload["width"], 2, "width")
        assert_equal(payload["height"], 2, "height")
        assert_equal(payload["resolution"], 0.1, "resolution")
        assert_equal(payload["origin"]["x"], 1.0, "origin x")
        assert_equal(payload["origin"]["yaw"], 0.5, "origin yaw")
        assert_equal(payload["data"], [0, 100, 100, -1], "occupancy data flipped to ROS map order")


def test_apply_map_cell_edits_preserves_image_coordinates() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        yaml_path = root / "map.yaml"
        pgm_path = root / "map.pgm"
        write_p5(pgm_path)
        yaml_path.write_text(
            "image: map.pgm\n"
            "resolution: 0.1\n"
            "occupied_thresh: 0.65\n"
            "free_thresh: 0.196\n"
            "negate: 0\n",
            encoding="utf-8",
        )
        result = apply_map_cell_edits(
            yaml_path,
            [{"x": 0, "y": 0, "value": 100}, {"x": 1, "y": 0, "value": -1}],
        )
        assert_equal(result["changed_cells"], 1, "changed cells")
        assert_equal(read_pgm(pgm_path), (2, 1, 255, [0, 108]), "edited PGM pixels")


def test_build_imported_map_record() -> None:
    record = build_imported_map_record(
        map_id="map_a",
        map_name="Desk",
        floor="F20",
        mode="single",
        project_id="project_a",
        project_name="M20Pro 工地巡检",
        building="B1",
        directory=Path("/tmp/Desk"),
        yaml_path=Path("/tmp/Desk/occ_grid.yaml"),
        source_path="/home/user/active_map",
        created_at="2026-06-29 10:10:00",
    )
    assert_equal(record["id"], "map_a", "map id")
    assert_equal(record["name"], "Desk", "name")
    assert_equal(record["floor"], "F20", "floor")
    assert_equal(record["mode"], "single", "mode")
    assert_equal(record["project_id"], "project_a", "project id")
    assert_equal(record["project_name"], "M20Pro 工地巡检", "project name")
    assert_equal(record["building"], "B1", "building")
    assert_equal(record["directory"], "/tmp/Desk", "directory")
    assert_equal(record["yaml_path"], "/tmp/Desk/occ_grid.yaml", "yaml path")
    assert_equal(record["source"], "106_active_map", "source")
    assert_equal(record["source_path"], "/home/user/active_map", "source path")
    assert_equal(record["created_at"], "2026-06-29 10:10:00", "created at")


def test_apply_map_delete_state_cascades_references() -> None:
    result = apply_map_delete_state(
        archived_maps=[
            {"id": "map_old", "name": "Old"},
            {"id": "map_child", "parent_map_id": "map_old"},
            {"id": "map_keep"},
        ],
        annotations=[
            {"id": "point_old", "map_id": "map_old"},
            {"id": "point_keep", "map_id": "map_keep"},
        ],
        tasks=[
            {"id": "task_old", "map_id": "map_old", "annotation_ids": ["point_old"]},
            {"id": "task_cross", "annotation_ids": ["point_keep", "point_old"]},
            {"id": "task_keep", "map_id": "map_keep", "annotation_ids": ["point_keep"]},
        ],
        sessions=[{
            "id": "session_a",
            "active_floor": "F20",
            "status": "imported",
            "floor_steps": [{"floor": "F20", "status": "imported", "map_id": "map_old"}],
        }],
        settings={"active_task": {"task_id": "task_old", "status": "completed"}},
        map_id="map_old",
        protected_map_ids=["map_keep"],
        updated_at="now",
    )
    assert_true(result["ok"], "delete state ok")
    assert_equal([item["id"] for item in result["maps"]], ["map_child", "map_keep"], "map removed")
    assert_equal(result["maps"][0].get("deleted_parent_map_id"), "map_old", "child history kept")
    assert_equal([item["id"] for item in result["annotations"]], ["point_keep"], "point cascaded")
    assert_equal([item["id"] for item in result["tasks"]], ["task_keep"], "tasks cascaded")
    assert_equal(result["sessions"][0]["floor_steps"][0].get("map_id"), None, "session map cleared")
    assert_equal(result["sessions"][0]["floor_steps"][0]["status"], "saved", "session restored")
    assert_equal(result["settings"]["active_task"], None, "terminal task cleared")
    assert_equal(result["deleted_annotations"], 1, "deleted point count")
    assert_equal(result["deleted_tasks"], 2, "deleted task count")


def test_map_delete_protection_and_archive_ownership() -> None:
    blocked = apply_map_delete_state(
        archived_maps=[{"id": "map_current"}],
        annotations=[],
        tasks=[],
        sessions=[],
        settings={},
        map_id="map_current",
        protected_map_ids=["map_current"],
        updated_at="now",
    )
    assert_equal(blocked["code"], "map_in_use", "current map protected")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "maps"
        owned = root / "owned"
        outside = Path(tmpdir) / "outside"
        owned.mkdir(parents=True)
        outside.mkdir()
        deletable = removable_map_archive_directory(root, {"directory": str(owned)}, [])
        protected = removable_map_archive_directory(root, {"directory": str(outside)}, [])
        shared = removable_map_archive_directory(root, {"directory": str(owned)}, [{"directory": str(owned)}])
        assert_true(deletable["delete"], "owned archive deletable")
        assert_equal(protected["reason"], "outside_map_archive", "outside archive preserved")
        assert_equal(shared["reason"], "shared_map_directory", "shared archive preserved")


def main() -> int:
    for test in (
        test_find_map_yaml_prefers_known_names,
        test_load_builtin_maps_from_manifest,
        test_map_record_merge_find_and_default,
        test_repository_has_no_legacy_builtin_floor_assets,
        test_navigation_map_requires_stable_factory_binding_and_edits_inherit_it,
        test_map_asset_manifest_uses_explicit_map_ids,
        test_ensure_map_yaml_repairs_to_local_relative_image,
        test_ensure_map_yaml_reports_missing_image,
        test_read_pgm_p2_and_p5,
        test_map_file_metadata_payload_is_lightweight,
        test_map_file_fingerprint_tracks_yaml_and_image,
        test_load_map_file_payload_builds_nav_occupancy_grid,
        test_apply_map_cell_edits_preserves_image_coordinates,
        test_build_imported_map_record,
        test_apply_map_delete_state_cascades_references,
        test_map_delete_protection_and_archive_ownership,
    ):
        test()
        print(f"[OK] {test.__name__}")
    print("[OK] map contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
