import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, TimerAction
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from m20pro_navigation.field_profile_contract import (
    command_mux_field_parameters,
    floor_manager_field_parameters,
    load_field_profile,
    stair_executor_field_parameters,
    web_navigation_field_parameters,
    web_teleoperation_field_parameters,
)
def generate_launch_description():
    bringup_share = get_package_share_directory("m20pro_bringup")
    inspection_share = get_package_share_directory("m20pro_inspection")
    radar_share = get_package_share_directory("m20pro_radar_inspection")
    default_params = os.path.join(bringup_share, "config", "m20pro_real.yaml")
    default_field_profile = os.path.join(
        bringup_share, "config", "m20pro_field_profile.yaml"
    )
    field_profile = load_field_profile(default_field_profile)
    floor_manager_parameters = floor_manager_field_parameters(field_profile)
    command_mux_parameters = command_mux_field_parameters(field_profile)
    stair_executor_parameters = stair_executor_field_parameters(field_profile)
    web_navigation_parameters = web_navigation_field_parameters(field_profile)
    web_teleoperation_parameters = web_teleoperation_field_parameters(field_profile)
    default_map_manifest = os.path.join(bringup_share, "config", "map_manifest.yaml")
    default_dddmr_map_assets = "/home/user/.m20pro_web/dddmr_map_assets.yaml"
    default_rviz = os.path.join(bringup_share, "rviz", "m20pro_dddmr_3d.rviz")
    inspection_launch = os.path.join(inspection_share, "launch", "m20pro_inspection.launch.py")
    default_inspection_model = os.path.join(inspection_share, "models", "best_rk3588_fp16.rknn")
    default_inspection_classes = os.path.join(inspection_share, "models", "labels_zh.txt")
    radar_launch = os.path.join(radar_share, "launch", "m20pro_radar_inspection.launch.py")

    params_file = LaunchConfiguration("params_file")
    floor_config = LaunchConfiguration("floor_config")
    map_manifest = LaunchConfiguration("map_manifest")
    scan_topic = LaunchConfiguration("scan_topic")
    navigation_backend = LaunchConfiguration("navigation_backend")
    enable_dddmr_bridge = LaunchConfiguration("enable_dddmr_bridge")
    enable_dddmr_runtime = LaunchConfiguration("enable_dddmr_runtime")
    dddmr_runtime_backend = LaunchConfiguration("dddmr_runtime_backend")
    dddmr_action = LaunchConfiguration("dddmr_action")
    dddmr_cmd_vel_topic = LaunchConfiguration("dddmr_cmd_vel_topic")
    dddmr_edge_cloud_topic = LaunchConfiguration("dddmr_edge_cloud_topic")
    dddmr_socket_cloud_topic = LaunchConfiguration("dddmr_socket_cloud_topic")
    dddmr_input_cloud_topic = LaunchConfiguration("dddmr_input_cloud_topic")
    enable_dddmr_socket_bridge = LaunchConfiguration("enable_dddmr_socket_bridge")
    dddmr_socket_cloud_path = LaunchConfiguration("dddmr_socket_cloud_path")
    dddmr_edge_cloud_status_topic = LaunchConfiguration(
        "dddmr_edge_cloud_status_topic"
    )
    dddmr_map_cloud_topic = LaunchConfiguration("dddmr_map_cloud_topic")
    dddmr_map_ground_topic = LaunchConfiguration("dddmr_map_ground_topic")
    enable_dddmr_map_assets = LaunchConfiguration("enable_dddmr_map_assets")
    dddmr_map_asset_manifest = LaunchConfiguration("dddmr_map_asset_manifest")
    dddmr_map_asset_reload_period_s = LaunchConfiguration("dddmr_map_asset_reload_period_s")
    dddmr_mapcloud_file = LaunchConfiguration("dddmr_mapcloud_file")
    dddmr_mapground_file = LaunchConfiguration("dddmr_mapground_file")
    dddmr_map_max_points = LaunchConfiguration("dddmr_map_max_points")
    dddmr_field_test_flat_map = LaunchConfiguration("dddmr_field_test_flat_map")
    dddmr_field_test_flat_map_extent_m = LaunchConfiguration("dddmr_field_test_flat_map_extent_m")
    dddmr_field_test_flat_map_spacing_m = LaunchConfiguration("dddmr_field_test_flat_map_spacing_m")
    dddmr_field_test_flat_map_height_m = LaunchConfiguration("dddmr_field_test_flat_map_height_m")
    dddmr_map_status_topic = LaunchConfiguration("dddmr_map_status_topic")
    dddmr_navigate_to_pose_action = LaunchConfiguration(
        "dddmr_navigate_to_pose_action"
    )
    dddmr_mapping_host = LaunchConfiguration("dddmr_mapping_host")
    dddmr_mapping_user = LaunchConfiguration("dddmr_mapping_user")
    dddmr_mapping_start_command = LaunchConfiguration("dddmr_mapping_start_command")
    dddmr_mapping_finish_command = LaunchConfiguration("dddmr_mapping_finish_command")
    dddmr_mapping_cancel_command = LaunchConfiguration("dddmr_mapping_cancel_command")
    dddmr_mapping_status_command = LaunchConfiguration("dddmr_mapping_status_command")
    enable_floor_manager = LaunchConfiguration("enable_floor_manager")
    enable_floor_goal_bridge = LaunchConfiguration("enable_floor_goal_bridge")
    enable_stair_connector = LaunchConfiguration("enable_stair_connector")
    enable_system_check = LaunchConfiguration("enable_system_check")
    enable_config_audit = LaunchConfiguration("enable_config_audit")
    initial_floor = LaunchConfiguration("initial_floor")
    enable_initialpose_3d_adapter = LaunchConfiguration("enable_initialpose_3d_adapter")
    initialpose_3d_z = LaunchConfiguration("initialpose_3d_z")
    enable_web_dashboard = LaunchConfiguration("enable_web_dashboard")
    web_dashboard_port = LaunchConfiguration("web_dashboard_port")
    web_dashboard_data_dir = LaunchConfiguration("web_dashboard_data_dir")
    default_floor_config = PathJoinSubstitution(
        [web_dashboard_data_dir, "runtime_navigation.yaml"]
    )
    web_dashboard_map_archive_dir = LaunchConfiguration("web_dashboard_map_archive_dir")
    robot_pose_display_yaw_offset_rad = LaunchConfiguration("robot_pose_display_yaw_offset_rad")
    initialpose_topic = LaunchConfiguration("initialpose_topic")
    relocalization_result_topic = LaunchConfiguration("relocalization_result_topic")
    factory_host = LaunchConfiguration("factory_host")
    factory_user = LaunchConfiguration("factory_user")
    factory_active_map = LaunchConfiguration("factory_active_map")
    factory_mapping_start_command = LaunchConfiguration("factory_mapping_start_command")
    factory_mapping_finish_command = LaunchConfiguration("factory_mapping_finish_command")
    factory_mapping_cancel_command = LaunchConfiguration("factory_mapping_cancel_command")
    enable_stair_zone_postprocess = LaunchConfiguration("enable_stair_zone_postprocess")
    stair_zones_topic = LaunchConfiguration("stair_zones_topic")
    enable_camera_proxy = LaunchConfiguration("enable_camera_proxy")
    front_camera_url = LaunchConfiguration("front_camera_url")
    rear_camera_url = LaunchConfiguration("rear_camera_url")
    camera_proxy_backend = LaunchConfiguration("camera_proxy_backend")
    camera_proxy_fps = LaunchConfiguration("camera_proxy_fps")
    camera_proxy_jpeg_quality = LaunchConfiguration("camera_proxy_jpeg_quality")
    camera_proxy_ffmpeg_mjpeg_qscale = LaunchConfiguration("camera_proxy_ffmpeg_mjpeg_qscale")
    camera_proxy_max_width = LaunchConfiguration("camera_proxy_max_width")
    camera_proxy_transport = LaunchConfiguration("camera_proxy_transport")
    enable_inspection = LaunchConfiguration("enable_inspection")
    inspection_backend = LaunchConfiguration("inspection_backend")
    inspection_source_type = LaunchConfiguration("inspection_source_type")
    inspection_rtsp_url = LaunchConfiguration("inspection_rtsp_url")
    inspection_camera_name = LaunchConfiguration("inspection_camera_name")
    inspection_model_path = LaunchConfiguration("inspection_model_path")
    inspection_class_names_path = LaunchConfiguration("inspection_class_names_path")
    enable_radar_inspection = LaunchConfiguration("enable_radar_inspection")
    radar_backend = LaunchConfiguration("radar_backend")
    radar_device_url = LaunchConfiguration("radar_device_url")
    radar_request_timeout_s = LaunchConfiguration("radar_request_timeout_s")
    radar_poll_interval_s = LaunchConfiguration("radar_poll_interval_s")
    radar_max_wait_s = LaunchConfiguration("radar_max_wait_s")
    radar_dry_run_duration_s = LaunchConfiguration("radar_dry_run_duration_s")
    radar_scan_mode = LaunchConfiguration("radar_scan_mode")
    radar_scan_density = LaunchConfiguration("radar_scan_density")
    radar_release_on_analysis = LaunchConfiguration("radar_release_on_analysis")
    radar_start_retry_timeout_s = LaunchConfiguration("radar_start_retry_timeout_s")
    radar_start_retry_interval_s = LaunchConfiguration("radar_start_retry_interval_s")
    radar_result_retry_count = LaunchConfiguration("radar_result_retry_count")
    radar_result_retry_interval_s = LaunchConfiguration("radar_result_retry_interval_s")
    radar_query_error_timeout_s = LaunchConfiguration("radar_query_error_timeout_s")
    radar_modeling_scene = LaunchConfiguration("radar_modeling_scene")
    radar_modeling_enable_camera = LaunchConfiguration("radar_modeling_enable_camera")
    radar_inspection_timeout_s = LaunchConfiguration("radar_inspection_timeout_s")
    radar_output_dir = LaunchConfiguration("radar_output_dir")
    use_rviz = LaunchConfiguration("rviz")
    rviz_config = LaunchConfiguration("rviz_config")
    rviz_delay_s = LaunchConfiguration("rviz_delay_s")
    enable_axis_command = LaunchConfiguration("enable_axis_command")
    enable_initialpose_relocalization = LaunchConfiguration("enable_initialpose_relocalization")
    enable_gnss_adapter = LaunchConfiguration("enable_gnss_adapter")
    gnss_source_topic = LaunchConfiguration("gnss_source_topic")
    gnss_fix_topic = LaunchConfiguration("gnss_fix_topic")
    gnss_status_topic = LaunchConfiguration("gnss_status_topic")

    dddmr_bridge_selected = PythonExpression(
        [
            "'",
            enable_dddmr_bridge,
            "'.lower() in ('true', '1', 'yes', 'on') and '",
            navigation_backend,
            "' == 'dddmr_3d'",
        ]
    )
    dddmr_runtime_selected = PythonExpression(
        [
            "'",
            enable_dddmr_runtime,
            "'.lower() in ('true', '1', 'yes', 'on') and '",
            navigation_backend,
            "' == 'dddmr_3d'",
        ]
    )
    dddmr_official_localization_selected = PythonExpression(
        [
            "'",
            enable_dddmr_runtime,
            "'.lower() in ('true', '1', 'yes', 'on') and '",
            navigation_backend,
            "' == 'dddmr_3d' and '",
            dddmr_runtime_backend,
            "' == 'official'",
        ]
    )
    factory_map_tf_selected = PythonExpression(
        [
            "not ('",
            dddmr_official_localization_selected,
            "'.lower() in ('true', '1', 'yes', 'on'))",
        ]
    )
    dddmr_motion_enabled = PythonExpression(
        [
            "'",
            enable_axis_command,
            "'.lower() in ('true', '1', 'yes', 'on') and '",
            navigation_backend,
            "' == 'dddmr_3d'",
        ]
    )
    dddmr_edge_cloud_selected = PythonExpression(
        [
            "'",
            navigation_backend,
            "' == 'dddmr_3d'",
        ]
    )
    dddmr_socket_bridge_selected = PythonExpression(
        [
            "'",
            enable_dddmr_socket_bridge,
            "'.lower() in ('true', '1', 'yes', 'on') and '",
            navigation_backend,
            "' == 'dddmr_3d'",
        ]
    )
    dddmr_map_assets_selected = PythonExpression(
        ["'", navigation_backend, "' == 'dddmr_3d'"]
    )
    # v4 has one production goal contract: the M20Pro action adapter forwards
    # it to official DDDMR P2P. There is no Nav2 goal fallback.
    navigate_to_pose_action = dddmr_navigate_to_pose_action

    return LaunchDescription([
        LogInfo(
            msg=(
                "M20Pro field profile: %s hash=%s"
                % (field_profile["profile_name"], field_profile["profile_hash"])
            )
        ),
        DeclareLaunchArgument("params_file", default_value=default_params),
        DeclareLaunchArgument("floor_config", default_value=default_floor_config),
        DeclareLaunchArgument("map_manifest", default_value=default_map_manifest),
        DeclareLaunchArgument("scan_topic", default_value="/scan"),
        DeclareLaunchArgument("enable_gnss_adapter", default_value="true"),
        DeclareLaunchArgument("gnss_source_topic", default_value="/GPS"),
        DeclareLaunchArgument("gnss_fix_topic", default_value="/m20pro/gnss/fix"),
        DeclareLaunchArgument("gnss_status_topic", default_value="/m20pro/gnss/status"),
        DeclareLaunchArgument(
            "navigation_backend",
            default_value="dddmr_3d",
            choices=["dddmr_3d"],
            description="v3 only accepts the DDDMR 3D runtime backend.",
        ),
        DeclareLaunchArgument(
            "enable_dddmr_bridge",
            default_value="true",
            description=(
                "Start the DDDMR bridge locally; leave false when it runs in "
                "a Humble process."
            ),
        ),
        DeclareLaunchArgument(
            "enable_dddmr_runtime",
            default_value="true",
            description=(
                "Start the local official DDDMR runtime in this ROS process."
            ),
        ),
        DeclareLaunchArgument(
            "dddmr_runtime_backend",
            default_value="official",
            description=(
                "official is the production DDDMR runtime; field_proxy is explicit test-only fallback."
            ),
        ),
        DeclareLaunchArgument("dddmr_action", default_value="/p2p_move_base"),
        DeclareLaunchArgument("dddmr_cmd_vel_topic", default_value="/dddmr/cmd_vel"),
        DeclareLaunchArgument(
            "dddmr_edge_cloud_topic",
            default_value="/m20pro/edge_cloud",
            description="Raw edge-cloud topic used by the 106 DrDDS source.",
        ),
        DeclareLaunchArgument(
            "dddmr_socket_cloud_topic",
            default_value="/m20pro/dddmr/edge_cloud_socket",
            description=(
                "Private ROS topic for the local socket relay; it is kept separate "
                "from the raw 106 edge-cloud topic."
            ),
        ),
        DeclareLaunchArgument(
            "dddmr_input_cloud_topic",
            default_value="/dddmr/edge_cloud",
            description="104-normalized PointCloud2 consumed by DDDMR.",
        ),
        DeclareLaunchArgument(
            "enable_dddmr_socket_bridge",
            default_value="true",
            description=(
                "Publish the DrDDS socket relay as a native ROS PointCloud2 "
                "for the official DDDMR input adapter."
            ),
        ),
        DeclareLaunchArgument(
            "dddmr_socket_cloud_path",
            default_value="/run/m20pro/dddmr_edge_cloud.sock",
            description="Unix stream written by the local DrDDS edge-cloud source.",
        ),
        DeclareLaunchArgument(
            "dddmr_edge_cloud_status_topic",
            default_value="/m20pro/dddmr/edge_cloud/status",
        ),
        DeclareLaunchArgument("dddmr_map_cloud_topic", default_value="/mapcloud"),
        DeclareLaunchArgument("dddmr_map_ground_topic", default_value="/mapground"),
        DeclareLaunchArgument(
            "enable_dddmr_map_assets",
            default_value="true",
            description=(
                "v3 requires DDDMR map assets for localization, navigation and obstacle handling."
            ),
        ),
        DeclareLaunchArgument(
            "dddmr_map_asset_manifest", default_value=default_dddmr_map_assets
        ),
        DeclareLaunchArgument("dddmr_map_asset_reload_period_s", default_value="1.0"),
        DeclareLaunchArgument("dddmr_mapcloud_file", default_value=""),
        DeclareLaunchArgument("dddmr_mapground_file", default_value=""),
        DeclareLaunchArgument(
            "dddmr_map_max_points",
            default_value="0",
            description="0 keeps all PCD points; cap only after target memory testing.",
        ),
        DeclareLaunchArgument(
            "dddmr_field_test_flat_map",
            default_value="false",
            description="Publish a clearly marked provisional flat map for field_proxy site tests when no DDDMR assets are available.",
        ),
        DeclareLaunchArgument("dddmr_field_test_flat_map_extent_m", default_value="2.0"),
        DeclareLaunchArgument("dddmr_field_test_flat_map_spacing_m", default_value="0.25"),
        DeclareLaunchArgument("dddmr_field_test_flat_map_height_m", default_value="0.0"),
        DeclareLaunchArgument(
            "dddmr_map_status_topic",
            default_value="/m20pro/dddmr/map/status",
        ),
        DeclareLaunchArgument(
            "dddmr_navigate_to_pose_action",
            default_value="/navigate_to_pose_3d",
        ),
        DeclareLaunchArgument("dddmr_mapping_host", default_value="localhost"),
        DeclareLaunchArgument("dddmr_mapping_user", default_value="user"),
        DeclareLaunchArgument("dddmr_mapping_start_command", default_value=""),
        DeclareLaunchArgument("dddmr_mapping_finish_command", default_value=""),
        DeclareLaunchArgument("dddmr_mapping_cancel_command", default_value=""),
        DeclareLaunchArgument("dddmr_mapping_status_command", default_value=""),
        DeclareLaunchArgument("enable_floor_manager", default_value="true"),
        DeclareLaunchArgument("enable_floor_goal_bridge", default_value="true"),
        DeclareLaunchArgument(
            "enable_stair_connector",
            default_value="false",
            description="Start the single unified stair connector executor.",
        ),
        DeclareLaunchArgument("enable_system_check", default_value="true"),
        DeclareLaunchArgument("enable_config_audit", default_value="true"),
        DeclareLaunchArgument(
            "initial_floor",
            default_value="",
            description="Optional runtime map label; empty means ordinary map navigation without a floor registry.",
        ),
        DeclareLaunchArgument("enable_initialpose_3d_adapter", default_value="true"),
        DeclareLaunchArgument("initialpose_3d_z", default_value="0.0"),
        DeclareLaunchArgument("enable_web_dashboard", default_value="false"),
        DeclareLaunchArgument("web_dashboard_port", default_value="8080"),
        DeclareLaunchArgument("web_dashboard_data_dir", default_value="~/.m20pro_web"),
        DeclareLaunchArgument("web_dashboard_map_archive_dir", default_value="~/m20pro_maps"),
        DeclareLaunchArgument("robot_pose_display_yaw_offset_rad", default_value="0.0"),
        DeclareLaunchArgument("initialpose_topic", default_value="/initialpose"),
        DeclareLaunchArgument(
            "relocalization_result_topic",
            default_value="/m20pro_tcp_bridge/relocalization_result",
        ),
        DeclareLaunchArgument("factory_host", default_value="10.21.31.106"),
        DeclareLaunchArgument("factory_user", default_value="user"),
        DeclareLaunchArgument("factory_active_map", default_value="/var/opt/robot/data/maps/active"),
        DeclareLaunchArgument("enable_camera_proxy", default_value="false"),
        DeclareLaunchArgument("front_camera_url", default_value="rtsp://10.21.31.103:8554/video1"),
        DeclareLaunchArgument("rear_camera_url", default_value="rtsp://10.21.31.103:8554/video2"),
        DeclareLaunchArgument("camera_proxy_backend", default_value="ffmpeg_mjpeg"),
        DeclareLaunchArgument("camera_proxy_fps", default_value="10.0"),
        DeclareLaunchArgument("camera_proxy_jpeg_quality", default_value="45"),
        DeclareLaunchArgument("camera_proxy_ffmpeg_mjpeg_qscale", default_value="5"),
        DeclareLaunchArgument("camera_proxy_max_width", default_value="480"),
        DeclareLaunchArgument("camera_proxy_transport", default_value="tcp"),
        DeclareLaunchArgument("enable_inspection", default_value="false"),
        DeclareLaunchArgument("inspection_backend", default_value="auto"),
        DeclareLaunchArgument("inspection_source_type", default_value="rtsp"),
        DeclareLaunchArgument("inspection_rtsp_url", default_value="rtsp://10.21.31.103:8554/video1"),
        DeclareLaunchArgument("inspection_camera_name", default_value="front_wide"),
        DeclareLaunchArgument("inspection_model_path", default_value=default_inspection_model),
        DeclareLaunchArgument("inspection_class_names_path", default_value=default_inspection_classes),
        DeclareLaunchArgument("enable_radar_inspection", default_value="false"),
        DeclareLaunchArgument("radar_backend", default_value="dry_run"),
        DeclareLaunchArgument("radar_device_url", default_value="http://192.168.107.72:8080"),
        DeclareLaunchArgument("radar_request_timeout_s", default_value="10.0"),
        DeclareLaunchArgument("radar_poll_interval_s", default_value="2.0"),
        DeclareLaunchArgument("radar_max_wait_s", default_value="1800.0"),
        DeclareLaunchArgument("radar_dry_run_duration_s", default_value="2.0"),
        DeclareLaunchArgument("radar_scan_mode", default_value="measuring"),
        DeclareLaunchArgument("radar_scan_density", default_value="low"),
        DeclareLaunchArgument("radar_release_on_analysis", default_value="true"),
        DeclareLaunchArgument("radar_start_retry_timeout_s", default_value="120.0"),
        DeclareLaunchArgument("radar_start_retry_interval_s", default_value="5.0"),
        DeclareLaunchArgument("radar_result_retry_count", default_value="5"),
        DeclareLaunchArgument("radar_result_retry_interval_s", default_value="2.0"),
        DeclareLaunchArgument("radar_query_error_timeout_s", default_value="120.0"),
        DeclareLaunchArgument("radar_modeling_scene", default_value="modeling"),
        DeclareLaunchArgument("radar_modeling_enable_camera", default_value="false"),
        DeclareLaunchArgument("radar_inspection_timeout_s", default_value="1800.0"),
        DeclareLaunchArgument("radar_output_dir", default_value=""),
        DeclareLaunchArgument(
            "factory_mapping_start_command",
            default_value=(
                "ssh -o BatchMode=yes -o ConnectTimeout=8 {factory_user}@{factory_host} "
                "\"nohup sudo -n drmap mapping -b -s -n {map_name} > "
                "/tmp/m20pro_drmap_mapping_{session_id}.log 2>&1 &\""
            ),
        ),
        DeclareLaunchArgument(
            "factory_mapping_finish_command",
            default_value=(
                "ssh -o BatchMode=yes -o ConnectTimeout=8 {factory_user}@{factory_host} "
                "\"sudo -n drmap stop_mapping\""
            ),
        ),
        DeclareLaunchArgument(
            "factory_mapping_cancel_command",
            default_value=(
                "ssh -o BatchMode=yes -o ConnectTimeout=8 {factory_user}@{factory_host} "
                "\"sudo -n drmap stop_mapping\""
            ),
        ),
        DeclareLaunchArgument("enable_stair_zone_postprocess", default_value="false"),
        DeclareLaunchArgument("stair_zones_topic", default_value="/m20pro/stair_zones"),
        DeclareLaunchArgument("rviz", default_value="true"),
        DeclareLaunchArgument("rviz_config", default_value=default_rviz),
        DeclareLaunchArgument("rviz_delay_s", default_value="5.0"),
        DeclareLaunchArgument(
            "enable_axis_command",
            default_value="false",
            description="Set true only when 104 is allowed to send /cmd_vel axis commands to 103.",
        ),
        DeclareLaunchArgument(
            "enable_initialpose_relocalization",
            default_value="true",
            description="Enable the active relocalization bridge for the current navigation stack.",
        ),

        Node(
            package="m20pro_navigation",
            executable="config_audit",
            name="m20pro_config_audit",
            output="screen",
            parameters=[
                {
                    "map_manifest": map_manifest,
                    "floor_config": floor_config,
                    "fail_on_error": False,
                }
            ],
            condition=IfCondition(enable_config_audit),
        ),
        Node(
            package="m20pro_navigation",
            executable="command_mux",
            name="m20pro_command_mux",
            output="screen",
            parameters=[command_mux_parameters],
        ),
        Node(
            package="m20pro_navigation",
            executable="dddmr_socket_cloud_publisher",
            name="m20pro_dddmr_socket_cloud_publisher",
            output="screen",
            parameters=[
                {
                    "socket_path": dddmr_socket_cloud_path,
                    "output_topic": dddmr_socket_cloud_topic,
                    "frame_id": "m20pro_base_link",
                }
            ],
            condition=IfCondition(dddmr_socket_bridge_selected),
        ),
        Node(
            package="m20pro_bringup",
            executable="dddmr_edge_cloud_adapter",
            name="m20pro_dddmr_edge_cloud_adapter",
            output="screen",
            parameters=[
                {
                    "input_topic": dddmr_socket_cloud_topic,
                    "output_topic": dddmr_input_cloud_topic,
                    "status_topic": dddmr_edge_cloud_status_topic,
                    "max_points": field_profile["dddmr"]["edge_cloud"]["max_points"],
                    "max_range_m": field_profile["dddmr"]["edge_cloud"]["range_max_m"],
                    # 2026-08-31: 实测输入为突发流，帧间隙最大约 1.5s（标称 10Hz）。
                    # 默认 0.75s 超时会在间隙时翻成 edge_cloud_stale，屏蔽 monitor 的
                    # 2.0s 容忍，导致 runtime_3d 自检间歇失败。与 edge_timeout_s 对齐。
                    "cloud_timeout_s": 2.0,
                }
            ],
            condition=IfCondition(dddmr_edge_cloud_selected),
        ),
        Node(
            package="m20pro_navigation",
            executable="gnss_adapter",
            name="m20pro_gnss_adapter",
            output="screen",
            parameters=[
                {
                    "enabled": ParameterValue(enable_gnss_adapter, value_type=bool),
                    "source_topic": gnss_source_topic,
                    "fix_topic": gnss_fix_topic,
                    "status_topic": gnss_status_topic,
                    "frame_id": "m20pro_gnss",
                    "timeout_s": 3.0,
                    "max_hdop": 2.5,
                    "min_satellites": 6,
                }
            ],
            condition=IfCondition(enable_gnss_adapter),
        ),
        Node(
            package="m20pro_navigation",
            executable="dddmr_action_bridge",
            name="m20pro_dddmr_action_bridge",
            output="screen",
            parameters=[
                {
                    "enabled": True,
                    "motion_enabled": ParameterValue(
                        dddmr_motion_enabled,
                        value_type=bool,
                    ),
                    "navigate_to_pose_action": navigate_to_pose_action,
                    "dddmr_action": dddmr_action,
                    "dddmr_cmd_vel_topic": dddmr_cmd_vel_topic,
                    "edge_cloud_status_topic": dddmr_edge_cloud_status_topic,
                    "require_edge_cloud": True,
                    "require_dddmr_map": True,
                    "map_cloud_topic": dddmr_map_cloud_topic,
                    "map_ground_topic": dddmr_map_ground_topic,
                    "map_status_topic": dddmr_map_status_topic,
                    "require_map_status": ParameterValue(
                        dddmr_map_assets_selected,
                        value_type=bool,
                    ),
                    "expected_map_frame": "map",
                    "navigation_cmd_vel_topic": "/cmd_vel_nav",
                    "max_forward_speed_mps": command_mux_parameters[
                        "teleop_max_forward_speed_mps"
                    ],
                    "max_reverse_speed_mps": command_mux_parameters[
                        "teleop_max_reverse_speed_mps"
                    ],
                    "max_lateral_speed_mps": command_mux_parameters[
                        "teleop_max_lateral_speed_mps"
                    ],
                    "max_angular_speed_radps": command_mux_parameters[
                        "teleop_max_angular_speed_radps"
                    ],
                }
            ],
            condition=IfCondition(dddmr_bridge_selected),
        ),
        Node(
            package="m20pro_navigation",
            executable="dddmr_map_asset_server",
            name="m20pro_dddmr_map_asset_server",
            # 2026-08-31: crashed once on a transient manifest parse and
            # never came back, leaving runtime_3d failed. Respawn like
            # global_planner / mcl_3dl.
            respawn=True,
            respawn_delay=5.0,
            output="screen",
            parameters=[
                {
                    "asset_manifest": dddmr_map_asset_manifest,
                    "initial_floor": initial_floor,
                    "reload_period_s": dddmr_map_asset_reload_period_s,
                    "mapcloud_file": dddmr_mapcloud_file,
                    "mapground_file": dddmr_mapground_file,
                    "mapcloud_topic": dddmr_map_cloud_topic,
                    "mapground_topic": dddmr_map_ground_topic,
                    "max_points": dddmr_map_max_points,
                    "field_test_fallback_enabled": ParameterValue(
                        dddmr_field_test_flat_map,
                        value_type=bool,
                    ),
                    "field_test_fallback_extent_m": dddmr_field_test_flat_map_extent_m,
                    "field_test_fallback_spacing_m": dddmr_field_test_flat_map_spacing_m,
                    "field_test_fallback_height_m": dddmr_field_test_flat_map_height_m,
                    "status_topic": dddmr_map_status_topic,
                    "floor_topic": "/m20pro/current_floor",
                    "frame_id": "map",
                    "pg_map_server_name": "map1",
                    "keyframe_radius_m": 8.0,
                    "keyframe_stride": 6,
                    "keyframe_max_points": 3000,
                }
            ],
            condition=IfCondition(dddmr_map_assets_selected),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(
                    bringup_share, "launch", "m20pro_dddmr_runtime.launch.py"
                )
            ),
            launch_arguments={
                "enabled": "true",
                "runtime_backend": dddmr_runtime_backend,
                "params_file": os.path.join(
                    bringup_share, "config", "dddmr_m20pro_navigation.yaml"
                ),
                "dddmr_action": dddmr_action,
                "cmd_vel_topic": dddmr_cmd_vel_topic,
                "edge_cloud_topic": dddmr_input_cloud_topic,
                "odom_topic": "/m20pro/dddmr/odom",
                "motion_socket_path": "/run/m20pro/dddmr_motion_info.sock",
                "base_frame": "m20pro_base_link",
                "map_frame": "map",
            }.items(),
            condition=IfCondition(dddmr_runtime_selected),
        ),
        Node(
            package="m20pro_navigation",
            executable="stair_executor",
            name="m20pro_stair_executor",
            output="screen",
            parameters=[{"enabled": True, **stair_executor_parameters}],
            condition=IfCondition(enable_stair_connector),
        ),
        Node(
            package="m20pro_navigation",
            executable="tcp_bridge",
            name="m20pro_tcp_bridge",
            output="screen",
            parameters=[
                params_file,
                {
                    "publish_tf": True,
                    "publish_map_to_odom_tf": ParameterValue(
                        factory_map_tf_selected, value_type=bool
                    ),
                    # Official mcl_3dl republishes the received /odom as
                    # odom -> base. Keep one TF owner in that mode.
                    "publish_odom_to_base_tf": ParameterValue(
                        factory_map_tf_selected, value_type=bool
                    ),
                    "base_frame": "m20pro_base_link",
                    "enable_native_goal_bridge": False,
                    "enable_initialpose_relocalization": False,
                    "enable_initialpose_3d_relocalization": False,
                    "enable_axis_command": ParameterValue(enable_axis_command, value_type=bool),
                },
            ],
            condition=UnlessCondition(enable_initialpose_3d_adapter),
        ),
        Node(
            package="m20pro_navigation",
            executable="tcp_bridge",
            name="m20pro_tcp_bridge",
            output="screen",
            parameters=[
                params_file,
                {
                    "publish_tf": True,
                    "publish_map_to_odom_tf": ParameterValue(
                        factory_map_tf_selected, value_type=bool
                    ),
                    # Official mcl_3dl republishes the received /odom as
                    # odom -> base. Keep one TF owner in that mode.
                    "publish_odom_to_base_tf": ParameterValue(
                        factory_map_tf_selected, value_type=bool
                    ),
                    "base_frame": "m20pro_base_link",
                    "enable_native_goal_bridge": False,
                    "enable_axis_command": ParameterValue(enable_axis_command, value_type=bool),
                    "enable_initialpose_relocalization": False,
                    "enable_initialpose_3d_relocalization": ParameterValue(
                        PythonExpression(
                            [
                                "'",
                                enable_initialpose_relocalization,
                                "'.lower() in ('true','1','yes','on') and not ('",
                                dddmr_official_localization_selected,
                                "'.lower() in ('true','1','yes','on'))",
                            ]
                        ),
                        value_type=bool,
                    ),
                },
            ],
            condition=IfCondition(enable_initialpose_3d_adapter),
        ),
        Node(
            package="m20pro_navigation",
            executable="scan_recording_relay",
            name="m20pro_scan_recording_relay",
            output="screen",
            parameters=[
                {
                    # Keep the real scan in recordings without making it a 2D
                    # navigation dependency.
                    "input_topic": scan_topic,
                    "output_topic": "/m20pro/recording_scan",
                }
            ],
        ),
        Node(
            package="m20pro_navigation",
            executable="floor_manager",
            name="m20pro_floor_manager",
            output="screen",
            parameters=[
                {
                    "initial_floor": initial_floor,
                    "cmd_vel_topic": "/cmd_vel_nav",
                    "navigate_to_pose_action": navigate_to_pose_action,
                    **floor_manager_parameters,
                }
            ],
            condition=IfCondition(enable_floor_manager),
        ),
        Node(
            package="m20pro_navigation",
            executable="floor_goal_bridge",
            name="m20pro_floor_goal_bridge",
            output="screen",
            parameters=[
                {
                    "floor_config": floor_config,
                    "default_floor": initial_floor,
                    "enable_same_floor_goal_bridge": True,
                }
            ],
            condition=IfCondition(enable_floor_goal_bridge),
        ),
        Node(
            package="m20pro_navigation",
            executable="initialpose_3d_adapter",
            name="m20pro_initialpose_3d_adapter",
            output="screen",
            parameters=[
                {
                    "enabled": True,
                    "z": ParameterValue(initialpose_3d_z, value_type=float),
                    "config_file": floor_config,
                }
            ],
            condition=IfCondition(enable_initialpose_3d_adapter),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(inspection_launch),
            launch_arguments={
                "enabled": enable_inspection,
                "backend": inspection_backend,
                "source_type": inspection_source_type,
                "rtsp_url": inspection_rtsp_url,
                "camera_name": inspection_camera_name,
                "model_path": inspection_model_path,
                "class_names_path": inspection_class_names_path,
            }.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(radar_launch),
            launch_arguments={
                "radar_backend": radar_backend,
                "radar_device_url": radar_device_url,
                "radar_request_timeout_s": radar_request_timeout_s,
                "radar_poll_interval_s": radar_poll_interval_s,
                "radar_max_wait_s": radar_max_wait_s,
                "radar_dry_run_duration_s": radar_dry_run_duration_s,
                "radar_scan_mode": radar_scan_mode,
                "radar_scan_density": radar_scan_density,
                "radar_release_on_analysis": radar_release_on_analysis,
                "radar_start_retry_timeout_s": radar_start_retry_timeout_s,
                "radar_start_retry_interval_s": radar_start_retry_interval_s,
                "radar_result_retry_count": radar_result_retry_count,
                "radar_result_retry_interval_s": radar_result_retry_interval_s,
                "radar_query_error_timeout_s": radar_query_error_timeout_s,
                "radar_modeling_scene": radar_modeling_scene,
                "radar_modeling_enable_camera": radar_modeling_enable_camera,
                "radar_output_dir": radar_output_dir,
            }.items(),
            condition=IfCondition(enable_radar_inspection),
        ),
        Node(
            package="m20pro_cloud_bridge",
            executable="web_dashboard",
            name="m20pro_web_dashboard",
            output="screen",
            parameters=[
                {
                    "port": web_dashboard_port,
                    "data_dir": web_dashboard_data_dir,
                    "map_archive_dir": web_dashboard_map_archive_dir,
                    "robot_pose_display_yaw_offset_rad": ParameterValue(
                        robot_pose_display_yaw_offset_rad,
                        value_type=float,
                    ),
                    "map_manifest": map_manifest,
                    "floor_config": floor_config,
                    "navigation_backend": navigation_backend,
                    "navigation_backend_status_topic": "/m20pro/navigation_backend/status",
                    "dddmr_runtime_status_topic": "/m20pro/dddmr/runtime/status",
                    "pose_topic": "/m20pro/dddmr/map_pose",
                    "enable_gnss_adapter": ParameterValue(
                        enable_gnss_adapter,
                        value_type=bool,
                    ),
                    "gnss_status_topic": gnss_status_topic,
                    "dddmr_map_asset_manifest": dddmr_map_asset_manifest,
                    "dddmr_edge_cloud_topic": dddmr_input_cloud_topic,
                    "dddmr_edge_cloud_status_topic": dddmr_edge_cloud_status_topic,
                    "dddmr_map_cloud_topic": dddmr_map_cloud_topic,
                    "dddmr_map_ground_topic": dddmr_map_ground_topic,
                    "dddmr_map_status_topic": dddmr_map_status_topic,
                    "dddmr_mapping_host": dddmr_mapping_host,
                    "dddmr_mapping_user": dddmr_mapping_user,
                    "dddmr_mapping_start_command": dddmr_mapping_start_command,
                    "dddmr_mapping_finish_command": dddmr_mapping_finish_command,
                    "dddmr_mapping_cancel_command": dddmr_mapping_cancel_command,
                    "dddmr_mapping_status_command": dddmr_mapping_status_command,
                    "initialpose_topic": initialpose_topic,
                    "relocalization_result_topic": relocalization_result_topic,
                    "factory_host": factory_host,
                    "factory_user": factory_user,
                    "factory_active_map": factory_active_map,
                    "factory_mapping_start_command": factory_mapping_start_command,
                    "factory_mapping_finish_command": factory_mapping_finish_command,
                    "factory_mapping_cancel_command": factory_mapping_cancel_command,
                    "enable_stair_zone_postprocess": ParameterValue(
                        enable_stair_zone_postprocess,
                        value_type=bool,
                    ),
                    "stair_zones_topic": stair_zones_topic,
                    # The Web node observes the exact /scan stream consumed by Nav2.
                    "scan_topic": scan_topic,
                    "startup_sync_selected_map_delay_s": 6.0,
                    "enable_camera_proxy": ParameterValue(enable_camera_proxy, value_type=bool),
                    "front_camera_url": front_camera_url,
                    "rear_camera_url": rear_camera_url,
                    "camera_proxy_backend": camera_proxy_backend,
                    "camera_proxy_fps": ParameterValue(camera_proxy_fps, value_type=float),
                    "camera_proxy_jpeg_quality": ParameterValue(
                        camera_proxy_jpeg_quality,
                        value_type=int,
                    ),
                    "camera_proxy_ffmpeg_mjpeg_qscale": ParameterValue(
                        camera_proxy_ffmpeg_mjpeg_qscale,
                        value_type=int,
                    ),
                    "camera_proxy_max_width": ParameterValue(
                        camera_proxy_max_width,
                        value_type=int,
                    ),
                    "camera_proxy_transport": camera_proxy_transport,
                    "wait_for_radar_inspection": ParameterValue(
                        enable_radar_inspection,
                        value_type=bool,
                    ),
                    "radar_inspection_timeout_s": ParameterValue(
                        radar_inspection_timeout_s,
                        value_type=float,
                    ),
                    "radar_results_dir": radar_output_dir,
                    "cmd_vel_topic": "/cmd_vel_nav",
                    "teleop_cmd_vel_topic": "/cmd_vel_teleop",
                    **web_navigation_parameters,
                    **web_teleoperation_parameters,
                }
            ],
            condition=IfCondition(enable_web_dashboard),
        ),
        Node(
            package="m20pro_navigation",
            executable="system_check",
            name="m20pro_system_check",
            output="screen",
            parameters=[
                {
                    "mode": "real",
                    "scan_topic": scan_topic,
                    "scan_timeout_s": 3.0,
                    "check_period_s": 5.0,
                    "require_topic_messages": ParameterValue(
                        dddmr_map_assets_selected,
                        value_type=bool,
                    ),
                    "require_dddmr": ParameterValue(
                        dddmr_map_assets_selected,
                        value_type=bool,
                    ),
                    "dddmr_edge_cloud_topic": dddmr_input_cloud_topic,
                    "dddmr_map_cloud_topic": dddmr_map_cloud_topic,
                    "dddmr_map_ground_topic": dddmr_map_ground_topic,
                    "require_nav2": False,
                    "require_costmaps": False,
                    "require_map": False,
                    "require_nodes": ParameterValue(
                        dddmr_map_assets_selected,
                        value_type=bool,
                    ),
                    "expected_nodes": [
                        "m20pro_tcp_bridge",
                        "m20pro_command_mux",
                        "m20pro_dddmr_edge_cloud_adapter",
                        "m20pro_dddmr_action_bridge",
                        "m20pro_dddmr_map_asset_server",
                        "m20pro_floor_manager",
                    ],
                    "require_scan": False,
                    "require_dynamic_obstacles": False,
                    "require_floor_manager": ParameterValue(
                        enable_floor_manager,
                        value_type=bool,
                    ),
                    "check_scan_content": True,
                    "check_local_costmap_content": False,
                    "check_tf_height": False,
                    "tf_global_frame": "odom",
                    "tf_base_frame": "m20pro_base_link",
                    "max_abs_base_z": 1.0,
                    "min_scan_finite_bins": 20,
                    "min_scan_close_bins": 1,
                    "scan_close_range_m": 2.0,
                    "min_local_costmap_marked_cells": 1,
                }
            ],
            condition=IfCondition(enable_system_check),
        ),
        TimerAction(
            period=rviz_delay_s,
            actions=[
                Node(
                    package="rviz2",
                    executable="rviz2",
                    name="rviz2",
                    output="screen",
                    arguments=["-d", rviz_config],
                    condition=IfCondition(use_rviz),
                )
            ],
        ),
    ])
