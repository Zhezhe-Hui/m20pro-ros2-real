"""Bridge dashboard floor goals to the standard Nav2 NavigateToPose action."""

import json
from typing import Optional

import rclpy
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String
from action_msgs.msg import GoalStatus


class Nav2GoalBridge(Node):
    def __init__(self) -> None:
        super().__init__("m20pro_2d_nav2_goal_bridge")
        self.declare_parameter("goal_topic", "/m20pro/floor_goal")
        self.declare_parameter("stop_topic", "/m20pro/stop_task")
        self.declare_parameter("action_name", "/navigate_to_pose")
        self.declare_parameter(
            "status_topic", "/m20pro_tcp_bridge/navigation_status"
        )
        self.declare_parameter(
            "backend_status_topic", "/m20pro/navigation_backend/status"
        )
        self.declare_parameter("motion_enabled", True)
        self.client = ActionClient(
            self, NavigateToPose, str(self.get_parameter("action_name").value)
        )
        self.status_pub = self.create_publisher(
            String, str(self.get_parameter("status_topic").value), 10
        )
        self.backend_pub = self.create_publisher(
            String, str(self.get_parameter("backend_status_topic").value), 10
        )
        self.create_subscription(
            PoseStamped,
            str(self.get_parameter("goal_topic").value),
            self._on_goal,
            10,
        )
        self.create_subscription(
            String,
            str(self.get_parameter("stop_topic").value),
            self._on_stop,
            10,
        )
        self.goal_handle = None
        self.goal_sequence = 0
        self.create_timer(0.5, self._publish_backend_status)
        self._publish_status("nav_idle")

    def _publish_status(self, text: str) -> None:
        msg = String()
        msg.data = str(text)
        self.status_pub.publish(msg)

    def _publish_backend_status(self) -> None:
        payload = {
            "backend": "nav2_2d",
            "configured": "nav2_2d",
            "active": True,
            "ready": bool(self.client.server_is_ready()),
            "motion_enabled": bool(self.get_parameter("motion_enabled").value),
            "state": "goal_active" if self.goal_handle is not None else "idle",
            "action_server_ready": bool(self.client.server_is_ready()),
            "action_type_available": True,
            "goal_active": self.goal_handle is not None,
            "reason": "nav2_2d_ready" if self.client.server_is_ready() else "nav2_action_unavailable",
        }
        msg = String()
        msg.data = json.dumps(payload, separators=(",", ":"))
        self.backend_pub.publish(msg)

    def _on_stop(self, _msg: String) -> None:
        if self.goal_handle is not None:
            future = self.goal_handle.cancel_goal_async()
            future.add_done_callback(lambda _future: self._finish_goal("nav_goal_cancelled"))
        else:
            self._publish_status("nav_goal_cancelled")

    def _on_goal(self, msg: PoseStamped) -> None:
        if self.goal_handle is not None:
            self.goal_handle.cancel_goal_async()
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header = msg.header
        goal.pose.header.frame_id = "map"
        goal.pose.pose = msg.pose
        self.goal_sequence += 1
        sequence = self.goal_sequence
        self._publish_status("nav_goal_accepted")
        if not self.client.wait_for_server(timeout_sec=2.0):
            self._publish_status("nav_goal_failed action_server_unavailable")
            return
        future = self.client.send_goal_async(goal)
        future.add_done_callback(lambda result: self._goal_response(result, sequence))

    def _goal_response(self, future, sequence: int) -> None:
        if sequence != self.goal_sequence:
            return
        handle = future.result()
        if handle is None or not handle.accepted:
            self._publish_status("nav_goal_failed goal_rejected")
            return
        self.goal_handle = handle
        self._publish_status("nav_goal_active")
        result_future = handle.get_result_async()
        result_future.add_done_callback(lambda result: self._goal_result(result, sequence))

    def _goal_result(self, future, sequence: int) -> None:
        if sequence != self.goal_sequence:
            return
        result = future.result()
        status = int(getattr(result, "status", GoalStatus.STATUS_UNKNOWN))
        if status == GoalStatus.STATUS_SUCCEEDED:
            self._finish_goal("nav_goal_succeeded")
        elif status == GoalStatus.STATUS_CANCELED:
            self._finish_goal("nav_goal_cancelled")
        else:
            self._finish_goal("nav_goal_failed status=%d" % status)

    def _finish_goal(self, status: str) -> None:
        self.goal_handle = None
        self._publish_status(status)


def main(args: Optional[list] = None) -> None:
    rclpy.init(args=args)
    node = Nav2GoalBridge()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
