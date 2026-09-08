#!/usr/bin/env python3
"""Visualization-only republisher for the DDDMR static map assets.

RViz renders a PointCloud2 through its message frame.  The production asset
server publishes the Lightning map with frame ``map``, but the only
``map -> base`` TF on the wire comes from the robot's own localization map
frame, which is unrelated to the Lightning map origin (measured ~1.45 m
offset on 2026-08-13), so the map appears misplaced in RViz until DDDMR MCL
converges.

This node republishes the map/ground clouds with frame ``lightning_map``.
The visualization launch pairs it with a static identity TF
``lightning_map -> m20pro_base_link``, so the map renders around the robot's
mapping pose.  It never touches the production ``map`` frame and never runs
inside the real stack; use it for RViz development viewing only.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import PointCloud2


class MapVizRepublisher(Node):
    def __init__(self) -> None:
        super().__init__("m20pro_map_viz_republisher")
        self.declare_parameter("mapcloud_topic", "/map1/mapcloud")
        self.declare_parameter("mapground_topic", "/map1/mapground")
        self.declare_parameter("viz_mapcloud_topic", "/viz/mapcloud")
        self.declare_parameter("viz_mapground_topic", "/viz/mapground")
        self.declare_parameter("viz_frame_id", "lightning_map")

        qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._viz_mapcloud = self.create_publisher(
            PointCloud2, str(self.get_parameter("viz_mapcloud_topic").value), qos
        )
        self._viz_mapground = self.create_publisher(
            PointCloud2, str(self.get_parameter("viz_mapground_topic").value), qos
        )
        self.create_subscription(
            PointCloud2,
            str(self.get_parameter("mapcloud_topic").value),
            self._republish_cloud,
            qos,
        )
        self.create_subscription(
            PointCloud2,
            str(self.get_parameter("mapground_topic").value),
            self._republish_ground,
            qos,
        )
        self.get_logger().info(
            "map viz republisher ready: %s/%s -> %s/%s (frame=%s)"
            % (
                self.get_parameter("mapcloud_topic").value,
                self.get_parameter("mapground_topic").value,
                self.get_parameter("viz_mapcloud_topic").value,
                self.get_parameter("viz_mapground_topic").value,
                self.get_parameter("viz_frame_id").value,
            )
        )

    def _republish_cloud(self, message: PointCloud2) -> None:
        self._publish_frame(self._viz_mapcloud, message)

    def _republish_ground(self, message: PointCloud2) -> None:
        self._publish_frame(self._viz_mapground, message)

    def _publish_frame(self, publisher, message: PointCloud2) -> None:
        out = PointCloud2()
        out.header = message.header
        out.header.frame_id = str(self.get_parameter("viz_frame_id").value)
        out.height = message.height
        out.width = message.width
        out.fields = message.fields
        out.is_bigendian = message.is_bigendian
        out.point_step = message.point_step
        out.row_step = message.row_step
        out.is_dense = message.is_dense
        out.data = message.data
        publisher.publish(out)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MapVizRepublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
