import math
import os
from pathlib import Path
from typing import Dict, Optional

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from rclpy.node import Node
from std_msgs.msg import String


class InitialPose3DAdapter(Node):
    """Resolve interactive initial poses onto the configured 3D floor height."""

    def __init__(self) -> None:
        super().__init__("m20pro_initialpose_3d_adapter")
        self.declare_parameter("input_topic", "/initialpose")
        self.declare_parameter("output_topic", "/m20pro/initialpose_3d")
        self.declare_parameter("mcl_output_topic", "/initial_3d_pose")
        self.declare_parameter("current_floor_topic", "/m20pro/current_floor")
        self.declare_parameter("config_file", "")
        self.declare_parameter("z", 0.0)
        self.declare_parameter("enabled", False)

        self.floor_z_map: Dict[str, float] = {}
        self._floor_z_map_mtime_ns: Optional[int] = None
        self._floor_z_map_path = ""
        self._refresh_floor_z_map(force=True)
        self.current_floor = ""
        self.output_pub = self.create_publisher(
            PoseStamped,
            str(self.get_parameter("output_topic").value),
            10,
        )
        self.mcl_output_pub = self.create_publisher(
            PoseWithCovarianceStamped,
            str(self.get_parameter("mcl_output_topic").value),
            10,
        )
        self.create_subscription(
            String,
            str(self.get_parameter("current_floor_topic").value),
            self._on_current_floor,
            10,
        )
        self.create_subscription(
            PoseWithCovarianceStamped,
            str(self.get_parameter("input_topic").value),
            self._on_initialpose,
            10,
        )
        self.get_logger().info(
            "initialpose 3D adapter ready; enabled=%s fallback_z=%.3f floor_z_entries=%d"
            % (
                bool(self.get_parameter("enabled").value),
                float(self.get_parameter("z").value),
                len(self.floor_z_map),
            )
        )

    def _on_current_floor(self, msg: String) -> None:
        self.current_floor = msg.data.strip()

    def _on_initialpose(self, msg: PoseWithCovarianceStamped) -> None:
        if not bool(self.get_parameter("enabled").value):
            return
        requested_z = self._finite_z(msg.pose.pose.position.z)
        pose = PoseStamped()
        pose.header = msg.header
        pose.pose = msg.pose.pose
        pose.pose.position.z = self._resolve_z(requested_z)
        pose.header.stamp = self.get_clock().now().to_msg()
        self.output_pub.publish(pose)
        # DDDMR MCL consumes PoseWithCovarianceStamped on /initial_3d_pose.
        # Keep the existing PoseStamped output for the M20Pro native adapter,
        # but do not force the official localization path through that adapter.
        mcl_pose = PoseWithCovarianceStamped()
        mcl_pose.header = pose.header
        mcl_pose.pose = msg.pose
        mcl_pose.pose.pose.position.z = pose.pose.position.z
        self.mcl_output_pub.publish(mcl_pose)

    def _resolve_z(self, requested_z: Optional[float] = None) -> float:
        self._refresh_floor_z_map()
        fallback_z = float(self.get_parameter("z").value)
        if requested_z is not None and abs(requested_z - fallback_z) > 1e-6:
            return requested_z
        if self.current_floor in self.floor_z_map:
            return self.floor_z_map[self.current_floor]
        if not self.current_floor and len(self.floor_z_map) == 1:
            return next(iter(self.floor_z_map.values()))
        if requested_z is not None:
            return requested_z
        return fallback_z

    def _refresh_floor_z_map(self, *, force: bool = False) -> None:
        path = self._resolve_path(str(self.get_parameter("config_file").value))
        if not path:
            if force:
                self.floor_z_map = {}
                self._floor_z_map_path = ""
                self._floor_z_map_mtime_ns = None
            return
        try:
            stat = os.stat(path)
        except OSError as exc:
            if force or self.floor_z_map:
                self.get_logger().warning("cannot stat floor config for z map: %s" % exc)
            self.floor_z_map = {}
            self._floor_z_map_path = path
            self._floor_z_map_mtime_ns = None
            return
        if (
            not force
            and self._floor_z_map_path == path
            and self._floor_z_map_mtime_ns == stat.st_mtime_ns
        ):
            return
        self.floor_z_map = self._load_floor_z_map_from_path(path)
        self._floor_z_map_path = path
        self._floor_z_map_mtime_ns = stat.st_mtime_ns
        if force or self.floor_z_map:
            self.get_logger().info(
                "loaded runtime floor z map: path=%s entries=%d"
                % (path, len(self.floor_z_map))
            )

    def _load_floor_z_map_from_path(self, path: str) -> Dict[str, float]:
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file) or {}
        except OSError as exc:
            self.get_logger().warning("cannot read floor config for z map: %s" % exc)
            return {}
        floors = data.get("floors") or {}
        floor_z_map: Dict[str, float] = {}
        if not isinstance(floors, dict):
            return floor_z_map
        for floor_id, floor in floors.items():
            if not isinstance(floor, dict):
                continue
            z_value = floor.get("z")
            initial_pose = floor.get("initial_pose")
            if z_value is None and isinstance(initial_pose, dict):
                z_value = initial_pose.get("z")
            resolved_z = self._finite_z(z_value)
            if resolved_z is not None:
                floor_z_map[str(floor_id)] = resolved_z
        return floor_z_map

    @staticmethod
    def _finite_z(value: object) -> Optional[float]:
        try:
            z = float(value)
        except (TypeError, ValueError):
            return None
        return z if math.isfinite(z) else None

    def _resolve_path(self, value: str) -> str:
        path = os.path.expandvars(os.path.expanduser(value))
        if path.startswith("package://"):
            package_and_path = path[len("package://") :]
            package_name, _, relative_path = package_and_path.partition("/")
            if not package_name or not relative_path:
                return ""
            return os.path.join(get_package_share_directory(package_name), relative_path)
        if os.path.isabs(path):
            return path
        if path:
            return str((Path.cwd() / path).resolve())
        return ""


def main(args: Optional[list] = None) -> None:
    rclpy.init(args=args)
    node = InitialPose3DAdapter()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
