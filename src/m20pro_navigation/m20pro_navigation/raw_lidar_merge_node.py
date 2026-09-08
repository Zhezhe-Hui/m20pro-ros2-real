#!/usr/bin/env python3
"""Merge the two raw RSAIRY clouds into the single rigid Lightning input.

rslidar_sdk publishes the front and rear lidar (parsed from factory raw
MSOP packets, no attitude compensation) on /m20pro/raw_lidar_front and
/m20pro/raw_lidar_rear.  Lightning-LM consumes one lidar topic, so this
node time-syncs the pair and republishes the concatenated cloud on
/m20pro/lidar_points_dense_ros (the existing mapping input contract -
XYZIRT layout, point_step 26, per-point PTP timestamps.  The merged payload is
sorted by absolute point timestamp because the two lidar scan ranges overlap.

The node also writes the dense-chain heartbeat file so the mapping start
gate (scripts/104_dddmr_mapping_control.sh) sees the raw chain exactly
like the legacy vendor-passthrough chain.
"""

import os
import threading
import time
from typing import Optional

import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import PointCloud2
from std_msgs.msg import Header

from m20pro_navigation.raw_lidar_merge_contract import (
    LidarPairBuffer,
    field_signature,
    merge_payloads_by_timestamp,
    point_count,
    validate_cloud_payload,
)


class RawLidarMergeNode(Node):
    def __init__(self) -> None:
        super().__init__("m20pro_raw_lidar_merge")
        self.declare_parameter("front_topic", "/m20pro/raw_lidar_front")
        self.declare_parameter("rear_topic", "/m20pro/raw_lidar_rear")
        self.declare_parameter("output_topic", "/m20pro/lidar_points_dense_ros")
        self.declare_parameter("frame_id", "lidar_link")
        self.declare_parameter("sync_window_s", 0.02)
        self.declare_parameter("max_queue", 8)
        self.declare_parameter("max_point_time_offset_s", 0.25)
        self.declare_parameter("max_scan_span_s", 0.25)
        self.declare_parameter(
            "heartbeat_path", "/tmp/m20pro_dense_cloud_publisher.heartbeat"
        )
        self.declare_parameter(
            "recorder_path",
            os.environ.get("M20PRO_MERGE_RECORDER_PATH", "/tmp/rec_cloud.txt"),
        )
        self.declare_parameter("recorder_floor_z_min", -1.8)
        self.declare_parameter("recorder_floor_z_max", -0.3)
        front_topic = str(self.get_parameter("front_topic").value)
        rear_topic = str(self.get_parameter("rear_topic").value)
        self.output_topic = str(self.get_parameter("output_topic").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.sync_window_s = float(self.get_parameter("sync_window_s").value)
        self.max_queue = int(self.get_parameter("max_queue").value)
        self.max_point_time_offset_s = float(
            self.get_parameter("max_point_time_offset_s").value
        )
        self.max_scan_span_s = float(self.get_parameter("max_scan_span_s").value)
        self.heartbeat_path = str(self.get_parameter("heartbeat_path").value)
        self.recorder_path = str(self.get_parameter("recorder_path").value or "").strip()
        if self.recorder_path:
            with open(self.recorder_path, "a", encoding="utf-8") as handle:
                handle.write("=== recorder start t=%.3f pid=%d ===\n"
                             % (time.time(), os.getpid()))
        self.rec_z_min = float(self.get_parameter("recorder_floor_z_min").value)
        self.rec_z_max = float(self.get_parameter("recorder_floor_z_max").value)
        self._rec_offsets = None
        if self.recorder_path:
            self.get_logger().info("raw lidar forensic recorder -> %s" % self.recorder_path)
        qos = QoSProfile(depth=5, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.VOLATILE)
        self.publisher = self.create_publisher(PointCloud2, self.output_topic, qos)
        self._pairs = LidarPairBuffer(self.max_queue, self.sync_window_s)
        self._pair_lock = threading.Lock()
        self._published_count = 0
        self._invalid_count = 0
        self._mismatch_count = 0
        self._last_heartbeat = 0.0
        self._last_stamp_delta = 0.0
        self.create_subscription(PointCloud2, front_topic, self._make_cb("front"), qos)
        self.create_subscription(PointCloud2, rear_topic, self._make_cb("rear"), qos)
        self.get_logger().info(
            "raw lidar merge ready: %s + %s -> %s"
            % (front_topic, rear_topic, self.output_topic))

    def _make_cb(self, key: str):
        def callback(msg: PointCloud2) -> None:
            error = validate_cloud_payload(
                bytes(msg.data),
                msg.width,
                msg.height,
                msg.point_step,
                msg.fields,
                msg.is_bigendian,
                self._stamp(msg),
                max_point_time_offset_s=self.max_point_time_offset_s,
                max_scan_span_s=self.max_scan_span_s,
            )
            if error is not None:
                self._invalid_count += 1
                if self._invalid_count <= 3 or self._invalid_count % 100 == 0:
                    self.get_logger().warn(
                        "raw lidar %s frame rejected: %s" % (key, error)
                    )
                return
            stamp_ns = int(round(self._stamp(msg) * 1e9))
            with self._pair_lock:
                pairs = self._pairs.add(key, stamp_ns, msg)
            for pair in pairs:
                self._publish_pair(pair.front, pair.rear, pair.delta_ns)
        return callback

    @staticmethod
    def _stamp(msg: PointCloud2) -> float:
        return float(msg.header.stamp.sec) + float(msg.header.stamp.nanosec) * 1e-9

    def _publish_pair(self, front: PointCloud2, rear: PointCloud2, delta_ns: int) -> None:
        if front.point_step != rear.point_step or front.is_bigendian != rear.is_bigendian:
            self.get_logger().warn("raw lidar layout mismatch; dropping rear frame")
            self._mismatch_count += 1
            return
        if field_signature(front.fields) != field_signature(rear.fields):
            self.get_logger().warn("raw lidar field layout mismatch; dropping pair")
            self._mismatch_count += 1
            return
        front_points = point_count(front)
        rear_points = point_count(rear)
        if front_points + rear_points == 0:
            return
        merged = PointCloud2()
        merged.header = Header()
        if self._stamp(front) <= self._stamp(rear):
            merged.header.stamp = front.header.stamp
        else:
            merged.header.stamp = rear.header.stamp
        merged.header.frame_id = self.frame_id
        merged.height = 1
        merged.width = front_points + rear_points
        merged.fields = list(front.fields)
        merged.is_bigendian = bool(front.is_bigendian)
        merged.point_step = int(front.point_step)
        merged.row_step = merged.width * merged.point_step
        merged.is_dense = bool(front.is_dense) and bool(rear.is_dense)
        point_step = int(front.point_step)
        front_bytes = bytes(front.data)[:front_points * point_step]
        rear_bytes = bytes(rear.data)[:rear_points * point_step]
        timestamp_offset = next(
            int(field.offset) for field in front.fields if field.name == "timestamp"
        )
        payload = merge_payloads_by_timestamp(
            front_bytes,
            rear_bytes,
            point_step,
            timestamp_offset,
            bool(front.is_bigendian),
        )
        merged_error = validate_cloud_payload(
            payload,
            merged.width,
            merged.height,
            merged.point_step,
            merged.fields,
            merged.is_bigendian,
            self._stamp(merged),
            max_point_time_offset_s=self.max_point_time_offset_s,
            max_scan_span_s=self.max_scan_span_s,
        )
        if merged_error is not None:
            self._invalid_count += 1
            self.get_logger().warn(
                "merged raw lidar frame rejected: %s" % merged_error
            )
            return
        if "_data" in merged.__slots__:
            merged._data = payload
        else:
            merged.data = list(payload)
        delta_s = float(delta_ns) * 1e-9
        self._last_stamp_delta = delta_s
        self.publisher.publish(merged)
        self._published_count += 1
        self._record_frame(merged, payload)
        now = time.time()
        if self.heartbeat_path and now - self._last_heartbeat >= 0.5:
            self._last_heartbeat = now
            try:
                tmp_path = self.heartbeat_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as handle:
                    handle.write(
                        "stamp=%.3f frame=%d topic=%s\n"
                        "source=raw_lidar_sdk front=%s rear=%s\n"
                        % (now, self._published_count, self.output_topic,
                           "ok", "ok")
                    )
                os.replace(tmp_path, self.heartbeat_path)
            except OSError:
                pass
        if self._published_count <= 3 or self._published_count % 100 == 0:
            self.get_logger().info(
                "merged raw lidar frame=%d points=%d (%d+%d) stamp_delta=%.4fs"
                % (self._published_count, merged.width, front_points,
                   rear_points, delta_s))
        if self._published_count % 500 == 0:
            self.get_logger().info(
                "raw lidar merge stats invalid=%d mismatch=%d unmatched=%d overflow=%d stale=%d"
                % (
                    self._invalid_count,
                    self._mismatch_count,
                    self._pairs.dropped_unmatched,
                    self._pairs.dropped_overflow,
                    self._pairs.dropped_stale,
                )
            )

    def _record_frame(self, msg: PointCloud2, payload: bytes) -> None:
        if not self.recorder_path:
            return
        try:
            if self._rec_offsets is None:
                offs = {f.name: (f.offset, f.datatype) for f in msg.fields}
                self._rec_offsets = (offs["x"][0], offs["y"][0], offs["z"][0],
                                     offs["timestamp"][0])
            ox, oy, oz, ot = self._rec_offsets
            step = int(msg.point_step)
            n = int(msg.width) * int(msg.height)
            raw = np.frombuffer(payload[: n * step], dtype=np.uint8).reshape(n, step)
            xyz = np.empty((n, 3), dtype=np.float64)
            for i, o in enumerate((ox, oy, oz)):
                xyz[:, i] = np.frombuffer(raw[:, o:o + 4].tobytes(), dtype=np.float32)
            ts = np.frombuffer(raw[:, ot:ot + 8].tobytes(), dtype=np.float64)
            mask = (xyz[:, 2] > self.rec_z_min) & (xyz[:, 2] < self.rec_z_max)
            g = int(mask.sum())
            line = "t=%.3f stamp=%.3f n=%d g=%d" % (time.time(), self._stamp(msg), n, g)
            if g >= 200:
                p = xyz[mask]
                c = p - p.mean(axis=0)
                cov = c.T.dot(c) / g
                w, v = np.linalg.eigh(cov)
                normal = v[:, 0]
                if normal[2] < 0:
                    normal = -normal
                nn = normal / max(1e-9, float(np.linalg.norm(normal)))
                tilt = float(np.degrees(np.arccos(max(-1.0, min(1.0, nn[2])))))
                line += " tilt=%.3f nx=%.4f ny=%.4f nz=%.4f" % (tilt, nn[0], nn[1], nn[2])
            line += " t0=%.3f span=%.4f\n" % (float(ts.min()), float(ts.max() - ts.min()))
            with open(self.recorder_path, "a", encoding="utf-8") as handle:
                handle.write(line)
        except Exception as exc:  # recorder must never break the chain
            if self._published_count <= 3:
                self.get_logger().warn("recorder error: %s" % exc)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RawLidarMergeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
