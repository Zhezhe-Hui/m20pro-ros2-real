"""Adapt the M20Pro factory /GPS topic into standard ROS GNSS outputs."""

from __future__ import annotations

import json
import math
import time
from typing import Any, Dict, Optional

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus
from std_msgs.msg import String

from .gnss_contract import (
    GNSS_FIX_TOPIC,
    GNSS_FRAME_ID,
    GNSS_SOURCE_TOPIC,
    GNSS_STATUS_TOPIC,
    covariance_from_dop,
    gnss_quality_status,
    normalize_gnss_sample,
)

try:
    from drdds.msg import NavSat
except ImportError:  # Available only in the factory ROS environment.
    NavSat = None


def _json_message(payload: Dict[str, Any]) -> String:
    message = String()
    message.data = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    return message


class GnssAdapter(Node):
    def __init__(self) -> None:
        super().__init__("m20pro_gnss_adapter")
        self.declare_parameter("enabled", True)
        self.declare_parameter("source_topic", GNSS_SOURCE_TOPIC)
        self.declare_parameter("fix_topic", GNSS_FIX_TOPIC)
        self.declare_parameter("status_topic", GNSS_STATUS_TOPIC)
        self.declare_parameter("frame_id", GNSS_FRAME_ID)
        self.declare_parameter("timeout_s", 3.0)
        self.declare_parameter("max_hdop", 2.5)
        self.declare_parameter("min_satellites", 6)
        self.declare_parameter("uere_m", 4.0)
        self.declare_parameter("publish_period_s", 1.0)

        self._enabled = bool(self.get_parameter("enabled").value)
        self._source_topic = str(self.get_parameter("source_topic").value)
        self._fix_topic = str(self.get_parameter("fix_topic").value)
        self._status_topic = str(self.get_parameter("status_topic").value)
        self._frame_id = str(self.get_parameter("frame_id").value)
        self._timeout_s = max(0.5, float(self.get_parameter("timeout_s").value))
        self._max_hdop = max(0.1, float(self.get_parameter("max_hdop").value))
        self._min_satellites = max(0, int(self.get_parameter("min_satellites").value))
        self._uere_m = max(0.1, float(self.get_parameter("uere_m").value))

        self._last_sample: Optional[Dict[str, Any]] = None
        self._last_received_at: Optional[float] = None
        self._fix_publisher = self.create_publisher(NavSatFix, self._fix_topic, 10)
        self._status_publisher = self.create_publisher(String, self._status_topic, 10)

        if self._enabled and NavSat is not None:
            self.create_subscription(NavSat, self._source_topic, self._on_navsat, 10)
            self.get_logger().info(
                "GNSS adapter ready: %s -> %s, status=%s"
                % (self._source_topic, self._fix_topic, self._status_topic)
            )
        elif not self._enabled:
            self.get_logger().info("GNSS adapter disabled")
        else:
            self.get_logger().warning(
                "drdds.msg.NavSat is unavailable; GNSS adapter will publish status only"
            )

        self.create_timer(
            max(0.2, float(self.get_parameter("publish_period_s").value)),
            self._publish_status,
        )
        self._publish_status()

    def _on_navsat(self, message: Any) -> None:
        now_mono = time.monotonic()
        sample = normalize_gnss_sample(
            message,
            source_topic=self._source_topic,
            received_at=time.time(),
        )
        self._last_sample = sample
        self._last_received_at = now_mono
        self._fix_publisher.publish(self._to_navsat_fix(sample))
        self._publish_status()

    def _to_navsat_fix(self, sample: Dict[str, Any]) -> NavSatFix:
        message = NavSatFix()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = self._frame_id
        message.status.status = (
            NavSatStatus.STATUS_FIX
            if sample.get("fix_valid")
            else NavSatStatus.STATUS_NO_FIX
        )
        service = NavSatStatus.SERVICE_GPS
        for name in ("SERVICE_GLONASS", "SERVICE_COMPASS", "SERVICE_GALILEO"):
            service |= int(getattr(NavSatStatus, name, 0))
        message.status.service = service

        latitude = sample.get("latitude")
        longitude = sample.get("longitude")
        altitude = sample.get("altitude_m")
        message.latitude = (
            float(latitude) if isinstance(latitude, (int, float)) else math.nan
        )
        message.longitude = (
            float(longitude) if isinstance(longitude, (int, float)) else math.nan
        )
        message.altitude = (
            float(altitude) if isinstance(altitude, (int, float)) else math.nan
        )
        covariance = covariance_from_dop(
            hdop=sample.get("hdop"),
            vdop=sample.get("vdop"),
            uere_m=self._uere_m,
        )
        message.position_covariance = list(covariance["covariance"])
        message.position_covariance_type = int(covariance["type"])
        return message

    def _status_payload(self) -> Dict[str, Any]:
        age_s = None
        if self._last_received_at is not None:
            age_s = max(0.0, time.monotonic() - self._last_received_at)
        return gnss_quality_status(
            self._last_sample,
            enabled=self._enabled,
            message_type_available=NavSat is not None,
            age_s=age_s,
            timeout_s=self._timeout_s,
            max_hdop=self._max_hdop,
            min_satellites=self._min_satellites,
            source_topic=self._source_topic,
            fix_topic=self._fix_topic,
        )

    def _publish_status(self) -> None:
        self._status_publisher.publish(_json_message(self._status_payload()))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = GnssAdapter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
