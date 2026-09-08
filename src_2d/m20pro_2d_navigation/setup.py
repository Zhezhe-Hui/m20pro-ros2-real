from setuptools import setup


package_name = "m20pro_2d_navigation"

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
    description="Independent 2D motion, command arbitration and Nav2 transport for the M20 Pro.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "tcp_bridge = m20pro_2d_navigation.tcp_bridge_node:main",
            "command_mux = m20pro_2d_navigation.command_mux_node:main",
        ],
    },
)
