#!/usr/bin/env python3
"""Runtime-level checks for Web task APIs exposing the DDDMR gate."""

from __future__ import annotations

import sys
import threading
import time
import types
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/m20pro_navigation"))
sys.path.insert(0, str(ROOT / "src/m20pro_cloud_bridge"))

from m20pro_cloud_bridge.web_dashboard_node import WebDashboardNode  # noqa: E402


def assert_equal(actual: Any, expected: Any, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


class _Parameter:
    def __init__(self, value: Any) -> None:
        self.value = value


class Runtime:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data_lock = threading.RLock()
        self._preflight_lock = threading.RLock()
        self._settings: Dict[str, Any] = {
            "selected_map_id": "map_f1",
            "working_map_id": "map_f1",
            "active_task": None,
            "map_relocalization_required": None,
        }
        self._state: Dict[str, Any] = {
            "map": {"available": True},
            "localization_ok": True,
            "pose": {
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "yaw": 0.0,
                "yaw_deg": 0.0,
                "last_update": time.time(),
            },
        }
        self._annotations: List[Dict[str, Any]] = [
            self._annotation("near", 1.0, 0.0),
            self._annotation("far", 4.2, 0.0),
        ]
        self._tasks: List[Dict[str, Any]] = [
            {"id": "task_near", "name": "near", "map_id": "map_f1", "annotation_ids": ["near"], "status": "ready", "created_at": "now"},
            {"id": "task_far", "name": "far", "map_id": "map_f1", "annotation_ids": ["far"], "status": "ready", "created_at": "now"},
            {"id": "task_multi", "name": "multi", "map_id": "map_f1", "annotation_ids": ["near", "far"], "status": "ready", "created_at": "now"},
        ]
        self.saved: List[str] = []
        self.events: List[Dict[str, Any]] = []

        for name in (
            "_create_task",
            "_field_test_task_gate_payload",
            "_task_start_pre_runtime_context",
            "_tasks_payload",
            "_validate_task_annotations_for_map",
        ):
            setattr(self, name, types.MethodType(getattr(WebDashboardNode, name), self))
        self._as_bool = WebDashboardNode._as_bool
        self._error = WebDashboardNode._error
        self._find_by_id = WebDashboardNode._find_by_id

    @staticmethod
    def _annotation(annotation_id: str, x: float, y: float) -> Dict[str, Any]:
        return {
            "id": annotation_id,
            "label": annotation_id,
            "type": "patrol",
            "manual_point_type": "task",
            "floor": "F1",
            "map_id": "map_f1",
            "pose": {"x": x, "y": y, "z": 0.0, "yaw": 0.0},
            "dwell_s": 0.0,
        }

    def get_parameter(self, name: str) -> _Parameter:
        values = {
            "task_start_pose_timeout_s": 3.0,
            "task_start_costmap_odom_tolerance_m": 0.75,
        }
        return _Parameter(values[name])

    def _snapshot(self, include_debug: bool = False) -> Dict[str, Any]:
        return {
            "pose": dict(self._state["pose"]),
            "pose_age_sec": 0.2,
            "pose_timeout_s": 3.0,
            "selected_map_status": self._selected_map_status_payload(selected_map_id="map_f1"),
            "map_relocalization_required": self._settings.get("map_relocalization_required"),
            "localization_status": {
                "confirmed": self._settings.get("map_relocalization_required") is None,
                "code": (
                    "localized_confirmed"
                    if self._settings.get("map_relocalization_required") is None
                    else "map_relocalization_required"
                ),
            },
            "navigation_backend": {
                "backend": "dddmr_3d",
                "runtime": {
                    "backend": "field_proxy",
                    "ready": True,
                    "max_goal_distance_m": 3.0,
                },
                "field_test": {
                    "ready": True,
                    "runtime_backend": "field_proxy",
                    "acceptance": {
                        "ready": True,
                        "reason": "field_test_acceptance_ready",
                        "blocked_by": [],
                    },
                },
            },
        }

    def _effective_map_id(self, requested_map_id: Optional[str] = None, runtime_state: Any = None) -> str:
        return str(requested_map_id or self._settings.get("selected_map_id") or "map_f1")

    def _remember_working_map_id(self, map_id: Optional[str], reason: str = "") -> None:
        self._settings["working_map_id"] = map_id

    def _selected_map_status_payload(self, runtime_state: Any = None, selected_map_id: Optional[str] = None) -> Dict[str, Any]:
        return {"ready": True, "map_id": selected_map_id or "map_f1"}

    def _preflight_with_age_unlocked(self) -> Dict[str, Any]:
        return {"ok": True}

    def _map_file_snapshot_cached(self, map_id: Optional[str], map_cache: Any = None) -> Dict[str, Any]:
        return self._map_file_snapshot(map_id)

    def _map_file_snapshot(self, map_id: Optional[str]) -> Dict[str, Any]:
        return {
            "available": True,
            "map_id": map_id or "map_f1",
            "floor": "F1",
            "width": 200,
            "height": 200,
            "resolution": 0.1,
            "origin": {"x": -10.0, "y": -10.0},
            "data": [0] * 40000,
        }

    def _build_unified_navigation_plan(
        self,
        annotation_ids: Any,
        annotations_by_id: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "ok": True,
            "single_floor": True,
            "floor_sequence": ["F1"],
            "transition_paths": [],
            "annotation_ids": list(annotation_ids or []),
            "segments": [
                {
                    "index": 0,
                    "floor": "F1",
                    "map_id": "map_f1",
                    "annotation_ids": list(annotation_ids or []),
                }
            ],
        }

    def _task_navigation_plan_state(
        self,
        task: Dict[str, Any],
        annotations_by_id: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        plan = self._build_unified_navigation_plan(task.get("annotation_ids") or [], annotations_by_id)
        return {"ok": True, "plan": plan, "record": {"ok": True, "annotation_ids": list(task.get("annotation_ids") or [])}}

    def _radar_jobs_for_task(self, task_id: str) -> List[Dict[str, Any]]:
        return []

    def _save_json(self, name: str, payload: Any) -> None:
        self.saved.append(name)

    def _append_event(self, name: str, payload: Dict[str, Any]) -> None:
        self.events.append({"name": name, "payload": payload})


def test_tasks_payload_exposes_gate_for_each_task() -> None:
    runtime = Runtime()
    payload = WebDashboardNode._tasks_payload(runtime, {"map_id": ["map_f1"]})
    gates = {task["id"]: task["field_test_task_gate"] for task in payload["tasks"]}
    assert_equal(gates["task_near"]["ready"], True, "near task ready")
    assert_equal(gates["task_near"]["code"], "field_test_task_ready", "near code")
    assert_equal(gates["task_far"]["ready"], False, "far task blocked")
    assert_equal(gates["task_far"]["code"], "field_test_goal_too_far", "far code")
    assert_equal(gates["task_multi"]["ready"], False, "multi task blocked")
    assert_equal(gates["task_multi"]["code"], "field_test_single_waypoint_required", "multi code")


def test_create_and_start_use_gate() -> None:
    runtime = Runtime()
    near = WebDashboardNode._create_task(runtime, {"name": "new near", "map_id": "map_f1", "annotation_ids": ["near"]})
    assert_equal(near["ok"], True, "near create ok")
    assert_equal(near["field_test_task_gate"]["code"], "field_test_task_ready", "near create gate")

    far = WebDashboardNode._create_task(runtime, {"name": "new far", "map_id": "map_f1", "annotation_ids": ["far"]})
    assert_equal(far["ok"], False, "far create blocked")
    assert_equal(far["code"], "field_test_goal_too_far", "far create code")
    assert_equal(far["field_test_task_gate"]["code"], "field_test_goal_too_far", "far create gate")

    start_far = WebDashboardNode._task_start_pre_runtime_context(runtime, {"task_id": "task_far"})
    assert_equal(start_far["ok"], False, "far start blocked")
    assert_equal(start_far["code"], "field_test_goal_too_far", "far start code")

    start_near = WebDashboardNode._task_start_pre_runtime_context(runtime, {"task_id": "task_near"})
    assert_equal(start_near["ok"], True, "near start ok")
    assert_equal(start_near["field_test_task_gate"]["code"], "field_test_task_ready", "near start gate")


def test_map_relocalization_lock_blocks_field_test_tasks() -> None:
    runtime = Runtime()
    runtime._settings["map_relocalization_required"] = {"map_id": "map_f1", "reason": "manual_select"}
    payload = WebDashboardNode._tasks_payload(runtime, {"map_id": ["map_f1"]})
    gates = {task["id"]: task["field_test_task_gate"] for task in payload["tasks"]}
    assert_equal(
        gates["task_near"]["code"],
        "field_test_map_relocalization_required",
        "near task gate reports relocalization lock",
    )
    assert_equal(
        gates["task_near"]["blocked_by"],
        ["map_relocalization"],
        "near task reports map/localization blockers",
    )

    create_near = WebDashboardNode._create_task(runtime, {"name": "blocked", "map_id": "map_f1", "annotation_ids": ["near"]})
    assert_equal(create_near["ok"], False, "create blocked by relocalization lock")
    assert_equal(create_near["code"], "field_test_map_relocalization_required", "create relocalization code")


def main() -> int:
    for test in (
        test_tasks_payload_exposes_gate_for_each_task,
        test_create_and_start_use_gate,
        test_map_relocalization_lock_blocks_field_test_tasks,
    ):
        test()
        print(f"[OK] {test.__name__}")
    print("[OK] DDDMR task gate runtime tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
