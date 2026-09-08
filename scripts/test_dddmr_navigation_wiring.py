#!/usr/bin/env python3
"""Source wiring checks for the guarded DDDMR navigation backend."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAVIGATION = ROOT / "src/m20pro_navigation"
BRINGUP = ROOT / "src/m20pro_bringup"
CLOUD_BRIDGE = ROOT / "src/m20pro_cloud_bridge"
DDDMR_SYS_CORE = ROOT / "src/dddmr_sys_core"


def test_bridge_uses_the_existing_command_mux_boundary() -> None:
    bridge = (
        NAVIGATION / "m20pro_navigation/dddmr_nav2_bridge_node.py"
    ).read_text(encoding="utf-8")
    assert 'self.declare_parameter("dddmr_action", "/p2p_move_base")' in bridge
    assert 'self.declare_parameter("dddmr_cmd_vel_topic", "/dddmr/cmd_vel")' in bridge
    assert 'self.declare_parameter("navigation_cmd_vel_topic", "/cmd_vel_nav")' in bridge
    assert '"edge_cloud_status_topic", "/m20pro/dddmr/edge_cloud/status"' in bridge
    assert 'self.declare_parameter("require_edge_cloud", True)' in bridge
    assert 'self.declare_parameter("require_dddmr_map", False)' in bridge
    assert 'self.declare_parameter("map_cloud_topic", "/mapcloud")' in bridge
    assert 'self.declare_parameter("map_ground_topic", "/mapground")' in bridge
    assert 'self.declare_parameter("map_status_topic", "/m20pro/dddmr/map/status")' in bridge
    assert 'self.declare_parameter("require_map_status", False)' in bridge
    contract = (
        NAVIGATION / "m20pro_navigation/dddmr_navigation_contract.py"
    ).read_text(encoding="utf-8")
    assert '"dddmr_edge_cloud_unavailable"' in contract
    assert 'self.declare_parameter("motion_enabled", False)' in bridge
    assert "bounded_dddmr_velocity(" in bridge
    assert "dddmr_velocity_watchdog(" in bridge
    assert 'self.declare_parameter("watchdog_period_s", 0.1)' in bridge
    assert "self._cancel_backend_goal(backend_handle)" in bridge
    assert "def _cancel_late_backend_goal(self, future: Any) -> None:" in bridge
    assert "admission = self._admission()" in bridge
    assert "def request_shutdown(self) -> None:" in bridge
    assert 'self._fault_code = "dddmr_bridge_shutdown"' in bridge
    assert "self._publish_zero()" in bridge
    assert "map_qos = QoSProfile(depth=1)" in bridge
    assert "DurabilityPolicy.TRANSIENT_LOCAL" in bridge
    assert "self._on_map_status" in bridge
    assert "if rclpy.ok():" in bridge
    assert "rclpy.shutdown()" in bridge
    assert '"action_type_available": PToPMoveBase is not None' in bridge
    assert '"ready": bool(' in bridge
    assert '"/cmd_vel"' not in bridge
    assert (DDDMR_SYS_CORE / "action/PToPMoveBase.action").exists()

    map_asset_server = (
        NAVIGATION / "m20pro_navigation/dddmr_map_asset_server_node.py"
    ).read_text(encoding="utf-8")
    assert (
        'from .dddmr_map_asset_io import _finite_xyz, _parse_pcd, _split_paths'
        in map_asset_server
    )

    setup = (NAVIGATION / "setup.py").read_text(encoding="utf-8")
    assert (
        '"dddmr_action_bridge = m20pro_navigation.dddmr_nav2_bridge_node:main"'
        in setup
    )
    assert (
        '"dddmr_map_asset_server = m20pro_navigation.dddmr_map_asset_server_node:main"'
        in setup
    )


def test_real_launch_defaults_to_dddmr_only_and_requires_explicit_motion() -> None:
    real_launch = (BRINGUP / "launch/m20pro_real.launch.py").read_text(
        encoding="utf-8"
    )
    dddmr_runtime_launch = (BRINGUP / "launch/m20pro_dddmr_runtime.launch.py").read_text(
        encoding="utf-8"
    )
    top_launch = (BRINGUP / "launch/m20pro.launch.py").read_text(encoding="utf-8")
    for source in (real_launch, top_launch):
        assert '"navigation_backend"' in source
        assert 'default_value="dddmr_3d"' in source
        assert 'choices=["dddmr_3d"]' in source
        assert 'default_value="false"' in source
        assert 'dddmr_map_asset_reload_period_s' in source
        assert 'default_value="1.0"' in source
        if "default_dddmr_map_assets" in source:
            assert 'default_dddmr_map_assets = "/home/user/.m20pro_web/dddmr_map_assets.yaml"' in source
            assert 'default_value=default_dddmr_map_assets' in source
        else:
            assert 'default_value="/home/user/.m20pro_web/dddmr_map_assets.yaml"' in source
        assert 'DeclareLaunchArgument("dddmr_mapping_host", default_value="localhost")' in source

    assert 'executable="dddmr_action_bridge"' in real_launch
    assert 'executable="dddmr_edge_cloud_adapter"' in real_launch
    assert 'package="m20pro_bringup",\n            executable="dddmr_edge_cloud_adapter"' in real_launch
    assert 'executable="dddmr_map_asset_server"' in real_launch
    assert "m20pro_dddmr_runtime.launch.py" in real_launch
    assert '"params_file": os.path.join(' in real_launch
    assert 'bringup_share, "config", "dddmr_m20pro_navigation.yaml"' in real_launch
    runtime_launch = (BRINGUP / "launch/m20pro_dddmr_runtime.launch.py").read_text(
        encoding="utf-8"
    )
    assert 'default_value="official"' in runtime_launch
    assert 'choices=["official", "field_proxy"]' in runtime_launch
    assert 'executable="mcl_feature"' in runtime_launch
    assert 'executable="mcl_3dl"' in runtime_launch
    assert 'package="perception_3d"' in runtime_launch
    assert 'executable="perception_3d_ros_node"' in runtime_launch
    assert 'name="perception_3d_global"' in runtime_launch
    assert 'enable_global_perception' in runtime_launch
    assert 'p2p_move_base creates perception_3d_local' in runtime_launch
    assert '"perception_global_node": "perception_3d_global"' in runtime_launch
    # Both official executables create several named ROS nodes internally.
    # Applying launch-level name= would disable their named YAML sections.
    assert 'name="m20pro_dddmr_mcl_feature"' not in runtime_launch
    assert 'name="m20pro_dddmr_mcl_3dl"' not in runtime_launch
    assert 'executable="dddmr_legacy_base_tf_publisher"' in runtime_launch
    assert 'name="m20pro_dddmr_legacy_base_alias"' in runtime_launch
    assert 'legacy_base_frame' in runtime_launch
    assert 'enable_gnss_adapter": ParameterValue(' in real_launch
    assert 'default_value="/m20pro/edge_cloud"' in real_launch
    assert 'default_value="/m20pro/dddmr/edge_cloud_socket"' in real_launch
    assert 'dddmr_socket_cloud_topic = LaunchConfiguration("dddmr_socket_cloud_topic")' in real_launch
    assert '"output_topic": dddmr_socket_cloud_topic' in real_launch
    assert '"input_topic": dddmr_socket_cloud_topic' in real_launch
    assert '"floor_topic": "/m20pro/current_floor"' in real_launch
    assert 'default_value="/dddmr/edge_cloud"' in real_launch
    assert "dddmr_bridge_selected" in real_launch
    assert "dddmr_motion_enabled" in real_launch
    assert "dddmr_map_assets_selected" in real_launch
    assert real_launch.index(
        'web_dashboard_data_dir = LaunchConfiguration("web_dashboard_data_dir")'
    ) < real_launch.index("default_floor_config = PathJoinSubstitution(")
    assert '[web_dashboard_data_dir, "runtime_navigation.yaml"]' in real_launch
    assert '["\'", navigation_backend, "\' == \'dddmr_3d\'"]' in real_launch
    assert "nav2_runtime_enabled" not in real_launch
    assert "nav2_map_server" not in real_launch
    assert "nav2_navigation_real_foxy.launch.py" not in real_launch
    assert "nav2_startup_gate" not in real_launch
    assert '"require_nav2": False' in real_launch
    assert '"require_costmaps": False' in real_launch
    assert '"require_map": False' in real_launch
    assert '"navigate_to_pose_action": navigate_to_pose_action' in real_launch
    assert '"navigation_cmd_vel_topic": "/cmd_vel_nav"' in real_launch
    assert '"require_dddmr": ParameterValue(' in real_launch
    assert '"dddmr_edge_cloud_topic": dddmr_input_cloud_topic' in real_launch
    assert '"dddmr_map_cloud_topic": dddmr_map_cloud_topic' in real_launch
    assert '"dddmr_map_ground_topic": dddmr_map_ground_topic' in real_launch
    assert '"odom_topic": "/m20pro/dddmr/odom"' in real_launch
    assert 'executable="dddmr_socket_odom_publisher"' in dddmr_runtime_launch
    assert '"socket_path": motion_socket_path' in dddmr_runtime_launch
    assert '"output_topic": odom_topic' in dddmr_runtime_launch
    assert real_launch.count('"publish_odom_to_base_tf": ParameterValue(') == 2
    assert 'factory_map_tf_selected, value_type=bool' in real_launch
    assert '"enable_dddmr_bridge": enable_dddmr_bridge' in top_launch
    assert '"dddmr_action": dddmr_action' in top_launch
    assert '"dddmr_cmd_vel_topic": dddmr_cmd_vel_topic' in top_launch
    assert '"dddmr_socket_cloud_topic": dddmr_socket_cloud_topic' in top_launch
    adapter = (NAVIGATION / "m20pro_navigation/initialpose_3d_adapter.py").read_text(
        encoding="utf-8"
    )
    assert "resolved_z = self._finite_z(z_value)" in adapter
    assert 'floor_z_map[str(floor_id)] = float(z_value)' not in adapter
    web_node = (
        ROOT / "src/m20pro_cloud_bridge/m20pro_cloud_bridge/web_dashboard_node.py"
    ).read_text(encoding="utf-8")
    system_check = (
        NAVIGATION / "m20pro_navigation/system_check_node.py"
    ).read_text(encoding="utf-8")
    assert 'self.declare_parameter("require_dddmr", False)' in system_check
    assert 'self._mark_nonempty_cloud(edge_topic)' in system_check
    assert 'runtime_label = "DDDMR 3D"' in system_check
    assert "maps and Nav2 are active" not in system_check
    edge_adapter = (BRINGUP / "src/dddmr_edge_cloud_adapter.cpp").read_text(
        encoding="utf-8"
    )
    assert "cloud->data.size() / cloud->point_step" in edge_adapter
    assert 'last_code_ = "edge_cloud_ready"' not in edge_adapter
    assert '"edge_cloud_ready" : "edge_cloud_too_few_points"' in edge_adapter
    assert "output.fields = source.fields" in edge_adapter
    assert "point_data.insert" in edge_adapter
    assert "last_source_points_" in edge_adapter

    runtime_monitor = (
        NAVIGATION / "m20pro_navigation/dddmr_runtime_monitor_node.py"
    ).read_text(encoding="utf-8")
    assert 'self.declare_parameter("perception_global_node", "perception_3d_global")' in runtime_monitor
    assert "def _global_perception_ready(self) -> bool:" in runtime_monitor
    assert 'code = "dddmr_global_perception_unavailable"' in runtime_monitor
    assert '"global_perception_ready": global_perception_ready' in runtime_monitor
    assert 'self.declare_parameter("pose_topic", "/m20pro/dddmr/map_pose")' in runtime_monitor
    assert "DurabilityPolicy.TRANSIENT_LOCAL" in runtime_monitor
    assert "def _publish_pose(self) -> None:" in runtime_monitor
    assert "self._mcl_node_ready_cached = False" in runtime_monitor
    assert "self._global_perception_ready_cached = False" in runtime_monitor
    assert "self._callback_group = ReentrantCallbackGroup()" in runtime_monitor
    assert "callback_group=self._callback_group" in runtime_monitor
    assert "if not self._mcl_node_ready_cached or not self._tf_ready(transform, tf_age):" in runtime_monitor
    assert "self._mcl_node_ready_cached = self._mcl_node_ready()" in runtime_monitor
    assert "MultiThreadedExecutor(num_threads=2)" in runtime_monitor
    assert "executor.spin()" in runtime_monitor
    assert 'code = "dddmr_mcl_node_unavailable"' in runtime_monitor
    assert 'code = "dddmr_mcl_tf_unavailable"' in runtime_monitor
    assert '"mcl_node_ready": self._mcl_node_ready_cached' in runtime_monitor
    assert runtime_monitor.index('elif not self._mcl_node_ready_cached:') < runtime_monitor.index('elif not action_ready:')
    assert '"pose_topic": "/m20pro/dddmr/map_pose"' in real_launch
    assert 'runtime.get("mcl_ready") and runtime.get("tf_ready")' in web_node


def test_humble_bridge_launch_is_disabled_by_default() -> None:
    bridge_launch = (
        BRINGUP / "launch/m20pro_dddmr_bridge.launch.py"
    ).read_text(encoding="utf-8")
    assert 'DeclareLaunchArgument("enabled", default_value="false")' in bridge_launch
    assert (
        'DeclareLaunchArgument("motion_enabled", default_value="false")'
        in bridge_launch
    )
    assert 'default_value="/dddmr/cmd_vel"' in bridge_launch
    assert 'default_value="/cmd_vel_nav"' in bridge_launch
    assert 'default_value="/m20pro/dddmr/edge_cloud/status"' in bridge_launch
    assert 'default_value="/mapcloud"' in bridge_launch
    assert 'default_value="/mapground"' in bridge_launch
    assert 'default_value="/m20pro/dddmr/map/status"' in bridge_launch
    assert 'default_value="1.0"' in (
        BRINGUP / "launch/m20pro_real.launch.py"
    ).read_text(encoding="utf-8")
    assert 'DeclareLaunchArgument("enable_gnss_adapter", default_value="false")' in (
        BRINGUP / "launch/m20pro_web_dashboard.launch.py"
    ).read_text(encoding="utf-8")
    assert 'default_value="/home/user/.m20pro_web/dddmr_map_assets.yaml"' in (
        BRINGUP / "launch/m20pro_web_dashboard.launch.py"
    ).read_text(encoding="utf-8")
    assert 'DeclareLaunchArgument("dddmr_mapping_host", default_value="localhost")' in (
        BRINGUP / "launch/m20pro_web_dashboard.launch.py"
    ).read_text(encoding="utf-8")
    assert 'choices=["dddmr_3d"]' in (
        BRINGUP / "launch/m20pro_web_dashboard.launch.py"
    ).read_text(encoding="utf-8")
    assert 'default_value="/home/user/.m20pro_web/dddmr_map_assets.yaml"' in (
        BRINGUP / "launch/m20pro.launch.py"
    ).read_text(encoding="utf-8")
    smoke = (ROOT / "scripts/smoke_dddmr_edge_cloud_ros.py").read_text(
        encoding="utf-8"
    )
    assert "create_cloud_xyz32" in smoke
    assert "edge_cloud_frame_mismatch" in smoke
    bridge_smoke = (ROOT / "scripts/smoke_dddmr_bridge_action_ros.py").read_text(
        encoding="utf-8"
    )
    assert "require_dddmr_map:=true" in bridge_smoke
    assert "require_map_status:=true" in bridge_smoke
    assert "field_test_flat_map_ready" in bridge_smoke
    edge_source = (
        ROOT / "tools/edge_scan_feasibility/drdds_edge_scan_demo.cpp"
    ).read_text(encoding="utf-8")
    assert 'ChannelLidarPointCloud edge_cloud_pub' in edge_source
    assert '"/m20pro/edge_cloud"' in edge_source
    assert "edge_cloud_accumulator" in edge_source
    assert 'executable="dddmr_action_bridge"' in bridge_launch


def test_start_scripts_pass_the_backend_selection() -> None:
    full_source = (BRINGUP / "scripts" / "m20pro_real_full.sh").read_text(encoding="utf-8")
    assert 'if [[ "${MODE}" == "move" ]]; then' in full_source
    assert 'DEFAULT_NAVIGATION_BACKEND="dddmr_3d"' in full_source
    assert 'DEFAULT_ENABLE_DDDMR_BRIDGE="true"' in full_source
    assert 'DEFAULT_ENABLE_DDDMR_RUNTIME="false"' in full_source
    assert 'DEFAULT_DDDMR_RUNTIME_BACKEND="official"' in full_source
    assert 'M20PRO_NAVIGATION_BACKEND:-${DEFAULT_NAVIGATION_BACKEND}' in full_source
    assert 'M20PRO_ENABLE_DDDMR_BRIDGE:-${DEFAULT_ENABLE_DDDMR_BRIDGE}' in full_source
    assert 'M20PRO_ENABLE_DDDMR_RUNTIME:-${DEFAULT_ENABLE_DDDMR_RUNTIME}' in full_source
    assert 'M20PRO_DDDMR_RUNTIME_BACKEND:-${DEFAULT_DDDMR_RUNTIME_BACKEND}' in full_source
    assert 'ENABLE_DDDMR_MAP_ASSETS="${M20PRO_ENABLE_DDDMR_MAP_ASSETS:-}"' in full_source
    assert 'if [[ -z "${ENABLE_DDDMR_MAP_ASSETS}" ]]; then' in full_source
    assert 'ENABLE_DDDMR_MAP_ASSETS="true"' in full_source
    assert '/home/user/.m20pro_web/dddmr_map_assets.yaml' in full_source
    assert 'case "${NAVIGATION_BACKEND}" in' in full_source
    assert 'dddmr_3d) ;;' in full_source
    assert 'navigation_backend:="${NAVIGATION_BACKEND}"' in full_source
    assert 'enable_dddmr_bridge:="${ENABLE_DDDMR_BRIDGE}"' in full_source
    assert 'enable_dddmr_runtime:="${ENABLE_DDDMR_RUNTIME}"' in full_source
    assert 'dddmr_runtime_backend:="${DDDMR_RUNTIME_BACKEND}"' in full_source
    assert 'enable_dddmr_map_assets:="${ENABLE_DDDMR_MAP_ASSETS}"' in full_source
    assert 'dddmr_map_asset_manifest:="${DDDMR_MAP_ASSET_MANIFEST}"' in full_source
    assert "dddmr_mapping_host:" in full_source
    assert "dddmr_mapping_user:" in full_source
    assert "dddmr_mapping_start_command:" in full_source
    assert "dddmr_mapping_finish_command:" in full_source
    assert "dddmr_mapping_cancel_command:" in full_source
    assert "dddmr_mapping_status_command:" in full_source
    assert 'DDDMR_MAPPING_HOST="${M20PRO_DDDMR_MAPPING_HOST:-localhost}"' in full_source
    assert 'DDDMR_MAPPING_CONTROL_SCRIPT="${WS_DIR}/scripts/lightning_raw_mapping_control.sh"' in full_source
    assert 'if [[ "${MODE}" == "move" && "${NAVIGATION_BACKEND}" == "dddmr_3d" ]]; then' in full_source
    assert "${DDDMR_MAPPING_CONTROL_SCRIPT} start {floor}" in full_source
    assert "${DDDMR_MAPPING_CONTROL_SCRIPT} status {floor}" in full_source
    assert "{floor}}" not in full_source
    assert "selected_map_floor_for_launch" in full_source
    assert "SELECTED_MAP_YAML" not in full_source
    assert "render-nav2-yaml" not in full_source
    assert "RUNTIME_NAV2_PARAMS" not in full_source
    assert "real_nav2_params_file" not in full_source

    nav_source = (BRINGUP / "scripts" / "m20pro_real_nav.sh").read_text(encoding="utf-8")
    assert 'M20PRO_NAVIGATION_BACKEND:-dddmr_3d' in nav_source
    assert 'M20PRO_ENABLE_DDDMR_BRIDGE:-true' in nav_source
    assert 'DEFAULT_ENABLE_DDDMR_RUNTIME="false"' in nav_source
    assert 'M20PRO_DDDMR_RUNTIME_BACKEND:-official' in nav_source
    assert 'ENABLE_DDDMR_MAP_ASSETS="${M20PRO_ENABLE_DDDMR_MAP_ASSETS:-}"' in nav_source
    assert 'if [[ -z "${ENABLE_DDDMR_MAP_ASSETS}" ]]; then' in nav_source
    assert 'ENABLE_DDDMR_MAP_ASSETS="true"' in nav_source
    assert '/home/user/.m20pro_web/dddmr_map_assets.yaml' in nav_source
    assert 'case "${NAVIGATION_BACKEND}" in' in nav_source
    assert 'dddmr_3d) ;;' in nav_source
    assert 'navigation_backend:="${NAVIGATION_BACKEND}"' in nav_source
    assert 'enable_dddmr_bridge:="${ENABLE_DDDMR_BRIDGE}"' in nav_source
    assert 'enable_dddmr_runtime:="${ENABLE_DDDMR_RUNTIME}"' in nav_source
    assert 'dddmr_runtime_backend:="${DDDMR_RUNTIME_BACKEND}"' in nav_source
    assert 'enable_dddmr_map_assets:="${ENABLE_DDDMR_MAP_ASSETS}"' in nav_source
    assert 'dddmr_map_asset_manifest:="${DDDMR_MAP_ASSET_MANIFEST}"' in nav_source
    assert "dddmr_mapping_host:" in nav_source
    assert "dddmr_mapping_user:" in nav_source
    assert "dddmr_mapping_start_command:" in nav_source
    assert "dddmr_mapping_finish_command:" in nav_source
    assert "dddmr_mapping_cancel_command:" in nav_source
    assert "dddmr_mapping_status_command:" in nav_source
    assert 'DDDMR_MAPPING_HOST="${M20PRO_DDDMR_MAPPING_HOST:-localhost}"' in nav_source
    assert 'DDDMR_MAPPING_CONTROL_SCRIPT="${WS_DIR}/scripts/lightning_raw_mapping_control.sh"' in nav_source
    assert 'if [[ "${MODE}" == "move" && "${NAVIGATION_BACKEND}" == "dddmr_3d" ]]; then' in nav_source
    assert "${DDDMR_MAPPING_CONTROL_SCRIPT} start {floor}" in nav_source
    assert "${DDDMR_MAPPING_CONTROL_SCRIPT} status {floor}" in nav_source
    assert "{floor}}" not in nav_source
    assert "selected_map_floor_for_launch" in nav_source
    assert "SELECTED_MAP_YAML" not in nav_source

    web_source = (BRINGUP / "scripts" / "m20pro_real_web.sh").read_text(
        encoding="utf-8"
    )
    assert 'DDDMR_MAP_ASSET_MANIFEST="${M20PRO_DDDMR_MAP_ASSET_MANIFEST:-/home/user/.m20pro_web/dddmr_map_assets.yaml}"' in web_source
    assert 'dddmr_map_asset_manifest:="${DDDMR_MAP_ASSET_MANIFEST}"' in web_source
    assert 'ENABLE_GNSS_ADAPTER="${M20PRO_ENABLE_GNSS_ADAPTER:-false}"' in web_source
    assert 'gnss_status_topic:="${GNSS_STATUS_TOPIC}"' in web_source
    assert 'enable_gnss_adapter:="${ENABLE_GNSS_ADAPTER}"' in web_source
    assert 'DDDMR_MAPPING_HOST="${M20PRO_DDDMR_MAPPING_HOST:-localhost}"' in web_source
    assert 'LAUNCH_ARGS=(' in web_source
    assert 'if [[ -n "${DDDMR_MAPPING_START_COMMAND}" ]]' in web_source
    assert 'if [[ -n "${DDDMR_MAPPING_FINISH_COMMAND}" ]]' in web_source
    assert 'if [[ -n "${DDDMR_MAPPING_CANCEL_COMMAND}" ]]' in web_source
    assert 'if [[ -n "${DDDMR_MAPPING_STATUS_COMMAND}" ]]' in web_source
    assert "Nav2" not in web_source


def test_foxy_runtime_builder_accepts_a_fixed_offline_dddmr_source() -> None:
    source = (ROOT / "scripts/prepare_dddmr_foxy_runtime.sh").read_text(
        encoding="utf-8"
    )
    foxy_patch = (
        ROOT / "scripts/patches/dddmr_navigation/foxy_rosidl_typesupport.patch"
    ).read_text(encoding="utf-8")
    foxy_perception_patch = (
        ROOT / "scripts/patches/dddmr_navigation/foxy_perception_3d.patch"
    ).read_text(encoding="utf-8")
    foxy_pcl_patch = (
        ROOT / "scripts/patches/dddmr_navigation/foxy_pcl_version.patch"
    ).read_text(encoding="utf-8")
    foxy_ackermann_patch = (
        ROOT / "scripts/patches/dddmr_navigation/foxy_ackermann_msgs_dependency.patch"
    ).read_text(encoding="utf-8")
    foxy_lego_loam_bag_patch = (
        ROOT / "scripts/patches/dddmr_navigation/foxy_lego_loam_bag_tools.patch"
    ).read_text(encoding="utf-8")
    foxy_mcl_tf_patch = (
        ROOT / "scripts/patches/dddmr_navigation/foxy_mcl_tf_timestamp.patch"
    ).read_text(encoding="utf-8")
    foxy_tf2_header = (
        ROOT / "scripts/foxy_compat/include/tf2_eigen/tf2_eigen.hpp"
    ).read_text(encoding="utf-8")
    foxy_tf2_sensor_header = (
        ROOT / "scripts/foxy_compat/include/tf2_sensor_msgs/tf2_sensor_msgs.hpp"
    ).read_text(encoding="utf-8")
    ackermann_package = (ROOT / "src/ackermann_msgs/package.xml").read_text(
        encoding="utf-8"
    )
    ackermann_cmake = (ROOT / "src/ackermann_msgs/CMakeLists.txt").read_text(
        encoding="utf-8"
    )
    ackermann_drive = (ROOT / "src/ackermann_msgs/msg/AckermannDrive.msg").read_text(
        encoding="utf-8"
    )
    ackermann_drive_stamped = (
        ROOT / "src/ackermann_msgs/msg/AckermannDriveStamped.msg"
    ).read_text(encoding="utf-8")
    assert 'DDDMR_SOURCE_ROOT="${M20PRO_OFFICIAL_DDDMR_SOURCE_ROOT:-${ROOT_DIR}/vendor/dddmr_navigation}"' in source
    assert '"${DDDMR_SOURCE_ROOT}/src/dddmr_mcl_3dl"' in source
    assert '"${DDDMR_SOURCE_ROOT}/src/dddmr_p2p_move_base"' in source
    assert 'dddmr_source=offline:${DDDMR_SOURCE_ROOT}' in source
    assert 'ACKERMANN_MSGS_SOURCE_ROOT="${ROOT_DIR}/src/ackermann_msgs"' in source
    assert 'DDDMR_FOXY_ROSIDL_PATCH=' in source
    assert 'patch --batch --forward -d "${TARGET}/src/dddmr_navigation" -p1' in source
    assert "rosidl_target_interfaces" in foxy_patch
    assert "rosidl_get_typesupport_target" in foxy_patch
    assert "tf2_ros::CreateTimerROS" in foxy_perception_patch
    assert "std::vector<std::string>{}" in foxy_perception_patch
    assert "#include <vector>" in foxy_perception_patch
    assert "rcl_yaml_param_parser" in foxy_perception_patch
    assert "rclcpp/parameter_map.hpp" in foxy_perception_patch
    assert "find_package(PCL REQUIRED QUIET)" in foxy_pcl_patch
    assert "find_package(PCL 1.15 REQUIRED QUIET)" in foxy_pcl_patch
    assert "dddmr_lego_loam/lego_loam_bor" in foxy_pcl_patch
    assert "DDDMR_FOXY_ACKERMANN_PATCH=" in source
    assert "<depend>ackermann_msgs</depend>" in foxy_ackermann_patch
    assert "DDDMR_FOXY_LEGO_LOAM_BAG_TOOLS_PATCH=" in source
    assert "LEGO_LOAM_BOR_BUILD_BAG_TOOLS" in foxy_lego_loam_bag_patch
    assert "rosbag2_storage" in foxy_lego_loam_bag_patch
    assert "lego_loam_bag_lidar2depthimg_node" in foxy_lego_loam_bag_patch
    assert "DDDMR_FOXY_MCL_TF_TIMESTAMP_PATCH=" in source
    assert "map2odom_trans_.header.stamp = clock_->now();" in foxy_mcl_tf_patch
    assert "laser_header_.stamp" in foxy_mcl_tf_patch
    assert "<name>ackermann_msgs</name>" in ackermann_package
    assert "rosidl_default_generators" in ackermann_cmake
    assert "float32 steering_angle" in ackermann_drive
    assert "std_msgs/Header header" in ackermann_drive_stamped
    assert 'FOXY_COMPAT_ROOT="${ROOT_DIR}/scripts/foxy_compat"' in source
    assert 'tf2_eigen/tf2_eigen.hpp' in source
    assert 'tf2_geometry_msgs/tf2_geometry_msgs.hpp' in source
    assert 'CMAKE_CXX_FLAGS=-I${TARGET}/foxy_compat/include' in source
    assert "std::make_shared<tf2_ros::CreateTimerROS>" in source
    assert "get_node_timers_interface" in source
    assert "[A-Za-z0-9_]+_group_" in source
    assert "rclcpp::PARAMETER_STRING_ARRAY" in source
    assert "std::vector<std::string>{}" in source
    assert "rclcpp::PARAMETER_DOUBLE_ARRAY" in source
    assert "std::vector<double>{}" in source
    assert 'dddmr_local_planner' in source
    assert 'cloud_out = cloud_in;' in source
    assert 'pcl::PointCloud<pcl_t>::Ptr(new pcl::PointCloud<pcl_t>())' in source
    assert 'sync_request_in_flight_' in source
    assert 'if(sync_request_in_flight_)' in source
    assert 'sync_request_in_flight_ = true' in source
    assert 'sync_request_in_flight_ = false' in source
    assert 'map2odom_trans_.transform.translation.x = map_pos.x_' in source
    assert r'tf2::toMsg\(\s*tf2::Vector3' in source
    assert 'src/dddmr_mcl_3dl/src/sub_maps.cpp' in source
    assert 'src/dddmr_mcl_3dl/src/mcl_3dl.cpp' in source
    assert 'p2p_root="${TARGET}/src/dddmr_navigation/src/dddmr_p2p_move_base"' in source
    assert 'std::shared_future<rclcpp_action::ClientGoalHandle<dddmr_sys_core::action::GetPlan>::SharedPtr>' in source
    assert 'std::shared_future<rclcpp_action::ClientGoalHandle<dddmr_sys_core::action::RecoveryBehaviors>::SharedPtr>' in source
    assert 'auto goal_handle = goal_handle_future.get();' in source
    assert '-DLEGO_LOAM_BOR_BUILD_BAG_TOOLS=OFF' in source
    assert '#include <tf2_eigen/tf2_eigen.h>' in foxy_tf2_header
    assert '#include <tf2_sensor_msgs/tf2_sensor_msgs.h>' in foxy_tf2_sensor_header
    assert 'perception_3d:perception_3d_ros_node' in source
    assert 'required official DDDMR executable is missing' in source
    assert 'sudo apt remove' not in source
    assert 'vendored glog was not installed in the isolated runtime prefix' in source


def test_start_scripts_do_not_pass_empty_optional_launch_values() -> None:
    full_source = (BRINGUP / "scripts" / "m20pro_real_full.sh").read_text(
        encoding="utf-8"
    )
    nav_source = (BRINGUP / "scripts" / "m20pro_real_nav.sh").read_text(
        encoding="utf-8"
    )
    for source in (full_source, nav_source):
        assert 'if [[ -n "${DDDMR_MAPPING_START_COMMAND}" ]]' in source
        assert 'if [[ -n "${DDDMR_MAPPING_FINISH_COMMAND}" ]]' in source
        assert 'if [[ -n "${DDDMR_MAPPING_CANCEL_COMMAND}" ]]' in source
        assert 'if [[ -n "${DDDMR_MAPPING_STATUS_COMMAND}" ]]' in source
    assert 'if [[ -n "${DDDMR_MAPCLOUD_FILE}" ]]' in full_source
    assert 'if [[ -n "${DDDMR_MAPGROUND_FILE}" ]]' in full_source
    assert 'initial_floor:="${SELECTED_MAP_FLOOR}"' in full_source
    assert 'initial_floor:="${SELECTED_MAP_FLOOR}"' in nav_source
    assert 'if [[ -n "${M20PRO_DDDMR_MAPCLOUD_FILE:-}" ]]' in nav_source
    assert 'if [[ -n "${M20PRO_DDDMR_MAPGROUND_FILE:-}" ]]' in nav_source
    assert 'dddmr_map_asset_reload_period_s:="${DDDMR_MAP_ASSET_RELOAD_PERIOD_S}"' in full_source
    assert 'dddmr_map_asset_reload_period_s:="${DDDMR_MAP_ASSET_RELOAD_PERIOD_S}"' in nav_source


def test_cli_preflight_uses_only_dddmr_3d_runtime_gates() -> None:
    preflight = (ROOT / "scripts/104_preflight_check.sh").read_text(encoding="utf-8")
    web_dashboard = (
        CLOUD_BRIDGE / "m20pro_cloud_bridge/web_dashboard_node.py"
    ).read_text(encoding="utf-8")
    for expected in (
        "m20pro_dddmr_edge_cloud_adapter",
        "m20pro_dddmr_action_bridge",
        "m20pro_dddmr_map_asset_server",
        "/dddmr/edge_cloud",
        "/mapcloud",
        "/mapground",
        "/m20pro/cmd_vel_mux/status",
        'backend.get("backend") != "dddmr_3d"',
        'map_3d.get("ready")',
        'backend.get("action_server_ready")',
    ):
        assert expected in preflight
    for expected in (
        'self.declare_parameter("dddmr_edge_cloud_topic", "/dddmr/edge_cloud")',
        'self.declare_parameter("scan_topic", "/scan")',
        'edge_status_ready = (',
        'int(edge_payload.get("finite_points") or 0) > 0',
        'mapcloud/mapground are static 3D assets',
    ):
        assert expected in web_dashboard
    for forbidden in (
        "map_server",
        "controller_server",
        "planner_server",
        "bt_navigator",
        "/local_costmap/costmap",
        "/global_costmap/costmap",
        "topic_once 8 /scan",
        "Nav2/costmap",
        "/m20pro/command_mux/status",
    ):
        assert forbidden not in preflight
    assert "/LIDAR/POINTS" not in preflight
    assert "/LIDAR/POINTS" not in web_dashboard


if __name__ == "__main__":
    test_bridge_uses_the_existing_command_mux_boundary()
    test_real_launch_defaults_to_dddmr_only_and_requires_explicit_motion()
    test_humble_bridge_launch_is_disabled_by_default()
    test_start_scripts_pass_the_backend_selection()
    test_start_scripts_do_not_pass_empty_optional_launch_values()
    test_cli_preflight_uses_only_dddmr_3d_runtime_gates()
    print("DDDMR navigation wiring tests passed")
