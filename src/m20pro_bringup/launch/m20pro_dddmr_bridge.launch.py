"""Run the guarded DDDMR P2P action adapter in a Humble environment."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    enabled = LaunchConfiguration("enabled")
    motion_enabled = LaunchConfiguration("motion_enabled")
    navigate_to_pose_action = LaunchConfiguration("navigate_to_pose_action")
    dddmr_action = LaunchConfiguration("dddmr_action")
    dddmr_cmd_vel_topic = LaunchConfiguration("dddmr_cmd_vel_topic")
    navigation_cmd_vel_topic = LaunchConfiguration("navigation_cmd_vel_topic")
    edge_cloud_status_topic = LaunchConfiguration("edge_cloud_status_topic")
    map_cloud_topic = LaunchConfiguration("map_cloud_topic")
    map_ground_topic = LaunchConfiguration("map_ground_topic")
    map_status_topic = LaunchConfiguration("map_status_topic")
    require_map_status = LaunchConfiguration("require_map_status")
    target_value = LaunchConfiguration("target_value")
    max_forward_speed_mps = LaunchConfiguration("max_forward_speed_mps")
    max_reverse_speed_mps = LaunchConfiguration("max_reverse_speed_mps")
    max_lateral_speed_mps = LaunchConfiguration("max_lateral_speed_mps")
    max_angular_speed_radps = LaunchConfiguration("max_angular_speed_radps")

    return LaunchDescription(
        [
            DeclareLaunchArgument("enabled", default_value="false"),
            DeclareLaunchArgument("motion_enabled", default_value="false"),
            DeclareLaunchArgument(
                "navigate_to_pose_action",
                default_value="/navigate_to_pose_3d",
            ),
            DeclareLaunchArgument("dddmr_action", default_value="/p2p_move_base"),
            DeclareLaunchArgument(
                "dddmr_cmd_vel_topic",
                default_value="/dddmr/cmd_vel",
            ),
            DeclareLaunchArgument(
                "navigation_cmd_vel_topic",
                default_value="/cmd_vel_nav",
            ),
            DeclareLaunchArgument(
                "edge_cloud_status_topic",
                default_value="/m20pro/dddmr/edge_cloud/status",
            ),
            DeclareLaunchArgument("map_cloud_topic", default_value="/mapcloud"),
            DeclareLaunchArgument("map_ground_topic", default_value="/mapground"),
            DeclareLaunchArgument(
                "map_status_topic", default_value="/m20pro/dddmr/map/status"
            ),
            DeclareLaunchArgument("require_map_status", default_value="false"),
            DeclareLaunchArgument("target_value", default_value="0.0"),
            DeclareLaunchArgument("max_forward_speed_mps", default_value="0.18"),
            DeclareLaunchArgument("max_reverse_speed_mps", default_value="0.12"),
            DeclareLaunchArgument("max_lateral_speed_mps", default_value="0.30"),
            DeclareLaunchArgument("max_angular_speed_radps", default_value="0.45"),
            Node(
                package="m20pro_navigation",
                executable="dddmr_action_bridge",
                name="m20pro_dddmr_action_bridge",
                output="screen",
                parameters=[
                    {
                        "enabled": ParameterValue(enabled, value_type=bool),
                        "motion_enabled": ParameterValue(
                            motion_enabled,
                            value_type=bool,
                        ),
                        "navigate_to_pose_action": navigate_to_pose_action,
                        "dddmr_action": dddmr_action,
                        "dddmr_cmd_vel_topic": dddmr_cmd_vel_topic,
                        "navigation_cmd_vel_topic": navigation_cmd_vel_topic,
                        "edge_cloud_status_topic": edge_cloud_status_topic,
                        "require_edge_cloud": True,
                        "require_dddmr_map": True,
                        "map_cloud_topic": map_cloud_topic,
                        "map_ground_topic": map_ground_topic,
                        "map_status_topic": map_status_topic,
                        "require_map_status": ParameterValue(
                            require_map_status, value_type=bool
                        ),
                        "expected_map_frame": "map",
                        "target_value": ParameterValue(target_value, value_type=float),
                        "max_forward_speed_mps": ParameterValue(
                            max_forward_speed_mps,
                            value_type=float,
                        ),
                        "max_reverse_speed_mps": ParameterValue(
                            max_reverse_speed_mps,
                            value_type=float,
                        ),
                        "max_lateral_speed_mps": ParameterValue(
                            max_lateral_speed_mps,
                            value_type=float,
                        ),
                        "max_angular_speed_radps": ParameterValue(
                            max_angular_speed_radps,
                            value_type=float,
                        ),
                    }
                ],
            ),
        ]
    )
