import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from m20pro_navigation.field_profile_contract import (
    load_field_profile,
    web_navigation_field_parameters,
    web_teleoperation_field_parameters,
)


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
    floor_config = LaunchConfiguration("floor_config")
    map_archive_dir = LaunchConfiguration("map_archive_dir")
    robot_pose_display_yaw_offset_rad = LaunchConfiguration("robot_pose_display_yaw_offset_rad")
    map_manifest = LaunchConfiguration("map_manifest")
    dddmr_map_asset_manifest = LaunchConfiguration("dddmr_map_asset_manifest")
    factory_host = LaunchConfiguration("factory_host")
    factory_user = LaunchConfiguration("factory_user")
    factory_active_map = LaunchConfiguration("factory_active_map")
    factory_mapping_start_command = LaunchConfiguration("factory_mapping_start_command")
    factory_mapping_finish_command = LaunchConfiguration("factory_mapping_finish_command")
    factory_mapping_cancel_command = LaunchConfiguration("factory_mapping_cancel_command")
    dddmr_mapping_host = LaunchConfiguration("dddmr_mapping_host")
    dddmr_mapping_user = LaunchConfiguration("dddmr_mapping_user")
    dddmr_mapping_start_command = LaunchConfiguration("dddmr_mapping_start_command")
    dddmr_mapping_finish_command = LaunchConfiguration("dddmr_mapping_finish_command")
    dddmr_mapping_cancel_command = LaunchConfiguration("dddmr_mapping_cancel_command")
    dddmr_mapping_status_command = LaunchConfiguration("dddmr_mapping_status_command")
    navigation_backend = LaunchConfiguration("navigation_backend")
    navigation_backend_status_topic = LaunchConfiguration("navigation_backend_status_topic")
    dddmr_runtime_status_topic = LaunchConfiguration("dddmr_runtime_status_topic")
    enable_gnss_adapter = LaunchConfiguration("enable_gnss_adapter")
    gnss_status_topic = LaunchConfiguration("gnss_status_topic")
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
    initialpose_topic = LaunchConfiguration("initialpose_topic")
    relocalization_result_topic = LaunchConfiguration("relocalization_result_topic")
    wait_for_radar_inspection = LaunchConfiguration("wait_for_radar_inspection")
    radar_inspection_timeout_s = LaunchConfiguration("radar_inspection_timeout_s")
    radar_results_dir = LaunchConfiguration("radar_results_dir")

    return LaunchDescription([
        DeclareLaunchArgument("host", default_value="0.0.0.0"),
        DeclareLaunchArgument("port", default_value="8080"),
        DeclareLaunchArgument("data_dir", default_value="~/.m20pro_web"),
        DeclareLaunchArgument(
            "floor_config",
            default_value=PathJoinSubstitution([data_dir, "runtime_navigation.yaml"]),
        ),
        DeclareLaunchArgument("map_archive_dir", default_value="~/m20pro_maps"),
        DeclareLaunchArgument("robot_pose_display_yaw_offset_rad", default_value="0.0"),
        DeclareLaunchArgument(
            "map_manifest",
            default_value=os.path.join(bringup_share, "config", "map_manifest.yaml"),
        ),
        DeclareLaunchArgument(
            "dddmr_map_asset_manifest",
            default_value="/home/user/.m20pro_web/dddmr_map_assets.yaml",
        ),
        DeclareLaunchArgument("factory_host", default_value="10.21.31.106"),
        DeclareLaunchArgument("factory_user", default_value="user"),
        DeclareLaunchArgument(
            "factory_active_map",
            default_value="/var/opt/robot/data/maps/active",
        ),
        DeclareLaunchArgument(
            "factory_mapping_start_command",
            default_value=(
                "ssh -o BatchMode=yes -o ConnectTimeout=8 {factory_user}@{factory_host} "
                "\"nohup sudo -n drmap mapping -b -s -n {map_name} > "
                "/tmp/m20pro_drmap_mapping_{session_id}.log 2>&1 &\""
            ),
            description="Shell command template for starting drmap mapping on 106.",
        ),
        DeclareLaunchArgument(
            "factory_mapping_finish_command",
            default_value=(
                "ssh -o BatchMode=yes -o ConnectTimeout=8 {factory_user}@{factory_host} "
                "\"sudo -n drmap stop_mapping\""
            ),
            description="Shell command template for stopping/saving drmap mapping on 106.",
        ),
        DeclareLaunchArgument(
            "factory_mapping_cancel_command",
            default_value=(
                "ssh -o BatchMode=yes -o ConnectTimeout=8 {factory_user}@{factory_host} "
                "\"sudo -n drmap stop_mapping\""
            ),
            description="Shell command template for cancelling drmap mapping on 106.",
        ),
        DeclareLaunchArgument("dddmr_mapping_host", default_value="localhost"),
        DeclareLaunchArgument("dddmr_mapping_user", default_value="user"),
        DeclareLaunchArgument("dddmr_mapping_start_command", default_value=""),
        DeclareLaunchArgument("dddmr_mapping_finish_command", default_value=""),
        DeclareLaunchArgument("dddmr_mapping_cancel_command", default_value=""),
        DeclareLaunchArgument("dddmr_mapping_status_command", default_value=""),
        DeclareLaunchArgument(
            "navigation_backend",
            default_value="dddmr_3d",
            choices=["dddmr_3d"],
            description="v3 only accepts the DDDMR 3D runtime backend.",
        ),
        DeclareLaunchArgument(
            "navigation_backend_status_topic",
            default_value="/m20pro/navigation_backend/status",
        ),
        DeclareLaunchArgument(
            "dddmr_runtime_status_topic",
            default_value="/m20pro/dddmr/runtime/status",
        ),
        DeclareLaunchArgument("enable_gnss_adapter", default_value="false"),
        DeclareLaunchArgument("gnss_status_topic", default_value="/m20pro/gnss/status"),
        DeclareLaunchArgument("enable_stair_zone_postprocess", default_value="true"),
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
        DeclareLaunchArgument("initialpose_topic", default_value="/initialpose"),
        DeclareLaunchArgument(
            "relocalization_result_topic",
            default_value="/m20pro_tcp_bridge/relocalization_result",
        ),
        DeclareLaunchArgument("wait_for_radar_inspection", default_value="false"),
        DeclareLaunchArgument("radar_inspection_timeout_s", default_value="1800.0"),
        DeclareLaunchArgument("radar_results_dir", default_value="~/.m20pro_radar_results"),
        Node(
            package="m20pro_cloud_bridge",
            executable="web_dashboard",
            name="m20pro_web_dashboard",
            output="screen",
            parameters=[
                {
                    "host": host,
                    "port": port,
                    "data_dir": data_dir,
                    "floor_config": floor_config,
                    "map_archive_dir": map_archive_dir,
                    "robot_pose_display_yaw_offset_rad": ParameterValue(
                        robot_pose_display_yaw_offset_rad,
                        value_type=float,
                    ),
                    "map_manifest": map_manifest,
                    "dddmr_map_asset_manifest": dddmr_map_asset_manifest,
                    "factory_host": factory_host,
                    "factory_user": factory_user,
                    "factory_active_map": factory_active_map,
                    "factory_mapping_start_command": factory_mapping_start_command,
                    "factory_mapping_finish_command": factory_mapping_finish_command,
                    "factory_mapping_cancel_command": factory_mapping_cancel_command,
                    "dddmr_mapping_host": dddmr_mapping_host,
                    "dddmr_mapping_user": dddmr_mapping_user,
                    "dddmr_mapping_start_command": dddmr_mapping_start_command,
                    "dddmr_mapping_finish_command": dddmr_mapping_finish_command,
                    "dddmr_mapping_cancel_command": dddmr_mapping_cancel_command,
                    "dddmr_mapping_status_command": dddmr_mapping_status_command,
                    "navigation_backend": navigation_backend,
                    "map_select_load_nav2_map": False,
                    "startup_sync_selected_map_to_nav2": False,
                    "navigation_backend_status_topic": navigation_backend_status_topic,
                    "dddmr_runtime_status_topic": dddmr_runtime_status_topic,
                    "enable_gnss_adapter": ParameterValue(
                        enable_gnss_adapter,
                        value_type=bool,
                    ),
                    "gnss_status_topic": gnss_status_topic,
                    "enable_stair_zone_postprocess": ParameterValue(
                        enable_stair_zone_postprocess,
                        value_type=bool,
                    ),
                    "stair_zones_topic": stair_zones_topic,
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
                    "initialpose_topic": initialpose_topic,
                    "relocalization_result_topic": relocalization_result_topic,
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
                    "teleop_cmd_vel_topic": "/cmd_vel_teleop",
                    **web_navigation_parameters,
                    **web_teleoperation_parameters,
                }
            ],
        ),
    ])
