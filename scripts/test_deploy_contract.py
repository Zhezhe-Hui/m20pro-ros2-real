#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    deploy = (ROOT / "scripts" / "local_deploy_to_test_robot.sh").read_text(
        encoding="utf-8"
    )
    edge = (ROOT / "scripts" / "local_deploy_edge_scan_to_106.sh").read_text(
        encoding="utf-8"
    )
    install = (ROOT / "scripts" / "104_install_staged_workspace.sh").read_text(
        encoding="utf-8"
    )
    bundle_maker_path = ROOT / "scripts" / "local_make_104_source_bundle.sh"
    bundle_installer_path = ROOT / "scripts" / "104_install_source_bundle.sh"
    bundle_maker = bundle_maker_path.read_text(encoding="utf-8")
    bundle_installer = bundle_installer_path.read_text(encoding="utf-8")
    windows_bundle_path = ROOT / "scripts" / "windows_deploy_104_bundle.ps1"
    windows_bundle = windows_bundle_path.read_text(encoding="utf-8")
    windows_runtime_path = ROOT / "scripts" / "test_windows_deploy_104_bundle_runtime.py"
    deploy_verify_path = ROOT / "scripts" / "104_verify_dddmr_field_test_deploy.sh"
    deploy_verify = deploy_verify_path.read_text(encoding="utf-8")
    full = (
        ROOT / "src/m20pro_bringup/scripts/m20pro_real_full.sh"
    ).read_text(encoding="utf-8")
    autostart = (ROOT / "scripts" / "104_enable_autostart.sh").read_text(
        encoding="utf-8"
    )
    status = (ROOT / "scripts" / "104_status.sh").read_text(encoding="utf-8")
    autostart_status = (ROOT / "scripts" / "104_autostart_status.sh").read_text(
        encoding="utf-8"
    )
    mirror = (ROOT / "scripts" / "104_update_from_mirror.sh").read_text(
        encoding="utf-8"
    )
    scripts_readme = (ROOT / "scripts" / "README.md").read_text(encoding="utf-8")

    assert "local_deploy_edge_scan_to_106.sh" in deploy
    assert "M20PRO_DEPLOY_PREPARE_ONLY" in deploy
    assert "m20pro_field_profile.py\" check" not in deploy
    assert "matched_on=104,106" not in deploy
    assert "field_profile_hash" not in deploy
    assert "sudo -n sed" not in deploy
    assert deploy.index("local_deploy_edge_scan_to_106.sh") < deploy.index("rsync -e")
    assert "104_prepare_staged_workspace.sh" in deploy
    assert "systemctl restart m20pro-edge-scan-106.service" in deploy
    assert 'if [[ "${M20PRO_DEPLOY_SKIP_EDGE:-0}" != "1" && "${PREPARE_ONLY}" != "1" ]]; then' in deploy
    assert 'if [[ "${PREPARE_ONLY}" == "1" ]]; then' in deploy
    assert 'perception.get("mode") == "edge_scan"' in deploy
    assert 'scan.get("frame_id") == "m20pro_base_link"' in deploy
    assert 'int(scan.get("finite_ranges") or 0) >= 20' in deploy
    assert "/api/dddmr/field_test" in deploy
    assert "DDDMR field_test" in deploy
    assert "provisional=%s source=%s" in deploy
    assert 'asset_status.get("parsed")' in deploy
    assert "M20PRO_DEPLOY_REQUIRE_DDDMR_FIELD_TEST" in deploy
    assert "exit 16" in deploy
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP" in full
    assert 'if [[ -z "${DDDMR_FIELD_TEST_FLAT_MAP}" ]]; then' in full
    assert "auto-enable 3D map assets for backend" in full
    assert "field_test_flat_map:=\"${DDDMR_FIELD_TEST_FLAT_MAP}\"" in full
    for excluded in (
        ".git/",
        "build/",
        "install/",
        "log/",
        "*/__pycache__/",
        "*.pyc",
        "bags/",
        "dist/",
        "*.db3",
        "杂项/",
        "dddmr_navigation/",
    ):
        assert excluded in deploy
    assert 'REVISION="${REVISION}-worktree"' in deploy
    assert bundle_maker_path.exists()
    assert bundle_installer_path.exists()
    assert "M20PRO_BUNDLE_OUTPUT_DIR" in bundle_maker
    assert "104_install_source_bundle.sh" in bundle_maker
    assert "windows_deploy_104_bundle.ps1" in bundle_maker
    assert "M20PRO_BUNDLE_REVISION" in bundle_maker
    assert "REVISION_FILE" in bundle_maker
    assert "sha256sum -c" in bundle_maker
    assert "--exclude='dist/'" in bundle_maker
    assert "--exclude='杂项/'" in bundle_maker
    assert "--exclude='dddmr_navigation/'" in bundle_maker
    assert "104_install_staged_workspace.sh" in bundle_installer
    assert 'bash "${STAGE}/scripts/104_install_staged_workspace.sh"' in bundle_installer
    assert "M20PRO_DEPLOY_BACKUP_DIR" in bundle_installer
    assert "M20PRO_BUNDLE_EXTRACT_ROOT" in bundle_installer
    assert 'REAL_MODE="${3:-move}"' in bundle_installer
    assert "104_accept_dddmr_field_test.sh" in bundle_installer
    assert "104_dddmr_field_test_report.sh" in bundle_installer
    assert windows_bundle_path.exists()
    assert windows_runtime_path.exists()
    assert "Windows PowerShell 104 deployment runtime smoke passed" in windows_runtime_path.read_text(encoding="utf-8")
    assert "[ValidateSet(\"move\", \"shadow\")]" in windows_bundle
    assert "Get-ChildItem -Path $DistDir -Filter \"m20pro_real_ros2_ws_*.tgz\"" in windows_bundle
    assert "$BundlePath.revision" in windows_bundle
    assert "Stage-File" in windows_bundle
    assert "Copy-Item -LiteralPath $SourcePath" in windows_bundle
    assert "$StageDir" in windows_bundle
    assert "UTF8Encoding($false)" in windows_bundle
    assert "[System.IO.File]::WriteAllText($RunnerPath, $RemoteScript, $Utf8NoBom)" in windows_bundle
    assert "& scp $StagedBundlePath $StagedShaPath $StagedInstallerPath" in windows_bundle
    assert "RemoteRunnerPath" in windows_bundle
    assert "& scp $RunnerPath" in windows_bundle
    assert '"-tt",' in windows_bundle
    assert "M20PRO_BUNDLE_REVISION=\"${REVISION}\"" in windows_bundle
    assert "104_verify_dddmr_field_test_deploy.sh" in windows_bundle
    assert "104_accept_dddmr_field_test.sh" in windows_bundle
    assert "104_dddmr_field_test_report.sh" in windows_bundle
    assert "RequireFieldReady" in windows_bundle
    assert "RestartEdge106" in windows_bundle
    assert "M20PRO_EDGE_HOST" in windows_bundle
    assert "m20pro-edge-scan-106.service" in windows_bundle
    assert "post-106-restart DDDMR acceptance" in windows_bundle
    assert "$InitialRequireReadyText" in windows_bundle
    assert "DryRun" in windows_bundle
    assert "ros2 topic pub" not in windows_bundle
    assert "ros2 action send_goal" not in windows_bundle
    assert "/api/tasks/start" not in windows_bundle
    assert deploy_verify_path.exists()
    assert "/api/dddmr/field_test" in deploy_verify
    assert "/api/dddmr/field_test_task?distance_m=1.0" in deploy_verify
    assert "/api/tasks?map_id=live_map&include_all=true" in deploy_verify
    assert "dddmrCreateFieldTestTaskBtn" in deploy_verify
    assert "createDddmrFieldTestTask" in deploy_verify
    assert "field_test_task_gate" in deploy_verify
    assert "read-only" in deploy_verify
    for forbidden_write in (
        "curl -X",
        "POST ",
        "DELETE ",
        "/api/tasks/start",
        "/api/tasks/stop",
        "/api/dddmr/field_test_mode",
        "/api/dddmr/mapping/start",
        "/api/localization",
        "ros2 topic pub",
        "ros2 action send_goal",
    ):
        assert forbidden_write not in deploy_verify, forbidden_write

    assert "106_enable_edge_scan_service.sh" in edge
    assert "tools/edge_scan_feasibility" in edge
    assert "m20pro_field_profile.yaml" in edge
    assert "field_profile_contract.py" in edge
    assert "m20pro_field_profile.py" in edge
    assert 'STAGE="${REMOTE_WS}.edge_stage.${STAMP}"' in edge
    assert "--no-owner --no-group" in edge
    assert '"${STAGE}/tools/edge_scan_feasibility/"' in edge
    assert 'sudo -n rsync -a --delete' in edge
    assert 'sudo -n chown -R' in edge
    assert 'systemctl restart m20pro-edge-scan-106.service' not in edge
    assert "systemctl is-enabled --quiet m20pro-edge-scan-106.service" in edge
    assert "systemctl is-active --quiet m20pro-edge-scan-106.service" in edge

    move_index = install.index('mv "${STAGE}" "${TARGET}"')
    build_index = install.index("colcon build --symlink-install")
    cutover_index = install.index("cutover_started=1", install.index("systemctl stop"))
    assert cutover_index < move_index
    assert move_index < build_index
    assert "A symlink install embeds absolute build paths" in install
    assert 'source /opt/robot/scripts/setup_ros2.sh' in install
    assert 'REAL_MODE="${5:-move}"' in install
    assert 'bash "${TARGET}/scripts/104_enable_autostart.sh" "${REAL_MODE}"' in install
    assert "rollback" in install
    assert "systemctl reset-failed m20pro-real.service" in install
    prepare = (ROOT / "scripts" / "104_prepare_staged_workspace.sh").read_text(
        encoding="utf-8"
    )
    assert 'ln -sfn "${STAGE}" "${LATEST_LINK}"' in prepare
    assert "latest" in prepare
    assert 'if [[ "${MODE}" == "move" ]]; then' in autostart
    assert 'WS_DIR="${M20PRO_WS:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"' in autostart
    assert 'DEFAULT_NAVIGATION_BACKEND="dddmr_3d"' in autostart
    assert 'DEFAULT_ENABLE_DDDMR_BRIDGE="true"' in autostart
    assert 'DEFAULT_ENABLE_DDDMR_RUNTIME="false"' in autostart
    assert 'DEFAULT_DDDMR_RUNTIME_BACKEND="official"' in autostart
    assert 'DEFAULT_DDDMR_FIELD_TEST_FLAT_MAP="false"' in autostart
    assert 'DEFAULT_DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M="2.0"' in autostart
    assert 'DEFAULT_DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M="0.25"' in autostart
    assert 'DEFAULT_DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M="0.0"' in autostart
    assert 'M20PRO_NAVIGATION_BACKEND=${M20PRO_NAVIGATION_BACKEND:-${DEFAULT_NAVIGATION_BACKEND}}' in autostart
    assert 'M20PRO_ENABLE_DDDMR_BRIDGE=${M20PRO_ENABLE_DDDMR_BRIDGE:-${DEFAULT_ENABLE_DDDMR_BRIDGE}}' in autostart
    assert 'M20PRO_ENABLE_DDDMR_RUNTIME=${M20PRO_ENABLE_DDDMR_RUNTIME:-${DEFAULT_ENABLE_DDDMR_RUNTIME}}' in autostart
    assert 'M20PRO_DDDMR_RUNTIME_BACKEND=${M20PRO_DDDMR_RUNTIME_BACKEND:-${DEFAULT_DDDMR_RUNTIME_BACKEND}}' in autostart
    assert 'M20PRO_DDDMR_FIELD_TEST_FLAT_MAP=${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP:-${DEFAULT_DDDMR_FIELD_TEST_FLAT_MAP}}' in autostart
    assert 'M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M=${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M:-${DEFAULT_DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M}}' in autostart
    assert 'M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M=${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M:-${DEFAULT_DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M}}' in autostart
    assert 'M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M=${M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M:-${DEFAULT_DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M}}' in autostart
    assert 'M20PRO_DDDMR_FIELD_TEST_MODE_SCRIPT=${M20PRO_DDDMR_FIELD_TEST_MODE_SCRIPT:-${DEFAULT_DDDMR_FIELD_TEST_MODE_SCRIPT}}' in autostart
    assert "EFFECTIVE_NAVIGATION_BACKEND" in autostart
    assert "lightning_raw_mapping_control.sh start {floor}" in autostart
    assert "lightning_raw_mapping_control.sh status {floor}" in autostart
    assert "M20PRO_DDDMR_MAPPING_HOST=${M20PRO_DDDMR_MAPPING_HOST:-localhost}" in autostart
    assert "M20PRO_ENABLE_INSPECTION=${M20PRO_ENABLE_INSPECTION:-false}" in autostart
    assert "M20PRO_INSPECTION_BACKEND=${M20PRO_INSPECTION_BACKEND:-rknn}" in autostart
    assert "best_rk3588_fp16.rknn" in autostart
    assert "models/best.pt" not in autostart
    assert "[104_status] DDDMR:" in status
    assert "navigation_backend_summary.py" in status
    assert "[104_autostart_status] DDDMR:" in autostart_status
    assert "navigation_backend_summary.py" in autostart_status
    assert "104_accept_dddmr_field_test.sh" in scripts_readme
    assert "field_test.acceptance.ready" in scripts_readme
    assert "ready/reason/blocked_by/provisional/source" in scripts_readme
    assert "/GPS" in scripts_readme
    assert "/m20pro/gnss/fix" in scripts_readme
    default_file = (ROOT / "systemd" / "m20pro-real.default").read_text(
        encoding="utf-8"
    )
    assert "M20PRO_NAVIGATION_BACKEND=dddmr_3d" in default_file
    assert "M20PRO_ENABLE_DDDMR_BRIDGE=true" in default_file
    assert "M20PRO_ENABLE_DDDMR_RUNTIME=true" in default_file
    assert "M20PRO_DDDMR_RUNTIME_BACKEND=official" in default_file
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP=false" in default_file
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_EXTENT_M=2.0" in default_file
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_SPACING_M=0.25" in default_file
    assert "M20PRO_DDDMR_FIELD_TEST_FLAT_MAP_HEIGHT_M=0.0" in default_file
    assert "M20PRO_DDDMR_FIELD_TEST_MODE_SCRIPT=/home/user/m20pro_real_ros2_ws_v4/scripts/104_dddmr_field_test_mode.sh" in default_file
    assert "M20PRO_DDDMR_MAPPING_HOST=localhost" in default_file
    assert "lightning_raw_mapping_control.sh start {floor}" in default_file
    assert "lightning_raw_mapping_control.sh status {floor}" in default_file
    assert "M20PRO_DEPLOY_REAL_MODE" in deploy
    assert 'DEPLOY_REAL_MODE="${M20PRO_DEPLOY_REAL_MODE:-move}"' in deploy
    assert 'real_mode=${DEPLOY_REAL_MODE}' in deploy
    assert 'invalid M20PRO_DEPLOY_REAL_MODE' in deploy
    assert "104_install_staged_workspace.sh" in deploy
    assert "DEPLOY_REAL_MODE" in deploy
    assert "REVISION" in deploy
    assert "DEPLOY_REAL_MODE" in deploy
    assert '"${DEPLOY_REAL_MODE}"' in deploy
    assert "REAL_MODE=\"${5:-move}\"" in install
    assert 'bash "${TARGET}/scripts/104_enable_autostart.sh" "${REAL_MODE}"' in install

    gitee_mirror = "git@gitee.com:gggghw/m20pro-ros2-real.git"
    assert f'M20PRO_REMOTE_URL:-{gitee_mirror}' in mirror
    assert "github.com" not in mirror
    assert gitee_mirror in scripts_readme
    assert "只读部署公钥" in scripts_readme

    assert "edge_previous_state" in deploy
    assert "systemctl stop m20pro-edge-scan-106.service" in deploy
    assert "systemctl disable m20pro-edge-scan-106.service" in deploy
    assert 'M20PRO_DEPLOY_KEEP_BACKUP:-0' in deploy
    assert "M20PRO_DEPLOY_SSH_KEY" in deploy
    assert "M20PRO_DEPLOY_EDGE_SSH_KEY" in deploy
    assert "RSYNC_SSH_COMMAND" in deploy
    assert "${BACKUP}.systemd'" in deploy
    assert "removed successful-deployment backup" in deploy

    print("test-robot deployment contract tests passed")


if __name__ == "__main__":
    main()
