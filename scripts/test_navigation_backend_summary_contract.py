#!/usr/bin/env python3
"""Contract tests for the shared navigation backend summary helper."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from navigation_backend_summary import summarize_navigation_state  # noqa: E402

NOW_S = 1720000001.0


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError("%s: expected %r, got %r" % (message, expected, actual))


def assert_true(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_summarize_field_test_state() -> None:
    payload = {
        "active_task": {"task_id": "task_ready", "status": "succeeded"},
        "command_mux_status": {
            "last_update": NOW_S - 1.0,
            "parsed": {"mode": "navigation", "reason": "task_start", "output_nonzero": False},
        },
        "navigation_backend": {
            "backend": "dddmr_3d",
            "bridge_seen": True,
            "field_test_mode": {
                "available": True,
                "script": "/home/user/m20pro_real_ros2_ws/scripts/104_dddmr_field_test_mode.sh",
                "current": {
                    "mode": "dddmr_3d",
                    "label": "DDDMR",
                    "navigation_backend": "dddmr_3d",
                    "motion_enabled": True,
                    "ready": True,
                    "field_test_ready": True,
                },
            },
            "field_test": {
                "ready": True,
                "reason": "field_test_ready",
                "mode": "move",
                "runtime_backend": "field_proxy",
                "notes": [{"ready": True}, {"ready": False}],
            },
            "runtime": {
                "backend": "field_proxy",
                "ready": True,
                "state": "idle",
                "code": "field_proxy_ready",
                "tf_ready": True,
                "tf_code": "field_proxy_tf_ready",
                "max_goal_distance_m": 3.0,
            },
            "gnss": {
                "ready": True,
                "code": "gnss_anchor_ready",
                "anchor_usable": True,
                "source_topic": "/GPS",
                "fix_topic": "/m20pro/gnss/fix",
                "latitude": 30.1,
                "longitude": 120.2,
                "altitude_m": 18.5,
                "speed_kmh": 0.8,
                "course_deg": 91.0,
                "num_satellites": 10,
                "visible_satellites": 16,
                "pdop": 1.2,
                "hdop": 1.0,
                "vdop": 1.7,
            },
            "edge_cloud": {"ready": True, "code": "ok", "finite_points": 12000, "frame_id": "m20pro_base_link"},
            "map_3d": {
                "ready": True,
                "mapcloud_ready": True,
                "mapground_ready": True,
                "mapcloud_points": 1349135,
                "mapground_points": 1349135,
            },
        },
        "dddmr_map_assets": {
            "workspace": {"ready_floor_count": 1, "floor_count": 1},
            "status": {
                "ready": True,
                "provisional": True,
                "code": "field_test_flat_map_ready",
                "source": "field_test_flat_map",
                "floor": "F20",
                "mapcloud_points": 81,
                "mapground_points": 81,
            },
        },
    }

    summary = summarize_navigation_state(payload, now_s=NOW_S)
    assert_equal(summary["backend"], "dddmr_3d", "backend")
    assert_true(summary["bridge_seen"], "bridge seen")
    assert_equal(summary["ready"], True, "ready")
    assert_equal(summary["reason"], "field_test_ready", "reason")
    assert_equal(summary["mode"], "move", "mode")
    assert_equal(summary["runtime_backend"], "field_proxy", "runtime backend")
    assert_equal(summary["field_test_mode"]["available"], True, "DDDMR mode available")
    assert_equal(summary["field_test_mode"]["current_mode"], "dddmr_3d", "DDDMR mode current")
    assert_equal(summary["runtime"]["ready"], True, "runtime ready")
    assert_equal(summary["runtime"]["tf_ready"], True, "runtime tf ready")
    assert_equal(summary["runtime"]["tf_code"], "field_proxy_tf_ready", "runtime tf code")
    assert_equal(summary["notes_ready"], 1, "notes ready")
    assert_equal(summary["notes_total"], 2, "notes total")
    assert_equal(summary["field_test"]["acceptance"]["ready"], True, "acceptance ready")
    assert_equal(summary["field_test"]["acceptance"]["reason"], "field_test_acceptance_ready", "acceptance reason")
    assert_equal(summary["field_test"]["acceptance"]["blocked_by"], [], "acceptance blockers")
    assert_equal(summary["gnss"]["source_topic"], "/GPS", "gnss source topic")
    assert_equal(summary["gnss"]["fix_topic"], "/m20pro/gnss/fix", "gnss fix topic")
    assert_equal(summary["gnss"]["latitude"], 30.1, "gnss latitude")
    assert_equal(summary["gnss"]["visible_satellites"], 16, "gnss visible satellites")
    assert_equal(summary["edge_cloud"]["finite_points"], 12000, "edge points")
    assert_equal(summary["map_3d"]["mapcloud_ready"], True, "mapcloud ready")
    assert_equal(summary["assets"]["ready_floor_count"], 1, "asset ready floors")
    assert_equal(summary["assets"]["status"]["provisional"], True, "asset provisional")
    assert_equal(summary["assets"]["status"]["source"], "field_test_flat_map", "asset source")


def test_summarize_field_test_acceptance_blockers() -> None:
    payload = {
        "active_task": {"task_id": "task_active", "status": "running"},
        "command_mux_status": {
            "last_update": NOW_S - 1.0,
            "parsed": {"mode": "navigation", "reason": "task_start", "output_nonzero": False},
        },
        "navigation_backend": {
            "backend": "dddmr_3d",
            "bridge_seen": True,
            "field_test_mode": {
                "available": True,
                "script": "/home/user/m20pro_real_ros2_ws/scripts/104_dddmr_field_test_mode.sh",
                "current": {
                    "mode": "dddmr_3d",
                    "label": "DDDMR",
                    "navigation_backend": "dddmr_3d",
                    "motion_enabled": True,
                    "ready": True,
                    "field_test_ready": True,
                },
            },
            "field_test": {
                "ready": True,
                "reason": "field_test_ready",
                "mode": "move",
                "runtime_backend": "field_proxy",
                "notes": [],
            },
            "gnss": {
                "ready": True,
                "code": "gnss_anchor_ready",
                "anchor_usable": True,
                "source_topic": "/GPS",
                "fix_topic": "/m20pro/gnss/fix",
            },
            "edge_cloud": {"ready": True, "code": "ok", "finite_points": 12000, "frame_id": "m20pro_base_link"},
            "map_3d": {"ready": True, "mapcloud_ready": True, "mapground_ready": True},
        },
    }

    summary = summarize_navigation_state(payload, now_s=NOW_S)
    acceptance = summary["field_test"]["acceptance"]
    assert_equal(acceptance["ready"], False, "acceptance not ready")
    assert_equal(acceptance["reason"], "field_test_active_task_running", "acceptance active task reason")
    assert_equal(acceptance["blocked_by"], ["active_task"], "acceptance active task blockers")
    assert_equal(acceptance["active_task"]["running"], True, "active task running")


def test_summarize_field_test_command_mux_blocker() -> None:
    payload = {
        "active_task": {"task_id": "task_idle", "status": "succeeded"},
        "command_mux_status": {
            "last_update": NOW_S - 1.0,
            "parsed": {"mode": "navigation", "reason": "task_start", "output_nonzero": True},
        },
        "navigation_backend": {
            "backend": "dddmr_3d",
            "bridge_seen": True,
            "field_test_mode": {
                "available": True,
                "script": "/home/user/m20pro_real_ros2_ws/scripts/104_dddmr_field_test_mode.sh",
                "current": {
                    "mode": "dddmr_3d",
                    "label": "DDDMR",
                    "navigation_backend": "dddmr_3d",
                    "motion_enabled": True,
                    "ready": True,
                    "field_test_ready": True,
                },
            },
            "field_test": {
                "ready": True,
                "reason": "field_test_ready",
                "mode": "move",
                "runtime_backend": "field_proxy",
                "notes": [],
            },
            "gnss": {
                "ready": True,
                "code": "gnss_anchor_ready",
                "anchor_usable": True,
                "source_topic": "/GPS",
                "fix_topic": "/m20pro/gnss/fix",
            },
            "edge_cloud": {"ready": True, "code": "ok", "finite_points": 12000, "frame_id": "m20pro_base_link"},
            "map_3d": {"ready": True, "mapcloud_ready": True, "mapground_ready": True},
        },
    }

    summary = summarize_navigation_state(payload, now_s=NOW_S)
    acceptance = summary["field_test"]["acceptance"]
    assert_equal(acceptance["ready"], False, "acceptance not ready")
    assert_equal(acceptance["reason"], "field_test_command_mux_output_nonzero", "acceptance mux reason")
    assert_equal(acceptance["blocked_by"], ["command_mux"], "acceptance mux blockers")
    assert_equal(acceptance["command_mux"]["output_nonzero"], True, "command mux nonzero")


def test_summarize_field_test_command_mux_missing_blocks_acceptance() -> None:
    payload = {
        "active_task": {"task_id": "task_idle", "status": "succeeded"},
        "navigation_backend": {
            "backend": "dddmr_3d",
            "bridge_seen": True,
            "field_test_mode": {
                "available": True,
                "script": "/home/user/m20pro_real_ros2_ws/scripts/104_dddmr_field_test_mode.sh",
                "current": {
                    "mode": "dddmr_3d",
                    "label": "DDDMR",
                    "navigation_backend": "dddmr_3d",
                    "motion_enabled": True,
                    "ready": True,
                    "field_test_ready": True,
                },
            },
            "field_test": {
                "ready": True,
                "reason": "field_test_ready",
                "mode": "move",
                "runtime_backend": "field_proxy",
                "notes": [],
            },
            "gnss": {
                "ready": True,
                "code": "gnss_anchor_ready",
                "anchor_usable": True,
                "source_topic": "/GPS",
                "fix_topic": "/m20pro/gnss/fix",
            },
            "edge_cloud": {"ready": True, "code": "ok", "finite_points": 12000, "frame_id": "m20pro_base_link"},
            "map_3d": {"ready": True, "mapcloud_ready": True, "mapground_ready": True},
        },
    }

    summary = summarize_navigation_state(payload, now_s=NOW_S)
    acceptance = summary["field_test"]["acceptance"]
    assert_equal(acceptance["ready"], False, "acceptance not ready")
    assert_equal(
        acceptance["reason"],
        "field_test_command_mux_status_missing",
        "acceptance mux missing reason",
    )
    assert_equal(acceptance["blocked_by"], ["command_mux"], "acceptance mux missing blockers")
    assert_equal(acceptance["command_mux"]["seen"], False, "command mux missing seen")


def test_summarize_field_test_command_mux_stale_blocks_acceptance() -> None:
    payload = {
        "active_task": {"task_id": "task_idle", "status": "succeeded"},
        "command_mux_status": {
            "last_update": NOW_S - 10.0,
            "parsed": {"mode": "navigation", "reason": "task_start", "output_nonzero": False},
        },
        "navigation_backend": {
            "backend": "dddmr_3d",
            "bridge_seen": True,
            "field_test_mode": {
                "available": True,
                "script": "/home/user/m20pro_real_ros2_ws/scripts/104_dddmr_field_test_mode.sh",
                "current": {
                    "mode": "dddmr_3d",
                    "label": "DDDMR",
                    "navigation_backend": "dddmr_3d",
                    "motion_enabled": True,
                    "ready": True,
                    "field_test_ready": True,
                },
            },
            "field_test": {
                "ready": True,
                "reason": "field_test_ready",
                "mode": "move",
                "runtime_backend": "field_proxy",
                "notes": [],
            },
            "gnss": {
                "ready": True,
                "code": "gnss_anchor_ready",
                "anchor_usable": True,
                "source_topic": "/GPS",
                "fix_topic": "/m20pro/gnss/fix",
            },
            "edge_cloud": {"ready": True, "code": "ok", "finite_points": 12000, "frame_id": "m20pro_base_link"},
            "map_3d": {"ready": True, "mapcloud_ready": True, "mapground_ready": True},
        },
    }

    summary = summarize_navigation_state(payload, now_s=NOW_S)
    acceptance = summary["field_test"]["acceptance"]
    assert_equal(acceptance["ready"], False, "acceptance not ready")
    assert_equal(
        acceptance["reason"],
        "field_test_command_mux_status_stale",
        "acceptance mux stale reason",
    )
    assert_equal(acceptance["blocked_by"], ["command_mux"], "acceptance mux stale blockers")
    assert_equal(acceptance["command_mux"]["stale"], True, "command mux stale flag")
    assert_equal(acceptance["command_mux"]["age_s"], 10.0, "command mux age")


def test_summarize_field_test_multiple_blockers() -> None:
    payload = {
        "active_task": {"task_id": "task_active", "status": "running"},
        "command_mux_status": {
            "last_update": NOW_S - 1.0,
            "parsed": {"mode": "navigation", "reason": "task_start", "output_nonzero": True},
        },
        "navigation_backend": {
            "backend": "dddmr_3d",
            "bridge_seen": True,
            "field_test_mode": {
                "available": True,
                "script": "/home/user/m20pro_real_ros2_ws/scripts/104_dddmr_field_test_mode.sh",
                "current": {
                    "mode": "dddmr_3d",
                    "label": "DDDMR",
                    "navigation_backend": "dddmr_3d",
                    "motion_enabled": True,
                    "ready": True,
                    "field_test_ready": True,
                },
            },
            "field_test": {
                "ready": True,
                "reason": "field_test_ready",
                "mode": "move",
                "runtime_backend": "field_proxy",
                "notes": [],
            },
            "gnss": {
                "ready": True,
                "code": "gnss_anchor_ready",
                "anchor_usable": True,
                "source_topic": "/GPS",
                "fix_topic": "/m20pro/gnss/fix",
            },
            "edge_cloud": {"ready": True, "code": "ok", "finite_points": 12000, "frame_id": "m20pro_base_link"},
            "map_3d": {"ready": True, "mapcloud_ready": True, "mapground_ready": True},
        },
    }

    summary = summarize_navigation_state(payload, now_s=NOW_S)
    acceptance = summary["field_test"]["acceptance"]
    assert_equal(acceptance["ready"], False, "acceptance not ready")
    assert_equal(acceptance["reason"], "field_test_active_task_running", "acceptance multiple reason")
    assert_equal(acceptance["blocked_by"], ["active_task", "command_mux"], "acceptance multiple blockers")


def test_summarize_uses_declared_dddmr_mode() -> None:
    payload = {
        "navigation_backend": {
            "backend": "dddmr_3d",
            "bridge_seen": True,
            "field_test_mode": {
                "available": True,
                "script": "/home/user/m20pro_real_ros2_ws/scripts/104_dddmr_field_test_mode.sh",
                "current": {
                    "mode": "dddmr_3d",
                    "label": "DDDMR",
                    "navigation_backend": "dddmr_3d",
                    "motion_enabled": True,
                    "field_test_ready": True,
                },
            },
            "field_test": {
                "ready": True,
                "reason": "field_test_ready",
                "mode": "move",
                "runtime_backend": "field_proxy",
                "notes": [],
            },
        },
    }

    summary = summarize_navigation_state(payload, now_s=NOW_S)
    assert_equal(summary["backend"], "dddmr_3d", "dddmr backend")
    assert_equal(summary["field_test_mode"]["current_mode"], "dddmr_3d", "dddmr current mode")
    assert_equal(
        summary["field_test_mode"]["current_navigation_backend"],
        "dddmr_3d",
        "dddmr current navigation backend",
    )


def test_summarize_field_test_map_localization_blockers() -> None:
    payload = {
        "active_task": {"task_id": "task_idle", "status": "succeeded"},
        "command_mux_status": {
            "last_update": NOW_S - 1.0,
            "parsed": {"mode": "navigation", "reason": "idle", "output_nonzero": False},
        },
        "selected_map_status": {
            "ready": True,
            "code": "ready",
            "message": "地图一致",
        },
        "map_relocalization_required": {
            "map_id": "map_f1",
            "reason": "manual_select",
        },
        "localization_status": {
            "confirmed": False,
            "code": "map_relocalization_required",
        },
        "navigation_backend": {
            "backend": "dddmr_3d",
            "bridge_seen": True,
            "field_test": {
                "ready": True,
                "reason": "field_test_ready",
                "mode": "move",
                "runtime_backend": "field_proxy",
                "notes": [],
            },
            "runtime": {
                "backend": "field_proxy",
                "ready": True,
                "tf_ready": True,
                "max_goal_distance_m": 3.0,
            },
            "edge_cloud": {"ready": True, "code": "ok", "finite_points": 100, "frame_id": "m20pro_base_link"},
            "map_3d": {"ready": True, "mapcloud_ready": True, "mapground_ready": True},
        },
    }

    summary = summarize_navigation_state(payload, now_s=NOW_S)
    acceptance = summary["field_test"]["acceptance"]
    assert_equal(acceptance["ready"], False, "map/localization acceptance not ready")
    assert_equal(
        acceptance["reason"],
        "field_test_map_relocalization_required",
        "map relocalization reason",
    )
    assert_equal(
        acceptance["blocked_by"],
        ["map_relocalization", "localization"],
        "map/localization blockers",
    )
    assert_equal(
        acceptance["localization_status"]["code"],
        "map_relocalization_required",
        "localization detail is retained",
    )


def test_summarize_uses_top_level_field_test_mode() -> None:
    payload = {
        "navigation_backend": {
            "backend": "dddmr_3d",
            "field_test": {"ready": False, "reason": "field_proxy_tf_unavailable"},
        },
        "field_test_mode": {
            "available": True,
            "script": "/home/user/m20pro_real_ros2_ws/scripts/104_dddmr_field_test_mode.sh",
            "current": {
                "mode": "dddmr_3d",
                "label": "DDDMR",
                "navigation_backend": "dddmr_3d",
                "motion_enabled": True,
                "field_test_ready": False,
            },
        },
    }

    summary = summarize_navigation_state(payload, now_s=NOW_S)
    assert_equal(summary["field_test_mode"]["available"], True, "top-level mode available")
    assert_equal(
        summary["field_test_mode"]["script"],
        "/home/user/m20pro_real_ros2_ws/scripts/104_dddmr_field_test_mode.sh",
        "top-level mode script",
    )
    assert_equal(summary["field_test_mode"]["current_label"], "DDDMR", "top-level mode label")
    assert_equal(summary["field_test_mode"]["current_motion_enabled"], True, "top-level motion flag")


def test_summarize_handles_missing_state() -> None:
    summary = summarize_navigation_state({})
    assert_equal(summary["backend"], "", "empty backend")
    assert_equal(summary["ready"], False, "empty ready")
    assert_equal(summary["notes_total"], 0, "empty notes")
    assert_equal(summary["assets"]["floor_count"], 0, "empty assets")


if __name__ == "__main__":
    test_summarize_field_test_state()
    test_summarize_field_test_acceptance_blockers()
    test_summarize_field_test_command_mux_blocker()
    test_summarize_field_test_command_mux_missing_blocks_acceptance()
    test_summarize_field_test_command_mux_stale_blocks_acceptance()
    test_summarize_field_test_multiple_blockers()
    test_summarize_uses_declared_dddmr_mode()
    test_summarize_field_test_map_localization_blockers()
    test_summarize_uses_top_level_field_test_mode()
    test_summarize_handles_missing_state()
    print("navigation backend summary contract tests passed")
