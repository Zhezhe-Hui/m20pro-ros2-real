"""Expose local 2D odometry as the web dashboard PoseStamped source."""

from typing import Optional

import rclpy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node


class OdomPoseAdapter(Node):
    def __init__(self) -> None:
        super().__init__("m20pro_2d_odom_pose")
        self.declare_parameter("odom_topic", "/odom")
        self.declare_parameter("pose_topic", "/m20pro/2d/map_pose")
        self.publisher = self.create_publisher(
            PoseStamped, str(self.get_parameter("pose_topic").value), 10
        )
        self.create_subscription(
            Odometry,
            str(self.get_parameter("odom_topic").value),
            self._on_odom,
            10,
        )

    def _on_odom(self, msg: Odometry) -> None:
        pose = PoseStamped()
        pose.header = msg.header
        pose.pose = msg.pose.pose
        self.publisher.publish(pose)


def main(args: Optional[list] = None) -> None:
    rclpy.init(args=args)
    node = OdomPoseAdapter()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
