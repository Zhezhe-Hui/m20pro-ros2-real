#!/usr/bin/env python3
"""Contract checks for the read-only DDDMR acceptance script."""

from pathlib import Path
import os


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def main() -> None:
    script_path = ROOT / "scripts" / "104_accept_dddmr_field_test.sh"
    report_path = ROOT / "scripts" / "104_dddmr_field_test_report.sh"
    script = script_path.read_text(encoding="utf-8")
    report = report_path.read_text(encoding="utf-8")
    scripts_readme = _read("scripts/README.md")
    root_readme = _read("README.md")
    dddmr_doc = _read("docs/dddmr_navigation_v1.md")
    frontend_contract = _read("docs/frontend_api_contract.md")
    frontend_html = _read("src/m20pro_cloud_bridge/m20pro_cloud_bridge/static/dashboard.html")
    frontend_script = _read("src/m20pro_cloud_bridge/m20pro_cloud_bridge/static/dashboard.js")
    backend = _read("src/m20pro_cloud_bridge/m20pro_cloud_bridge/web_dashboard_node.py")
    project_log = _read("m20pro日志.md")

    assert script_path.exists()
    assert os.access(script_path, os.X_OK)
    assert report_path.exists()
    assert os.access(report_path, os.X_OK)
    assert "navigation_backend_summary.py" in script
    assert "/api/dddmr/field_test" in script
    assert "/api/state?debug=0" in script
    assert "payload_source" in script
    assert "SUMMARY_JSON" in script
    assert "PAYLOAD_JSON" in script
    assert "_print_next_steps" in script
    assert "next_steps" in script
    assert "field_test" in script
    assert 'field_test.get("acceptance")' in script
    assert "blocked_by" in script
    assert "exit 10" in script
    assert "sys.exit(11)" in script
    assert "sys.exit(12)" in script
    assert "sys.exit(13)" in script
    assert "PASS field_test_ready" in script
    assert "assets.ready_floors" in script
    assert "asset_status.get(\"provisional\")" in script
    assert "asset_status.get(\"source\")" in script
    assert "runtime_detail" in script
    assert "tf_ready=%s" in script
    assert "tf_code=%s" in script
    assert "command_mux.seen=%s mode=%s output_nonzero=%s stale=%s age_s=%s reason=%s" in script
    assert "read-only acceptance" in script
    field_contract = _read("src/m20pro_navigation/m20pro_navigation/dddmr_field_test_contract.py")
    assert 'if not mux["seen"] or mux["stale"] or mux["output_nonzero"]:' in field_contract
    assert "field_test_command_mux_status_missing" in field_contract
    assert "field_test_command_mux_status_stale" in field_contract
    assert "selected_map_status" in field_contract
    assert "map_relocalization_required" in field_contract
    assert "localization_status" in field_contract
    assert "field_test_map_relocalization_required" in field_contract
    assert 'blocked_by.append("selected_map")' in field_contract
    assert 'blocked_by.append("map_relocalization")' in field_contract
    assert 'blocked_by.append("localization")' in field_contract
    assert "COMMAND_MUX_STATUS_TIMEOUT_S = 3.0" in field_contract
    task_contract = _read("src/m20pro_cloud_bridge/m20pro_cloud_bridge/task_contract.py")
    assert "field_test_selected_map_not_ready" in task_contract
    assert "field_test_map_relocalization_required" in task_contract
    assert "field_test_localization_not_confirmed" in task_contract
    assert "selected_map_status=state_snapshot.get" in backend
    assert "localization_status=state_snapshot.get" in backend
    assert "_refresh_field_test_acceptance_for_snapshot" in backend
    assert "确认 m20pro_command_mux 已启动" in backend
    assert "当前固定地图仍有 2101 重定位锁" in backend
    assert "scripts/104_status.sh 查看 command_mux" in backend
    assert "_active_task_running" not in script
    assert "_command_mux_unexpected_nonzero" not in script

    forbidden = (
        "/api/tasks/start",
        "/api/tasks/stop",
        "/api/teleop",
        "/api/localization",
        "/api/maps/select",
        "/m20pro/floor_goal",
        "ros2 topic pub",
        "ros2 action send_goal",
        "curl -X",
        "POST ",
        "DELETE ",
        "PUT ",
    )
    for token in forbidden:
        assert token not in script, token
        assert token not in report, token

    assert "read-only report" in report
    assert "/api/dddmr/field_test" in report
    assert "/api/state?debug=0" in report
    assert "/api/tasks" in report
    assert "/api/annotations?map_id=live_map" in report
    assert "/healthz" in report
    assert "navigation_backend_summary.py" in report
    assert "field_test_task_gate" in report
    assert "applicable=%s ready=%s blocked=%s total_tasks=%s" in report
    assert "next_steps" in report
    assert "command_mux.seen=%s mode=%s output_nonzero=%s stale=%s age_s=%s reason=%s" in report
    assert "[104_dddmr_field_test_report] map/localization:" in report
    assert "selected_map_status.ready=%s code=%s message=%s" in report
    assert "map_relocalization_required=true" in report
    assert "map_relocalization_required=false" in report
    assert "localization.confirmed=%s code=%s message=%s" in report
    assert "pose_fresh=%s pose_age_sec=%s pose_timeout_s=%s current_pose=%s" in report
    assert "edge_cloud.ready=%s finite_points=%s frame=%s code=%s" in report
    assert "map_3d.ready=%s mapcloud=%s mapground=%s assets.provisional=%s source=%s code=%s" in report
    assert "[104_dddmr_field_test_report] nearest_annotations:" in report
    assert "within_field_limit=%s" in report
    assert "no task, teleop, gait, localization, mode-switch, mapping, or velocity command will be sent" in report

    assert "104_accept_dddmr_field_test.sh" in scripts_readme
    assert "104_dddmr_field_test_report.sh" in scripts_readme
    assert "field_test.acceptance.ready" in scripts_readme
    assert "next_steps" in scripts_readme
    assert "field_test_task_gate" in scripts_readme
    assert "/api/dddmr/field_test_task" in scripts_readme
    assert "不会启动任务" in scripts_readme
    assert "selected_map_status" in scripts_readme
    assert "localization_status" in scripts_readme
    assert "nearest_annotations" in scripts_readme
    assert "field_test_command_mux_status_missing" in scripts_readme
    assert "field_test_command_mux_status_stale" in scripts_readme
    assert "/GPS" in scripts_readme
    assert "/m20pro/gnss/fix" in scripts_readme
    assert "104_accept_dddmr_field_test.sh" in root_readme
    assert "104_dddmr_field_test_report.sh" in root_readme
    assert "next_steps" in root_readme
    assert "field_test_task_gate" in root_readme
    assert "/api/dddmr/field_test_task" in root_readme
    assert "不会启动任务" in root_readme
    assert "selected_map_status" in root_readme
    assert "localization_status" in root_readme
    assert "nearest_annotations" in root_readme
    assert "field_test_command_mux_status_missing" in root_readme
    assert "field_test_command_mux_status_stale" in root_readme
    assert "/GPS" in root_readme
    assert "/m20pro/gnss/fix" in root_readme
    assert "/api/dddmr/field_test" in root_readme
    assert "104_accept_dddmr_field_test.sh" in dddmr_doc
    assert "104_dddmr_field_test_report.sh" in dddmr_doc
    assert "field_test.acceptance.ready" in dddmr_doc
    assert "field_test_task_gate" in dddmr_doc
    assert "/api/dddmr/field_test_task" in dddmr_doc
    assert "不会启动任务" in dddmr_doc
    assert "next_steps" in dddmr_doc
    assert "selected_map_status" in dddmr_doc
    assert "localization_status" in dddmr_doc
    assert "nearest_annotations" in dddmr_doc
    assert "/GPS" in dddmr_doc
    assert "/m20pro/gnss/fix" in dddmr_doc
    assert "用于 3D / 大地图参考" in dddmr_doc
    assert "field_test_command_mux_status_missing" in dddmr_doc
    assert "field_test_command_mux_status_stale" in dddmr_doc
    assert "navigation_backend.gnss" in dddmr_doc
    assert "/GPS" in dddmr_doc
    assert "/m20pro/gnss/fix" in dddmr_doc
    assert "104_accept_dddmr_field_test.sh" in frontend_contract
    assert "104_dddmr_field_test_report.sh" in frontend_contract
    assert "/api/dddmr/field_test" in frontend_contract
    assert "next_steps" in frontend_contract
    assert "field_test_task_gate" in frontend_contract
    assert "/api/dddmr/field_test_task" in frontend_contract
    assert "### POST `/api/dddmr/field_test_task`" in frontend_contract
    assert "不会调用" in frontend_contract
    assert "selected_map_status" in frontend_contract
    assert "localization_status" in frontend_contract
    assert "nearest_annotations" in frontend_contract
    assert "navigation_backend.gnss" in frontend_contract
    assert "field_test_command_mux_status_missing" in frontend_contract
    assert "field_test_command_mux_status_stale" in frontend_contract
    assert '"age_s": 0.2' in frontend_contract
    assert '"stale": false' in frontend_contract
    assert "source_topic" in frontend_contract
    assert "fix_topic" in frontend_contract
    assert "读取 DDDMR" not in frontend_html
    assert "生成 DDDMR 近点任务" not in frontend_html
    assert '"/api/dddmr/field_test"' in frontend_script
    assert '"/api/dddmr/field_test_task"' in frontend_script
    assert "refreshDddmrFieldTestBtn" in frontend_script
    assert "dddmrCreateFieldTestTaskBtn" in frontend_script
    assert "读取状态" in frontend_script
    assert "生成近点任务" in frontend_script
    assert "createDddmrFieldTestTask" in frontend_script
    assert "loadDddmrFieldTestAcceptance" in frontend_script
    assert "navigationGnssAuxText" in frontend_script
    assert "辅助锚点" in frontend_script
    assert "不会发送任务、速度、重定位或切图命令" in frontend_script
    assert "104_accept_dddmr_field_test.sh" in project_log
    assert "104_dddmr_field_test_report.sh" in project_log
    assert "/api/dddmr/field_test_task" in project_log

    print("DDDMR acceptance contract tests passed")


if __name__ == "__main__":
    main()
