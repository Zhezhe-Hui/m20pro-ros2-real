from setuptools import setup

package_name = "m20pro_navigation"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="M20Pro Developer",
    maintainer_email="user@example.com",
    description="ROS 2 navigation bridge and lightweight planner for DEEP Robotics M20 Pro.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "tcp_bridge = m20pro_navigation.tcp_bridge_node:main",
            "grid_planner = m20pro_navigation.grid_planner_node:main",
            "path_follower = m20pro_navigation.path_follower_node:main",
            "control_gui = m20pro_navigation.control_gui:main",
            "map_editor = m20pro_navigation.map_editor:main",
            "floor_manager = m20pro_navigation.floor_manager:main",
            "floor_goal_bridge = m20pro_navigation.floor_goal_bridge:main",
            "initialpose_3d_adapter = m20pro_navigation.initialpose_3d_adapter:main",
            "system_check = m20pro_navigation.system_check_node:main",
            "config_audit = m20pro_navigation.config_audit_node:main",
            "scan_recording_relay = m20pro_navigation.scan_recording_relay:main",
            "dddmr_socket_cloud_publisher = m20pro_navigation.dddmr_socket_cloud_publisher:main",
            "dddmr_dense_cloud_publisher = m20pro_navigation.dddmr_dense_cloud_publisher:main",
            "command_mux = m20pro_navigation.command_mux_node:main",
            "stair_executor = m20pro_navigation.stair_executor_node:main",
            "terrain_guard_106 = m20pro_navigation.terrain_guard_106_node:main",
            "terrain_guard_replay = m20pro_navigation.terrain_guard_replay:main",
            "gnss_adapter = m20pro_navigation.gnss_adapter_node:main",
            "dddmr_action_bridge = m20pro_navigation.dddmr_nav2_bridge_node:main",
            "dddmr_feature_split = m20pro_navigation.dddmr_feature_split_node:main",
            "dddmr_map_asset_server = m20pro_navigation.dddmr_map_asset_server_node:main",
            "dddmr_runtime_monitor = m20pro_navigation.dddmr_runtime_monitor_node:main",
            "dddmr_legacy_base_tf_publisher = m20pro_navigation.dddmr_legacy_base_tf_publisher:main",
            "motion_info_odom_adapter = m20pro_navigation.motion_info_odom_adapter_node:main",
            "dddmr_socket_odom_publisher = m20pro_navigation.dddmr_socket_odom_publisher:main",
            "dddmr_p2p_field_proxy = m20pro_navigation.dddmr_p2p_field_proxy_node:main",
        ],
    },
)
