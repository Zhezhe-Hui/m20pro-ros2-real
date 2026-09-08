#!/usr/bin/env python3
"""Publish zero joint positions for the RViz-only M20Pro model."""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import JointState
from std_msgs.msg import String


class VisualJointStatePublisher(Node):
    def __init__(self):
        super().__init__("m20pro_visual_joint_state_publisher")
        self.declare_parameter("joint_names", [])
        self.declare_parameter("rate_hz", 20.0)
        self.declare_parameter("robot_description", "")
        self.joint_names = list(self.get_parameter("joint_names").value or [])
        robot_description = str(self.get_parameter("robot_description").value or "")
        rate_hz = max(1.0, float(self.get_parameter("rate_hz").value))
        self.publisher = self.create_publisher(
            JointState, "/m20pro/visualization/joint_states", 10
        )
        description_qos = QoSProfile(depth=1)
        description_qos.reliability = ReliabilityPolicy.RELIABLE
        description_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.description_publisher = self.create_publisher(
            String, "/robot_description", description_qos
        )
        description_message = String()
        description_message.data = robot_description
        self.description_publisher.publish(description_message)
        self.timer = self.create_timer(1.0 / rate_hz, self.publish_joint_state)

    def publish_joint_state(self):
        message = JointState()
        message.header.stamp = self.get_clock().now().to_msg()
        message.name = self.joint_names
        message.position = [0.0] * len(self.joint_names)
        self.publisher.publish(message)


def main():
    rclpy.init()
    node = VisualJointStatePublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
