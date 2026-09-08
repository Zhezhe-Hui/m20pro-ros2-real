"""Start the official DDDMR 3D navigation runtime for M20Pro.

Lightning-LM is intentionally absent from this launch. It is started by the
separate mapping launch only. This launch owns the official DDDMR feature
front-end, 3D MCL, global perception, global planner and P2P local planner;
the M20Pro bridge remains the only process that talks to the robot chassis.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    bringup_share = get_package_share_directory("m20pro_bringup")
    default_params = os.path.join(
        bringup_share, "config", "dddmr_m20pro_navigation.yaml"
    )
    enabled = LaunchConfiguration("enabled")
    params_file = LaunchConfiguration("params_file")
    runtime_backend = LaunchConfiguration("runtime_backend")
    dddmr_action = LaunchConfiguration("dddmr_action")
    cmd_vel_topic = LaunchConfiguration("cmd_vel_topic")
    edge_cloud_topic = LaunchConfiguration("edge_cloud_topic")
    odom_topic = LaunchConfiguration("odom_topic")
    motion_socket_path = LaunchConfiguration("motion_socket_path")
    base_frame = LaunchConfiguration("base_frame")
    map_frame = LaunchConfiguration("map_frame")
    enable_localization = LaunchConfiguration("enable_localization")
    enable_global_planner = LaunchConfiguration("enable_global_planner")
    enable_p2p_move_base = LaunchConfiguration("enable_p2p_move_base")
    enable_feature_frontend = LaunchConfiguration("enable_feature_frontend")
    enable_global_perception = LaunchConfiguration("enable_global_perception")
    runtime_status_topic = LaunchConfiguration("runtime_status_topic")
    max_goal_distance_m = LaunchConfiguration("max_goal_distance_m")
    max_linear_mps = LaunchConfiguration("max_linear_mps")
    max_angular_radps = LaunchConfiguration("max_angular_radps")
    legacy_base_frame = LaunchConfiguration("legacy_base_frame")
    official_selected = PythonExpression(
        [
            "'",
            enabled,
            "'.lower() in ('true', '1', 'yes', 'on') and '",
            runtime_backend,
            "' == 'official'",
        ]
    )
    field_proxy_selected = PythonExpression(
        [
            "'",
            enabled,
            "'.lower() in ('true', '1', 'yes', 'on') and '",
            runtime_backend,
            "' == 'field_proxy'",
        ]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("enabled", default_value="false"),
            DeclareLaunchArgument("params_file", default_value=default_params),
            DeclareLaunchArgument(
                "runtime_backend",
                default_value="official",
                choices=["official", "field_proxy"],
                description="Official DDDMR is the production backend; field_proxy is explicit test-only fallback.",
            ),
            DeclareLaunchArgument("dddmr_action", default_value="/p2p_move_base"),
            DeclareLaunchArgument("cmd_vel_topic", default_value="/dddmr/cmd_vel"),
            DeclareLaunchArgument("edge_cloud_topic", default_value="/dddmr/edge_cloud"),
        DeclareLaunchArgument("odom_topic", default_value="/odom"),
        DeclareLaunchArgument("motion_socket_path", default_value="/run/m20pro/dddmr_motion_info.sock"),
            DeclareLaunchArgument("base_frame", default_value="m20pro_base_link"),
            DeclareLaunchArgument("map_frame", default_value="map"),
            DeclareLaunchArgument(
                "legacy_base_frame",
                default_value="base_link",
                description="Official LeGO feature code still checks this legacy base frame.",
            ),
            DeclareLaunchArgument("enable_localization", default_value="true"),
            DeclareLaunchArgument("enable_global_planner", default_value="true"),
            DeclareLaunchArgument("enable_p2p_move_base", default_value="true"),
            DeclareLaunchArgument("enable_feature_frontend", default_value="true"),
            DeclareLaunchArgument(
                "enable_global_perception",
                default_value="true",
                description=(
                    "Start the official global perception_3d node. The P2P process "
                    "owns perception_3d_local internally."
                ),
            ),
            DeclareLaunchArgument(
                "runtime_status_topic",
                default_value="/m20pro/dddmr/runtime/status",
            ),
            DeclareLaunchArgument("max_goal_distance_m", default_value="3.0"),
            DeclareLaunchArgument("max_linear_mps", default_value="0.18"),
            DeclareLaunchArgument("max_angular_radps", default_value="0.45"),
            LogInfo(
                msg=(
                    "Starting official DDDMR 3D runtime: mcl_feature + mcl_3dl + "
                    "perception_3d_global + global_planner + p2p_move_base; "
                    "M20Pro owns /odom, TF and final cmd_vel."
                ),
                condition=IfCondition(official_selected),
            ),
            LogInfo(
                msg=(
                    "Starting M20Pro DDDMR field-proxy runtime: low-speed "
                    "/p2p_move_base action server; test-only explicit fallback."
                ),
                condition=IfCondition(field_proxy_selected),
            ),
            Node(
                package="m20pro_navigation",
                executable="dddmr_p2p_field_proxy",
                name="m20pro_dddmr_p2p_field_proxy",
                output="screen",
                parameters=[
                    {
                        "enabled": True,
                        "dddmr_action": dddmr_action,
                        "cmd_vel_topic": cmd_vel_topic,
                        "status_topic": runtime_status_topic,
                        "max_goal_distance_m": max_goal_distance_m,
                        "max_linear_mps": max_linear_mps,
                        "max_angular_radps": max_angular_radps,
                    }
                ],
                condition=IfCondition(field_proxy_selected),
            ),
            Node(
                package="m20pro_navigation",
                executable="dddmr_legacy_base_tf_publisher",
                name="m20pro_dddmr_legacy_base_alias",
                output="screen",
                parameters=[
                    {
                        "base_frame": base_frame,
                        "legacy_base_frame": legacy_base_frame,
                        "publish_hz": 10.0,
                    }
                ],
                condition=IfCondition(official_selected),
            ),
            Node(
                package="m20pro_navigation",
                executable="dddmr_socket_odom_publisher",
                name="m20pro_motion_info_odom_adapter",
                output="screen",
                parameters=[
                    {
                        "socket_path": motion_socket_path,
                        "output_topic": odom_topic,
                    }
                ],
                condition=IfCondition(official_selected),
            ),
            # 2026-09-01: 官方 mcl_feature(lego_loam_bor 闭源 LeGO-LOAM 投影)
            # 需要带 float ring 的结构化多线云, 对 M20Pro 过滤后的 xyz 云输出
            # 恒为空, mcl_3dl 永远饿死、无法重定位。mcl_3dl 实测只消费
            # laser_cloud_flat(地面) 与 laser_cloud_less_sharp(非地面) 两通道,
            # 用轻量 z 带分割节点替代, 运行时不再依赖 lego_loam_bor。
            Node(
                package="m20pro_navigation",
                executable="dddmr_feature_split",
                name="m20pro_dddmr_feature_split",
                output="screen",
                parameters=[
                    {
                        "input_topic": edge_cloud_topic,
                        # 2026-09-01: less_sharp 点数直接决定 mcl_3dl 逐粒子
                        # KdTree 搜索量(80 粒子)。4700 点让 RK3588 上每次
                        # 更新数秒; 原厂 LeGO less_sharp 仅数百特征点。
                        # stride 12 → ~1200 点, 更新频率与语义都更接近原厂。
                        "less_sharp_stride": 12,
                    },
                ],
                condition=IfCondition(
                    PythonExpression(["'", official_selected, "' and '", enable_feature_frontend, "'.lower() in ('true','1','yes','on')"])
                ),
            ),
            Node(
                package="mcl_3dl",
                executable="mcl_3dl",
                output="screen",
                # 2026-08-31: mcl_3dl segfaulted once on a bad (empty-keyframe)
                # map and never came back, leaving runtime_3d failed until a
                # manual service restart. Respawn like global_planner.
                respawn=True,
                respawn_delay=5.0,
                parameters=[
                    params_file,
                    {
                        "map_frame": map_frame,
                        "robot_frame": base_frame,
                        "odom_frame": "odom",
                        # 2026-09-01: mcl_3dl 初值 snap-to-ground 后加回 base
                        # 离地高度, 否则 z 从初值就差一个机身高度并塌缩。
                        "base_height": 0.84,
                    },
                ],
                remappings=[
                    ("odom", odom_topic),
                ],
                condition=IfCondition(
                    PythonExpression(["'", official_selected, "' and '", enable_localization, "'.lower() in ('true','1','yes','on')"])
                ),
            ),
            Node(
                package="global_planner",
                executable="global_planner_node",
                # The official YAML parameter section is keyed "global_planner";
                # without this remap the node runs with empty parameters.
                name="global_planner",
                output="screen",
                respawn=True,
                respawn_delay=5.0,
                # 2026-08-21: 未加载地图时 "Waiting for static layer" 以 ~1Hz
                # 永久刷屏, 40 分钟即可把 journald 200MB 配额占满并挤掉全部
                # 现场证据日志 (当天 fail-to-fetch 排查因此无日志可用)。
                # ERROR 级别保留, 仅压制 INFO 噪声。Foxy 的 rcl 不支持
                # "logger:=LEVEL" 写法 (会导致节点启动即崩溃), 只能整进程
                # 设置默认级别。
                arguments=["--ros-args", "--log-level", "ERROR"],
                parameters=[params_file],
                condition=IfCondition(
                    PythonExpression(["'", official_selected, "' and '", enable_global_planner, "'.lower() in ('true','1','yes','on')"])
                ),
            ),
            # p2p_move_base creates perception_3d_local inside its own process.
            # The global graph is a separate official process and therefore must
            # retain this node name so its YAML parameter section is selected.
            Node(
                package="perception_3d",
                executable="perception_3d_ros_node",
                name="perception_3d_global",
                output="screen",
                respawn=True,
                respawn_delay=5.0,
                # 2026-08-21: 无 map->base TF 时 "Timed out waiting for
                # transform" 以 10Hz 刷屏, 是日志洪水主因之一; 压制到 ERROR。
                arguments=["--ros-args", "--log-level", "ERROR"],
                parameters=[params_file],
                condition=IfCondition(
                    PythonExpression(
                        [
                            "'",
                            official_selected,
                            "' and '",
                            enable_global_perception,
                            "'.lower() in ('true','1','yes','on')",
                        ]
                    )
                ),
            ),
            Node(
                package="p2p_move_base",
                executable="p2p_move_base_node",
                output="screen",
                respawn=True,
                respawn_delay=5.0,
                # 2026-08-21: 内部 perception_3d_local.lidar 以 10Hz 刷
                # "Failed to get transforms" (无地图时的常态), 压制到 ERROR。
                arguments=["--ros-args", "--log-level", "ERROR"],
                parameters=[params_file],
                remappings=[("cmd_vel", cmd_vel_topic)],
                condition=IfCondition(
                    PythonExpression(["'", official_selected, "' and '", enable_p2p_move_base, "'.lower() in ('true','1','yes','on')"])
                ),
            ),
            Node(
                package="m20pro_navigation",
                executable="dddmr_runtime_monitor",
                name="m20pro_dddmr_runtime_monitor",
                output="screen",
                parameters=[
                    {
                        "edge_status_topic": "/m20pro/dddmr/edge_cloud/status",
                        "map_status_topic": "/m20pro/dddmr/map/status",
                        "mcl_pose_topic": "/mcl_pose",
                        "pose_topic": "/m20pro/dddmr/map_pose",
                        "dddmr_action": dddmr_action,
                        "map_frame": map_frame,
                        "base_frame": base_frame,
                        "perception_global_node": "perception_3d_global",
                    }
                ],
                condition=IfCondition(official_selected),
            ),
        ]
    )
