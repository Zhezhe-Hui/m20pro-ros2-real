#!/usr/bin/env python3
"""Offline tests for m20pro_cloud_bridge.mapping_contract."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/m20pro_cloud_bridge"))

from m20pro_cloud_bridge.mapping_contract import (  # noqa: E402
    apply_mapping_command_result,
    floor_map_name,
    mark_mapping_floor_imported,
    mapping_command_context,
    mapping_command_status,
    mapping_environment_precondition,
    mapping_finish_asset_registration_payload,
    mapping_runtime_precondition,
    mapping_start_precondition,
    normalize_mapping_session_request,
    recover_interrupted_mapping_sessions,
    prepare_mapping_session_create,
    sanitize_mapping_name,
    select_mapping_floor,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


class IdFactory:
    def __init__(self) -> None:
        self.counts = {}

    def __call__(self, prefix: str) -> str:
        count = self.counts.get(prefix, 0) + 1
        self.counts[prefix] = count
        return f"{prefix}_{count}"


def test_sanitize_mapping_name() -> None:
    assert_equal(sanitize_mapping_name(" F20 / desk map ", "fallback"), "F20_desk_map", "sanitize")
    assert_equal(sanitize_mapping_name(" .. ", "fallback"), "fallback", "fallback")


def test_normalize_mapping_session_request() -> None:
    request = normalize_mapping_session_request(
        {
            "name": "  ",
            "building": "B1",
            "mode": "",
            "floors": " F20, F21 ,, ",
            "map_name": " desk/test ",
        },
        default_project_name="M20Pro 工地巡检",
        default_map_name="{active_floor}_20260629_101010",
    )
    assert_equal(request["project_name"], "M20Pro 工地巡检", "default project")
    assert_equal(request["building"], "B1", "building")
    assert_equal(request["mode"], "multi", "mode")
    assert_equal(request["floors"], ["F20", "F21"], "floors")
    assert_equal(request["active_floor"], "F20", "active floor")
    assert_equal(request["map_name"], "desk_test", "map name")


def test_prepare_mapping_session_create_reuses_project() -> None:
    id_factory = IdFactory()
    project = {"id": "project_existing", "name": "Project", "building": "B1"}
    prepared = prepare_mapping_session_create(
        {"project_name": "Project", "building": "B1", "floors": ["F20"]},
        projects=[project],
        id_factory=id_factory,
        now_text=lambda: "2026-06-29 10:20:00",
        default_project_name="M20Pro 工地巡检",
        default_map_name="{active_floor}_stamp",
    )
    assert_equal(prepared["created_project"], None, "no new project")
    assert_equal(prepared["updated_project"]["floors"], ["F20"], "existing project registers floor")
    assert_equal(prepared["session"]["project_id"], "project_existing", "project id")
    assert_equal(prepared["session"]["id"], "map_session_1", "session id")
    assert_equal(prepared["session"]["map_name"], "F20_stamp", "map name")
    assert_equal(prepared["session"]["status"], "created", "status")
    assert_equal(
        prepared["session"]["floor_steps"],
        [{"floor": "F20", "map_name": "F20_stamp", "status": "ready", "updated_at": "2026-06-29 10:20:00"}],
        "single-floor step",
    )


def test_multi_floor_steps_and_selection() -> None:
    prepared = prepare_mapping_session_create(
        {
            "project_name": "Project",
            "building": "B1",
            "floors": ["F19", "F20", "F21"],
            "active_floor": "F20",
            "map_name": "F20_site",
        },
        projects=[{"id": "project_existing", "name": "Project", "building": "B1"}],
        id_factory=IdFactory(),
        now_text=lambda: "created",
        default_project_name="default",
        default_map_name="{active_floor}_stamp",
    )
    session = prepared["session"]
    assert_equal(
        [item["map_name"] for item in session["floor_steps"]],
        ["F19_site", "F20_site", "F21_site"],
        "floor-specific names",
    )
    assert_equal(floor_map_name("site", "F20", "F21", True), "site_F21", "generic base name")

    selected = select_mapping_floor(session, "F21", updated_at="selected")
    assert_equal(selected["ok"], True, "select floor")
    assert_equal(selected["session"]["active_floor"], "F21", "active floor after selection")
    assert_equal(selected["session"]["map_name"], "F21_site", "active map name after selection")
    assert_equal(selected["session"]["status"], "pending", "selected step status")
    assert_equal(select_mapping_floor(session, "F22", updated_at="now")["code"], "mapping_floor_missing", "missing floor")

    busy = dict(session)
    busy["status"] = "mapping"
    assert_equal(select_mapping_floor(busy, "F21", updated_at="now")["code"], "mapping_floor_busy", "busy floor")

    legacy = {
        "id": "legacy",
        "floors": ["F20", "F21"],
        "active_floor": "F20",
        "map_name": "F20_legacy",
        "status": "saved",
        "updated_at": "old",
    }
    migrated = select_mapping_floor(legacy, "F21", updated_at="migrated")
    assert_equal(migrated["ok"], True, "legacy session selection")
    assert_equal(migrated["session"]["map_name"], "F21_legacy", "legacy step map name")
    assert_equal(len(migrated["session"]["floor_steps"]), 2, "legacy steps persisted")


def test_per_floor_mapping_lifecycle() -> None:
    session = {
        "id": "s1",
        "active_floor": "F20",
        "map_name": "F20_site",
        "status": "created",
        "floor_steps": [
            {"floor": "F20", "map_name": "F20_site", "status": "ready"},
            {"floor": "F21", "map_name": "F21_site", "status": "pending"},
        ],
    }
    mapping = apply_mapping_command_result(
        session,
        param_name="dddmr_mapping_start_command",
        result={"ok": True},
        updated_at="mapping",
    )
    assert_equal(mapping["status"], "mapping", "session mapping")
    assert_equal(mapping["floor_steps"][0]["status"], "mapping", "step mapping")
    saved = apply_mapping_command_result(
        mapping,
        param_name="dddmr_mapping_finish_command",
        result={"ok": True},
        updated_at="saved",
    )
    assert_equal(saved["floor_steps"][0]["status"], "saved", "step saved")
    imported = mark_mapping_floor_imported(
        saved,
        floor="F20",
        map_id="map_20",
        updated_at="imported",
    )
    assert_equal(imported["floor_steps"][0]["status"], "imported", "step imported")
    assert_equal(imported["floor_steps"][0]["map_id"], "map_20", "step imported map")


def test_prepare_mapping_session_create_adds_project() -> None:
    id_factory = IdFactory()
    prepared = prepare_mapping_session_create(
        {"project_name": "", "building": "", "floors": []},
        projects=[],
        id_factory=id_factory,
        now_text=lambda: "2026-06-29 10:21:00",
        default_project_name="M20Pro 工地巡检",
        default_map_name="{active_floor}_stamp",
    )
    assert_equal(prepared["created_project"]["id"], "project_1", "new project id")
    assert_equal(prepared["created_project"]["floors"], [], "new empty project floor registry")
    assert_equal(prepared["session"]["project_id"], "project_1", "session project id")
    assert_equal(prepared["session"]["map_name"], "map_stamp", "fallback map name")


def test_mapping_command_status() -> None:
    assert_equal(mapping_command_status("dddmr_mapping_start_command", "created", {"ok": True}), "mapping", "start")
    assert_equal(mapping_command_status("dddmr_mapping_finish_command", "mapping", {"ok": True}), "saved", "finish")
    assert_equal(mapping_command_status("dddmr_mapping_cancel_command", "mapping", {"ok": True}), "cancelled", "cancel")
    assert_equal(mapping_command_status("unknown", "created", {"ok": True}), "created", "unknown ok")
    assert_equal(mapping_command_status("unknown", "created", {"manual_required": True}), "waiting_manual", "manual")
    assert_equal(mapping_command_status("unknown", "created", {"ok": False}), "created", "failure keeps status")
    assert_equal(
        mapping_command_status("dddmr_mapping_finish_command", "mapping", {"ok": False}),
        "failed",
        "failed finish is terminal",
    )


def test_mapping_start_precondition() -> None:
    assert_equal(mapping_start_precondition({"status": "created"})["ok"], True, "created can start")
    assert_equal(mapping_start_precondition({"status": "mapping"})["code"], "mapping_session_busy", "mapping is busy")
    assert_equal(mapping_start_precondition({"status": "saved"})["code"], "mapping_session_terminal", "saved is terminal")
    assert_equal(mapping_start_precondition({"status": "imported"})["code"], "mapping_session_terminal", "imported is terminal")
    assert_equal(mapping_start_precondition({"status": "failed"})["code"], "mapping_session_terminal", "failed is terminal")


def test_recover_interrupted_mapping_sessions() -> None:
    sessions = [
        {
            "id": "session_a",
            "status": "mapping",
            "project_name": "Project",
            "building": "B1",
            "active_floor": "F20",
            "floors": ["F20"],
            "map_name": "F20_site",
            "floor_steps": [
                {"floor": "F20", "map_name": "F20_site", "status": "mapping", "updated_at": "old"},
            ],
            "updated_at": "old",
        },
        {
            "id": "session_b",
            "status": "saved",
            "project_name": "Project",
            "building": "B1",
            "active_floor": "F21",
            "floors": ["F21"],
            "map_name": "F21_site",
            "floor_steps": [
                {"floor": "F21", "map_name": "F21_site", "status": "saved", "updated_at": "old"},
            ],
            "updated_at": "old",
        },
    ]
    recovered = recover_interrupted_mapping_sessions(
        sessions,
        mapping_status={"ok": True, "state": "idle"},
        now_text=lambda: "now",
    )
    assert_equal(recovered["changed"], True, "stale mapping recovered")
    assert_equal(recovered["sessions"][0]["status"], "cancelled", "stale session downgraded")
    assert_equal(
        recovered["sessions"][0]["status_message"],
        "三维建图服务已重启或退出，当前会话已自动取消，请重新创建建图任务",
        "stale session message",
    )
    assert_equal(recovered["sessions"][0]["failure_code"], "mapping_interrupted_restart", "failure code")
    assert_equal(recovered["sessions"][0]["floor_steps"][0]["status"], "cancelled", "step downgraded")
    assert_equal(recovered["sessions"][0]["floor_steps"][0]["updated_at"], "now", "step updated")
    assert_equal(recovered["sessions"][1]["status"], "saved", "saved session untouched")

    crashed = recover_interrupted_mapping_sessions(
        [dict(sessions[0])],
        mapping_status={"ok": True, "state": "error", "code": "lightning_mapping_process_died"},
        now_text=lambda: "crash",
    )
    assert_equal(crashed["sessions"][0]["status"], "failed", "crashed mapper fails session")
    assert_equal(
        crashed["sessions"][0]["failure_code"],
        "lightning_mapping_process_died",
        "crashed mapper failure code",
    )
    assert_equal(crashed["sessions"][0]["floor_steps"][0]["status"], "failed", "crashed step fails")

    live = recover_interrupted_mapping_sessions(
        [dict(sessions[0])],
        mapping_status={"ok": True, "state": "running"},
        now_text=lambda: "later",
    )
    assert_equal(live["changed"], False, "running session preserved")

    # 2026-08-31: a saving session with a live background save job must not
    # be downgraded while the job archives (mapper has already stopped).
    saving_session = dict(sessions[0])
    saving_session["status"] = "saving"
    saving_live = recover_interrupted_mapping_sessions(
        [saving_session],
        mapping_status={"ok": True, "state": "idle", "save_job_state": "running"},
        now_text=lambda: "during_save",
    )
    assert_equal(saving_live["changed"], False, "in-flight save job preserves saving session")
    saving_stale = recover_interrupted_mapping_sessions(
        [saving_session],
        mapping_status={"ok": True, "state": "idle"},
        now_text=lambda: "after_restart",
    )
    assert_equal(saving_stale["changed"], True, "saving session without live job still downgraded")


def test_mapping_environment_precondition() -> None:
    commands = {"start": "start", "finish": "finish", "cancel": "cancel", "status": "status"}
    idle = {
        "ok": True,
        "configured": True,
        "state": "idle",
        "package_available": True,
        "mapping_launch_available": True,
        "save_service_available": False,
    }
    assert_equal(mapping_environment_precondition(commands, idle)["ok"], True, "idle environment ready")

    missing = dict(commands)
    missing["status"] = ""
    missing_result = mapping_environment_precondition(missing, idle)
    assert_equal(missing_result["code"], "dddmr_mapping_commands_unconfigured", "status command required")
    assert_equal(missing_result["missing_commands"], ["status"], "missing status command")

    failed = dict(idle, ok=False, code="ssh_failed")
    assert_equal(mapping_environment_precondition(commands, failed)["code"], "ssh_failed", "status query required")
    package_missing = dict(idle, package_available=False, code="dddmr_runtime_missing")
    assert_equal(
        mapping_environment_precondition(commands, package_missing)["code"],
        "dddmr_runtime_missing",
        "mapping package required",
    )
    launch_missing = dict(idle, mapping_launch_available=False, code="dddmr_mapping_launch_missing")
    assert_equal(
        mapping_environment_precondition(commands, launch_missing)["code"],
        "dddmr_mapping_launch_missing",
        "mapping launch package required",
    )


def test_mapping_runtime_precondition() -> None:
    idle = {
        "ok": True,
        "configured": True,
        "state": "idle",
        "package_available": True,
        "mapping_launch_available": True,
        "save_service_available": False,
    }
    running = dict(idle, state="running", save_service_available=True)
    assert_equal(
        mapping_runtime_precondition("dddmr_mapping_start_command", idle)["ok"],
        True,
        "idle runtime can start",
    )
    assert_equal(
        mapping_runtime_precondition("dddmr_mapping_start_command", running)["code"],
        "dddmr_mapping_busy",
        "running runtime cannot start",
    )
    assert_equal(
        mapping_runtime_precondition("dddmr_mapping_finish_command", idle)["code"],
        "dddmr_mapping_not_running",
        "idle runtime cannot finish",
    )
    starting = dict(idle, state="starting")
    assert_equal(
        mapping_runtime_precondition("dddmr_mapping_finish_command", starting)["code"],
        "dddmr_mapping_starting",
        "starting runtime asks the operator to wait instead of failing as not running",
    )
    diverged = dict(idle, state="error", code="lightning_diverged", message="diverged")
    assert_equal(
        mapping_runtime_precondition("dddmr_mapping_finish_command", diverged)["code"],
        "lightning_diverged",
        "diverged mapper reports divergence instead of a generic not-running error",
    )
    died = dict(idle, state="error", code="lightning_mapping_process_died", message="died")
    assert_equal(
        mapping_runtime_precondition("dddmr_mapping_finish_command", died)["code"],
        "lightning_mapping_process_died",
        "dead mapper reports its own terminal code",
    )
    assert_equal(
        mapping_runtime_precondition("dddmr_mapping_finish_command", running)["ok"],
        True,
        "running runtime can finish",
    )
    no_save_service = dict(running, save_service_available=False)
    assert_equal(
        mapping_runtime_precondition("dddmr_mapping_finish_command", no_save_service)["code"],
        "dddmr_save_service_missing",
        "finish requires save service",
    )
    no_source_cloud = dict(idle, source_cloud_available=False)
    assert_equal(
        mapping_runtime_precondition("dddmr_mapping_start_command", no_source_cloud)["ok"],
        True,
        "start precondition must not block on source cloud: the start command self-heals the dense chain",
    )
    with_source_cloud = dict(idle, source_cloud_available=True)
    assert_equal(
        mapping_runtime_precondition("dddmr_mapping_start_command", with_source_cloud)["ok"],
        True,
        "idle runtime with source cloud can start",
    )
    finish_ignores_source_cloud = dict(running, source_cloud_available=False)
    assert_equal(
        mapping_runtime_precondition("dddmr_mapping_finish_command", finish_ignores_source_cloud)["ok"],
        True,
        "finish does not gate on source cloud",
    )
    assert_equal(
        mapping_runtime_precondition("dddmr_mapping_start_command", {"configured": False})["code"],
        "dddmr_mapping_status_unconfigured",
        "runtime status command required",
    )


def test_apply_mapping_command_result() -> None:
    session = {"id": "s1", "status": "created", "updated_at": "old"}
    updated = apply_mapping_command_result(
        session,
        param_name="dddmr_mapping_start_command",
        result={"ok": True},
        updated_at="new",
    )
    assert_equal(updated["status"], "mapping", "updated status")
    assert_equal(updated["updated_at"], "new", "updated at")
    assert_equal(session["status"], "created", "original unchanged")


def test_mapping_command_context() -> None:
    context = mapping_command_context(
        {
            "id": "session_a",
            "project_name": "Project",
            "building": "B1",
            "mode": "multi",
            "active_floor": "F20",
            "map_name": "desk/test",
            "floors": ["F20", "F21"],
        },
        factory_host="10.21.31.106",
        factory_user="user",
        factory_active_map="/home/user/active_map",
        map_archive_dir="/home/user/m20pro_maps",
    )
    assert_equal(context["session_id"], "session_a", "session id")
    assert_equal(context["map_name"], "desk_test", "sanitized map name")
    assert_equal(context["floors"], "F20,F21", "floors")
    assert_equal(context["factory_host"], "10.21.31.106", "factory host")


def test_mapping_finish_asset_registration_payload() -> None:
    session = {
        "id": "session_a",
        "project_name": "Project",
        "building": "B1",
        "active_floor": "F20",
        "map_name": "v4-test",
        "floor_steps": [{"floor": "F20", "map_name": "v4-test", "status": "saved"}],
    }
    result = {
        "ok": True,
        "backend": "lightning_lm",
        "map_id": "m20pro_F20_lightning_20260806_095415",
        "archive_target": "/root/lightning_maps/m20pro_F20_lightning_20260806_095415",
        "mapcloud": "/root/lightning_maps/m20pro_F20_lightning_20260806_095415/map.pcd",
        "mapground": "/root/lightning_maps/m20pro_F20_lightning_20260806_095415/ground.pcd",
        "poses": "/root/lightning_maps/m20pro_F20_lightning_20260806_095415/poses.pcd",
        "pose_graph_dir": "/root/lightning_maps/m20pro_F20_lightning_20260806_095415",
    }
    payload = mapping_finish_asset_registration_payload(
        session,
        result,
        source="lightning_lm_frontend_mapping",
        updated_at="now",
    )
    assert_equal(payload["floor"], "F20", "asset floor")
    assert_equal(payload["label"], "v4-test", "asset label from session")
    assert_equal(payload["source"], "lightning_lm_frontend_mapping", "asset source")
    assert_equal(payload["mapcloud"], [result["mapcloud"]], "mapcloud path")
    assert_equal(payload["mapground"], [result["mapground"]], "mapground path")
    assert_equal(payload["map_id"], result["map_id"], "map id preserved")
    assert_equal(payload["pose_graph_dir"], result["pose_graph_dir"], "pose graph preserved")
    assert "archive=/root/lightning_maps/m20pro_F20_lightning_20260806_095415" in payload["note"]

    fallback = mapping_finish_asset_registration_payload(
        session,
        {
            "ok": True,
            "archive_target": "/root/lightning_maps/fallback",
        },
        source="dddmr_3d_frontend_mapping",
        updated_at="now",
    )
    assert_equal(fallback["mapcloud"], ["/root/lightning_maps/fallback/map.pcd"], "fallback mapcloud")
    assert_equal(fallback["mapground"], ["/root/lightning_maps/fallback/ground.pcd"], "fallback mapground")
    assert_equal(fallback["pose_graph_dir"], "/root/lightning_maps/fallback", "fallback pose graph")


def test_web_finish_registers_dddmr_map_assets() -> None:
    web_source = (
        ROOT / "src/m20pro_cloud_bridge/m20pro_cloud_bridge/web_dashboard_node.py"
    ).read_text(encoding="utf-8")
    assert "mapping_finish_asset_registration_payload(" in web_source
    assert "self._register_dddmr_map_assets(asset_payload)" in web_source
    assert '"dddmr_map_asset_registration_failed"' in web_source
    assert '"mapcloud"' in web_source
    assert '"mapground"' in web_source


def main() -> int:
    for test in (
        test_sanitize_mapping_name,
        test_normalize_mapping_session_request,
        test_prepare_mapping_session_create_reuses_project,
        test_multi_floor_steps_and_selection,
        test_per_floor_mapping_lifecycle,
        test_prepare_mapping_session_create_adds_project,
        test_mapping_command_status,
        test_mapping_start_precondition,
        test_mapping_environment_precondition,
        test_mapping_runtime_precondition,
        test_apply_mapping_command_result,
        test_mapping_command_context,
        test_recover_interrupted_mapping_sessions,
        test_mapping_finish_asset_registration_payload,
        test_web_finish_registers_dddmr_map_assets,
    ):
        test()
        print(f"[OK] {test.__name__}")
    print("[OK] mapping contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
