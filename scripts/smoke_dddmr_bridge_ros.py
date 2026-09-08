#!/usr/bin/env python3
"""Verify that the installed bridge fails closed without DDDMR messages."""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import time
from typing import Any, Callable, Dict, List

import rclpy
from geometry_msgs.msg import Twist
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String


TIMEOUT_S = 8.0


class Harness(Node):
    def __init__(self, prefix: str) -> None:
        super().__init__(f"dddmr_bridge_smoke_{os.getpid()}")
        self.statuses: List[Dict[str, Any]] = []
        self.commands: List[Twist] = []
        self.command_pub = self.create_publisher(Twist, f"{prefix}/dddmr_cmd_vel", 10)
        self.create_subscription(String, f"{prefix}/status", self._on_status, 10)
        self.create_subscription(Twist, f"{prefix}/cmd_vel_nav", self.commands.append, 10)
        self.action_client = ActionClient(
            self,
            NavigateToPose,
            f"{prefix}/navigate_to_pose_3d",
        )

    def _on_status(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            self.statuses.append(payload)


def spin_until(node: Node, condition: Callable[[], bool], label: str) -> None:
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
        if condition():
            return
    raise AssertionError("timed out waiting for %s" % label)


def command_is_zero(command: Twist) -> bool:
    return all(
        abs(value) <= 1e-9
        for value in (
            command.linear.x,
            command.linear.y,
            command.linear.z,
            command.angular.x,
            command.angular.y,
            command.angular.z,
        )
    )


def main() -> None:
    if importlib.util.find_spec("dddmr_sys_core") is not None:
        print("DDDMR messages are installed; missing-type smoke test skipped")
        return

    os.environ["ROS_LOCALHOST_ONLY"] = "1"
    os.environ["ROS_DOMAIN_ID"] = str(180 + os.getpid() % 20)
    prefix = "/dddmr_bridge_smoke_%d" % os.getpid()
    command = [
        "ros2",
        "run",
        "m20pro_navigation",
        "dddmr_action_bridge",
        "--ros-args",
        "-p",
        "enabled:=true",
        "-p",
        "motion_enabled:=true",
        "-p",
        "status_period_s:=0.1",
        "-p",
        "navigate_to_pose_action:=%s/navigate_to_pose_3d" % prefix,
        "-p",
        "dddmr_action:=%s/p2p_move_base" % prefix,
        "-p",
        "dddmr_cmd_vel_topic:=%s/dddmr_cmd_vel" % prefix,
        "-p",
        "navigation_cmd_vel_topic:=%s/cmd_vel_nav" % prefix,
        "-p",
        "status_topic:=%s/status" % prefix,
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
        spin_until(node, lambda: bool(node.statuses), "bridge status")
        status = node.statuses[-1]
        assert status["enabled"] is True
        assert status["motion_enabled"] is True
        assert status["action_type_available"] is False
        assert status["action_server_ready"] is False
        assert status["ready"] is False

        assert node.action_client.wait_for_server(timeout_sec=TIMEOUT_S)
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.pose.orientation.w = 1.0
        goal_future = node.action_client.send_goal_async(goal)
        spin_until(node, goal_future.done, "rejected NavigateToPose goal")
        assert goal_future.result().accepted is False

        command_message = Twist()
        command_message.linear.x = 0.5
        command_message.angular.z = 0.5
        for _ in range(5):
            node.command_pub.publish(command_message)
            rclpy.spin_once(node, timeout_sec=0.1)
        assert all(command_is_zero(command) for command in node.commands)

        os.killpg(process.pid, signal.SIGINT)
        deadline = time.monotonic() + TIMEOUT_S
        while process.poll() is None and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
        assert process.poll() == 0
        assert all(command_is_zero(command) for command in node.commands)
    finally:
        node.destroy_node()
        rclpy.shutdown()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3.0)
        output = process.stdout.read() if process.stdout is not None else ""
        if process.returncode not in (0, -signal.SIGINT):
            raise AssertionError("bridge process failed:\n%s" % output)

    print("DDDMR bridge missing-type ROS smoke test passed")


if __name__ == "__main__":
    main()
