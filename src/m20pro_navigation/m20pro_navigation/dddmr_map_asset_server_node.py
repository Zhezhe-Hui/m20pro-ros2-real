"""Publish validated DDDMR static mapcloud/mapground assets.

The upstream DDDMR map server owns map generation.  This node is the M20Pro
runtime boundary for already-accepted PCD assets: it loads a pair atomically,
publishes both topics transient-local, and clears the previous pair before a
floor switch so stale geometry cannot pass the navigation gate.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import rclpy
from geometry_msgs.msg import Pose, PoseArray
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import PointCloud2, PointField
from sensor_msgs_py import point_cloud2
from std_msgs.msg import String
from dddmr_sys_core.srv import GetKeyFrameCloud

try:
    import yaml
except ImportError:  # pragma: no cover - the ROS runtime installs python3-yaml
    yaml = None  # type: ignore[assignment]

from .dddmr_map_asset_io import _finite_xyz, _parse_pcd, _split_paths
from .dddmr_map_asset_contract import (
    generate_dddmr_field_test_flat_map_points,
)
from .lightning_mcl_map_adapter import (
    Keyframe,
    build_lightning_keyframes,
    load_lightning_path,
    load_pose_pcd,
    select_key_poses,
)


def _json_message(payload: Mapping[str, Any]) -> String:
    message = String()
    message.data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return message


def _create_map_cloud(header: Any, points: Iterable[Tuple[float, float, float]]) -> PointCloud2:
    """Publish XYZI because DDDMR StaticLayer converts maps to PointXYZI."""
    fields = [
        PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
        PointField(name="intensity", offset=12, datatype=PointField.FLOAT32, count=1),
    ]
    cloud_points = [(x, y, z, 0.0) for x, y, z in points]
    return point_cloud2.create_cloud(
        header, fields, cloud_points
    )


class DddmrMapAssetServer(Node):
    def __init__(self) -> None:
        super().__init__("m20pro_dddmr_map_asset_server")
        self.declare_parameter("asset_manifest", "")
        self.declare_parameter("initial_floor", "")
        self.declare_parameter("mapcloud_file", "")
        self.declare_parameter("mapground_file", "")
        self.declare_parameter("mapcloud_files", [])
        self.declare_parameter("mapground_files", [])
        self.declare_parameter("poses_file", "")
        self.declare_parameter("path_file", "")
        self.declare_parameter("floor_topic", "/m20pro/current_floor")
        self.declare_parameter("mapcloud_topic", "/mapcloud")
        self.declare_parameter("mapground_topic", "/mapground")
        self.declare_parameter("status_topic", "/m20pro/dddmr/map/status")
        self.declare_parameter("frame_id", "map")
        self.declare_parameter("field_test_fallback_enabled", False)
        self.declare_parameter("field_test_fallback_extent_m", 2.0)
        self.declare_parameter("field_test_fallback_spacing_m", 0.25)
        self.declare_parameter("field_test_fallback_height_m", 0.0)
        # Zero means lossless loading. Set an explicit cap only after measuring
        # the map's memory footprint on the target RK3588.
        self.declare_parameter("max_points", 0)
        self.declare_parameter("reload_period_s", 0.0)
        # These names deliberately match the official DDDMR pose-graph server
        # interface.  The adapter fills it from the real Lightning archive.
        self.declare_parameter("pg_map_server_name", "map1")
        self.declare_parameter("robot_base_frame", "m20pro_base_link")
        self.declare_parameter("keyframe_radius_m", 8.0)
        self.declare_parameter("keyframe_stride", 6)
        self.declare_parameter("keyframe_max_points", 3000)

        qos = QoSProfile(depth=1)
        qos.reliability = ReliabilityPolicy.RELIABLE
        qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self._mapcloud_pub = self.create_publisher(
            PointCloud2, str(self.get_parameter("mapcloud_topic").value), qos
        )
        self._mapground_pub = self.create_publisher(
            PointCloud2, str(self.get_parameter("mapground_topic").value), qos
        )
        pg_name = str(self.get_parameter("pg_map_server_name").value or "map1").strip("/")
        self._pg_name = pg_name or "map1"
        self._pg_mapcloud_pub = self.create_publisher(
            PointCloud2, "%s/mapcloud" % self._pg_name, qos
        )
        self._pg_mapground_pub = self.create_publisher(
            PointCloud2, "%s/mapground" % self._pg_name, qos
        )
        self._pg_key_poses_pub = self.create_publisher(
            PoseArray, "%s/key_poses" % self._pg_name, qos
        )
        self._keyframe_service = self.create_service(
            GetKeyFrameCloud,
            "%s/get_key_frame_cloud" % self._pg_name,
            self._on_get_key_frame_cloud,
        )
        status_qos = QoSProfile(depth=1)
        status_qos.reliability = ReliabilityPolicy.RELIABLE
        status_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self._status_pub = self.create_publisher(
            String, str(self.get_parameter("status_topic").value), status_qos
        )
        self.create_subscription(
            String,
            str(self.get_parameter("floor_topic").value),
            self._on_floor,
            10,
        )
        self._manifest_dir = Path.cwd()
        self._manifest_error: Optional[str] = None
        self._floor = str(self.get_parameter("initial_floor").value or "").strip()
        self._last_files: Dict[str, List[str]] = {"mapcloud": [], "mapground": []}
        self._last_code = "waiting_map_assets"
        self._last_error: Optional[str] = None
        self._mapcloud_points = 0
        self._mapground_points = 0
        self._keyframes: List[Keyframe] = []
        self._keyframe_error: Optional[str] = None
        self._pose_source = ""
        self._manifest_path: Optional[Path] = None
        self._manifest_mtime_ns: Optional[int] = None
        self._loaded_floor: Optional[str] = None
        self._loaded_manifest_mtime_ns: Optional[int] = None
        self._manifest = {}
        self._publish_empty()
        self._load_for_floor(self._floor, force=True)
        reload_s = float(self.get_parameter("reload_period_s").value)
        if reload_s > 0.0:
            self.create_timer(max(0.5, reload_s), lambda: self._load_for_floor(self._floor))

    @staticmethod
    def _load_manifest(path: Optional[Path]) -> Dict[str, Any]:
        if path is None:
            return {}
        if yaml is None:
            raise RuntimeError("python_yaml_unavailable")
        if not path.exists():
            return {}
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("asset_manifest_not_mapping")
        return raw

    def _manifest_source_path(self) -> Optional[Path]:
        value = str(self.get_parameter("asset_manifest").value or "").strip()
        if not value:
            return None
        try:
            return Path(value).expanduser().resolve()
        except (OSError, RuntimeError):
            return Path(value).expanduser()

    def _refresh_manifest_unlocked(self) -> bool:
        path = self._manifest_source_path()
        self._manifest_path = path
        if path is None:
            if self._manifest != {} or self._manifest_error is not None:
                self._manifest = {}
                self._manifest_error = None
                self._manifest_mtime_ns = None
                self._manifest_dir = Path.cwd()
                return True
            return False
        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            mtime_ns = None
        if mtime_ns == self._manifest_mtime_ns and self._manifest_error is None:
            return False
        self._manifest_dir = path.parent
        yaml_error = (yaml.YAMLError,) if yaml is not None else ()
        try:
            self._manifest = self._load_manifest(path)
            self._manifest_error = None
        except (OSError, ValueError, RuntimeError) + yaml_error as exc:
            # The dashboard rewrites the manifest in place; a reload tick can
            # observe a transiently incomplete document. Keep the previous
            # manifest and retry on the next tick instead of crashing the
            # whole node (2026-08-31 field incident).
            self._manifest_mtime_ns = None
            self._manifest_error = "%s:%s" % (type(exc).__name__, exc)
            return True
        self._manifest_mtime_ns = mtime_ns
        return True

    def _files_for_floor(self, floor: str) -> Tuple[List[Path], List[Path]]:
        manifest_floor: Mapping[str, Any] = {}
        floors = self._manifest.get("floors")
        if isinstance(floors, dict):
            candidate = floors.get(floor) or floors.get("default")
            if isinstance(candidate, dict):
                manifest_floor = candidate
        cloud_values: Any = manifest_floor.get("mapcloud") if manifest_floor else None
        ground_values: Any = manifest_floor.get("mapground") if manifest_floor else None
        if cloud_values is None:
            cloud_values = self.get_parameter("mapcloud_files").value
        if ground_values is None:
            ground_values = self.get_parameter("mapground_files").value
        if not _split_paths(cloud_values):
            cloud_values = self.get_parameter("mapcloud_file").value
        if not _split_paths(ground_values):
            ground_values = self.get_parameter("mapground_file").value
        cloud_paths = _split_paths(cloud_values)
        ground_paths = _split_paths(ground_values)
        if manifest_floor:
            cloud_paths = [
                path if path.is_absolute() else self._manifest_dir / path
                for path in cloud_paths
            ]
            ground_paths = [
                path if path.is_absolute() else self._manifest_dir / path
                for path in ground_paths
            ]
        return cloud_paths, ground_paths

    def _pose_sources_for_floor(self, floor: str, cloud_paths: Sequence[Path]) -> List[Path]:
        """Return trajectory candidates in preference order for one asset."""
        manifest_floor: Mapping[str, Any] = {}
        floors = self._manifest.get("floors")
        if isinstance(floors, dict):
            candidate = floors.get(floor) or floors.get("default")
            if isinstance(candidate, dict):
                manifest_floor = candidate
        raw_values: List[Any] = []
        for key in ("path", "trajectory", "path_file", "poses", "poses_file"):
            value = manifest_floor.get(key) if manifest_floor else None
            if value:
                raw_values.append(value)
        for value in (
            self.get_parameter("path_file").value,
            self.get_parameter("poses_file").value,
        ):
            if value:
                raw_values.append(value)
        candidates: List[Path] = []
        for value in raw_values:
            for path in _split_paths(value):
                candidates.append(path if path.is_absolute() else self._manifest_dir / path)
        for cloud_path in cloud_paths:
            candidates.extend((cloud_path.parent / "path.txt", cloud_path.parent / "poses.pcd"))
        seen = set()
        return [path for path in candidates if not (str(path) in seen or seen.add(str(path)))]

    def _load_keyframes(
        self,
        floor: str,
        cloud_paths: Sequence[Path],
        cloud_points: Sequence[Tuple[float, float, float]],
        ground_points: Sequence[Tuple[float, float, float]],
    ) -> None:
        self._keyframes = []
        self._keyframe_error = None
        self._pose_source = ""
        poses = []
        for path in self._pose_sources_for_floor(floor, cloud_paths):
            if not path.is_file():
                continue
            try:
                if path.name == "path.txt":
                    poses = load_lightning_path(path)
                else:
                    poses = load_pose_pcd(path)
            except (OSError, ValueError, UnicodeError) as exc:
                self._keyframe_error = "%s:%s" % (type(exc).__name__, exc)
                continue
            if poses:
                self._pose_source = str(path)
                break
        if not poses:
            self._keyframe_error = self._keyframe_error or "lightning_trajectory_missing"
            return
        try:
            selected_poses = select_key_poses(
                poses, int(self.get_parameter("keyframe_stride").value)
            )
            self._keyframes = build_lightning_keyframes(
                cloud_points,
                ground_points,
                selected_poses,
                radius_m=float(self.get_parameter("keyframe_radius_m").value),
                max_points=max(0, int(self.get_parameter("keyframe_max_points").value)),
            )
        except (TypeError, ValueError, OverflowError) as exc:
            self._keyframe_error = "%s:%s" % (type(exc).__name__, exc)
            self._keyframes = []
        if not self._keyframes:
            self._keyframe_error = self._keyframe_error or "lightning_keyframes_empty"

    def _publish_keyframe_index(self, stamp: Any) -> None:
        message = PoseArray()
        message.header = self._header(stamp)
        for keyframe in self._keyframes:
            x, y, z, qx, qy, qz, qw = keyframe["pose"]  # type: ignore[misc]
            pose = Pose()
            pose.position.x = float(x)
            pose.position.y = float(y)
            pose.position.z = float(z)
            pose.orientation.x = float(qx)
            pose.orientation.y = float(qy)
            pose.orientation.z = float(qz)
            pose.orientation.w = float(qw)
            message.poses.append(pose)
        self._pg_key_poses_pub.publish(message)

    def _on_get_key_frame_cloud(
        self,
        request: GetKeyFrameCloud.Request,
        response: GetKeyFrameCloud.Response,
    ) -> GetKeyFrameCloud.Response:
        index = int(request.key_frame_number)
        stamp = self.get_clock().now().to_msg()
        map_header = self._header(stamp)
        base_header = self._header(stamp)
        base_header.frame_id = str(self.get_parameter("robot_base_frame").value)
        keyframe: Optional[Keyframe] = (
            self._keyframes[index] if 0 <= index < len(self._keyframes) else None
        )
        map_points = list(keyframe.get("map", [])) if keyframe else []
        ground_points = list(keyframe.get("ground", [])) if keyframe else []
        map_base = list(keyframe.get("map_base", [])) if keyframe else []
        ground_base = list(keyframe.get("ground_base", [])) if keyframe else []
        response.key_frame_cloud = _create_map_cloud(map_header, map_points)
        response.key_frame_surface = _create_map_cloud(map_header, map_points)
        response.key_frame_ground = _create_map_cloud(map_header, ground_points)
        response.key_frame_ground_edge = _create_map_cloud(map_header, ground_points)
        response.key_frame_cloud_base_link = _create_map_cloud(base_header, map_base)
        response.key_frame_surface_base_link = _create_map_cloud(base_header, map_base)
        response.key_frame_ground_base_link = _create_map_cloud(base_header, ground_base)
        response.key_frame_ground_edge_base_link = _create_map_cloud(base_header, ground_base)
        return response

    def _load_files(self, paths: Sequence[Path]) -> List[Tuple[float, float, float]]:
        max_points = max(0, int(self.get_parameter("max_points").value))
        output: List[Tuple[float, float, float]] = []
        for path in paths:
            if not path.is_file():
                raise FileNotFoundError(str(path))
            remaining = max_points - len(output) if max_points else 0
            output.extend(_parse_pcd(path, remaining))
            if max_points and len(output) >= max_points:
                break
        return output[:max_points] if max_points else output

    def _publish_empty(self) -> None:
        now = self.get_clock().now().to_msg()
        empty = _create_map_cloud(self._header(now), [])
        self._mapcloud_pub.publish(empty)
        self._mapground_pub.publish(empty)
        self._pg_mapcloud_pub.publish(empty)
        self._pg_mapground_pub.publish(empty)
        # Do not publish an empty pose-graph index.  The official DDDMR MCL
        # treats a transient-local /map1/key_poses sample as the complete
        # keyframe set; an initial empty PoseArray races the real asset load and
        # makes mcl_3dl build empty KD-trees before valid keyframes arrive.
        # Status still reports not-ready while assets load, but the pose-graph
        # interface is only published once it contains real Lightning keyframes.

    def _header(self, stamp: Any) -> Any:
        from std_msgs.msg import Header

        header = Header()
        header.stamp = stamp
        header.frame_id = str(self.get_parameter("frame_id").value or "map")
        return header

    def _publish_status(self) -> None:
        ready = self._mapcloud_points > 0 and self._mapground_points > 0
        provisional = bool(self.get_parameter("field_test_fallback_enabled").value) and (
            self._last_code in {"field_test_flat_map_ready", "field_test_flat_map_fallback"}
        )
        payload = {
            "component": "dddmr_map_asset_server",
            "ready": ready,
            "provisional": provisional,
            "floor": self._floor or None,
            "mapcloud_points": self._mapcloud_points,
            "mapground_points": self._mapground_points,
            "keyframe_count": len(self._keyframes),
            "keyframes_ready": bool(self._keyframes),
            "mcl_ready": ready and bool(self._keyframes),
            "keyframe_error": self._keyframe_error,
            "pose_source": self._pose_source or None,
            "mapcloud_files": list(self._last_files["mapcloud"]),
            "mapground_files": list(self._last_files["mapground"]),
            "code": (
                self._last_code
                if provisional
                else (
                    "map_assets_ready"
                    if ready and self._keyframes
                    else self._last_code
                )
            ),
            "source": "field_test_flat_map" if provisional else "manifest",
            "error": self._last_error,
            "frame_id": str(self.get_parameter("frame_id").value or "map"),
            "stamp": time.time(),
        }
        self._status_pub.publish(_json_message(payload))

    def _field_test_fallback_points(self) -> List[Tuple[float, float, float]]:
        return generate_dddmr_field_test_flat_map_points(
            extent_m=float(self.get_parameter("field_test_fallback_extent_m").value),
            spacing_m=float(self.get_parameter("field_test_fallback_spacing_m").value),
            height_m=float(self.get_parameter("field_test_fallback_height_m").value),
        )

    def _publish_field_test_fallback(self, *, code: str, error: Optional[str] = None) -> None:
        points = self._field_test_fallback_points()
        if not points:
            raise RuntimeError("field_test_flat_map_empty")
        self._last_files = {"mapcloud": ["field_test_flat_map"], "mapground": ["field_test_flat_map"]}
        self._last_code = code
        self._last_error = error
        stamp = self.get_clock().now().to_msg()
        header = self._header(stamp)
        self._mapcloud_pub.publish(_create_map_cloud(header, points))
        self._mapground_pub.publish(_create_map_cloud(header, points))
        self._mapcloud_points = len(points)
        self._mapground_points = len(points)
        self._publish_status()

    def _load_for_floor(self, floor: str, *, force: bool = False) -> None:
        self._floor = str(floor or "").strip()
        self._refresh_manifest_unlocked()
        if (
            not force
            and self._floor == self._loaded_floor
            and self._manifest_mtime_ns == self._loaded_manifest_mtime_ns
            and self._mapcloud_points > 0
            and self._mapground_points > 0
        ):
            return
        self._mapcloud_points = 0
        self._mapground_points = 0
        self._last_error = None
        self._last_code = "loading_map_assets"
        self._last_files = {"mapcloud": [], "mapground": []}
        self._keyframes = []
        self._keyframe_error = None
        self._pose_source = ""
        self._publish_empty()
        self._publish_status()
        if self._manifest_error:
            self._last_code = "map_asset_manifest_invalid"
            self._last_error = self._manifest_error
            self._publish_status()
            return
        try:
            cloud_paths, ground_paths = self._files_for_floor(self._floor)
            self._last_files = {
                "mapcloud": [str(path) for path in cloud_paths],
                "mapground": [str(path) for path in ground_paths],
            }
            if not cloud_paths or not ground_paths:
                if bool(self.get_parameter("field_test_fallback_enabled").value):
                    self._publish_field_test_fallback(code="field_test_flat_map_ready")
                    self._loaded_floor = self._floor
                    self._loaded_manifest_mtime_ns = self._manifest_mtime_ns
                    return
                self._last_code = "map_assets_not_configured"
                self._publish_status()
                return
            cloud_points = self._load_files(cloud_paths)
            ground_points = self._load_files(ground_paths)
            if not cloud_points or not ground_points:
                if bool(self.get_parameter("field_test_fallback_enabled").value):
                    self._publish_field_test_fallback(code="field_test_flat_map_ready")
                    self._loaded_floor = self._floor
                    self._loaded_manifest_mtime_ns = self._manifest_mtime_ns
                    return
                self._last_code = "map_assets_empty"
                self._publish_status()
                return
            stamp = self.get_clock().now().to_msg()
            self._mapcloud_pub.publish(
                _create_map_cloud(self._header(stamp), cloud_points)
            )
            self._mapground_pub.publish(
                _create_map_cloud(self._header(stamp), ground_points)
            )
            self._pg_mapcloud_pub.publish(
                _create_map_cloud(self._header(stamp), cloud_points)
            )
            self._pg_mapground_pub.publish(
                _create_map_cloud(self._header(stamp), ground_points)
            )
            self._load_keyframes(
                self._floor,
                cloud_paths,
                cloud_points,
                ground_points,
            )
            self._publish_keyframe_index(stamp)
            self._mapcloud_points = len(cloud_points)
            self._mapground_points = len(ground_points)
            self._last_code = (
                "map_assets_ready"
                if self._keyframes
                else "map_assets_ready_keyframes_unavailable"
            )
            self.get_logger().info(
                "DDDMR map assets ready floor=%s mapcloud=%d mapground=%d"
                % (self._floor or "<default>", len(cloud_points), len(ground_points))
            )
        except (OSError, ValueError, RuntimeError) as exc:
            if bool(self.get_parameter("field_test_fallback_enabled").value):
                self.get_logger().warning(
                    "DDDMR map assets falling back to temporary flat map: %s" % exc
                )
                self._publish_field_test_fallback(
                    code="field_test_flat_map_fallback",
                    error="%s:%s" % (type(exc).__name__, exc),
                )
                self._loaded_floor = self._floor
                self._loaded_manifest_mtime_ns = self._manifest_mtime_ns
                return
            self._last_code = "map_assets_load_failed"
            self._last_error = "%s:%s" % (type(exc).__name__, exc)
            self.get_logger().error("DDDMR map asset load failed: %s" % self._last_error)
        self._loaded_floor = self._floor
        self._loaded_manifest_mtime_ns = self._manifest_mtime_ns
        self._publish_status()

    def _on_floor(self, message: String) -> None:
        floor = str(message.data or "").strip()
        if floor != self._floor:
            self._load_for_floor(floor, force=True)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DddmrMapAssetServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except RuntimeError as exc:
            if "rcl_shutdown already called" not in str(exc):
                raise


if __name__ == "__main__":
    main()
