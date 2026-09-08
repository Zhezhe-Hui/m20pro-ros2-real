#!/usr/bin/env python3
"""Verify the M20Pro edge-cloud adapter in an isolated ROS graph."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from typing import Any, Callable, Dict, List

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Header, String


TIMEOUT_S = 8.0


class Harness(Node):
    def __init__(self, prefix: str) -> None:
        super().__init__("dddmr_edge_cloud_smoke_%d" % os.getpid())
        qos = QoSProfile(depth=5)
        qos.reliability = ReliabilityPolicy.BEST_EFFORT
        qos.durability = DurabilityPolicy.VOLATILE
        self.input_pub = self.create_publisher(PointCloud2, "%s/input" % prefix, qos)
        self.outputs: List[PointCloud2] = []
        self.statuses: List[Dict[str, Any]] = []
        self.create_subscription(PointCloud2, "%s/output" % prefix, self.outputs.append, qos)
        self.create_subscription(String, "%s/status" % prefix, self._on_status, 10)

    def _on_status(self, message: String) -> None:
        try:
            value = json.loads(message.data)
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        if isinstance(value, dict):
            self.statuses.append(value)


def spin_until(node: Node, condition: Callable[[], bool], label: str) -> None:
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
        if condition():
            return
    raise AssertionError("timed out waiting for %s" % label)


def cloud(frame: str) -> PointCloud2:
    header = Header()
    header.frame_id = frame
    points = [(1.0 + index * 0.01, 0.2, 0.4 + index * 0.001) for index in range(25)]
    message = point_cloud2.create_cloud_xyz32(header, points)
    # Reproduce the vendor defect seen on 104: serialized data contains all
    # points while width/row_step describe only the first point.
    message.width = 1
    message.row_step = message.point_step
    return message


def main() -> None:
    os.environ["ROS_LOCALHOST_ONLY"] = "1"
    os.environ["ROS_DOMAIN_ID"] = str(200 + os.getpid() % 20)
    prefix = "/dddmr_edge_cloud_smoke_%d" % os.getpid()
    command = [
        "ros2",
        "run",
        "m20pro_bringup",
        "dddmr_edge_cloud_adapter",
        "--ros-args",
        "-p",
        "input_topic:=%s/input" % prefix,
        "-p",
        "output_topic:=%s/output" % prefix,
        "-p",
        "status_topic:=%s/status" % prefix,
        "-p",
        "publish_period_s:=0.05",
        "-p",
        "cloud_timeout_s:=0.25",
        "-p",
        "min_points:=20",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        env=dict(os.environ),
    )
    rclpy.init()
    node = Harness(prefix)
    try:
        spin_until(node, lambda: bool(node.statuses), "adapter status")
        node.input_pub.publish(cloud("m20pro_base_link"))
        spin_until(node, lambda: bool(node.outputs), "normalized edge cloud")
        values = list(
            point_cloud2.read_points(
                node.outputs[-1], field_names=("x", "y", "z"), skip_nans=False
            )
        )
        assert len(values) == 25
        assert abs(float(values[0][2]) - 0.4) < 1e-6
        spin_until(
            node,
            lambda: node.statuses and node.statuses[-1].get("ready") is False,
            "stale edge cloud status",
        )
        node.input_pub.publish(cloud("lidar_link"))
        spin_until(
            node,
            lambda: node.statuses
            and node.statuses[-1].get("code") == "edge_cloud_frame_mismatch",
            "frame rejection",
        )
    finally:
        node.destroy_node()
        rclpy.shutdown()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3.0)
        output = process.stdout.read() if process.stdout is not None else ""
        if process.returncode not in (0, -signal.SIGINT):
            raise AssertionError("adapter process failed:\n%s" % output)
    print("DDDMR edge-cloud ROS smoke test passed")


if __name__ == "__main__":
    main()
