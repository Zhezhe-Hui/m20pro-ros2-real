#!/usr/bin/env python3
"""Offline tests for m20pro_cloud_bridge.web_runtime_contract."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/m20pro_cloud_bridge"))

from m20pro_cloud_bridge.web_runtime_contract import (  # noqa: E402
    api_error_payload,
    as_bool,
    fmt_age_text,
    payload_with_age,
    random_suffix,
    sanitize_name,
    parse_json_text,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_parse_json_text() -> None:
    assert_equal(parse_json_text('{"ok": true}'), {"ok": True}, "valid json")
    assert_equal(parse_json_text("{bad"), None, "invalid json returns none")


def test_age_helpers() -> None:
    assert_equal(fmt_age_text(None), "无时间", "none age")
    assert_equal(fmt_age_text(0.4), "<1s", "subsecond age")
    assert_equal(fmt_age_text(12.4), "12s前", "rounded age")
    assert_equal(payload_with_age(None), None, "empty payload")
    aged = payload_with_age({"timestamp": 95.0, "value": 1}, now=100.0)
    assert_equal(aged["age_sec"], 5.0, "age injected")
    assert_equal(aged["value"], 1, "payload value retained")


def test_name_bool_error_helpers() -> None:
    assert_equal(sanitize_name(" F20 / 配电室:入口 ", "fallback"), "F20_配电室_入口", "name sanitized")
    assert_equal(sanitize_name("///", "fallback"), "fallback", "fallback used")
    assert_true(as_bool(True), "bool true")
    assert_true(as_bool(" yes "), "string yes")
    assert_true(not as_bool("0"), "string zero")
    assert_equal(api_error_payload("失败"), {"ok": False, "message": "失败"}, "simple error")
    assert_equal(
        api_error_payload("失败", {"code": "bad"}),
        {"ok": False, "message": "失败", "code": "bad"},
        "error extra",
    )
    assert_equal(len(random_suffix(6)), 6, "short suffix length")
    assert_true(random_suffix(0), "suffix has minimum length")


def test_task_start_gate_wiring() -> None:
    source = (ROOT / "src/m20pro_cloud_bridge/m20pro_cloud_bridge/web_dashboard_node.py").read_text(
        encoding="utf-8"
    )
    assert_true(
        source.count("task_start_localization_gate_decision(") >= 2,
        "startup and forced dispatch both use the localization gate",
    )
    assert_true(
        'self.declare_parameter("goal_reached_tolerance_m", 0.35)' in source,
        "dashboard fallback matches field profile XY tolerance",
    )
    assert_true(
        'self.declare_parameter("enable_gnss_adapter", True)' in source,
        "dashboard can explain gnss disabled state from launch wiring",
    )
    assert_true(
        '"tf_ready": bool(runtime.get("tf_ready"))' in source
        and '"tf_code": str(runtime.get("tf_code") or "")' in source,
        "dashboard exposes field-proxy TF readiness",
    )
    assert_true(
        "field_test_task_gate(" in source
        and 'task["field_test_task_gate"]' in source
        and '"field_test_task_gate": context.get("field_test_task_gate")' in source,
        "task create/list/start all expose the DDDMR task gate",
    )
    assert_true(
        "def _dddmr_field_test_task_payload" in source
        and '"/api/dddmr/field_test_task"' in source
        and '"created": False' in source
        and '"created": True' in source
        and "未启动任务、未发送速度" in source,
        "DDDMR near-task API creates only ordinary task data and keeps motion separate",
    )
    assert_true(
        "task_start_requires_nav2_alignment" in source
        and "require_nav_alignment=require_nav_alignment" in source,
        "task start scopes Nav2 local-costmap alignment to Nav2-backed modes",
    )
    assert_true(
        "recover_interrupted_mapping_sessions(" in source
        and 'self._save_json("mapping_sessions.json", self._sessions)' in source,
        "startup clears interrupted mapping sessions and persists the result",
    )


def main() -> int:
    for test in (
        test_parse_json_text,
        test_age_helpers,
        test_name_bool_error_helpers,
        test_task_start_gate_wiring,
    ):
        test()
        print(f"[OK] {test.__name__}")
    print("[OK] web runtime contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
