#!/usr/bin/env python3
"""Publish socket-bridged dense full-field clouds as native ROS PointCloud2.

Mirrors dddmr_socket_cloud_publisher.py, but the socket frames carry the
complete vendor PointCloud2 (x/y/z/intensity/ring/timestamp) so Lightning-LM
receives the real 96-line scan semantics instead of an xyz-only rebuild.

2026-08-20 attitude de-leveling (root cause fix, see dense_cloud_delevel.py):
the vendor driver interleaves merged (attitude-leveled) and single-lidar
(rigid) frames on /LIDAR/POINTS.  Lightning assumes one rigid sensor plus
IMU deskew, so this node drops the single-lidar frames and rotates merged
frames back into the body frame with the /IMU accelerometer roll/pitch at
the frame stamp before publishing.
"""

import os
import socket
import struct
import threading
import time
from typing import Optional, Tuple

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu, PointCloud2, PointField
from std_msgs.msg import Header

try:
    from m20pro_navigation.dense_cloud_delevel import (
        BACK_HEMISPHERE_X_MAX,
        FRAME_EMPTY,
        FRAME_FRONT_ONLY,
        FRAME_MERGED,
        FRAME_REAR_ONLY,
        FRONT_HEMISPHERE_X_MIN,
        ImuAttitudeTracker,
        apply_matrix_to_xyz_buffer,
        classify_hemispheres,
        delevel_matrix,
    )
except ImportError:
    # The dense chain launches this file by bare path; without the workspace
    # overlay the package root is not importable, so fall back to the module
    # living next to this file.
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from dense_cloud_delevel import (
        BACK_HEMISPHERE_X_MAX,
        FRAME_EMPTY,
        FRAME_FRONT_ONLY,
        FRAME_MERGED,
        FRAME_REAR_ONLY,
        FRONT_HEMISPHERE_X_MIN,
        ImuAttitudeTracker,
        apply_matrix_to_xyz_buffer,
        classify_hemispheres,
        delevel_matrix,
    )


MAGIC = b"M20PC2DF"
VERSION = 1
# magic(8s) version(I) sec(i) nanosec(I) frame_len(I) height(I) width(I)
# bigendian(B) dense(B) point_step(I) row_step(I) field_count(I)
FIXED = struct.Struct("<8sIiIIIIBBIII")
FIELD_HEAD = struct.Struct("<I")


class DddmrDenseCloudPublisher(Node):
    def __init__(self) -> None:
        super().__init__("m20pro_dddmr_dense_cloud_publisher")
        self.declare_parameter("socket_path", "/run/m20pro/lidar_points_dense.sock")
        self.declare_parameter("output_topic", "/m20pro/lidar_points_dense_ros")
        self.declare_parameter("frame_id", "")
        self.declare_parameter(
            "heartbeat_path", "/tmp/m20pro_dense_cloud_publisher.heartbeat"
        )
        # Attitude de-leveling parameters (2026-08-20 root cause fix).
        self.declare_parameter("attitude_delevel_enabled", True)
        self.declare_parameter("drop_single_lidar_frames", True)
        self.declare_parameter("imu_topic", "/IMU")
        self.declare_parameter("delevel_window_s", 0.30)
        self.declare_parameter("delevel_lookahead_s", 0.05)
        self.declare_parameter("delevel_min_samples", 10)
        self.socket_path = str(self.get_parameter("socket_path").value)
        self.output_topic = str(self.get_parameter("output_topic").value)
        self.fallback_frame = str(self.get_parameter("frame_id").value)
        self.heartbeat_path = str(self.get_parameter("heartbeat_path").value)
        self.delevel_enabled = bool(self.get_parameter("attitude_delevel_enabled").value)
        self.drop_singles = bool(self.get_parameter("drop_single_lidar_frames").value)
        self.imu_topic = str(self.get_parameter("imu_topic").value)
        self.delevel_window_s = float(self.get_parameter("delevel_window_s").value)
        self.delevel_lookahead_s = float(self.get_parameter("delevel_lookahead_s").value)
        self.delevel_min_samples = int(self.get_parameter("delevel_min_samples").value)
        qos = QoSProfile(depth=5, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.VOLATILE)
        self.publisher = self.create_publisher(PointCloud2, self.output_topic, qos)
        self._lock = threading.Lock()
        self._latest: Optional[PointCloud2] = None
        self._published_count = 0
        self._dropped_single_count = 0
        self._dropped_no_attitude_count = 0
        self._deleveled_count = 0
        self._last_heartbeat = 0.0
        self._stop = threading.Event()
        self._tracker = ImuAttitudeTracker()
        self._tracker_lock = threading.Lock()
        if self.delevel_enabled:
            imu_qos = QoSProfile(depth=400, reliability=ReliabilityPolicy.RELIABLE,
                                 durability=DurabilityPolicy.VOLATILE)
            self.create_subscription(Imu, self.imu_topic, self._on_imu, imu_qos)
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()
        self.create_timer(0.02, self._publish_latest)
        self.get_logger().info(
            "dense cloud publisher ready: %s -> %s (delevel=%s drop_singles=%s imu=%s)"
            % (self.socket_path, self.output_topic,
               self.delevel_enabled, self.drop_singles, self.imu_topic))

    def _on_imu(self, msg: Imu) -> None:
        try:
            stamp = float(msg.header.stamp.sec) + float(msg.header.stamp.nanosec) * 1e-9
            accel = msg.linear_acceleration
            sample = (stamp, accel.x, accel.y, accel.z)
        except (AttributeError, TypeError, ValueError):
            return
        with self._tracker_lock:
            self._tracker.add(*sample)

    def _read_exact(self, conn: socket.socket, length: int) -> Optional[bytes]:
        chunks = bytearray()
        while len(chunks) < length and not self._stop.is_set():
            chunk = conn.recv(length - len(chunks))
            if not chunk:
                return None
            chunks.extend(chunk)
        return bytes(chunks)

    def _delevel_message(self, message: PointCloud2) -> Optional[PointCloud2]:
        """Classify + restore rigid-body geometry; None means drop the frame."""
        try:
            import numpy
        except ImportError:
            self.get_logger().warn("numpy missing; de-leveling disabled")
            self.delevel_enabled = False
            return message
        data = bytes(message.data)
        point_step = int(message.point_step)
        if point_step < 12 or len(data) % point_step != 0:
            return message
        try:
            flat = numpy.frombuffer(data, dtype=numpy.uint8).reshape(-1, point_step)
            xs = numpy.frombuffer(flat[:, 0:4].tobytes(), dtype=numpy.float32)
            valid = numpy.isfinite(xs)
            front_count = int(numpy.count_nonzero(valid & (xs > FRONT_HEMISPHERE_X_MIN)))
            back_count = int(numpy.count_nonzero(valid & (xs < BACK_HEMISPHERE_X_MAX)))
            family = classify_hemispheres(front_count, back_count, int(xs.size))
        except (ValueError, struct.error):
            return message
        if family == FRAME_EMPTY:
            return message
        if family in (FRAME_FRONT_ONLY, FRAME_REAR_ONLY):
            if self.drop_singles:
                self._dropped_single_count += 1
                return None
            return message
        if family != FRAME_MERGED:
            return message
        stamp = float(message.header.stamp.sec) + float(message.header.stamp.nanosec) * 1e-9
        with self._tracker_lock:
            estimate = self._tracker.roll_pitch_at(
                stamp,
                window_s=self.delevel_window_s,
                lookahead_s=self.delevel_lookahead_s,
                min_samples=self.delevel_min_samples,
            )
        if estimate is None:
            self._dropped_no_attitude_count += 1
            if self._dropped_no_attitude_count <= 3 or self._dropped_no_attitude_count % 100 == 0:
                self.get_logger().warn(
                    "no usable /IMU attitude for merged frame stamp=%.3f (dropped=%d); "
                    "frame withheld so the mapper never sees leveled geometry"
                    % (stamp, self._dropped_no_attitude_count))
            return None
        roll, pitch, _used = estimate
        try:
            new_data = apply_matrix_to_xyz_buffer(
                data, point_step, delevel_matrix(roll, pitch))
        except (ValueError, RuntimeError) as exc:
            self.get_logger().warn("de-level transform failed: %s" % exc)
            return message
        if "_data" in message.__slots__:
            message._data = new_data
        else:
            message.data = list(new_data)
        self._deleveled_count += 1
        if self._deleveled_count <= 3 or self._deleveled_count % 500 == 0:
            self.get_logger().info(
                "delevel frame=%d roll=%.3fdeg pitch=%.3fdeg points=%d"
                % (self._deleveled_count, roll * 57.29578, pitch * 57.29578,
                   len(data) // point_step))
        return message

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
                self.get_logger().info("dense socket client connected")
                with conn:
                    while not self._stop.is_set():
                        raw_fixed = self._read_exact(conn, FIXED.size)
                        if raw_fixed is None:
                            self.get_logger().warn("dense socket client disconnected")
                            break
                        try:
                            (magic, version, sec, nanosec, frame_len,
                             height, width, bigendian, dense, point_step,
                             row_step, field_count) = FIXED.unpack(raw_fixed)
                        except struct.error:
                            self.get_logger().warn("dense socket bad fixed header")
                            break
                        if magic != MAGIC or version != VERSION:
                            self.get_logger().warn("dense socket bad magic/version: %r %d" %
                                                   (magic, version))
                            break
                        if frame_len > 256 or field_count > 64 or height > 64:
                            self.get_logger().warn(
                                "dense socket implausible header frame_len=%d field_count=%d height=%d" %
                                (frame_len, field_count, height))
                            break
                        frame_raw = self._read_exact(conn, frame_len)
                        if frame_raw is None:
                            self.get_logger().warn("dense socket eof at frame name")
                            break
                        fields = []
                        bad_fields = False
                        for _ in range(field_count):
                            raw_name_head = self._read_exact(conn, FIELD_HEAD.size)
                            if raw_name_head is None:
                                bad_fields = True
                                break
                            (name_len,) = FIELD_HEAD.unpack(raw_name_head)
                            if name_len > 256:
                                self.get_logger().warn("dense socket bad field name_len=%d" % name_len)
                                bad_fields = True
                                break
                            name_raw = self._read_exact(conn, name_len)
                            raw_field_tail = self._read_exact(conn, 9)
                            if name_raw is None or raw_field_tail is None:
                                bad_fields = True
                                break
                            offset, datatype, count = struct.unpack("<IBI", raw_field_tail)
                            fields.append(PointField(
                                name=name_raw.decode("utf-8", errors="replace"),
                                offset=offset, datatype=datatype, count=count))
                        if bad_fields:
                            break
                        if len(fields) != field_count:
                            self.get_logger().warn("dense socket field count mismatch %d/%d" %
                                                   (len(fields), field_count))
                            break
                        raw_data_len = self._read_exact(conn, 8)
                        if raw_data_len is None:
                            self.get_logger().warn("dense socket eof at data length")
                            break
                        (data_len,) = struct.unpack("<Q", raw_data_len)
                        if data_len > 64 * 1024 * 1024:
                            self.get_logger().warn("dense socket implausible data_len=%d" % data_len)
                            break
                        data = self._read_exact(conn, data_len)
                        if data is None:
                            self.get_logger().warn("dense socket eof at data payload")
                            break
                        message = PointCloud2()
                        message.header = Header()
                        message.header.stamp.sec = sec
                        message.header.stamp.nanosec = nanosec
                        message.header.frame_id = (
                            frame_raw.decode("utf-8", errors="replace")
                            or self.fallback_frame)
                        message.height = height
                        message.width = width
                        message.fields = fields
                        message.is_bigendian = bool(bigendian)
                        message.point_step = point_step
                        message.row_step = row_step
                        message.is_dense = bool(dense)
                        # Bypass the generated 'data' property setter: on
                        # Foxy it converts the 1MB payload into a Python
                        # list of ints (~850ms/frame on RK3588, blocking the
                        # receive thread via the GIL and throttling the whole
                        # DrDDS chain).  Assigning the raw bytes attribute
                        # directly keeps publish at ~1.5ms/frame.
                        # The generated message stores the payload in the
                        # `_data` slot (Foxy sensor_msgs layout); if a future
                        # ROS2 version renames it, fall back to the property
                        # setter so the node still works (slowly) instead of
                        # crashing the receive loop.
                        if "_data" in message.__slots__:
                            message._data = data
                        else:
                            message.data = list(data)
                        if self.delevel_enabled:
                            message = self._delevel_message(message)
                            if message is None:
                                continue
                        with self._lock:
                            self._latest = message
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
        self.publisher.publish(latest)
        self._published_count += 1
        now = time.time()
        if self.heartbeat_path and now - self._last_heartbeat >= 0.5:
            # Frame-level liveness signal for the mapping gate: fresh mtime
            # means the whole dense chain (106 passthrough -> 104 socket
            # bridge -> this publisher) delivered a publishable frame within
            # the window. Checking the file is instant, unlike booting a new
            # rclpy participant per status call on the loaded RK3588.
            self._last_heartbeat = now
            try:
                tmp_path = self.heartbeat_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as handle:
                    handle.write(
                        "stamp=%.3f frame=%d topic=%s\n"
                        "delevel=%s published=%d deleveled=%d dropped_single=%d "
                        "dropped_no_attitude=%d\n"
                        % (now, self._published_count, self.output_topic,
                           "on" if self.delevel_enabled else "off",
                           self._published_count, self._deleveled_count,
                           self._dropped_single_count,
                           self._dropped_no_attitude_count)
                    )
                os.replace(tmp_path, self.heartbeat_path)
            except OSError:
                pass
        if self._published_count <= 3 or self._published_count % 100 == 0:
            self.get_logger().info(
                "published dense cloud frame=%d points=%d frame=%s point_step=%d"
                % (self._published_count, latest.width,
                   latest.header.frame_id, latest.point_step))

    def destroy_node(self):
        self._stop.set()
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DddmrDenseCloudPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
