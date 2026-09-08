#!/usr/bin/env python3
"""Exercise the bridge against the real generated DDDMR action contract."""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import Twist
from nav2_msgs.action import NavigateToPose
from rclpy.action import (
    ActionClient,
    ActionServer,
    CancelResponse,
    GoalResponse,
)
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Header, String

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


class Harness(Node):
    def __init__(self, prefix: str) -> None:
        super().__init__("dddmr_bridge_action_smoke_%d" % os.getpid())
        self._callback_group = ReentrantCallbackGroup()
        self._lock = threading.RLock()
        self.statuses: List[Dict[str, Any]] = []
        self.commands: List[Twist] = []
        self.feedback: List[NavigateToPose.Feedback] = []
        self.started_modes: List[int] = []
        self.cancelled_modes: List[int] = []
        self.command_pub = self.create_publisher(
            Twist,
            "%s/dddmr_cmd_vel" % prefix,
            10,
        )
        map_qos = QoSProfile(depth=1)
        map_qos.reliability = ReliabilityPolicy.RELIABLE
        map_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.mapcloud_pub = self.create_publisher(
            PointCloud2,
            "%s/mapcloud" % prefix,
            map_qos,
        )
        self.mapground_pub = self.create_publisher(
            PointCloud2,
            "%s/mapground" % prefix,
            map_qos,
        )
        self.map_status_pub = self.create_publisher(
            String,
            "%s/map_status" % prefix,
            map_qos,
        )
        self.create_subscription(
            String,
            "%s/status" % prefix,
            self._on_status,
            10,
            callback_group=self._callback_group,
        )
        self.create_subscription(
            Twist,
            "%s/cmd_vel_nav" % prefix,
            self._on_command,
            10,
            callback_group=self._callback_group,
        )
        self.frontend = ActionClient(
            self,
            NavigateToPose,
            "%s/navigate_to_pose_3d" % prefix,
            callback_group=self._callback_group,
        )
        self.backend = ActionServer(
            self,
            PToPMoveBase,
            "%s/p2p_move_base" % prefix,
            execute_callback=self._execute_backend,
            goal_callback=self._on_backend_goal,
            cancel_callback=lambda _handle: CancelResponse.ACCEPT,
            callback_group=self._callback_group,
        )

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

    def send_goal(self, mode: int) -> Any:
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.pose.position.x = float(mode)
        goal.pose.pose.position.y = 6.0
        goal.pose.pose.position.z = 0.5
        goal.pose.pose.orientation.w = 1.0
        future = self.frontend.send_goal_async(
            goal,
            feedback_callback=self._on_feedback,
        )
        wait_until(future.done, "frontend goal response")
        return future.result()

    def _publish_backend_command(self, *, clamped: bool = False) -> None:
        command = Twist()
        command.linear.x = 0.9 if clamped else 0.05
        command.linear.y = -0.8 if clamped else 0.0
        command.angular.z = 1.2 if clamped else 0.05
        self.command_pub.publish(command)

    def publish_latched_map_assets(self) -> None:
        header = Header()
        header.stamp = self.get_clock().now().to_msg()
        header.frame_id = "map"
        cloud = point_cloud2.create_cloud_xyz32(
            header,
            [(0.0, 0.0, 0.0), (0.5, 0.0, 0.0), (0.0, 0.5, 0.0)],
        )
        self.mapcloud_pub.publish(cloud)
        self.mapground_pub.publish(cloud)
        status = String()
        status.data = json.dumps(
            {
                "ready": True,
                "provisional": True,
                "source": "field_test_flat_map",
                "code": "field_test_flat_map_ready",
            },
            separators=(",", ":"),
        )
        self.map_status_pub.publish(status)

    @staticmethod
    def _on_backend_goal(request: PToPMoveBase.Goal) -> GoalResponse:
        mode = int(round(request.target_pose.pose.position.x))
        if mode == 8:
            time.sleep(0.6)
        return GoalResponse.ACCEPT

    def _publish_backend_feedback(self, goal_handle: Any) -> None:
        feedback = PToPMoveBase.Feedback()
        feedback.base_position.header.frame_id = "map"
        feedback.base_position.transform.translation.x = 1.0
        feedback.base_position.transform.translation.y = 2.0
        feedback.base_position.transform.translation.z = 0.5
        feedback.base_position.transform.rotation.w = 1.0
        feedback.last_decision = "d_planning"
        feedback.current_decision = "d_recovery_rotate"
        goal_handle.publish_feedback(feedback)

    def _wait_for_cancel(self, goal_handle: Any, mode: int, *, publish: bool) -> Any:
        deadline = time.monotonic() + TIMEOUT_S
        while not goal_handle.is_cancel_requested and time.monotonic() < deadline:
            if publish:
                self._publish_backend_command()
            time.sleep(0.04)
        if not goal_handle.is_cancel_requested:
            raise AssertionError("backend mode %d was not cancelled" % mode)
        with self._lock:
            self.cancelled_modes.append(mode)
        result = PToPMoveBase.Result()
        goal_handle.canceled()
        return result

    def _execute_backend(self, goal_handle: Any) -> PToPMoveBase.Result:
        mode = int(round(goal_handle.request.target_pose.pose.position.x))
        with self._lock:
            self.started_modes.append(mode)

        if mode == 4:
            return self._wait_for_cancel(goal_handle, mode, publish=True)
        if mode == 5:
            return self._wait_for_cancel(goal_handle, mode, publish=False)
        if mode == 6:
            time.sleep(0.12)
            self._publish_backend_command()
            time.sleep(0.05)
            return self._wait_for_cancel(goal_handle, mode, publish=False)
        if mode == 7:
            return self._wait_for_cancel(goal_handle, mode, publish=True)
        if mode == 8:
            return self._wait_for_cancel(goal_handle, mode, publish=True)

        time.sleep(0.12)
        self._publish_backend_feedback(goal_handle)
        for index in range(4):
            self._publish_backend_command(clamped=index == 0)
            time.sleep(0.04)
        result = PToPMoveBase.Result()
        if mode == 1:
            goal_handle.succeed()
        elif mode == 2:
            result.status = 1
            goal_handle.succeed()
        elif mode == 3:
            result.status = 2
            result.result = "synthetic failure"
            goal_handle.abort()
        else:
            raise AssertionError("unknown backend test mode %d" % mode)
        return result

    def latest_status_code(self) -> str:
        with self._lock:
            if not self.statuses:
                return ""
            return str(self.statuses[-1].get("last_result_code") or "")

    def has_started(self, mode: int) -> bool:
        with self._lock:
            return mode in self.started_modes

    def was_cancelled(self, mode: int) -> bool:
        with self._lock:
            return mode in self.cancelled_modes

    def destroy_node(self) -> bool:
        self.backend.destroy()
        self.frontend.destroy()
        return super().destroy_node()


def wait_result(goal_handle: Any, label: str) -> Any:
    future = goal_handle.get_result_async()
    wait_until(future.done, label)
    return future.result()


def assert_status_code(node: Harness, code: str) -> None:
    wait_until(lambda: node.latest_status_code() == code, "status code %s" % code)


def main() -> None:
    if PToPMoveBase is None:
        print("DDDMR messages are not installed; real action smoke test skipped")
        return

    os.environ["ROS_LOCALHOST_ONLY"] = "1"
    os.environ["ROS_DOMAIN_ID"] = str(160 + os.getpid() % 20)
    prefix = "/dddmr_bridge_action_smoke_%d" % os.getpid()
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
        "status_period_s:=0.05",
        "-p",
        "watchdog_period_s:=0.05",
        "-p",
        "cmd_vel_startup_grace_s:=0.3",
        "-p",
        "cmd_vel_timeout_s:=0.25",
        "-p",
        "backend_cancel_timeout_s:=1.0",
        "-p",
        "max_forward_speed_mps:=0.18",
        "-p",
        "max_reverse_speed_mps:=0.12",
        "-p",
        "max_lateral_speed_mps:=0.30",
        "-p",
        "max_angular_speed_radps:=0.45",
        "-p",
        "navigate_to_pose_action:=%s/navigate_to_pose_3d" % prefix,
        "-p",
        "dddmr_action:=%s/p2p_move_base" % prefix,
        "-p",
        "dddmr_cmd_vel_topic:=%s/dddmr_cmd_vel" % prefix,
        "-p",
        "navigation_cmd_vel_topic:=%s/cmd_vel_nav" % prefix,
        "-p",
        "require_edge_cloud:=false",
        "-p",
        "require_dddmr_map:=true",
        "-p",
        "require_map_status:=true",
        "-p",
        "map_cloud_topic:=%s/mapcloud" % prefix,
        "-p",
        "map_ground_topic:=%s/mapground" % prefix,
        "-p",
        "map_status_topic:=%s/map_status" % prefix,
        "-p",
        "status_topic:=%s/status" % prefix,
    ]
    rclpy.init()
    node = Harness(prefix)
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()
    for _ in range(5):
        node.publish_latched_map_assets()
        time.sleep(0.05)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        env=dict(os.environ),
    )
    try:
        assert node.frontend.wait_for_server(timeout_sec=TIMEOUT_S)
        wait_until(
            lambda: any(status.get("ready") is True for status in node.statuses),
            "ready bridge status",
        )

        default_success = node.send_goal(1)
        assert default_success.accepted is True
        default_result = wait_result(default_success, "default-result success")
        assert default_result.status == GoalStatus.STATUS_SUCCEEDED
        assert_status_code(node, "dddmr_goal_succeeded_default_result")
        wait_until(lambda: bool(node.feedback), "translated feedback")
        feedback = node.feedback[-1]
        assert math.isclose(feedback.current_pose.pose.position.x, 1.0)
        assert math.isclose(feedback.current_pose.pose.position.z, 0.5)
        assert math.isclose(feedback.distance_remaining, 4.0)
        assert feedback.number_of_recoveries == 1
        wait_until(
            lambda: any(
                math.isclose(item.linear.x, 0.18)
                and math.isclose(item.linear.y, -0.30)
                and math.isclose(item.angular.z, 0.45)
                for item in node.commands
            ),
            "clamped navigation command",
        )

        explicit_success = node.send_goal(2)
        assert explicit_success.accepted is True
        explicit_result = wait_result(explicit_success, "explicit success")
        assert explicit_result.status == GoalStatus.STATUS_SUCCEEDED
        assert_status_code(node, "dddmr_goal_succeeded")

        failure = node.send_goal(3)
        assert failure.accepted is True
        assert wait_result(failure, "backend failure").status == GoalStatus.STATUS_ABORTED
        assert_status_code(node, "dddmr_goal_failed")

        cancel_goal = node.send_goal(4)
        assert cancel_goal.accepted is True
        wait_until(lambda: node.has_started(4), "cancel backend goal start")
        cancel_future = cancel_goal.cancel_goal_async()
        wait_until(cancel_future.done, "frontend cancel response")
        assert len(cancel_future.result().goals_canceling) == 1
        cancel_result = wait_result(cancel_goal, "frontend cancellation")
        assert cancel_result.status == GoalStatus.STATUS_CANCELED
        wait_until(lambda: node.was_cancelled(4), "backend cancellation propagation")
        assert_status_code(node, "dddmr_goal_cancelled")

        first_timeout = node.send_goal(5)
        assert first_timeout.accepted is True
        first_timeout_result = wait_result(first_timeout, "first command timeout")
        assert first_timeout_result.status == GoalStatus.STATUS_ABORTED
        wait_until(lambda: node.was_cancelled(5), "first-timeout backend cancellation")
        assert_status_code(node, "dddmr_cmd_vel_start_timeout")

        stale_timeout = node.send_goal(6)
        assert stale_timeout.accepted is True
        stale_timeout_result = wait_result(stale_timeout, "stale command timeout")
        assert stale_timeout_result.status == GoalStatus.STATUS_ABORTED
        wait_until(lambda: node.was_cancelled(6), "stale-timeout backend cancellation")
        assert_status_code(node, "dddmr_cmd_vel_timeout")

        active_goal = node.send_goal(7)
        assert active_goal.accepted is True
        wait_until(lambda: node.has_started(7), "concurrent backend goal start")
        second_goal = node.send_goal(2)
        assert second_goal.accepted is False
        cancel_future = active_goal.cancel_goal_async()
        wait_until(cancel_future.done, "active goal cleanup cancel response")
        assert wait_result(active_goal, "active goal cleanup").status == GoalStatus.STATUS_CANCELED
        wait_until(lambda: node.was_cancelled(7), "active backend cleanup cancellation")

        early_cancel = node.send_goal(8)
        assert early_cancel.accepted is True
        time.sleep(0.1)
        cancel_future = early_cancel.cancel_goal_async()
        wait_until(cancel_future.done, "early cancel response")
        assert len(cancel_future.result().goals_canceling) == 1
        early_cancel_result = wait_result(early_cancel, "early cancellation")
        assert early_cancel_result.status == GoalStatus.STATUS_CANCELED
        wait_until(lambda: node.has_started(8), "late backend goal start")
        wait_until(lambda: node.was_cancelled(8), "late backend goal cancellation")
        assert_status_code(node, "dddmr_goal_cancelled")

        wait_until(lambda: bool(node.commands), "navigation commands")
        assert command_is_zero(node.commands[-1])
        assert process.poll() is None
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
        deadline = time.monotonic() + TIMEOUT_S
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        executor.shutdown(timeout_sec=2.0)
        spin_thread.join(timeout=2.0)
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

    print("DDDMR bridge real-action ROS smoke test passed")


if __name__ == "__main__":
    main()
