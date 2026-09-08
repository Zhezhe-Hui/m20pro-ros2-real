#!/usr/bin/env python3
"""HTTP smoke for /api/tasks exposing the DDDMR gate."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


import rclpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/m20pro_navigation"))
sys.path.insert(0, str(ROOT / "src/m20pro_cloud_bridge"))

from m20pro_cloud_bridge.web_dashboard_node import WebDashboardNode  # noqa: E402


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def _annotation(annotation_id: str, x: float, y: float) -> dict:
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


def _write_test_map(map_dir: str) -> str:
    root = Path(map_dir)
    pgm = root / "map_f1.pgm"
    yaml = root / "map_f1.yaml"
    pgm.write_text(
        "P2\n"
        "4 4\n"
        "255\n"
        "254 254 254 254\n"
        "254 254 254 254\n"
        "254 254 254 254\n"
        "254 254 254 254\n",
        encoding="ascii",
    )
    yaml.write_text(
        "image: map_f1.pgm\n"
        "resolution: 1.0\n"
        "origin: [-2.0, -2.0, 0.0]\n"
        "negate: 0\n"
        "occupied_thresh: 0.65\n"
        "free_thresh: 0.196\n",
        encoding="utf-8",
    )
    return str(yaml)


def _write_floor_config(data_dir: str) -> str:
    path = Path(data_dir) / "runtime_navigation.yaml"
    path.write_text(
        "mission:\n"
        "  name: m20pro_runtime_navigation\n"
        "  frame_id: map\n"
        "  default_task_dwell_s: 5.0\n"
        "  default_transition_dwell_s: 0.0\n"
        "  default_charge_dwell_s: 0.0\n"
        "  default_goal_timeout_s: 90.0\n"
        "  default_retry_count: 1\n"
        "floors: {}\n",
        encoding="utf-8",
    )
    return str(path)


def _http_get_json(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=5.0) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return int(exc.code), json.loads(body) if body else {}


def _http_post_json(url: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5.0) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return int(exc.code), json.loads(body) if body else {}


def _task_count(node: WebDashboardNode) -> int:
    with node._data_lock:
        return len(node._tasks)


def _annotation_count(node: WebDashboardNode) -> int:
    with node._data_lock:
        return len(node._annotations)


def _active_task(node: WebDashboardNode) -> dict:
    with node._data_lock:
        active = node._settings.get("active_task")
    return dict(active) if isinstance(active, dict) else {}


def _install_field_test_state(node: WebDashboardNode, map_dir: str) -> None:
    now = time.time()
    yaml_path = _write_test_map(map_dir)
    with node._data_lock:
        node._settings.update(
            {
                "selected_map_id": "map_f1",
                "working_map_id": "map_f1",
                "active_task": None,
                "map_relocalization_required": None,
            }
        )
        node._maps = [{"id": "map_f1", "name": "F1", "floor": "F1", "yaml_path": yaml_path}]
        node._annotations = [_annotation("near", 1.0, 0.0), _annotation("far", 4.2, 0.0)]
        node._tasks = [
            {
                "id": "task_near",
                "name": "near",
                "map_id": "map_f1",
                "annotation_ids": ["near"],
                "status": "ready",
                "created_at": "now",
            },
            {
                "id": "task_far",
                "name": "far",
                "map_id": "map_f1",
                "annotation_ids": ["far"],
                "status": "ready",
                "created_at": "now",
            },
            {
                "id": "task_multi",
                "name": "multi",
                "map_id": "map_f1",
                "annotation_ids": ["near", "far"],
                "status": "ready",
                "created_at": "now",
            },
        ]
    with node._lock:
        node._state["pose"] = {
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "yaw": 0.0,
            "yaw_deg": 0.0,
            "last_update": now,
        }
        node._state["localization_ok"] = True
        live_map = node._map_file_snapshot("map_f1")
        node._state["map"] = {
            "available": True,
            "width": live_map.get("width"),
            "height": live_map.get("height"),
            "resolution": live_map.get("resolution"),
            "origin": live_map.get("origin"),
            "content_digest": live_map.get("content_digest"),
            "last_update": now,
        }
        node._state["navigation_backend_status"] = {
            "last_update": now,
            "parsed": {
                "ready": True,
                "motion_enabled": True,
                "action_type_available": True,
                "action_server_ready": True,
                "state": "ready",
            },
        }
        node._state["command_mux_status"] = {
            "last_update": now,
            "parsed": {
                "mode": "navigation",
                "reason": "idle",
                "output_nonzero": False,
                "updated_at": now,
            },
        }
        node._state["dddmr_runtime_status"] = {
            "last_update": now,
            "parsed": {
                "backend": "field_proxy",
                "ready": True,
                "state": "idle",
                "code": "field_proxy_ready",
                "tf_ready": True,
                "tf_code": "field_proxy_tf_ready",
                "max_goal_distance_m": 3.0,
            },
        }
        node._state["dddmr_edge_cloud_status"] = {
            "last_update": now,
            "parsed": {
                "ready": True,
                "code": "edge_cloud_ready",
                "frame_id": "m20pro_base_link",
                "finite_points": 200,
            },
        }
        node._state["dddmr_mapcloud"] = {
            "ready": True,
            "points": 100,
            "frame_id": "map",
            "last_update": now,
        }
        node._state["dddmr_mapground"] = {
            "ready": True,
            "points": 100,
            "frame_id": "map",
            "last_update": now,
        }
        node._state["dddmr_map_status"] = {
            "last_update": now,
            "parsed": {
                "ready": True,
                "floor": "F1",
                "provisional": False,
                "mapcloud_points": 100,
                "mapground_points": 100,
                "frame_id": "map",
                "code": "map_assets_ready",
            },
        }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="m20pro_field_gate_http_") as data_dir, tempfile.TemporaryDirectory(prefix="m20pro_field_gate_maps_") as map_dir:
        floor_config = _write_floor_config(data_dir)
        rclpy.init(
            args=[
                "--ros-args",
                "-p",
                "host:=127.0.0.1",
                "-p",
                "port:=0",
                "-p",
                f"data_dir:={data_dir}",
                "-p",
                f"map_archive_dir:={map_dir}",
                "-p",
                f"floor_config:={floor_config}",
                "-p",
                "navigation_backend:=dddmr_3d",
                "-p",
                "startup_sync_selected_map_to_nav2:=false",
                "-p",
                "auto_preflight_enabled:=false",
                "-p",
                "enable_camera_proxy:=false",
            ]
        )
        node = WebDashboardNode()
        try:
            _install_field_test_state(node, map_dir)
            port = int(node._server.server_port)
            base_url = f"http://127.0.0.1:{port}"
            status, payload = _http_get_json(f"{base_url}/api/tasks?map_id=map_f1")
            assert_equal(status, 200, "task list status")
            gates = {task["id"]: task["field_test_task_gate"] for task in payload["tasks"]}
            assert_equal(gates["task_near"]["ready"], True, "near task gate ready")
            assert_equal(gates["task_near"]["code"], "field_test_task_ready", "near task gate code")
            assert_equal(gates["task_far"]["ready"], False, "far task gate blocked")
            assert_equal(gates["task_far"]["code"], "field_test_goal_too_far", "far task gate code")
            assert_equal(gates["task_multi"]["ready"], False, "multi task gate blocked")
            assert_equal(
                gates["task_multi"]["code"],
                "field_test_single_waypoint_required",
                "multi task gate code",
            )

            before_tasks = _task_count(node)
            before_annotations = _annotation_count(node)
            status, preview = _http_get_json(
                f"{base_url}/api/dddmr/field_test_task?distance_m=1.0"
            )
            assert_equal(status, 200, "DDDMR task preview status")
            assert_equal(preview.get("ok"), True, "DDDMR task preview ok")
            assert_equal(preview.get("created"), False, "DDDMR task preview does not create")
            assert_equal(
                preview.get("field_test_task_gate", {}).get("code"),
                "field_test_task_ready",
                "DDDMR task preview gate code",
            )
            suggestion = preview.get("suggestion") or {}
            suggested_pose = suggestion.get("pose") or {}
            assert_equal(round(float(suggested_pose.get("x")), 3), 1.0, "preview suggested x")
            assert_equal(round(float(suggested_pose.get("y")), 3), 0.0, "preview suggested y")
            assert_equal(_task_count(node), before_tasks, "preview task count unchanged")
            assert_equal(
                _annotation_count(node),
                before_annotations,
                "preview annotation count unchanged",
            )

            status, created = _http_post_json(
                f"{base_url}/api/dddmr/field_test_task",
                {"distance_m": 1.0},
            )
            assert_equal(status, 200, "DDDMR task create status")
            assert_equal(created.get("ok"), True, "DDDMR task create ok")
            assert_equal(created.get("created"), True, "DDDMR task create flag")
            created_annotation = created.get("annotation") or {}
            created_task = created.get("task") or {}
            assert_equal(bool(created_annotation.get("id")), True, "created annotation id present")
            assert_equal(bool(created_task.get("id")), True, "created task id present")
            assert_equal(created_task.get("status"), "ready", "created task remains ready")
            assert_equal(
                created_task.get("annotation_ids"),
                [created_annotation.get("id")],
                "created task has exactly the created annotation",
            )
            assert_equal(
                created.get("field_test_task_gate", {}).get("code"),
                "field_test_task_ready",
                "created task gate code",
            )
            assert_equal(_active_task(node), {}, "DDDMR task create does not start task")
            assert_equal(_task_count(node), before_tasks + 1, "create task count increments")
            assert_equal(
                _annotation_count(node),
                before_annotations + 1,
                "create annotation count increments",
            )

            status, updated_tasks = _http_get_json(f"{base_url}/api/tasks?map_id=map_f1")
            assert_equal(status, 200, "task list after create status")
            listed = {
                task["id"]: task
                for task in updated_tasks.get("tasks") or []
                if isinstance(task, dict)
            }
            listed_created = listed.get(created_task.get("id"))
            assert_equal(bool(listed_created), True, "created task appears in task list")
            assert_equal(
                listed_created.get("field_test_task_gate", {}).get("code"),
                "field_test_task_ready",
                "created task list gate code",
            )
            assert_equal(listed_created.get("status"), "ready", "listed created task remains ready")
            assert_equal(
                updated_tasks.get("active_task") in ({}, None),
                True,
                "task list active task remains empty",
            )

            tasks_after_create = _task_count(node)
            annotations_after_create = _annotation_count(node)
            status, blocked = _http_post_json(
                f"{base_url}/api/dddmr/field_test_task",
                {"distance_m": 4.0},
            )
            assert_equal(status, 400, "far DDDMR task create status")
            assert_equal(blocked.get("ok"), False, "far DDDMR task create blocked")
            assert_equal(blocked.get("code"), "field_test_goal_too_far", "far DDDMR task code")
            assert_equal(_task_count(node), tasks_after_create, "far create task count unchanged")
            assert_equal(
                _annotation_count(node),
                annotations_after_create,
                "far create annotation count unchanged",
            )
            assert_equal(_active_task(node), {}, "far create does not start task")
        finally:
            node.destroy_node()
            rclpy.shutdown()
    print("[OK] DDDMR task gate HTTP smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
