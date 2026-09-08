"""Expose DDDMR's 3D action through the standard Nav2 NavigateToPose API."""

from __future__ import annotations

import json
import math
import signal
import threading
import time
from typing import Any, Dict, Optional

import rclpy
from geometry_msgs.msg import PoseStamped, Twist
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2

from .dddmr_navigation_contract import (
    bounded_dddmr_velocity,
    dddmr_goal_admission,
    dddmr_result_decision,
    dddmr_velocity_watchdog,
)

try:
    from dddmr_sys_core.action import PToPMoveBase
except ImportError:  # The bridge remains observable and rejects goals on non-DDDMR hosts.
    PToPMoveBase = None  # type: ignore[assignment,misc]


def _json_message(payload: Dict[str, Any]) -> String:
    message = String()
    message.data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return message


class DddmrNav2Bridge(Node):
    def __init__(self) -> None:
        super().__init__("m20pro_dddmr_action_bridge")
        self.declare_parameter("enabled", False)
        self.declare_parameter("motion_enabled", False)
        self.declare_parameter("navigate_to_pose_action", "/navigate_to_pose_3d")
        self.declare_parameter("dddmr_action", "/p2p_move_base")
        self.declare_parameter("dddmr_cmd_vel_topic", "/dddmr/cmd_vel")
        self.declare_parameter("navigation_cmd_vel_topic", "/cmd_vel_nav")
        self.declare_parameter("status_topic", "/m20pro/navigation_backend/status")
        self.declare_parameter(
            "edge_cloud_status_topic", "/m20pro/dddmr/edge_cloud/status"
        )
        self.declare_parameter("require_edge_cloud", True)
        self.declare_parameter("edge_cloud_timeout_s", 0.75)
        self.declare_parameter("map_cloud_topic", "/mapcloud")
        self.declare_parameter("map_ground_topic", "/mapground")
        self.declare_parameter("require_dddmr_map", False)
        self.declare_parameter("map_status_topic", "/m20pro/dddmr/map/status")
        self.declare_parameter("require_map_status", False)
        self.declare_parameter("expected_map_frame", "map")
        self.declare_parameter("target_value", 0.0)
        self.declare_parameter("cmd_vel_startup_grace_s", 3.0)
        self.declare_parameter("cmd_vel_timeout_s", 0.75)
        self.declare_parameter("backend_response_timeout_s", 5.0)
        self.declare_parameter("backend_goal_timeout_s", 1800.0)
        self.declare_parameter("backend_cancel_timeout_s", 2.0)
        self.declare_parameter("watchdog_period_s", 0.1)
        self.declare_parameter("status_period_s", 1.0)
        self.declare_parameter("max_forward_speed_mps", 0.45)
        self.declare_parameter("max_reverse_speed_mps", 0.30)
        self.declare_parameter("max_lateral_speed_mps", 0.30)
        self.declare_parameter("max_angular_speed_radps", 0.75)

        self._enabled = bool(self.get_parameter("enabled").value)
        self._motion_enabled = bool(self.get_parameter("motion_enabled").value)
        self._callback_group = ReentrantCallbackGroup()
        self._lock = threading.RLock()
        self._goal_reserved = False
        self._goal_active = False
        self._active_since: Optional[float] = None
        self._last_cmd_at: Optional[float] = None
        self._fault_code = ""
        self._state = "starting"
        self._last_result_code = ""
        self._goal_target: Optional[PoseStamped] = None
        self._recovery_count = 0
        self._last_recovery_decision = ""
        self._edge_cloud_ready = False
        self._edge_cloud_last_at: Optional[float] = None
        self._edge_cloud_code = "waiting_edge_cloud"
        self._map_cloud_ready = False
        self._map_ground_ready = False
        self._map_status_ready = False
        self._map_status_code = "waiting_map_status"

        self._status_pub = self.create_publisher(
            String, str(self.get_parameter("status_topic").value), 10
        )
        self._cmd_vel_pub = self.create_publisher(
            Twist, str(self.get_parameter("navigation_cmd_vel_topic").value), 10
        )
        self.create_subscription(
            Twist,
            str(self.get_parameter("dddmr_cmd_vel_topic").value),
            self._on_dddmr_cmd_vel,
            10,
            callback_group=self._callback_group,
        )
        self.create_subscription(
            String,
            str(self.get_parameter("edge_cloud_status_topic").value),
            self._on_edge_cloud_status,
            10,
            callback_group=self._callback_group,
        )
        map_qos = QoSProfile(depth=1)
        map_qos.reliability = ReliabilityPolicy.RELIABLE
        map_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.create_subscription(
            PointCloud2,
            str(self.get_parameter("map_cloud_topic").value),
            self._on_map_cloud,
            map_qos,
            callback_group=self._callback_group,
        )
        self.create_subscription(
            PointCloud2,
            str(self.get_parameter("map_ground_topic").value),
            self._on_map_ground,
            map_qos,
            callback_group=self._callback_group,
        )
        self.create_subscription(
            String,
            str(self.get_parameter("map_status_topic").value),
            self._on_map_status,
            map_qos,
            callback_group=self._callback_group,
        )

        self._dddmr_client: Optional[Any] = None
        if PToPMoveBase is not None:
            self._dddmr_client = ActionClient(
                self,
                PToPMoveBase,
                str(self.get_parameter("dddmr_action").value),
                callback_group=self._callback_group,
            )
        self._action_server = ActionServer(
            self,
            NavigateToPose,
            str(self.get_parameter("navigate_to_pose_action").value),
            execute_callback=self._execute,
            goal_callback=self._on_goal_request,
            cancel_callback=self._on_cancel_request,
            callback_group=self._callback_group,
        )
        self.create_timer(
            max(0.05, float(self.get_parameter("watchdog_period_s").value)),
            self._on_watchdog_timer,
            callback_group=self._callback_group,
        )
        self.create_timer(
            max(0.1, float(self.get_parameter("status_period_s").value)),
            self._publish_status,
            callback_group=self._callback_group,
        )
        self._state = "idle" if self._enabled else "disabled"
        self._publish_zero()
        self._publish_status()

    def _backend_server_ready(self) -> bool:
        return bool(self._dddmr_client is not None and self._dddmr_client.server_is_ready())

    def _admission(self) -> Dict[str, Any]:
        with self._lock:
            goal_active = bool(self._goal_reserved or self._goal_active)
        return dddmr_goal_admission(
            enabled=self._enabled,
            motion_enabled=self._motion_enabled,
            action_type_available=PToPMoveBase is not None,
            action_server_ready=self._backend_server_ready(),
            goal_active=goal_active,
            perception_ready=self._perception_ready(),
            map_ready=self._map_ready(),
        )

    def _perception_ready(self) -> bool:
        if not bool(self.get_parameter("require_edge_cloud").value):
            return True
        with self._lock:
            if not self._edge_cloud_ready or self._edge_cloud_last_at is None:
                return False
            age_s = time.monotonic() - self._edge_cloud_last_at
        return age_s <= max(
            0.05, float(self.get_parameter("edge_cloud_timeout_s").value)
        )

    def _on_edge_cloud_status(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
            ready = bool(payload.get("ready"))
            code = str(payload.get("code") or "edge_cloud_unknown")
        except (TypeError, ValueError, json.JSONDecodeError):
            ready = False
            code = "edge_cloud_status_invalid"
        with self._lock:
            self._edge_cloud_ready = ready
            self._edge_cloud_code = code
            self._edge_cloud_last_at = time.monotonic()

    def _cloud_has_points(self, message: PointCloud2) -> bool:
        try:
            expected_frame = str(self.get_parameter("expected_map_frame").value or "")
            if expected_frame and str(message.header.frame_id or "") != expected_frame:
                return False
            count = int(message.width) * max(1, int(message.height))
            point_step = int(message.point_step)
            fields = {str(field.name) for field in message.fields}
            if count <= 0 or point_step <= 0 or len(message.data) < point_step:
                return False
            if not {"x", "y", "z"}.issubset(fields):
                return False
            for point in point_cloud2.read_points(
                message, field_names=("x", "y", "z"), skip_nans=False
            ):
                try:
                    if all(math.isfinite(float(value)) for value in point):
                        return True
                except (TypeError, ValueError, OverflowError):
                    continue
            return False
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return False

    def _on_map_cloud(self, message: PointCloud2) -> None:
        with self._lock:
            self._map_cloud_ready = self._cloud_has_points(message)

    def _on_map_ground(self, message: PointCloud2) -> None:
        with self._lock:
            self._map_ground_ready = self._cloud_has_points(message)

    def _on_map_status(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
            ready = bool(payload.get("ready"))
            code = str(payload.get("code") or "dddmr_map_status_unknown")
        except (TypeError, ValueError, json.JSONDecodeError):
            ready = False
            code = "dddmr_map_status_invalid"
        with self._lock:
            self._map_status_ready = ready
            self._map_status_code = code

    def _map_ready(self) -> bool:
        if not bool(self.get_parameter("require_dddmr_map").value):
            return True
        with self._lock:
            # mapcloud/mapground are transient-local static assets, so a map
            # remains valid after the one-time latched sample is received.
            status_ok = (
                not bool(self.get_parameter("require_map_status").value)
                or self._map_status_ready
            )
            return bool(self._map_cloud_ready and self._map_ground_ready and status_ok)

    def _on_goal_request(self, _request: NavigateToPose.Goal) -> GoalResponse:
        with self._lock:
            admission = self._admission()
            if not admission.get("ok"):
                self._last_result_code = str(
                    admission.get("code") or "dddmr_goal_rejected"
                )
                self._state = "unavailable"
                accepted = False
            else:
                accepted = True
                self._state = "goal_reserved"
            if not accepted:
                self._publish_status()
                return GoalResponse.REJECT
            self._goal_reserved = True
        return GoalResponse.ACCEPT

    @staticmethod
    def _on_cancel_request(_goal_handle: Any) -> CancelResponse:
        return CancelResponse.ACCEPT

    def _execute(self, goal_handle: Any) -> NavigateToPose.Result:
        with self._lock:
            self._goal_reserved = True
            self._goal_active = False
            self._active_since = None
            self._last_cmd_at = None
            self._fault_code = ""
            self._state = "sending_goal"
            self._goal_target = goal_handle.request.pose
            self._recovery_count = 0
            self._last_recovery_decision = ""
        self._publish_status()

        result = NavigateToPose.Result()
        backend_handle: Optional[Any] = None
        try:
            if self._dddmr_client is None or PToPMoveBase is None:
                self._last_result_code = "dddmr_action_type_missing"
                goal_handle.abort()
                return result
            backend_goal = PToPMoveBase.Goal()
            backend_goal.target_pose = goal_handle.request.pose
            backend_goal.target_value = float(self.get_parameter("target_value").value)
            backend_goal_future = self._dddmr_client.send_goal_async(
                backend_goal,
                feedback_callback=lambda feedback: self._on_backend_feedback(
                    goal_handle,
                    feedback,
                ),
            )
            if not self._wait_for_future(
                backend_goal_future,
                goal_handle,
                timeout_s=float(self.get_parameter("backend_response_timeout_s").value),
            ):
                backend_goal_future.add_done_callback(
                    self._cancel_late_backend_goal
                )
                if goal_handle.is_cancel_requested:
                    self._last_result_code = "dddmr_goal_cancelled"
                else:
                    self._last_result_code = self._wait_failure_code(
                        "dddmr_goal_response_timeout"
                    )
                self._finish_goal(goal_handle, canceled=goal_handle.is_cancel_requested)
                return result
            backend_handle = backend_goal_future.result()
            if not backend_handle.accepted:
                self._last_result_code = "dddmr_goal_rejected"
                goal_handle.abort()
                return result
            with self._lock:
                self._goal_reserved = False
                self._goal_active = True
                self._active_since = time.monotonic()
                self._state = "navigating"
                self._last_result_code = "dddmr_goal_accepted"
            self._publish_status()
            backend_result_future = backend_handle.get_result_async()
            result_started = time.monotonic()
            while not backend_result_future.done():
                if goal_handle.is_cancel_requested:
                    self._cancel_backend_goal(backend_handle)
                    goal_handle.canceled()
                    self._last_result_code = "dddmr_goal_cancelled"
                    return result
                with self._lock:
                    fault_code = self._fault_code
                if fault_code:
                    self._cancel_backend_goal(backend_handle)
                    goal_handle.abort()
                    self._last_result_code = fault_code
                    return result
                goal_timeout_s = max(
                    1.0,
                    float(self.get_parameter("backend_goal_timeout_s").value),
                )
                if time.monotonic() - result_started > goal_timeout_s:
                    self._cancel_backend_goal(backend_handle)
                    goal_handle.abort()
                    self._last_result_code = "dddmr_goal_timeout"
                    return result
                time.sleep(0.05)
            with self._lock:
                fault_code = self._fault_code
            if fault_code:
                self._cancel_backend_goal(backend_handle)
                goal_handle.abort()
                self._last_result_code = fault_code
                return result
            wrapped = backend_result_future.result()
            backend_status = int(getattr(getattr(wrapped, "result", None), "status", -1))
            decision = dddmr_result_decision(
                transport_status=int(getattr(wrapped, "status", -1)),
                result_status=backend_status,
            )
            self._last_result_code = str(decision["code"])
            if decision.get("succeeded"):
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result
        except Exception as exc:
            self.get_logger().exception("DDDMR bridge execution failed")
            self._last_result_code = "dddmr_bridge_exception:%s" % type(exc).__name__
            if backend_handle is not None:
                self._cancel_backend_goal(backend_handle)
            if bool(goal_handle.is_active):
                goal_handle.abort()
            return result
        finally:
            self._publish_zero()
            with self._lock:
                self._goal_reserved = False
                self._goal_active = False
                self._active_since = None
                self._last_cmd_at = None
                self._goal_target = None
                self._state = "idle"
            self._publish_status()

    def _wait_for_future(
        self,
        future: Any,
        goal_handle: Any,
        *,
        timeout_s: float,
    ) -> bool:
        deadline = time.monotonic() + max(0.1, float(timeout_s))
        while not future.done() and time.monotonic() < deadline:
            if goal_handle.is_cancel_requested:
                return False
            with self._lock:
                if self._fault_code:
                    return False
            time.sleep(0.02)
        return bool(future.done())

    def _wait_failure_code(self, timeout_code: str) -> str:
        with self._lock:
            return self._fault_code or timeout_code

    @staticmethod
    def _finish_goal(goal_handle: Any, *, canceled: bool) -> None:
        if not bool(goal_handle.is_active):
            return
        if canceled:
            goal_handle.canceled()
        else:
            goal_handle.abort()

    def _cancel_backend_goal(self, backend_handle: Any) -> None:
        try:
            cancel_future = backend_handle.cancel_goal_async()
            deadline = time.monotonic() + max(
                0.1,
                float(self.get_parameter("backend_cancel_timeout_s").value),
            )
            while not cancel_future.done() and time.monotonic() < deadline:
                time.sleep(0.02)
        except Exception as exc:
            self.get_logger().warning(
                "failed to cancel DDDMR goal: %s" % type(exc).__name__
            )

    def _cancel_late_backend_goal(self, future: Any) -> None:
        try:
            backend_handle = future.result()
            if backend_handle is not None and backend_handle.accepted:
                self._cancel_backend_goal(backend_handle)
        except Exception as exc:
            self.get_logger().warning(
                "failed to cancel late DDDMR goal: %s" % type(exc).__name__
            )

    def _on_backend_feedback(self, goal_handle: Any, feedback_message: Any) -> None:
        if not bool(goal_handle.is_active):
            return
        backend_feedback = feedback_message.feedback
        transform = backend_feedback.base_position
        feedback = NavigateToPose.Feedback()
        feedback.current_pose.header = transform.header
        feedback.current_pose.pose.position.x = float(transform.transform.translation.x)
        feedback.current_pose.pose.position.y = float(transform.transform.translation.y)
        feedback.current_pose.pose.position.z = float(transform.transform.translation.z)
        feedback.current_pose.pose.orientation = transform.transform.rotation
        with self._lock:
            target = self._goal_target
            active_since = self._active_since
            decision = str(getattr(backend_feedback, "current_decision", "") or "")
            if "recovery" in decision and decision != self._last_recovery_decision:
                self._recovery_count += 1
                self._last_recovery_decision = decision
            feedback.number_of_recoveries = int(self._recovery_count)
        if target is not None:
            dx = float(target.pose.position.x) - feedback.current_pose.pose.position.x
            dy = float(target.pose.position.y) - feedback.current_pose.pose.position.y
            dz = float(target.pose.position.z) - feedback.current_pose.pose.position.z
            feedback.distance_remaining = float(math.sqrt(dx * dx + dy * dy + dz * dz))
        if active_since is not None:
            feedback.navigation_time = Duration(
                seconds=max(0.0, time.monotonic() - active_since)
            ).to_msg()
        goal_handle.publish_feedback(feedback)

    def _on_dddmr_cmd_vel(self, command: Twist) -> None:
        with self._lock:
            if not self._goal_active or not self._motion_enabled or self._fault_code:
                return
            try:
                bounded = bounded_dddmr_velocity(
                    {
                        "linear_x": command.linear.x,
                        "linear_y": command.linear.y,
                        "angular_z": command.angular.z,
                    },
                    max_forward_speed_mps=float(
                        self.get_parameter("max_forward_speed_mps").value
                    ),
                    max_reverse_speed_mps=float(
                        self.get_parameter("max_reverse_speed_mps").value
                    ),
                    max_lateral_speed_mps=float(
                        self.get_parameter("max_lateral_speed_mps").value
                    ),
                    max_angular_speed_radps=float(
                        self.get_parameter("max_angular_speed_radps").value
                    ),
                )
            except (TypeError, ValueError, OverflowError):
                self._fault_code = "dddmr_cmd_vel_invalid"
                self._state = "fault"
                self._publish_zero()
                return
            output = Twist()
            output.linear.x = float(bounded["linear_x"])
            output.linear.y = float(bounded["linear_y"])
            output.angular.z = float(bounded["angular_z"])
            self._cmd_vel_pub.publish(output)
            self._last_cmd_at = time.monotonic()

    def _on_watchdog_timer(self) -> None:
        now = time.monotonic()
        with self._lock:
            active = self._goal_active
            active_age = now - self._active_since if self._active_since is not None else None
            command_age = now - self._last_cmd_at if self._last_cmd_at is not None else None
            fault_code = self._fault_code
        watchdog = dddmr_velocity_watchdog(
            goal_active=active,
            active_age_s=active_age,
            command_age_s=command_age,
            startup_grace_s=float(self.get_parameter("cmd_vel_startup_grace_s").value),
            command_timeout_s=float(self.get_parameter("cmd_vel_timeout_s").value),
        )
        if watchdog.get("stop") and not fault_code:
            with self._lock:
                self._fault_code = str(watchdog["code"])
                self._state = "fault"
            self._publish_zero()
            self._publish_status()

    def _publish_zero(self) -> None:
        if not rclpy.ok():
            return
        self._cmd_vel_pub.publish(Twist())

    def _publish_status(self) -> None:
        with self._lock:
            payload = {
                "component": "dddmr_action_bridge",
                "backend": "dddmr_3d",
                "enabled": self._enabled,
                "motion_enabled": self._motion_enabled,
                "action_type_available": PToPMoveBase is not None,
                "action_server_ready": self._backend_server_ready(),
                "edge_cloud_required": bool(
                    self.get_parameter("require_edge_cloud").value
                ),
                "edge_cloud_ready": self._perception_ready(),
                "edge_cloud_code": self._edge_cloud_code,
                "map_required": bool(
                    self.get_parameter("require_dddmr_map").value
                ),
                "map_ready": self._map_ready(),
                "mapcloud_ready": self._map_cloud_ready,
                "mapground_ready": self._map_ground_ready,
                "map_status_ready": self._map_status_ready,
                "map_status_code": self._map_status_code,
                "ready": bool(
                    self._enabled
                    and self._motion_enabled
                    and PToPMoveBase is not None
                    and self._backend_server_ready()
                    and self._perception_ready()
                    and self._map_ready()
                ),
                "goal_active": self._goal_active,
                "state": self._state,
                "fault_code": self._fault_code or None,
                "last_result_code": self._last_result_code or None,
            }
        self._status_pub.publish(_json_message(payload))

    def request_shutdown(self) -> None:
        with self._lock:
            if self._goal_reserved or self._goal_active:
                self._fault_code = "dddmr_bridge_shutdown"
                self._state = "stopping"
        self._publish_zero()

    def destroy_node(self) -> bool:
        self._publish_zero()
        self._action_server.destroy()
        if self._dddmr_client is not None:
            self._dddmr_client.destroy()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    node = DddmrNav2Bridge()
    executor = MultiThreadedExecutor(num_threads=3)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.request_shutdown()
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
