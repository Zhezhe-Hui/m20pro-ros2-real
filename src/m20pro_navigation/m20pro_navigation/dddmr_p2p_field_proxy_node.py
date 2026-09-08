"""A low-speed `/p2p_move_base` runtime for the M20Pro DDDMR path."""

from __future__ import annotations

import json
import math
import signal
import threading
import time
from typing import Any, Dict, Optional, Tuple

import rclpy
from geometry_msgs.msg import Twist
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.time import Time
from std_msgs.msg import String
from tf2_ros import Buffer, TransformException, TransformListener

from .dddmr_field_proxy_contract import field_proxy_step, finite_number

try:
    from dddmr_sys_core.action import PToPMoveBase
except ImportError:
    PToPMoveBase = None  # type: ignore[assignment,misc]


SUCCESS = 1
FAILURE = 2


def _json_message(payload: Dict[str, Any]) -> String:
    message = String()
    message.data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return message


def _yaw_from_quaternion(quaternion: Any) -> Optional[float]:
    try:
        x = float(quaternion.x)
        y = float(quaternion.y)
        z = float(quaternion.z)
        w = float(quaternion.w)
        if not all(finite_number(value) for value in (x, y, z, w)):
            return None
        norm = math.sqrt(x * x + y * y + z * z + w * w)
        if norm <= 1e-9:
            return None
        x /= norm
        y /= norm
        z /= norm
        w /= norm
        siny_cosp = 2.0 * (w * z + x * y)
        cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
        return math.atan2(siny_cosp, cosy_cosp)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


class DddmrP2PFieldProxy(Node):
    def __init__(self) -> None:
        super().__init__("m20pro_dddmr_p2p_field_proxy")
        self.declare_parameter("enabled", False)
        self.declare_parameter("dddmr_action", "/p2p_move_base")
        self.declare_parameter("cmd_vel_topic", "/dddmr/cmd_vel")
        self.declare_parameter("status_topic", "/m20pro/dddmr/runtime/status")
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("base_frame", "m20pro_base_link")
        self.declare_parameter("control_period_s", 0.1)
        self.declare_parameter("goal_timeout_s", 180.0)
        self.declare_parameter("tf_fail_timeout_s", 2.0)
        self.declare_parameter("max_goal_distance_m", 3.0)
        self.declare_parameter("xy_tolerance_m", 0.18)
        self.declare_parameter("yaw_tolerance_rad", 0.30)
        self.declare_parameter("heading_tolerance_rad", 0.35)
        self.declare_parameter("max_linear_mps", 0.18)
        self.declare_parameter("min_linear_mps", 0.04)
        self.declare_parameter("max_angular_radps", 0.45)
        self.declare_parameter("linear_gain", 0.45)
        self.declare_parameter("angular_gain", 1.2)
        self.declare_parameter("status_period_s", 1.0)

        self._enabled = bool(self.get_parameter("enabled").value)
        self._callback_group = ReentrantCallbackGroup()
        self._lock = threading.RLock()
        self._goal_reserved = False
        self._goal_active = False
        self._state = "idle" if self._enabled else "disabled"
        self._last_code = ""
        self._last_decision = ""
        self._last_distance_m: Optional[float] = None

        self._cmd_pub = self.create_publisher(
            Twist, str(self.get_parameter("cmd_vel_topic").value), 10
        )
        self._status_pub = self.create_publisher(
            String, str(self.get_parameter("status_topic").value), 10
        )
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._action_server: Optional[Any] = None
        if PToPMoveBase is not None:
            self._action_server = ActionServer(
                self,
                PToPMoveBase,
                str(self.get_parameter("dddmr_action").value),
                execute_callback=self._execute,
                goal_callback=self._on_goal_request,
                cancel_callback=self._on_cancel_request,
                callback_group=self._callback_group,
            )
        self.create_timer(
            max(0.1, float(self.get_parameter("status_period_s").value)),
            self._publish_status,
            callback_group=self._callback_group,
        )
        self._publish_zero()
        self._publish_status()

    def _map_frame(self) -> str:
        return str(self.get_parameter("map_frame").value or "map")

    def _base_frame(self) -> str:
        return str(self.get_parameter("base_frame").value or "m20pro_base_link")

    @staticmethod
    def _on_cancel_request(_goal_handle: Any) -> CancelResponse:
        return CancelResponse.ACCEPT

    def _on_goal_request(self, request: Any) -> GoalResponse:
        with self._lock:
            if not self._enabled:
                self._state = "disabled"
                self._last_code = "field_proxy_disabled"
                self._publish_status()
                return GoalResponse.REJECT
            if PToPMoveBase is None or self._action_server is None:
                self._state = "unavailable"
                self._last_code = "field_proxy_action_type_missing"
                self._publish_status()
                return GoalResponse.REJECT
            if self._goal_reserved or self._goal_active:
                self._last_code = "field_proxy_goal_active"
                self._publish_status()
                return GoalResponse.REJECT
            goal_frame = str(request.target_pose.header.frame_id or self._map_frame())
            if goal_frame != self._map_frame():
                self._last_code = "field_proxy_goal_frame_mismatch"
                self._publish_status()
                return GoalResponse.REJECT
            current = self._lookup_pose()
            if current is None:
                self._state = "waiting_tf"
                self._last_code = "field_proxy_tf_unavailable"
                self._publish_status()
                return GoalResponse.REJECT
            distance = self._goal_distance_from_current(request, current)
            max_goal_distance = float(self.get_parameter("max_goal_distance_m").value)
            if max_goal_distance > 0.0 and distance > max_goal_distance:
                self._last_distance_m = distance
                self._last_code = "field_proxy_goal_too_far"
                self._publish_status()
                return GoalResponse.REJECT
            self._goal_reserved = True
            self._state = "goal_reserved"
            self._last_code = "field_proxy_goal_accepted"
        self._publish_status()
        return GoalResponse.ACCEPT

    def _goal_distance_from_current(
        self, request: Any, current: Tuple[Any, float, float, float]
    ) -> float:
        _transform, current_x, current_y, _current_yaw = current
        goal = request.target_pose.pose.position
        return math.hypot(float(goal.x) - current_x, float(goal.y) - current_y)

    def _lookup_pose(self) -> Optional[Tuple[Any, float, float, float]]:
        try:
            transform = self._tf_buffer.lookup_transform(
                self._map_frame(),
                self._base_frame(),
                Time(),
            )
            translation = transform.transform.translation
            rotation = transform.transform.rotation
            x = float(translation.x)
            y = float(translation.y)
            yaw = _yaw_from_quaternion(rotation)
            if yaw is None or not all(finite_number(value) for value in (x, y, yaw)):
                return None
            return transform, x, y, yaw
        except (TransformException, TypeError, ValueError, RuntimeError):
            return None

    def _execute(self, goal_handle: Any) -> Any:
        with self._lock:
            self._goal_reserved = False
            self._goal_active = True
            self._state = "navigating"
            self._last_code = "field_proxy_goal_running"
            self._last_decision = ""
            self._last_distance_m = None
        self._publish_status()

        target_pose = goal_handle.request.target_pose
        started = time.monotonic()
        last_tf_ok = started
        result = PToPMoveBase.Result()
        try:
            while rclpy.ok():
                if goal_handle.is_cancel_requested:
                    result.status = FAILURE
                    result.result = "field_proxy_goal_cancelled"
                    self._last_code = result.result
                    self._publish_zero()
                    goal_handle.canceled()
                    return result
                if time.monotonic() - started > float(
                    self.get_parameter("goal_timeout_s").value
                ):
                    result.status = FAILURE
                    result.result = "field_proxy_goal_timeout"
                    self._last_code = result.result
                    self._publish_zero()
                    goal_handle.abort()
                    return result

                current = self._lookup_pose()
                if current is None:
                    self._publish_zero()
                    with self._lock:
                        self._state = "waiting_tf"
                        self._last_code = "field_proxy_tf_unavailable"
                    if time.monotonic() - last_tf_ok > float(
                        self.get_parameter("tf_fail_timeout_s").value
                    ):
                        result.status = FAILURE
                        result.result = "field_proxy_tf_unavailable"
                        goal_handle.abort()
                        return result
                    time.sleep(self._period())
                    continue
                last_tf_ok = time.monotonic()
                transform, current_x, current_y, current_yaw = current
                goal_yaw = _yaw_from_quaternion(target_pose.pose.orientation)
                if goal_yaw is None:
                    goal_yaw = current_yaw
                step = field_proxy_step(
                    current_x=current_x,
                    current_y=current_y,
                    current_yaw=current_yaw,
                    goal_x=float(target_pose.pose.position.x),
                    goal_y=float(target_pose.pose.position.y),
                    goal_yaw=goal_yaw,
                    xy_tolerance_m=float(
                        self.get_parameter("xy_tolerance_m").value
                    ),
                    yaw_tolerance_rad=float(
                        self.get_parameter("yaw_tolerance_rad").value
                    ),
                    heading_tolerance_rad=float(
                        self.get_parameter("heading_tolerance_rad").value
                    ),
                    max_linear_mps=float(
                        self.get_parameter("max_linear_mps").value
                    ),
                    min_linear_mps=float(
                        self.get_parameter("min_linear_mps").value
                    ),
                    max_angular_radps=float(
                        self.get_parameter("max_angular_radps").value
                    ),
                    linear_gain=float(self.get_parameter("linear_gain").value),
                    angular_gain=float(self.get_parameter("angular_gain").value),
                )
                self._publish_feedback(goal_handle, transform, str(step["decision"]))
                with self._lock:
                    self._state = "navigating"
                    self._last_decision = str(step["decision"])
                    self._last_code = str(step["decision"])
                    self._last_distance_m = float(step["distance_m"])
                if bool(step["done"]):
                    self._publish_zero()
                    result.status = SUCCESS
                    result.result = "field_proxy_goal_succeeded"
                    self._last_code = result.result
                    goal_handle.succeed()
                    return result
                command = Twist()
                command.linear.x = float(step["linear_x"])
                command.linear.y = float(step["linear_y"])
                command.angular.z = float(step["angular_z"])
                self._cmd_pub.publish(command)
                time.sleep(self._period())
            result.status = FAILURE
            result.result = "field_proxy_shutdown"
            self._publish_zero()
            goal_handle.abort()
            return result
        except Exception as exc:
            self.get_logger().exception("DDDMR field proxy failed")
            result.status = FAILURE
            result.result = "field_proxy_exception:%s" % type(exc).__name__
            self._last_code = result.result
            self._publish_zero()
            if bool(goal_handle.is_active):
                goal_handle.abort()
            return result
        finally:
            self._publish_zero()
            with self._lock:
                self._goal_reserved = False
                self._goal_active = False
                self._state = "idle" if self._enabled else "disabled"
            self._publish_status()

    def _period(self) -> float:
        return max(0.02, float(self.get_parameter("control_period_s").value))

    def _publish_feedback(
        self, goal_handle: Any, transform: Any, current_decision: str
    ) -> None:
        if PToPMoveBase is None or not bool(goal_handle.is_active):
            return
        feedback = PToPMoveBase.Feedback()
        feedback.base_position = transform
        feedback.last_decision = self._last_decision
        feedback.current_decision = current_decision
        goal_handle.publish_feedback(feedback)

    def _publish_zero(self) -> None:
        if rclpy.ok():
            self._cmd_pub.publish(Twist())

    def _publish_status(self) -> None:
        tf_ready = self._lookup_pose() is not None
        with self._lock:
            if not self._enabled:
                code = "field_proxy_disabled"
            elif PToPMoveBase is None or self._action_server is None:
                code = "field_proxy_action_type_missing"
            elif not tf_ready:
                code = "field_proxy_tf_unavailable"
            else:
                code = self._last_code or "field_proxy_ready"
            payload = {
                "component": "dddmr_p2p_field_proxy",
                "backend": "field_proxy",
                "enabled": self._enabled,
                "action_type_available": PToPMoveBase is not None,
                "action_server_ready": self._action_server is not None,
                "tf_ready": tf_ready,
                "tf_code": "field_proxy_tf_ready" if tf_ready else "field_proxy_tf_unavailable",
                "ready": bool(
                    self._enabled
                    and self._action_server is not None
                    and tf_ready
                ),
                "goal_active": self._goal_active,
                "state": self._state,
                "code": code,
                "decision": self._last_decision or None,
                "distance_m": self._last_distance_m,
                "action": str(self.get_parameter("dddmr_action").value),
                "cmd_vel_topic": str(self.get_parameter("cmd_vel_topic").value),
                "map_frame": self._map_frame(),
                "base_frame": self._base_frame(),
                "max_goal_distance_m": float(
                    self.get_parameter("max_goal_distance_m").value
                ),
            }
        self._status_pub.publish(_json_message(payload))

    def request_shutdown(self) -> None:
        with self._lock:
            if self._goal_reserved or self._goal_active:
                self._last_code = "field_proxy_shutdown"
                self._state = "stopping"
        self._publish_zero()

    def destroy_node(self) -> bool:
        self._publish_zero()
        if self._action_server is not None:
            self._action_server.destroy()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    node = DddmrP2PFieldProxy()
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
