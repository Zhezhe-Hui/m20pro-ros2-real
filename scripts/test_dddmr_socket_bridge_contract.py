#!/usr/bin/env python3
"""Static contract for the DrDDS-to-native-ROS edge-cloud bridge."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_socket_bridge_is_in_the_real_dddmr_input_path() -> None:
    launch = (ROOT / "src/m20pro_bringup/launch/m20pro_real.launch.py").read_text(
        encoding="utf-8"
    )
    start = (ROOT / "src/m20pro_bringup/scripts/m20pro_real_full.sh").read_text(
        encoding="utf-8"
    )
    setup = (ROOT / "src/m20pro_navigation/setup.py").read_text(encoding="utf-8")
    publisher = (
        ROOT / "src/m20pro_navigation/m20pro_navigation/dddmr_socket_cloud_publisher.py"
    ).read_text(encoding="utf-8")
    assert 'executable="dddmr_socket_cloud_publisher"' in launch
    assert 'default_value="/run/m20pro/dddmr_edge_cloud.sock"' in launch
    assert 'default_value="/m20pro/dddmr/edge_cloud_socket"' in launch
    assert '"output_topic": dddmr_socket_cloud_topic' in launch
    assert '"input_topic": dddmr_socket_cloud_topic' in launch
    assert 'ENABLE_DDDMR_SOCKET_BRIDGE="${M20PRO_ENABLE_DDDMR_SOCKET_BRIDGE:-true}"' in start
    assert 'dddmr_socket_cloud_path:="${DDDMR_SOCKET_CLOUD_PATH}"' in start
    assert 'dddmr_socket_cloud_publisher = m20pro_navigation.dddmr_socket_cloud_publisher:main' in setup
    assert 'self.declare_parameter("drop_non_monotonic_stamps", True)' in publisher
    assert 'self.declare_parameter("restamp_on_publish", True)' in publisher
    assert "source_stamp_ns <= self._last_source_stamp_ns" in publisher
    assert "message.header.stamp = self.get_clock().now().to_msg()" in publisher
    assert "message._data = points" in publisher


def test_source_is_a_restartable_target_native_service() -> None:
    source = (ROOT / "tools/edge_scan_feasibility/drdds_edge_cloud_socket_source.cpp").read_text(
        encoding="utf-8"
    )
    unit = (ROOT / "systemd/m20pro-dddmr-socket-source.service").read_text(
        encoding="utf-8"
    )
    installer = (ROOT / "scripts/104_install_dddmr_socket_bridge.sh").read_text(
        encoding="utf-8"
    )
    autostart = (ROOT / "scripts/104_enable_autostart.sh").read_text(encoding="utf-8")
    assert "std::signal(SIGPIPE, SIG_IGN);" in source
    assert "data.size() / step" in source
    assert "BindsTo=m20pro-real.service" in unit
    assert "FASTRTPS_DEFAULT_PROFILES_FILE=/opt/robot/fastdds.xml" in unit
    assert "WantedBy=m20pro-real.service" in unit
    assert "-lfastrtps" in installer
    assert "-lfastdds" not in installer
    assert "systemctl enable m20pro-dddmr-socket-source.service" in installer
    assert "SOCKET_UNIT_SRC=" in autostart
