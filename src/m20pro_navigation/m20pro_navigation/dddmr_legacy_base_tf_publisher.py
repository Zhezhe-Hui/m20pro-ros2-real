"""Continuously publish the zero-offset base-frame alias required by LeGO MCL."""

from __future__ import annotations

import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros import TransformBroadcaster


class LegacyBaseTfPublisher(Node):
    def __init__(self) -> None:
        super().__init__("m20pro_dddmr_legacy_base_alias")
        self.declare_parameter("base_frame", "m20pro_base_link")
        self.declare_parameter("legacy_base_frame", "base_link")
        self.declare_parameter("publish_hz", 10.0)
        self._base_frame = str(self.get_parameter("base_frame").value).strip("/")
        self._legacy_frame = str(
            self.get_parameter("legacy_base_frame").value
        ).strip("/")
        rate_hz = max(1.0, float(self.get_parameter("publish_hz").value))
        self._broadcaster = TransformBroadcaster(self)
        self._transform = TransformStamped()
        self._transform.header.frame_id = self._base_frame
        self._transform.child_frame_id = self._legacy_frame
        self._transform.transform.rotation.w = 1.0
        self.create_timer(1.0 / rate_hz, self._publish)

    def _publish(self) -> None:
        self._transform.header.stamp = self.get_clock().now().to_msg()
        self._broadcaster.sendTransform(self._transform)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = LegacyBaseTfPublisher()
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
