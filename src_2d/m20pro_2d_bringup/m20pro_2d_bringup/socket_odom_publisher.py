#!/usr/bin/env python3
"""Publish an isolated 2D odometry topic and TF from MotionInfo socket data."""

import math
import os
import socket
import struct
import threading
from typing import Optional

import rclpy
from geometry_msgs.msg import Quaternion, TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from tf2_ros import TransformBroadcaster


FRAME = struct.Struct("<IIfff")
MAGIC = 0x4D32304F
VERSION = 1


class SocketOdomPublisher(Node):
    def __init__(self) -> None:
        super().__init__("m20pro_2d_motion_odom")
        self.declare_parameter(
            "socket_path", "/run/m20pro/dddmr_motion_info.sock"
        )
        self.declare_parameter("output_topic", "/odom")
        self.declare_parameter("odom_frame", "odom")
        self.declare_parameter("base_frame", "m20pro_base_link")
        self.declare_parameter("publish_rate_hz", 50.0)

        self.socket_path = str(self.get_parameter("socket_path").value)
        self.odom_frame = str(self.get_parameter("odom_frame").value)
        self.base_frame = str(self.get_parameter("base_frame").value)
        output_topic = str(self.get_parameter("output_topic").value)
        publish_rate_hz = max(
            1.0, float(self.get_parameter("publish_rate_hz").value)
        )

        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self.publisher = self.create_publisher(Odometry, output_topic, qos)
        self.tf_broadcaster = TransformBroadcaster(self)
        self.lock = threading.Lock()
        self.latest = None
        self.stop_event = threading.Event()
        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0
        self.last_stamp_ns: Optional[int] = None

        self.thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.thread.start()
        self.create_timer(1.0 / publish_rate_hz, self._publish)
        self.get_logger().info(
            "2D MotionInfo odometry ready: %s -> %s -> %s"
            % (self.socket_path, self.odom_frame, self.base_frame)
        )

    @staticmethod
    def _read_frame(connection: socket.socket):
        data = bytearray()
        while len(data) < FRAME.size:
            part = connection.recv(FRAME.size - len(data))
            if not part:
                return None
            data.extend(part)
        return FRAME.unpack(data)

    def _receive_loop(self) -> None:
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        os.makedirs(os.path.dirname(self.socket_path), exist_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.socket_path)
        os.chmod(self.socket_path, 0o666)
        server.listen(1)
        server.settimeout(1.0)
        while not self.stop_event.is_set():
            try:
                connection, _ = server.accept()
            except socket.timeout:
                continue
            with connection:
                while not self.stop_event.is_set():
                    frame = self._read_frame(connection)
                    if frame is None:
                        break
                    if frame[0] != MAGIC or frame[1] != VERSION:
                        continue
                    velocities = tuple(
                        float(value) if math.isfinite(float(value)) else 0.0
                        for value in frame[2:]
                    )
                    with self.lock:
                        self.latest = velocities
        server.close()

    def _publish(self) -> None:
        with self.lock:
            velocities = self.latest
            self.latest = None
        if velocities is None:
            return

        vx, vy, wz = velocities
        now = self.get_clock().now()
        now_ns = now.nanoseconds
        dt = (
            0.0
            if self.last_stamp_ns is None
            else (now_ns - self.last_stamp_ns) * 1e-9
        )
        self.last_stamp_ns = now_ns
        if 0.0 < dt <= 0.5:
            cos_yaw = math.cos(self.yaw)
            sin_yaw = math.sin(self.yaw)
            self.x += (vx * cos_yaw - vy * sin_yaw) * dt
            self.y += (vx * sin_yaw + vy * cos_yaw) * dt
            self.yaw = math.atan2(
                math.sin(self.yaw + wz * dt), math.cos(self.yaw + wz * dt)
            )

        orientation = Quaternion(
            z=math.sin(self.yaw / 2.0), w=math.cos(self.yaw / 2.0)
        )
        message = Odometry()
        message.header.stamp = now.to_msg()
        message.header.frame_id = self.odom_frame
        message.child_frame_id = self.base_frame
        message.pose.pose.position.x = self.x
        message.pose.pose.position.y = self.y
        message.pose.pose.orientation = orientation
        message.twist.twist.linear.x = vx
        message.twist.twist.linear.y = vy
        message.twist.twist.angular.z = wz
        message.pose.covariance[0] = 0.05
        message.pose.covariance[7] = 0.05
        message.pose.covariance[35] = 0.10
        self.publisher.publish(message)

        transform = TransformStamped()
        transform.header.stamp = message.header.stamp
        transform.header.frame_id = self.odom_frame
        transform.child_frame_id = self.base_frame
        transform.transform.translation.x = self.x
        transform.transform.translation.y = self.y
        transform.transform.rotation = orientation
        self.tf_broadcaster.sendTransform(transform)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SocketOdomPublisher()
    try:
        rclpy.spin(node)
    finally:
        node.stop_event.set()
        node.destroy_node()
        rclpy.shutdown()
