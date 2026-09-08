#!/usr/bin/env python3
"""Runtime checks for the DDDMR-only task-start alignment gate."""

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
        self._teleop_lock = threading.RLock()
        self._teleop_session: Dict[str, Any] = {"active": False}
        self._teleop_acquiring = False
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
            # DDDMR does not use Nav2 local_costmap/odom as a start gate.
        }
        self._annotations: List[Dict[str, Any]] = [
            {
                "id": "near",
                "label": "near",
                "type": "patrol",
                "manual_point_type": "task",
                "floor": "F1",
                "map_id": "map_f1",
                "pose": {"x": 1.0, "y": 0.0, "z": 0.0, "yaw": 0.0},
                "dwell_s": 0.0,
            }
        ]
        self._tasks: List[Dict[str, Any]] = [
            {
                "id": "task_near",
                "name": "near",
                "map_id": "map_f1",
                "annotation_ids": ["near"],
                "status": "ready",
                "created_at": "now",
            }
        ]
        self.saved: List[str] = []
        self.events: List[Dict[str, Any]] = []
        self.reset_calls: List[Dict[str, Any]] = []
        self.mux_modes: List[str] = []
        self.dispatched = 0
        self.alignment_requests: List[bool] = []

        for name in (
            "_field_test_task_gate_payload",
            "_start_task",
            "_task_start_requires_nav2_alignment",
        ):
            setattr(self, name, types.MethodType(getattr(WebDashboardNode, name), self))
        self._error = WebDashboardNode._error
        self._find_by_id = WebDashboardNode._find_by_id

    def get_parameter(self, name: str) -> _Parameter:
        values = {
            "navigation_backend": "dddmr_3d",
            "task_start_pose_timeout_s": 3.0,
            "task_start_costmap_odom_tolerance_m": 0.75,
            "task_start_settle_s": 0.0,
        }
        return _Parameter(values[name])

    def _task_start_pre_runtime_context(
        self,
        payload: Dict[str, Any],
        *,
        require_nav_alignment: bool = False,
    ) -> Dict[str, Any]:
        self.alignment_requests.append(bool(require_nav_alignment))
        return WebDashboardNode._task_start_pre_runtime_context(
            self,
            payload,
            require_nav_alignment=require_nav_alignment,
        )

    def _snapshot(self, include_debug: bool = False) -> Dict[str, Any]:
        navigation_backend = {
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
        }
        return {
            "pose": dict(self._state["pose"]),
            "pose_age_sec": 0.2,
            "pose_timeout_s": 3.0,
            "navigation_backend": navigation_backend,
        }

    def _effective_map_id(
        self,
        requested_map_id: Optional[str] = None,
        runtime_state: Any = None,
    ) -> str:
        return str(requested_map_id or self._settings.get("selected_map_id") or "map_f1")

    def _remember_working_map_id(self, map_id: Optional[str], reason: str = "") -> None:
        self._settings["working_map_id"] = map_id

    def _validate_task_annotations_for_map(
        self,
        annotations: List[Dict[str, Any]],
        expected_map_id: str,
    ) -> Optional[Dict[str, Any]]:
        return None

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
        plan = self._build_unified_navigation_plan(
            task.get("annotation_ids") or [],
            annotations_by_id,
        )
        return {
            "ok": True,
            "plan": plan,
            "record": {
                "ok": True,
                "annotation_ids": list(task.get("annotation_ids") or []),
            },
        }

    def _save_json(self, name: str, payload: Any) -> None:
        self.saved.append(name)

    def _reset_navigation_session(self, reason: str, clear_costmaps: bool = False) -> None:
        self.reset_calls.append({"reason": reason, "clear_costmaps": clear_costmaps})

    def _set_command_mux_mode(self, mode: str, timeout_s: float = 1.0) -> Dict[str, Any]:
        self.mux_modes.append(mode)
        return {"ok": True, "mode": mode}

    def _append_active_task_timeline_event(
        self,
        active: Dict[str, Any],
        event: str,
        message: str,
        extra: Dict[str, Any],
    ) -> None:
        active.setdefault("timeline", []).append(
            {"event": event, "message": message, "extra": extra}
        )

    def _append_event(self, name: str, payload: Dict[str, Any]) -> None:
        self.events.append({"name": name, "payload": payload})

    def _dispatch_active_goal(self, force: bool = False) -> None:
        self.dispatched += 1


def test_dddmr_field_proxy_start_skips_nav2_costmap_alignment() -> None:
    runtime = Runtime()
    result = WebDashboardNode._start_task(runtime, {"task_id": "task_near"})
    assert_equal(result["ok"], True, "dddmr start should not need Nav2 local costmap")
    assert_equal(runtime.alignment_requests, [False, False], "dddmr skips second Nav2 alignment gate")
    assert_equal(runtime.mux_modes, ["navigation"], "command mux still switches to navigation")
    assert_equal(runtime.dispatched, 1, "goal dispatched once")
    assert_true(result.get("field_test_task_gate", {}).get("ready"), "DDDMR gate remains enforced")


def main() -> int:
    for test in (
        test_dddmr_field_proxy_start_skips_nav2_costmap_alignment,
    ):
        test()
        print(f"[OK] {test.__name__}")
    print("[OK] DDDMR task-start alignment runtime tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
