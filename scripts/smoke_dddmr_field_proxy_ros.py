#!/usr/bin/env python3
"""ROS smoke test for the low-speed DDDMR field-proxy runtime."""

from __future__ import annotations

import json
import math
import os
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import TransformStamped, Twist
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
from tf2_ros import TransformBroadcaster

try:
    from dddmr_sys_core.action import PToPMoveBase
except ImportError:
    PToPMoveBase = None  # type: ignore[assignment,misc]


TIMEOUT_S = 8.0


def wait_until(condition: Callable[[], bool], label: str, timeout_s: float = TIMEOUT_S) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError("timed out waiting for %s" % label)


class Harness(Node):
    def __init__(self, prefix: str) -> None:
        super().__init__("dddmr_field_proxy_smoke_%d" % os.getpid())
        self._lock = threading.RLock()
        self._prefix = prefix
        self.statuses: List[Dict[str, Any]] = []
        self.commands: List[Twist] = []
        self.feedback: List[Any] = []
        self.publish_tf = False
        self.tf_broadcaster = TransformBroadcaster(self)
        self.create_subscription(
            String,
            "%s/runtime/status" % prefix,
            self._on_status,
            10,
        )
        self.create_subscription(
            Twist,
            "%s/dddmr_cmd_vel" % prefix,
            self._on_command,
            10,
        )
        self.client = ActionClient(
            self,
            PToPMoveBase,
            "%s/p2p_move_base" % prefix,
        )
        self.create_timer(0.05, self._publish_tf)

    def _publish_tf(self) -> None:
        if not self.publish_tf:
            return
        transform = TransformStamped()
        transform.header.stamp = self.get_clock().now().to_msg()
        transform.header.frame_id = "map"
        transform.child_frame_id = "m20pro_base_link"
        transform.transform.rotation.w = 1.0
        self.tf_broadcaster.sendTransform(transform)

    def _on_status(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            with self._lock:
                self.statuses.append(payload)

    def _on_command(self, command: Twist) -> None:
        with self._lock:
            self.commands.append(command)

    def _on_feedback(self, feedback_message: Any) -> None:
        with self._lock:
            self.feedback.append(feedback_message.feedback)

    def latest_status(self) -> Dict[str, Any]:
        with self._lock:
            return self.statuses[-1] if self.statuses else {}


def wait_result(goal_handle: Any, label: str) -> Any:
    future = goal_handle.get_result_async()
    wait_until(future.done, label)
    return future.result()


def main() -> None:
    if PToPMoveBase is None:
        print("DDDMR messages are not installed; field proxy smoke test skipped")
        return

    os.environ["ROS_LOCALHOST_ONLY"] = "1"
    os.environ["ROS_DOMAIN_ID"] = str(170 + os.getpid() % 20)
    prefix = "/field_proxy_smoke_%d" % os.getpid()
    command = [
        "ros2",
        "run",
        "m20pro_navigation",
        "dddmr_p2p_field_proxy",
        "--ros-args",
        "-p",
        "enabled:=true",
        "-p",
        "dddmr_action:=%s/p2p_move_base" % prefix,
        "-p",
        "cmd_vel_topic:=%s/dddmr_cmd_vel" % prefix,
        "-p",
        "status_topic:=%s/runtime/status" % prefix,
        "-p",
        "max_goal_distance_m:=3.0",
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
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()
    try:
        assert node.client.wait_for_server(timeout_sec=TIMEOUT_S)
        wait_until(
            lambda: bool(node.latest_status().get("action_server_ready"))
            and not bool(node.latest_status().get("ready"))
            and not bool(node.latest_status().get("tf_ready")),
            "field proxy runtime blocked by missing TF",
        )
        missing_tf = node.latest_status()
        assert missing_tf.get("code") == "field_proxy_tf_unavailable"
        assert missing_tf.get("tf_code") == "field_proxy_tf_unavailable"
        node.publish_tf = True
        wait_until(
            lambda: bool(node.latest_status().get("ready")),
            "field proxy runtime ready",
        )
        ready = node.latest_status()
        assert ready.get("backend") == "field_proxy"
        assert ready.get("action_server_ready") is True
        assert ready.get("tf_ready") is True

        goal = PToPMoveBase.Goal()
        goal.target_pose.header.frame_id = "map"
        goal.target_pose.pose.position.x = 1.0
        goal.target_pose.pose.position.y = 0.0
        goal.target_pose.pose.orientation.w = 1.0
        goal_future = node.client.send_goal_async(goal, feedback_callback=node._on_feedback)
        wait_until(goal_future.done, "field proxy goal response")
        goal_handle = goal_future.result()
        assert goal_handle.accepted is True

        wait_until(
            lambda: any(
                abs(command.linear.x) > 1e-3 or abs(command.angular.z) > 1e-3
                for command in node.commands
            ),
            "field proxy velocity command",
        )
        assert any(
            abs(command.linear.x) > 1e-3 or abs(command.angular.z) > 1e-3
            for command in node.commands
        )

        cancel_future = goal_handle.cancel_goal_async()
        wait_until(cancel_future.done, "field proxy cancel response")
        cancel_result = cancel_future.result()
        assert cancel_result.goals_canceling or cancel_result.goals_canceling == []
        result = wait_result(goal_handle, "field proxy result")
        assert result.status == GoalStatus.STATUS_CANCELED
        wait_until(
            lambda: str(node.latest_status().get("code") or "").startswith("field_proxy_goal_cancelled")
            or str(node.latest_status().get("state") or "") == "idle",
            "field proxy cancelled status",
        )

        too_far_goal = PToPMoveBase.Goal()
        too_far_goal.target_pose.header.frame_id = "map"
        too_far_goal.target_pose.pose.position.x = 5.0
        too_far_goal.target_pose.pose.orientation.w = 1.0
        too_far_future = node.client.send_goal_async(too_far_goal)
        wait_until(too_far_future.done, "field proxy reject response")
        assert too_far_future.result().accepted is False

        print("DDDMR field-proxy ROS smoke test passed")
    finally:
        node.destroy_node()
        executor.shutdown()
        rclpy.shutdown()
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    main()
