#!/usr/bin/env python3
"""Publish socket-bridged DrDDS edge clouds as native ROS PointCloud2."""

import os
import socket
import struct
import threading
import time
from typing import Optional, Tuple

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import PointCloud2, PointField
from std_msgs.msg import Header


MAGIC = 0x4D323043
VERSION = 1
HEADER = struct.Struct("<IIiIII")


class DddmrSocketCloudPublisher(Node):
    def __init__(self) -> None:
        super().__init__("m20pro_dddmr_socket_cloud_publisher")
        self.declare_parameter("socket_path", "/tmp/m20pro_edge_cloud.sock")
        self.declare_parameter("output_topic", "/m20pro/edge_cloud")
        self.declare_parameter("frame_id", "m20pro_base_link")
        self.declare_parameter("drop_non_monotonic_stamps", True)
        self.declare_parameter("source_stamp_reset_timeout_s", 2.0)
        self.declare_parameter("restamp_on_publish", True)
        self.socket_path = str(self.get_parameter("socket_path").value)
        self.output_topic = str(self.get_parameter("output_topic").value)
        self.fallback_frame = str(self.get_parameter("frame_id").value)
        self.drop_non_monotonic_stamps = bool(
            self.get_parameter("drop_non_monotonic_stamps").value
        )
        self.source_stamp_reset_timeout_s = max(
            0.1,
            float(self.get_parameter("source_stamp_reset_timeout_s").value),
        )
        self.restamp_on_publish = bool(
            self.get_parameter("restamp_on_publish").value
        )
        qos = QoSProfile(depth=5, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.VOLATILE)
        self.publisher = self.create_publisher(PointCloud2, self.output_topic, qos)
        self._lock = threading.Lock()
        self._latest: Optional[Tuple[int, int, str, bytes]] = None
        self._published_count = 0
        self._last_source_stamp_ns: Optional[int] = None
        self._last_accepted_monotonic: Optional[float] = None
        self._dropped_non_monotonic = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()
        self.create_timer(0.02, self._publish_latest)
        self.get_logger().info("socket cloud publisher ready: %s -> %s" %
                               (self.socket_path, self.output_topic))

    def _read_exact(self, conn: socket.socket, length: int) -> Optional[bytes]:
        chunks = bytearray()
        while len(chunks) < length and not self._stop.is_set():
            chunk = conn.recv(length - len(chunks))
            if not chunk:
                return None
            chunks.extend(chunk)
        return bytes(chunks)

    def _receive_loop(self) -> None:
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        os.makedirs(os.path.dirname(self.socket_path) or ".", exist_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.socket_path)
        os.chmod(self.socket_path, 0o666)
        server.listen(1)
        server.settimeout(1.0)
        try:
            while not self._stop.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                with conn:
                    while not self._stop.is_set():
                        raw_header = self._read_exact(conn, HEADER.size)
                        if raw_header is None:
                            break
                        magic, version, sec, nanosec, count, frame_size = HEADER.unpack(raw_header)
                        if magic != MAGIC or version != VERSION or count > 100000 or frame_size > 512:
                            break
                        frame_raw = self._read_exact(conn, frame_size)
                        points = self._read_exact(conn, count * 3 * 4)
                        if frame_raw is None or points is None:
                            break
                        frame = frame_raw.decode("utf-8", errors="replace") or self.fallback_frame
                        source_stamp_ns = int(sec) * 1_000_000_000 + int(nanosec)
                        now_monotonic = time.monotonic()
                        reset_elapsed = (
                            self._last_accepted_monotonic is not None
                            and now_monotonic - self._last_accepted_monotonic
                            > self.source_stamp_reset_timeout_s
                        )
                        if (
                            self.drop_non_monotonic_stamps
                            and source_stamp_ns > 0
                            and self._last_source_stamp_ns is not None
                            and source_stamp_ns <= self._last_source_stamp_ns
                            and not reset_elapsed
                        ):
                            self._dropped_non_monotonic += 1
                            if (
                                self._dropped_non_monotonic <= 3
                                or self._dropped_non_monotonic % 100 == 0
                            ):
                                self.get_logger().warning(
                                    "dropped non-monotonic socket cloud count=%d source_stamp_ns=%d last_stamp_ns=%d"
                                    % (
                                        self._dropped_non_monotonic,
                                        source_stamp_ns,
                                        self._last_source_stamp_ns,
                                    )
                                )
                            continue
                        if source_stamp_ns > 0:
                            self._last_source_stamp_ns = source_stamp_ns
                        self._last_accepted_monotonic = now_monotonic
                        with self._lock:
                            self._latest = (sec, nanosec, frame, points)
        finally:
            server.close()
            try:
                os.unlink(self.socket_path)
            except FileNotFoundError:
                pass

    def _publish_latest(self) -> None:
        with self._lock:
            latest = self._latest
            self._latest = None
        if latest is None:
            return
        sec, nanosec, frame, points = latest
        message = PointCloud2()
        message.header = Header()
        if self.restamp_on_publish:
            message.header.stamp = self.get_clock().now().to_msg()
        else:
            message.header.stamp.sec = int(sec)
            message.header.stamp.nanosec = int(nanosec)
        message.header.frame_id = frame
        message.height = 1
        message.width = len(points) // 12
        message.fields = [
            PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
            PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
            PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
        ]
        message.is_bigendian = False
        message.point_step = 12
        message.row_step = len(points)
        message.is_dense = False
        # Foxy converts bytes through a Python integer list in the generated
        # setter. The native bytes slot avoids that copy and keeps the relay
        # from building a latency queue on RK3588.
        if "_data" in message.__slots__:
            message._data = points
        else:
            message.data = list(points)
        self.publisher.publish(message)
        self._published_count += 1
        if self._published_count <= 3 or self._published_count % 20 == 0:
            self.get_logger().info(
                "published socket cloud frame=%d points=%d frame=%s" %
                (self._published_count, message.width, message.header.frame_id)
            )

    def destroy_node(self):
        self._stop.set()
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DddmrSocketCloudPublisher()
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
