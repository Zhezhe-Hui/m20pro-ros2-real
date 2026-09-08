"""Read-only health monitor for the official DDDMR runtime."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import rclpy
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from tf2_ros import Buffer, TransformException, TransformListener

from dddmr_sys_core.action import PToPMoveBase


class DddmrRuntimeMonitor(Node):
    """Publish one explicit readiness source without issuing robot commands."""

    def __init__(self) -> None:
        super().__init__("m20pro_dddmr_runtime_monitor")
        self.declare_parameter("status_topic", "/m20pro/dddmr/runtime/status")
        self.declare_parameter("edge_status_topic", "/m20pro/dddmr/edge_cloud/status")
        self.declare_parameter("map_status_topic", "/m20pro/dddmr/map/status")
        self.declare_parameter("mcl_pose_topic", "/mcl_pose")
        self.declare_parameter("pose_topic", "/m20pro/dddmr/map_pose")
        self.declare_parameter("dddmr_action", "/p2p_move_base")
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("base_frame", "m20pro_base_link")
        self.declare_parameter("perception_global_node", "perception_3d_global")
        self.declare_parameter("mcl_pose_timeout_s", 2.0)
        self.declare_parameter("tf_timeout_s", 2.0)
        self.declare_parameter("edge_timeout_s", 2.0)
        # Map status is latched state, not a heartbeat. Zero disables expiry.
        self.declare_parameter("map_timeout_s", 0.0)

        # TF updates and status/pose timers must not share the default
        # mutually-exclusive callback group.  A graph query or a transient
        # TF lookup failure must not prevent the listener from accepting the
        # next transform sample.
        self._callback_group = ReentrantCallbackGroup()

        self._status_pub = self.create_publisher(
            String, str(self.get_parameter("status_topic").value), 10
        )
        self._pose_pub = self.create_publisher(
            PoseStamped, str(self.get_parameter("pose_topic").value), 10
        )
        self.create_subscription(
            String,
            str(self.get_parameter("edge_status_topic").value),
            self._on_edge_status,
            10,
            callback_group=self._callback_group,
        )
        map_qos = QoSProfile(depth=1)
        map_qos.reliability = ReliabilityPolicy.RELIABLE
        map_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.create_subscription(
            String,
            str(self.get_parameter("map_status_topic").value),
            self._on_map_status,
            map_qos,
            callback_group=self._callback_group,
        )
        self.create_subscription(
            PoseWithCovarianceStamped,
            str(self.get_parameter("mcl_pose_topic").value),
            self._on_mcl_pose,
            10,
            callback_group=self._callback_group,
        )
        self._edge: Dict[str, Any] = {}
        self._map: Dict[str, Any] = {}
        self._edge_at: Optional[float] = None
        self._map_at: Optional[float] = None
        self._mcl_pose_at: Optional[float] = None
        self._mcl_pose_frame = ""
        self._mcl_node_ready_cached = False
        self._global_perception_ready_cached = False
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._action_client = ActionClient(
            self,
            PToPMoveBase,
            str(self.get_parameter("dddmr_action").value),
            callback_group=self._callback_group,
        )
        self.create_timer(0.1, self._publish_pose, callback_group=self._callback_group)
        self.create_timer(0.5, self._publish_status, callback_group=self._callback_group)

    @staticmethod
    def _parse(message: String) -> Dict[str, Any]:
        try:
            payload = json.loads(message.data)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _on_edge_status(self, message: String) -> None:
        self._edge = self._parse(message)
        self._edge_at = time.monotonic()

    def _on_map_status(self, message: String) -> None:
        self._map = self._parse(message)
        self._map_at = time.monotonic()

    def _on_mcl_pose(self, message: PoseWithCovarianceStamped) -> None:
        self._mcl_pose_at = time.monotonic()
        self._mcl_pose_frame = str(message.header.frame_id or "")

    def _lookup_map_to_base(self):
        try:
            transform = self._tf_buffer.lookup_transform(
                str(self.get_parameter("map_frame").value),
                str(self.get_parameter("base_frame").value),
                rclpy.time.Time(),
            )
        except TransformException:
            return None, None
        stamp = transform.header.stamp
        stamp_s = float(stamp.sec) + float(stamp.nanosec) * 1e-9
        age_s = None if stamp_s <= 0.0 else max(0.0, time.time() - stamp_s)
        return transform, age_s

    def _tf_ready(self, transform: Any, age_s: Optional[float]) -> bool:
        return bool(
            transform is not None
            and age_s is not None
            and age_s <= float(self.get_parameter("tf_timeout_s").value)
        )

    def _mcl_node_ready(self) -> bool:
        return "mcl_3dl" in {name.strip("/") for name in self.get_node_names()}

    def _publish_pose(self) -> None:
        transform, tf_age = self._lookup_map_to_base()
        if not self._mcl_node_ready_cached or not self._tf_ready(transform, tf_age):
            return
        pose = PoseStamped()
        pose.header = transform.header
        pose.pose.position.x = transform.transform.translation.x
        pose.pose.position.y = transform.transform.translation.y
        pose.pose.position.z = transform.transform.translation.z
        pose.pose.orientation = transform.transform.rotation
        self._pose_pub.publish(pose)

    def _global_perception_ready(self) -> bool:
        expected = str(self.get_parameter("perception_global_node").value).strip("/")
        return bool(expected) and expected in set(self.get_node_names())

    def _publish_status(self) -> None:
        now = time.monotonic()
        edge_age = None if self._edge_at is None else now - self._edge_at
        map_age = None if self._map_at is None else now - self._map_at
        mcl_age = None if self._mcl_pose_at is None else now - self._mcl_pose_at
        edge_ready = bool(self._edge.get("ready")) and (
            edge_age is not None
            and edge_age <= float(self.get_parameter("edge_timeout_s").value)
        )
        map_timeout = float(self.get_parameter("map_timeout_s").value)
        map_ready = bool(self._map.get("mcl_ready")) and (
            map_age is not None
            and (map_timeout <= 0.0 or map_age <= map_timeout)
        )
        transform, tf_age = self._lookup_map_to_base()
        tf_ready = self._tf_ready(transform, tf_age)
        self._mcl_node_ready_cached = self._mcl_node_ready()
        self._global_perception_ready_cached = self._global_perception_ready()
        mcl_ready = self._mcl_node_ready_cached and tf_ready
        action_ready = self._action_client.server_is_ready()
        global_perception_ready = self._global_perception_ready_cached
        if not edge_ready:
            code = str(self._edge.get("code") or "dddmr_edge_cloud_unavailable")
        elif not map_ready:
            code = str(self._map.get("code") or "dddmr_mcl_map_unavailable")
        elif not global_perception_ready:
            code = "dddmr_global_perception_unavailable"
        elif not self._mcl_node_ready_cached:
            code = "dddmr_mcl_node_unavailable"
        elif not tf_ready:
            code = "dddmr_mcl_tf_unavailable"
        elif not action_ready:
            code = "dddmr_action_unavailable"
        else:
            code = "dddmr_official_ready"
        payload = {
            "component": "m20pro_dddmr_runtime_monitor",
            "backend": "official",
            "ready": code == "dddmr_official_ready",
            "state": "ready" if code == "dddmr_official_ready" else "waiting",
            "code": code,
            "edge_ready": edge_ready,
            "map_ready": map_ready,
            "global_perception_ready": global_perception_ready,
            "global_perception_node": str(
                self.get_parameter("perception_global_node").value
            ),
            "mcl_node_ready": self._mcl_node_ready_cached,
            "mcl_ready": mcl_ready,
            "mcl_pose_frame": self._mcl_pose_frame,
            "action_server_ready": action_ready,
            "tf_ready": tf_ready,
            "tf_code": "dddmr_mcl_tf_ready" if tf_ready else "dddmr_mcl_tf_unavailable",
            "edge_age_s": edge_age,
            "map_age_s": map_age,
            "mcl_pose_age_s": mcl_age,
            "tf_age_s": tf_age,
            "pose_topic": str(self.get_parameter("pose_topic").value),
            "stamp": time.time(),
        }
        message = String()
        message.data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self._status_pub.publish(message)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DddmrRuntimeMonitor()
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
