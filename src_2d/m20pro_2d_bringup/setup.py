from setuptools import setup


package_name = "m20pro_2d_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml"]),
        (
            "share/" + package_name + "/launch",
            [
                "launch/m20pro_2d_mapping.launch.py",
                "launch/nav2_2d.launch.py",
            ],
        ),
        (
            "share/" + package_name + "/config",
            [
                "config/slam_toolbox_2d.yaml",
                "config/nav2_params_2d.yaml",
                "config/m20pro_2d_map_manifest.yaml",
                "config/m20pro_2d_runtime_navigation.yaml",
                "config/m20pro_2d_fastdds_udp.xml",
            ],
        ),
        ("share/" + package_name + "/rviz", ["rviz/m20pro_2d.rviz"]),
        (
            "share/" + package_name + "/behavior_trees",
            ["behavior_trees/m20pro_navigate_to_pose_foxy.xml"],
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="M20Pro Developer",
    maintainer_email="user@example.com",
    description="Isolated 2D mapping runtime for the M20 Pro.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "socket_odom_publisher = m20pro_2d_bringup.socket_odom_publisher:main",
            "odom_pose_adapter = m20pro_2d_bringup.odom_pose_adapter:main",
            "nav2_goal_bridge = m20pro_2d_bringup.nav2_goal_bridge:main",
        ],
    },
)
