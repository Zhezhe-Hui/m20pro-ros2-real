#!/usr/bin/env python3
"""Runtime checks for the read-only DDDMR acceptance script."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "104_accept_dddmr_field_test.sh"


class StateHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        if self.path.startswith("/api/dddmr/field_test"):
            if getattr(self.server, "field_test_not_found", False):
                self.send_response(404)
                self.end_headers()
                return
            body = getattr(self.server, "field_test_body", getattr(self.server, "state_body", b"{}"))
        elif self.path.startswith("/api/state"):
            body = getattr(self.server, "state_body", b"{}")
        else:
            self.send_response(404)
            self.end_headers()
            return
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *args: object) -> None:
        return


def _base_payload() -> dict:
    return {
        "next_steps": [
            "在当前地图保存 runtime.max_goal_distance_m 以内的短距离任务点",
            "生成单点任务后从任务列表启动，并保持手柄急停可用",
        ],
        "active_task": {"task_id": "task_done", "status": "succeeded"},
        "command_mux_status": {
            "last_update": time.time(),
            "parsed": {"mode": "navigation", "reason": "task_start", "output_nonzero": False},
        },
        "navigation_backend": {
            "backend": "dddmr_3d",
            "bridge_seen": True,
            "field_test": {
                "ready": True,
                "reason": "field_test_ready",
                "mode": "move",
                "runtime_backend": "field_proxy",
                "notes": [{"ready": True}, {"ready": True}],
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
                "num_satellites": 10,
                "hdop": 1.0,
            },
            "edge_cloud": {
                "ready": True,
                "code": "ok",
                "finite_points": 12000,
                "frame_id": "m20pro_base_link",
            },
            "map_3d": {
                "ready": True,
                "mapcloud_ready": True,
                "mapground_ready": True,
                "mapcloud_points": 1000,
                "mapground_points": 800,
            },
        },
        "dddmr_map_assets": {
            "workspace": {"ready_floor_count": 0, "floor_count": 0},
            "status": {
                "ready": True,
                "provisional": True,
                "source": "field_test_flat_map",
                "code": "field_test_flat_map_ready",
                "mapcloud_points": 1000,
                "mapground_points": 800,
            },
        },
    }


def _run_case(server: ThreadingHTTPServer, body: object) -> subprocess.CompletedProcess:
    if isinstance(body, (dict, list)):
        server.field_test_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        server.state_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
    elif isinstance(body, str):
        server.field_test_body = body.encode("utf-8")
        server.state_body = body.encode("utf-8")
    else:
        server.field_test_body = body
        server.state_body = body
    server.field_test_not_found = False
    url = "http://127.0.0.1:%d" % server.server_port
    return subprocess.run(
        [str(SCRIPT), url],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), StateHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        ready = _run_case(server, _base_payload())
        assert ready.returncode == 0, ready.stdout + ready.stderr
        assert "PASS field_test_ready" in ready.stdout
        assert "field_test_acceptance_ready" in ready.stdout
        assert "source=/api/dddmr/field_test" in ready.stdout
        assert "provisional=True" in ready.stdout
        assert "source=field_test_flat_map" in ready.stdout
        assert "runtime.ready=True" in ready.stdout
        assert "tf_ready=True" in ready.stdout
        assert "command_mux.seen=True" in ready.stdout
        assert "stale=False" in ready.stdout
        assert "age_s=" in ready.stdout
        assert "next_steps:" in ready.stdout
        assert "短距离任务点" in ready.stdout
        assert "手柄急停" in ready.stdout

        fallback_payload = _base_payload()
        server.state_body = json.dumps(fallback_payload, ensure_ascii=False).encode("utf-8")
        server.field_test_not_found = True
        url = "http://127.0.0.1:%d" % server.server_port
        fallback = subprocess.run(
            [str(SCRIPT), url],
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert fallback.returncode == 0, fallback.stdout + fallback.stderr
        assert "source=/api/state?debug=0" in fallback.stdout

        gate = _base_payload()
        gate["navigation_backend"]["field_test"]["ready"] = False
        gate["navigation_backend"]["field_test"]["reason"] = "dddmr_map_unavailable"
        gate_failed = _run_case(server, gate)
        assert gate_failed.returncode == 11, gate_failed.stdout + gate_failed.stderr
        assert "blocked_by=field_test" in gate_failed.stdout

        tf_gate = _base_payload()
        tf_gate["navigation_backend"]["field_test"]["ready"] = False
        tf_gate["navigation_backend"]["field_test"]["reason"] = "field_proxy_tf_unavailable"
        tf_gate["navigation_backend"]["runtime"]["ready"] = False
        tf_gate["navigation_backend"]["runtime"]["state"] = "waiting_tf"
        tf_gate["navigation_backend"]["runtime"]["code"] = "field_proxy_tf_unavailable"
        tf_gate["navigation_backend"]["runtime"]["tf_ready"] = False
        tf_gate["navigation_backend"]["runtime"]["tf_code"] = "field_proxy_tf_unavailable"
        tf_failed = _run_case(server, tf_gate)
        assert tf_failed.returncode == 11, tf_failed.stdout + tf_failed.stderr
        assert "FAIL field_proxy_tf_unavailable" in tf_failed.stdout
        assert "runtime.backend=field_proxy" in tf_failed.stdout
        assert "tf_ready=False" in tf_failed.stdout

        map_lock = _base_payload()
        map_lock["selected_map_status"] = {"ready": True, "code": "ready", "message": "地图一致"}
        map_lock["map_relocalization_required"] = {"map_id": "map_f1", "reason": "manual_select"}
        map_lock["localization_status"] = {"confirmed": False, "code": "map_relocalization_required"}
        map_lock["navigation_backend"]["field_test"]["acceptance"] = {
            "ready": False,
            "reason": "field_test_map_relocalization_required",
            "blocked_by": ["map_relocalization", "localization"],
            "field_test_ready": True,
            "field_test_reason": "field_test_ready",
            "mode": "move",
            "runtime_backend": "field_proxy",
            "command_mux": {
                "seen": True,
                "mode": "navigation",
                "reason": "idle",
                "output_nonzero": False,
                "stale": False,
                "age_s": 0.1,
            },
            "selected_map_status": map_lock["selected_map_status"],
            "map_relocalization_required": map_lock["map_relocalization_required"],
            "localization_status": map_lock["localization_status"],
        }
        map_lock["field_test"] = map_lock["navigation_backend"]["field_test"]
        map_lock["acceptance"] = map_lock["navigation_backend"]["field_test"]["acceptance"]
        map_lock["next_steps"] = ["当前固定地图仍有 2101 重定位锁，先在定位面板完成开发手册 2101 重定位"]
        map_lock_failed = _run_case(server, map_lock)
        assert map_lock_failed.returncode == 11, map_lock_failed.stdout + map_lock_failed.stderr
        assert "FAIL field_test_map_relocalization_required" in map_lock_failed.stdout
        assert "blocked_by=map_relocalization,localization" in map_lock_failed.stdout
        assert "2101" in map_lock_failed.stdout

        active = _base_payload()
        active["active_task"] = {"task_id": "task_active", "status": "running"}
        active_failed = _run_case(server, active)
        assert active_failed.returncode == 12, active_failed.stdout + active_failed.stderr
        assert "blocked_by=active_task" in active_failed.stdout

        mux = _base_payload()
        mux["command_mux_status"]["parsed"]["output_nonzero"] = True
        mux_failed = _run_case(server, mux)
        assert mux_failed.returncode == 13, mux_failed.stdout + mux_failed.stderr
        assert "blocked_by=command_mux" in mux_failed.stdout

        mux_missing = _base_payload()
        mux_missing.pop("command_mux_status", None)
        mux_missing_failed = _run_case(server, mux_missing)
        assert mux_missing_failed.returncode == 13, mux_missing_failed.stdout + mux_missing_failed.stderr
        assert "FAIL field_test_command_mux_status_missing" in mux_missing_failed.stdout
        assert "blocked_by=command_mux" in mux_missing_failed.stdout
        assert "command_mux.seen=False" in mux_missing_failed.stdout

        mux_stale = _base_payload()
        mux_stale["command_mux_status"]["last_update"] = time.time() - 10.0
        mux_stale_failed = _run_case(server, mux_stale)
        assert mux_stale_failed.returncode == 13, mux_stale_failed.stdout + mux_stale_failed.stderr
        assert "FAIL field_test_command_mux_status_stale" in mux_stale_failed.stdout
        assert "blocked_by=command_mux" in mux_stale_failed.stdout
        assert "stale=True" in mux_stale_failed.stdout

        malformed = _run_case(server, "{not-json")
        assert malformed.returncode == 10, malformed.stdout + malformed.stderr
        assert "web_state_unavailable" in malformed.stdout
    finally:
        server.shutdown()
        server.server_close()
    print("DDDMR acceptance runtime tests passed")


if __name__ == "__main__":
    main()
