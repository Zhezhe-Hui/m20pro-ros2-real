"""Convert M20Pro body motion telemetry into local odometry for DDDMR.

The official DDDMR localization front-end needs continuous robot-frame odometry.
The factory TCP pose can be unavailable while the robot is not localized, so it
must not be the only /odom source for DDDMR.  /MOTION_INFO carries chassis-frame
velocities and remains available in that state; this node integrates those
velocities into a clean local odom frame for the DDDMR runtime.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import rclpy
from geometry_msgs.msg import Quaternion
from nav_msgs.msg import Odometry
from rclpy.node import Node

try:
    from drdds.msg import MotionInfo
except ImportError:  # pragma: no cover - only available on the robot image
    MotionInfo = None  # type: ignore[assignment]


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        output = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return output if math.isfinite(output) else default


def _yaw_quaternion(yaw: float) -> Quaternion:
    quat = Quaternion()
    half = yaw * 0.5
    quat.z = math.sin(half)
    quat.w = math.cos(half)
    return quat


class MotionInfoOdomAdapter(Node):
    def __init__(self) -> None:
        super().__init__("m20pro_motion_info_odom_adapter")
        self.declare_parameter("input_topic", "/MOTION_INFO")
        self.declare_parameter("odom_topic", "/m20pro/dddmr/odom")
        self.declare_parameter("odom_frame", "odom")
        self.declare_parameter("base_frame", "m20pro_base_link")
        self.declare_parameter("max_dt_s", 0.5)
        self.declare_parameter("velocity_deadband_mps", 0.005)
        self.declare_parameter("yaw_rate_deadband_radps", 0.002)
        self.declare_parameter("pose_z", 0.0)

        self._x = 0.0
        self._y = 0.0
        self._yaw = 0.0
        self._last_time = None
        self._pub = self.create_publisher(
            Odometry, str(self.get_parameter("odom_topic").value), 10
        )
        if MotionInfo is None:
            self.get_logger().error("drdds.msg.MotionInfo is unavailable")
            return
        self.create_subscription(
            MotionInfo,
            str(self.get_parameter("input_topic").value),
            self._on_motion_info,
            10,
        )
        self.get_logger().info(
            "motion-info odom adapter ready: %s -> %s"
            % (
                self.get_parameter("input_topic").value,
                self.get_parameter("odom_topic").value,
            )
        )

    def _on_motion_info(self, message: Any) -> None:
        now = self.get_clock().now()
        dt = 0.0
        if self._last_time is not None:
            dt = (now - self._last_time).nanoseconds * 1e-9
        self._last_time = now
        max_dt = max(0.01, _finite(self.get_parameter("max_dt_s").value, 0.5))
        if dt < 0.0 or dt > max_dt:
            dt = 0.0

        data = getattr(message, "data", message)
        vx = _finite(getattr(data, "vel_x", 0.0))
        vy = _finite(getattr(data, "vel_y", 0.0))
        wz = _finite(getattr(data, "vel_yaw", 0.0))
        if abs(vx) < _finite(self.get_parameter("velocity_deadband_mps").value, 0.005):
            vx = 0.0
        if abs(vy) < _finite(self.get_parameter("velocity_deadband_mps").value, 0.005):
            vy = 0.0
        if abs(wz) < _finite(self.get_parameter("yaw_rate_deadband_radps").value, 0.002):
            wz = 0.0

        if dt > 0.0:
            cos_yaw = math.cos(self._yaw)
            sin_yaw = math.sin(self._yaw)
            self._x += (vx * cos_yaw - vy * sin_yaw) * dt
            self._y += (vx * sin_yaw + vy * cos_yaw) * dt
            self._yaw = math.atan2(math.sin(self._yaw + wz * dt), math.cos(self._yaw + wz * dt))

        odom = Odometry()
        odom.header.stamp = now.to_msg()
        odom.header.frame_id = str(self.get_parameter("odom_frame").value or "odom")
        odom.child_frame_id = str(self.get_parameter("base_frame").value or "m20pro_base_link")
        odom.pose.pose.position.x = self._x
        odom.pose.pose.position.y = self._y
        odom.pose.pose.position.z = _finite(self.get_parameter("pose_z").value, 0.0)
        odom.pose.pose.orientation = _yaw_quaternion(self._yaw)
        odom.twist.twist.linear.x = vx
        odom.twist.twist.linear.y = vy
        odom.twist.twist.angular.z = wz
        odom.pose.covariance[0] = 0.05
        odom.pose.covariance[7] = 0.05
        odom.pose.covariance[14] = 0.20
        odom.pose.covariance[35] = 0.10
        odom.twist.covariance[0] = 0.10
        odom.twist.covariance[7] = 0.10
        odom.twist.covariance[35] = 0.10
        self._pub.publish(odom)


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = MotionInfoOdomAdapter()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
