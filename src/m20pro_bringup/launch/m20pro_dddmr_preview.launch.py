"""Start a DDDMR preview without touching the system service."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from m20pro_navigation.field_profile_contract import (
    load_field_profile,
    web_navigation_field_parameters,
    web_teleoperation_field_parameters,
)


def _launch_source(package_name: str, relative_path: str) -> PythonLaunchDescriptionSource:
    share = get_package_share_directory(package_name)
    return PythonLaunchDescriptionSource(os.path.join(share, relative_path))


def generate_launch_description():
    bringup_share = get_package_share_directory("m20pro_bringup")
    field_profile = load_field_profile(
        os.path.join(bringup_share, "config", "m20pro_field_profile.yaml")
    )
    web_teleoperation_parameters = web_teleoperation_field_parameters(field_profile)
    web_navigation_parameters = web_navigation_field_parameters(field_profile)

    host = LaunchConfiguration("host")
    port = LaunchConfiguration("port")
    data_dir = LaunchConfiguration("data_dir")
    map_archive_dir = LaunchConfiguration("map_archive_dir")
    robot_pose_display_yaw_offset_rad = LaunchConfiguration("robot_pose_display_yaw_offset_rad")
    map_manifest = LaunchConfiguration("map_manifest")
    floor_config = LaunchConfiguration("floor_config")
    navigation_backend = LaunchConfiguration("navigation_backend")
    navigation_backend_status_topic = LaunchConfiguration("navigation_backend_status_topic")
    gnss_status_topic = LaunchConfiguration("gnss_status_topic")
    enable_web_dashboard = LaunchConfiguration("enable_web_dashboard")
    dddmr_map_asset_manifest = LaunchConfiguration("dddmr_map_asset_manifest")
    dddmr_input_cloud_topic = LaunchConfiguration("dddmr_input_cloud_topic")
    dddmr_edge_cloud_status_topic = LaunchConfiguration("dddmr_edge_cloud_status_topic")
    dddmr_map_cloud_topic = LaunchConfiguration("dddmr_map_cloud_topic")
    dddmr_map_ground_topic = LaunchConfiguration("dddmr_map_ground_topic")
    dddmr_map_status_topic = LaunchConfiguration("dddmr_map_status_topic")
    dddmr_mapping_host = LaunchConfiguration("dddmr_mapping_host")
    dddmr_mapping_user = LaunchConfiguration("dddmr_mapping_user")
    dddmr_mapping_start_command = LaunchConfiguration("dddmr_mapping_start_command")
    dddmr_mapping_finish_command = LaunchConfiguration("dddmr_mapping_finish_command")
    dddmr_mapping_cancel_command = LaunchConfiguration("dddmr_mapping_cancel_command")
    enable_edge_cloud_adapter = LaunchConfiguration("enable_edge_cloud_adapter")
    enable_map_asset_server = LaunchConfiguration("enable_map_asset_server")
    enable_bridge = LaunchConfiguration("enable_bridge")
    enable_dddmr_runtime = LaunchConfiguration("enable_dddmr_runtime")
    enable_gnss_adapter = LaunchConfiguration("enable_gnss_adapter")
    edge_cloud_input_topic = LaunchConfiguration("edge_cloud_input_topic")
    edge_cloud_expected_frame = LaunchConfiguration("edge_cloud_expected_frame")
    edge_cloud_timeout_s = LaunchConfiguration("edge_cloud_timeout_s")
    edge_cloud_min_points = LaunchConfiguration("edge_cloud_min_points")
    edge_cloud_max_range_m = LaunchConfiguration("edge_cloud_max_range_m")
    map_asset_initial_floor = LaunchConfiguration("map_asset_initial_floor")
    map_asset_reload_period_s = LaunchConfiguration("map_asset_reload_period_s")
    map_asset_max_points = LaunchConfiguration("map_asset_max_points")
    dddmr_field_test_flat_map = LaunchConfiguration("dddmr_field_test_flat_map")
    dddmr_field_test_flat_map_extent_m = LaunchConfiguration("dddmr_field_test_flat_map_extent_m")
    dddmr_field_test_flat_map_spacing_m = LaunchConfiguration("dddmr_field_test_flat_map_spacing_m")
    dddmr_field_test_flat_map_height_m = LaunchConfiguration("dddmr_field_test_flat_map_height_m")
    dddmr_bridge_target_value = LaunchConfiguration("dddmr_bridge_target_value")
    dddmr_motion_enabled = LaunchConfiguration("dddmr_motion_enabled")
    dddmr_bridge_enabled = LaunchConfiguration("dddmr_bridge_enabled")
    dddmr_runtime_params_file = LaunchConfiguration("dddmr_runtime_params_file")
    dddmr_runtime_cmd_vel_topic = LaunchConfiguration("dddmr_runtime_cmd_vel_topic")
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
    wait_for_radar_inspection = LaunchConfiguration("wait_for_radar_inspection")
    radar_inspection_timeout_s = LaunchConfiguration("radar_inspection_timeout_s")
    radar_results_dir = LaunchConfiguration("radar_results_dir")
    scan_topic = LaunchConfiguration("scan_topic")
    teleop_cmd_vel_topic = LaunchConfiguration("teleop_cmd_vel_topic")

    preview_bridge = IncludeLaunchDescription(
        _launch_source("m20pro_bringup", "launch/m20pro_dddmr_bridge.launch.py"),
        launch_arguments={
            "enabled": dddmr_bridge_enabled,
            "motion_enabled": dddmr_motion_enabled,
            "navigate_to_pose_action": "/navigate_to_pose_3d",
            "dddmr_action": "/p2p_move_base",
            "dddmr_cmd_vel_topic": "/dddmr/cmd_vel",
            "navigation_cmd_vel_topic": "/cmd_vel_nav",
            "edge_cloud_status_topic": dddmr_edge_cloud_status_topic,
            "map_cloud_topic": dddmr_map_cloud_topic,
            "map_ground_topic": dddmr_map_ground_topic,
            "map_status_topic": dddmr_map_status_topic,
            "require_map_status": "true",
            "target_value": dddmr_bridge_target_value,
        }.items(),
        condition=IfCondition(enable_bridge),
    )

    preview_runtime = IncludeLaunchDescription(
        _launch_source("m20pro_bringup", "launch/m20pro_dddmr_runtime.launch.py"),
        launch_arguments={
            "enabled": enable_dddmr_runtime,
            "params_file": dddmr_runtime_params_file,
            "cmd_vel_topic": dddmr_runtime_cmd_vel_topic,
        }.items(),
        condition=IfCondition(enable_dddmr_runtime),
    )

    return LaunchDescription([
        DeclareLaunchArgument("host", default_value="0.0.0.0"),
        DeclareLaunchArgument("port", default_value="18080"),
        DeclareLaunchArgument("data_dir", default_value="~/.m20pro_web_dddmr_preview"),
        DeclareLaunchArgument("map_archive_dir", default_value="~/m20pro_maps_dddmr_preview"),
        DeclareLaunchArgument("robot_pose_display_yaw_offset_rad", default_value="0.0"),
        DeclareLaunchArgument(
            "map_manifest",
            default_value=os.path.join(bringup_share, "config", "map_manifest.yaml"),
        ),
        DeclareLaunchArgument(
            "floor_config",
            default_value=os.path.join(bringup_share, "config", "runtime_navigation.yaml"),
        ),
        DeclareLaunchArgument(
            "navigation_backend",
            default_value="dddmr_3d",
        ),
        DeclareLaunchArgument(
            "navigation_backend_status_topic",
            default_value="/m20pro/navigation_backend/status",
        ),
        DeclareLaunchArgument("gnss_status_topic", default_value="/m20pro/gnss/status"),
        DeclareLaunchArgument("enable_web_dashboard", default_value="true"),
        DeclareLaunchArgument("dddmr_map_asset_manifest", default_value="/home/user/.m20pro_web/dddmr_map_assets.yaml"),
        DeclareLaunchArgument("dddmr_input_cloud_topic", default_value="/dddmr/edge_cloud"),
        DeclareLaunchArgument(
            "dddmr_edge_cloud_status_topic",
            default_value="/m20pro/dddmr/edge_cloud/status",
        ),
        DeclareLaunchArgument("dddmr_map_cloud_topic", default_value="/mapcloud"),
        DeclareLaunchArgument("dddmr_map_ground_topic", default_value="/mapground"),
        DeclareLaunchArgument("dddmr_map_status_topic", default_value="/m20pro/dddmr/map/status"),
        DeclareLaunchArgument("dddmr_mapping_host", default_value="localhost"),
        DeclareLaunchArgument("dddmr_mapping_user", default_value="user"),
        DeclareLaunchArgument("dddmr_mapping_start_command", default_value=""),
        DeclareLaunchArgument("dddmr_mapping_finish_command", default_value=""),
        DeclareLaunchArgument("dddmr_mapping_cancel_command", default_value=""),
        DeclareLaunchArgument("enable_edge_cloud_adapter", default_value="true"),
        DeclareLaunchArgument("enable_map_asset_server", default_value="true"),
        DeclareLaunchArgument("enable_bridge", default_value="true"),
        DeclareLaunchArgument("enable_dddmr_runtime", default_value="false"),
        DeclareLaunchArgument("enable_gnss_adapter", default_value="false"),
        DeclareLaunchArgument("edge_cloud_input_topic", default_value="/m20pro/edge_cloud"),
        DeclareLaunchArgument("edge_cloud_expected_frame", default_value="m20pro_base_link"),
        DeclareLaunchArgument("edge_cloud_timeout_s", default_value="0.75"),
        DeclareLaunchArgument("edge_cloud_min_points", default_value="20"),
        DeclareLaunchArgument("edge_cloud_max_range_m", default_value="30.0"),
        DeclareLaunchArgument("map_asset_initial_floor", default_value=""),
        DeclareLaunchArgument("map_asset_reload_period_s", default_value="1.0"),
        DeclareLaunchArgument("map_asset_max_points", default_value="0"),
        DeclareLaunchArgument("dddmr_field_test_flat_map", default_value="true"),
        DeclareLaunchArgument("dddmr_field_test_flat_map_extent_m", default_value="2.0"),
        DeclareLaunchArgument("dddmr_field_test_flat_map_spacing_m", default_value="0.25"),
        DeclareLaunchArgument("dddmr_field_test_flat_map_height_m", default_value="0.0"),
        DeclareLaunchArgument("dddmr_bridge_target_value", default_value="0.0"),
        DeclareLaunchArgument("dddmr_motion_enabled", default_value="false"),
        DeclareLaunchArgument("dddmr_bridge_enabled", default_value="true"),
        DeclareLaunchArgument(
            "dddmr_runtime_params_file",
            default_value=os.path.join(bringup_share, "config", "dddmr_m20pro_navigation.yaml"),
        ),
        DeclareLaunchArgument("dddmr_runtime_cmd_vel_topic", default_value="/dddmr/cmd_vel"),
        DeclareLaunchArgument("initialpose_topic", default_value="/initialpose"),
        DeclareLaunchArgument(
            "relocalization_result_topic",
            default_value="/m20pro_tcp_bridge/relocalization_result",
        ),
        DeclareLaunchArgument("factory_host", default_value="10.21.31.106"),
        DeclareLaunchArgument("factory_user", default_value="user"),
        DeclareLaunchArgument("factory_active_map", default_value="/var/opt/robot/data/maps/active"),
        DeclareLaunchArgument("factory_mapping_start_command", default_value=""),
        DeclareLaunchArgument("factory_mapping_finish_command", default_value=""),
        DeclareLaunchArgument("factory_mapping_cancel_command", default_value=""),
        DeclareLaunchArgument("enable_stair_zone_postprocess", default_value="false"),
        DeclareLaunchArgument("stair_zones_topic", default_value="/m20pro/stair_zones"),
        DeclareLaunchArgument("enable_camera_proxy", default_value="false"),
        DeclareLaunchArgument("front_camera_url", default_value="rtsp://10.21.31.103:8554/video1"),
        DeclareLaunchArgument("rear_camera_url", default_value="rtsp://10.21.31.103:8554/video2"),
        DeclareLaunchArgument("camera_proxy_backend", default_value="ffmpeg_mjpeg"),
        DeclareLaunchArgument("camera_proxy_fps", default_value="10.0"),
        DeclareLaunchArgument("camera_proxy_jpeg_quality", default_value="45"),
        DeclareLaunchArgument("camera_proxy_ffmpeg_mjpeg_qscale", default_value="5"),
        DeclareLaunchArgument("camera_proxy_max_width", default_value="480"),
        DeclareLaunchArgument("camera_proxy_transport", default_value="tcp"),
        DeclareLaunchArgument("wait_for_radar_inspection", default_value="false"),
        DeclareLaunchArgument("radar_inspection_timeout_s", default_value="1800.0"),
        DeclareLaunchArgument("radar_results_dir", default_value="~/.m20pro_radar_results"),
        DeclareLaunchArgument("scan_topic", default_value="/scan"),
        DeclareLaunchArgument("teleop_cmd_vel_topic", default_value="/cmd_vel_teleop"),
        LogInfo(
            msg=[
                "Starting DDDMR read-only preview on port ",
                port,
                ", bridge enabled=",
                dddmr_bridge_enabled,
                ", runtime enabled=",
                enable_dddmr_runtime,
            ]
        ),
        Node(
            package="m20pro_bringup",
            executable="dddmr_edge_cloud_adapter",
            name="m20pro_dddmr_edge_cloud_adapter",
            output="screen",
            parameters=[
                {
                    "input_topic": edge_cloud_input_topic,
                    "output_topic": dddmr_input_cloud_topic,
                    "status_topic": dddmr_edge_cloud_status_topic,
                    "expected_frame": edge_cloud_expected_frame,
                    "cloud_timeout_s": ParameterValue(edge_cloud_timeout_s, value_type=float),
                    "min_points": ParameterValue(edge_cloud_min_points, value_type=int),
                    "max_range_m": ParameterValue(edge_cloud_max_range_m, value_type=float),
                }
            ],
            condition=IfCondition(enable_edge_cloud_adapter),
        ),
        Node(
            package="m20pro_navigation",
            executable="dddmr_map_asset_server",
            name="m20pro_dddmr_map_asset_server",
            output="screen",
            parameters=[
                {
                    "asset_manifest": dddmr_map_asset_manifest,
                    "initial_floor": map_asset_initial_floor,
                    "reload_period_s": ParameterValue(map_asset_reload_period_s, value_type=float),
                    "mapcloud_file": "",
                    "mapground_file": "",
                    "floor_topic": "/m20pro/current_floor",
                    "mapcloud_topic": dddmr_map_cloud_topic,
                    "mapground_topic": dddmr_map_ground_topic,
                    "status_topic": dddmr_map_status_topic,
                    "frame_id": "map",
                    "max_points": ParameterValue(map_asset_max_points, value_type=int),
                    "field_test_fallback_enabled": ParameterValue(
                        dddmr_field_test_flat_map,
                        value_type=bool,
                    ),
                    "field_test_fallback_extent_m": dddmr_field_test_flat_map_extent_m,
                    "field_test_fallback_spacing_m": dddmr_field_test_flat_map_spacing_m,
                    "field_test_fallback_height_m": dddmr_field_test_flat_map_height_m,
                }
            ],
            condition=IfCondition(enable_map_asset_server),
        ),
        preview_bridge,
        preview_runtime,
        Node(
            package="m20pro_navigation",
            executable="gnss_adapter",
            name="m20pro_gnss_adapter_preview",
            output="screen",
            parameters=[
                {
                    "enabled": ParameterValue(enable_gnss_adapter, value_type=bool),
                    "source_topic": "/GPS",
                    "fix_topic": "/m20pro/gnss/fix",
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
            package="m20pro_cloud_bridge",
            executable="web_dashboard",
            name="m20pro_web_dashboard_preview",
            output="screen",
            parameters=[
                {
                    "host": host,
                    "port": port,
                    "data_dir": data_dir,
                    "map_archive_dir": map_archive_dir,
                    "robot_pose_display_yaw_offset_rad": ParameterValue(
                        robot_pose_display_yaw_offset_rad,
                        value_type=float,
                    ),
                    "map_manifest": map_manifest,
                    "floor_config": floor_config,
                    "navigation_backend": navigation_backend,
                    "navigation_backend_status_topic": navigation_backend_status_topic,
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
                        wait_for_radar_inspection,
                        value_type=bool,
                    ),
                    "radar_inspection_timeout_s": ParameterValue(
                        radar_inspection_timeout_s,
                        value_type=float,
                    ),
                    "radar_results_dir": radar_results_dir,
                    "cmd_vel_topic": "/cmd_vel_nav",
                    "teleop_cmd_vel_topic": teleop_cmd_vel_topic,
                    **web_navigation_parameters,
                    **web_teleoperation_parameters,
                }
            ],
            condition=IfCondition(enable_web_dashboard),
        ),
    ])
