import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression


def generate_launch_description():
    bringup_share = get_package_share_directory("m20pro_bringup")
    inspection_share = get_package_share_directory("m20pro_inspection")
    real_launch = os.path.join(bringup_share, "launch", "m20pro_real.launch.py")

    mode = LaunchConfiguration("mode")
    rviz = LaunchConfiguration("rviz")
    initial_floor = LaunchConfiguration("initial_floor")
    floor_config = LaunchConfiguration("floor_config")
    map_manifest = LaunchConfiguration("map_manifest")
    real_params_file = LaunchConfiguration("real_params_file")
    enable_axis_command = LaunchConfiguration("enable_axis_command")
    enable_gnss_adapter = LaunchConfiguration("enable_gnss_adapter")
    gnss_source_topic = LaunchConfiguration("gnss_source_topic")
    gnss_fix_topic = LaunchConfiguration("gnss_fix_topic")
    gnss_status_topic = LaunchConfiguration("gnss_status_topic")
    navigation_backend = LaunchConfiguration("navigation_backend")
    enable_dddmr_bridge = LaunchConfiguration("enable_dddmr_bridge")
    enable_dddmr_runtime = LaunchConfiguration("enable_dddmr_runtime")
    dddmr_runtime_backend = LaunchConfiguration("dddmr_runtime_backend")
    dddmr_action = LaunchConfiguration("dddmr_action")
    dddmr_cmd_vel_topic = LaunchConfiguration("dddmr_cmd_vel_topic")
    dddmr_edge_cloud_topic = LaunchConfiguration("dddmr_edge_cloud_topic")
    dddmr_socket_cloud_topic = LaunchConfiguration("dddmr_socket_cloud_topic")
    dddmr_input_cloud_topic = LaunchConfiguration("dddmr_input_cloud_topic")
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
    enable_stair_connector = LaunchConfiguration("enable_stair_connector")
    enable_initialpose_relocalization = LaunchConfiguration("enable_initialpose_relocalization")
    enable_initialpose_3d_adapter = LaunchConfiguration("enable_initialpose_3d_adapter")
    initialpose_3d_z = LaunchConfiguration("initialpose_3d_z")
    enable_web_dashboard = LaunchConfiguration("enable_web_dashboard")
    web_dashboard_port = LaunchConfiguration("web_dashboard_port")
    web_dashboard_data_dir = LaunchConfiguration("web_dashboard_data_dir")
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

    return LaunchDescription([
        DeclareLaunchArgument(
            "mode",
            default_value="real",
            description="Real-only workspace compatibility argument; use real.",
        ),
        DeclareLaunchArgument("rviz", default_value="true"),
        DeclareLaunchArgument("initial_floor", default_value=""),
        DeclareLaunchArgument("web_dashboard_data_dir", default_value="~/.m20pro_web"),
        DeclareLaunchArgument(
            "map",
            default_value=os.path.join(bringup_share, "maps", "Original_map", "occ_grid.yaml"),
        ),
        DeclareLaunchArgument(
            "floor_config",
            default_value=PathJoinSubstitution([web_dashboard_data_dir, "runtime_navigation.yaml"]),
        ),
        DeclareLaunchArgument(
            "map_manifest",
            default_value=os.path.join(bringup_share, "config", "map_manifest.yaml"),
        ),
        DeclareLaunchArgument(
            "real_params_file",
            default_value=os.path.join(bringup_share, "config", "m20pro_real.yaml"),
        ),
        DeclareLaunchArgument("enable_axis_command", default_value="false"),
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
        DeclareLaunchArgument("enable_dddmr_bridge", default_value="true"),
        DeclareLaunchArgument("enable_dddmr_runtime", default_value="true"),
        DeclareLaunchArgument("dddmr_runtime_backend", default_value="official"),
        DeclareLaunchArgument("dddmr_action", default_value="/p2p_move_base"),
        DeclareLaunchArgument("dddmr_cmd_vel_topic", default_value="/dddmr/cmd_vel"),
        DeclareLaunchArgument(
            "dddmr_edge_cloud_topic", default_value="/m20pro/edge_cloud"
        ),
        DeclareLaunchArgument(
            "dddmr_socket_cloud_topic",
            default_value="/m20pro/dddmr/edge_cloud_socket",
        ),
        DeclareLaunchArgument(
            "dddmr_input_cloud_topic", default_value="/dddmr/edge_cloud"
        ),
        DeclareLaunchArgument(
            "dddmr_edge_cloud_status_topic",
            default_value="/m20pro/dddmr/edge_cloud/status",
        ),
        DeclareLaunchArgument("dddmr_map_cloud_topic", default_value="/mapcloud"),
        DeclareLaunchArgument("dddmr_map_ground_topic", default_value="/mapground"),
        DeclareLaunchArgument(
            "enable_dddmr_map_assets",
            default_value="false",
            description=(
                "Compatibility argument; DDDMR backend modes enable map assets "
                "automatically."
            ),
        ),
        DeclareLaunchArgument(
            "dddmr_map_asset_manifest",
            default_value="/home/user/.m20pro_web/dddmr_map_assets.yaml",
        ),
        DeclareLaunchArgument("dddmr_map_asset_reload_period_s", default_value="1.0"),
        DeclareLaunchArgument("dddmr_mapcloud_file", default_value=""),
        DeclareLaunchArgument("dddmr_mapground_file", default_value=""),
        DeclareLaunchArgument("dddmr_map_max_points", default_value="0"),
        DeclareLaunchArgument("dddmr_field_test_flat_map", default_value="false"),
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
        DeclareLaunchArgument("enable_stair_connector", default_value="false"),
        DeclareLaunchArgument(
            "enable_initialpose_relocalization",
            default_value="true",
            description="Enable the active relocalization bridge for the current navigation stack.",
        ),
        DeclareLaunchArgument("enable_initialpose_3d_adapter", default_value="true"),
        DeclareLaunchArgument("initialpose_3d_z", default_value="0.0"),
        DeclareLaunchArgument("enable_web_dashboard", default_value="false"),
        DeclareLaunchArgument("web_dashboard_port", default_value="8080"),
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
        DeclareLaunchArgument(
            "inspection_model_path",
            default_value=os.path.join(inspection_share, "models", "best_rk3588_fp16.rknn"),
        ),
        DeclareLaunchArgument(
            "inspection_class_names_path",
            default_value=os.path.join(inspection_share, "models", "labels_zh.txt"),
        ),
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

        LogInfo(
            msg="m20pro_bringup is real-only; non-real mode is unsupported in this workspace.",
            condition=IfCondition(PythonExpression(["'", mode, "' != 'real'"])),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(real_launch),
            launch_arguments={
                "rviz": rviz,
                "initial_floor": initial_floor,
                "floor_config": floor_config,
                "map_manifest": map_manifest,
                "params_file": real_params_file,
                "enable_axis_command": enable_axis_command,
                "enable_gnss_adapter": enable_gnss_adapter,
                "gnss_source_topic": gnss_source_topic,
                "gnss_fix_topic": gnss_fix_topic,
                "gnss_status_topic": gnss_status_topic,
                "navigation_backend": navigation_backend,
                "enable_dddmr_bridge": enable_dddmr_bridge,
                "enable_dddmr_runtime": enable_dddmr_runtime,
                "dddmr_runtime_backend": dddmr_runtime_backend,
                "dddmr_action": dddmr_action,
                "dddmr_cmd_vel_topic": dddmr_cmd_vel_topic,
                "dddmr_edge_cloud_topic": dddmr_edge_cloud_topic,
                "dddmr_socket_cloud_topic": dddmr_socket_cloud_topic,
                "dddmr_input_cloud_topic": dddmr_input_cloud_topic,
                "dddmr_edge_cloud_status_topic": dddmr_edge_cloud_status_topic,
                "dddmr_map_cloud_topic": dddmr_map_cloud_topic,
                "dddmr_map_ground_topic": dddmr_map_ground_topic,
                "dddmr_map_asset_manifest": dddmr_map_asset_manifest,
                "dddmr_map_asset_reload_period_s": dddmr_map_asset_reload_period_s,
                "dddmr_map_status_topic": dddmr_map_status_topic,
                "dddmr_mapping_host": dddmr_mapping_host,
                "dddmr_mapping_user": dddmr_mapping_user,
                "dddmr_mapping_start_command": dddmr_mapping_start_command,
                "dddmr_mapping_finish_command": dddmr_mapping_finish_command,
                "dddmr_mapping_cancel_command": dddmr_mapping_cancel_command,
                "dddmr_mapping_status_command": dddmr_mapping_status_command,
                "enable_dddmr_map_assets": enable_dddmr_map_assets,
                "dddmr_mapcloud_file": dddmr_mapcloud_file,
                "dddmr_mapground_file": dddmr_mapground_file,
                "dddmr_map_max_points": dddmr_map_max_points,
                "dddmr_field_test_flat_map": dddmr_field_test_flat_map,
                "dddmr_field_test_flat_map_extent_m": dddmr_field_test_flat_map_extent_m,
                "dddmr_field_test_flat_map_spacing_m": dddmr_field_test_flat_map_spacing_m,
                "dddmr_field_test_flat_map_height_m": dddmr_field_test_flat_map_height_m,
                "dddmr_navigate_to_pose_action": dddmr_navigate_to_pose_action,
                "enable_stair_connector": enable_stair_connector,
                "enable_initialpose_relocalization": enable_initialpose_relocalization,
                "enable_initialpose_3d_adapter": enable_initialpose_3d_adapter,
                "initialpose_3d_z": initialpose_3d_z,
                "enable_web_dashboard": enable_web_dashboard,
                "web_dashboard_port": web_dashboard_port,
                "web_dashboard_data_dir": web_dashboard_data_dir,
                "web_dashboard_map_archive_dir": web_dashboard_map_archive_dir,
                "robot_pose_display_yaw_offset_rad": robot_pose_display_yaw_offset_rad,
                "initialpose_topic": initialpose_topic,
                "relocalization_result_topic": relocalization_result_topic,
                "factory_host": factory_host,
                "factory_user": factory_user,
                "factory_active_map": factory_active_map,
                "factory_mapping_start_command": factory_mapping_start_command,
                "factory_mapping_finish_command": factory_mapping_finish_command,
                "factory_mapping_cancel_command": factory_mapping_cancel_command,
                "enable_stair_zone_postprocess": enable_stair_zone_postprocess,
                "enable_camera_proxy": enable_camera_proxy,
                "front_camera_url": front_camera_url,
                "rear_camera_url": rear_camera_url,
                "camera_proxy_backend": camera_proxy_backend,
                "camera_proxy_fps": camera_proxy_fps,
                "camera_proxy_jpeg_quality": camera_proxy_jpeg_quality,
                "camera_proxy_ffmpeg_mjpeg_qscale": camera_proxy_ffmpeg_mjpeg_qscale,
                "camera_proxy_max_width": camera_proxy_max_width,
                "camera_proxy_transport": camera_proxy_transport,
                "enable_inspection": enable_inspection,
                "inspection_backend": inspection_backend,
                "inspection_source_type": inspection_source_type,
                "inspection_rtsp_url": inspection_rtsp_url,
                "inspection_camera_name": inspection_camera_name,
                "inspection_model_path": inspection_model_path,
                "inspection_class_names_path": inspection_class_names_path,
                "enable_radar_inspection": enable_radar_inspection,
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
                "radar_inspection_timeout_s": radar_inspection_timeout_s,
                "radar_output_dir": radar_output_dir,
            }.items(),
            condition=IfCondition(PythonExpression(["'", mode, "' == 'real'"])),
        ),
    ])
