"""Turn a Lightning-LM map archive into the keyframe interface used by DDDMR MCL.

Lightning stores one global cloud plus a trajectory, while DDDMR MCL requests
per-keyframe clouds from a pose-graph server.  The conversion below preserves
the real Lightning map geometry: each keyframe is a radius-selected portion of
the global map expressed both in map and robot-base coordinates.  It does not
invent a flat map or substitute a second mapper.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from .dddmr_map_asset_io import _parse_pcd

Point = Tuple[float, float, float]
Pose = Tuple[float, float, float, float, float, float, float]
Keyframe = Dict[str, object]


def _normalized_quaternion(qx: float, qy: float, qz: float, qw: float) -> Tuple[float, float, float, float]:
    norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if not math.isfinite(norm) or norm < 1e-9:
        return (0.0, 0.0, 0.0, 1.0)
    return (qx / norm, qy / norm, qz / norm, qw / norm)


def load_lightning_path(path: Path) -> List[Pose]:
    """Load Lightning's ``timestamp x y z qx qy qz qw`` trajectory file."""
    poses: List[Pose] = []
    for raw_line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "timestamp" in line.lower():
            continue
        fields = line.split()
        if len(fields) < 8:
            continue
        try:
            _, x, y, z, qx, qy, qz, qw = (float(value) for value in fields[:8])
        except (TypeError, ValueError, OverflowError):
            continue
        if not all(math.isfinite(value) for value in (x, y, z, qx, qy, qz, qw)):
            continue
        qx, qy, qz, qw = _normalized_quaternion(qx, qy, qz, qw)
        poses.append((x, y, z, qx, qy, qz, qw))
    return poses


def load_pose_pcd(path: Path) -> List[Pose]:
    """Fallback for archives that retained ``poses.pcd`` but not ``path.txt``."""
    points = _parse_pcd(path, 0)
    poses: List[Pose] = []
    for index, (x, y, z) in enumerate(points):
        if index + 1 < len(points):
            next_x, next_y, _ = points[index + 1]
            yaw = math.atan2(next_y - y, next_x - x)
        elif poses:
            qx, qy, qz, qw = poses[-1][3:]
            poses.append((x, y, z, qx, qy, qz, qw))
            continue
        else:
            yaw = 0.0
        poses.append((x, y, z, 0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)))
    return poses


def select_key_poses(poses: Sequence[Pose], stride: int) -> List[Pose]:
    if not poses:
        return []
    step = max(1, int(stride))
    selected = list(poses[::step])
    if selected[-1] != poses[-1]:
        selected.append(poses[-1])
    return selected


def _spatial_index(points: Iterable[Point], cell_size: float) -> Dict[Tuple[int, int, int], List[Point]]:
    index: Dict[Tuple[int, int, int], List[Point]] = {}
    for point in points:
        key = tuple(int(math.floor(value / cell_size)) for value in point)
        index.setdefault(key, []).append(point)
    return index


def _nearby_points(
    index: Dict[Tuple[int, int, int], List[Point]],
    pose: Pose,
    radius: float,
    max_points: int,
) -> List[Point]:
    x, y, z = pose[:3]
    cell_size = radius
    center = tuple(int(math.floor(value / cell_size)) for value in (x, y, z))
    radius_squared = radius * radius
    candidates: List[Point] = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for point in index.get((center[0] + dx, center[1] + dy, center[2] + dz), []):
                    px, py, pz = point
                    if (px - x) ** 2 + (py - y) ** 2 + (pz - z) ** 2 <= radius_squared:
                        candidates.append(point)
    if max_points > 0 and len(candidates) > max_points:
        stride = max(1, math.ceil(len(candidates) / max_points))
        candidates = candidates[::stride][:max_points]
    return candidates


def _map_to_base(point: Point, pose: Pose) -> Point:
    """Apply the inverse of a map->base pose to one map-frame point."""
    px, py, pz, qx, qy, qz, qw = pose
    vx, vy, vz = point[0] - px, point[1] - py, point[2] - pz
    # Quaternion-vector multiplication with conjugate(q), equivalent to the
    # transpose rotation matrix without requiring numpy on the robot.
    ix = qw * vx - qy * vz + qz * vy
    iy = qw * vy - qz * vx + qx * vz
    iz = qw * vz - qx * vy + qy * vx
    iw = qx * vx + qy * vy + qz * vz
    return (
        ix * qw + iw * qx + iy * qz - iz * qy,
        iy * qw + iw * qy + iz * qx - ix * qz,
        iz * qw + iw * qz + ix * qy - iy * qx,
    )


def build_lightning_keyframes(
    map_points: Sequence[Point],
    ground_points: Sequence[Point],
    poses: Sequence[Pose],
    *,
    radius_m: float,
    max_points: int,
) -> List[Keyframe]:
    """Build the exact keyframe service payloads expected by ``mcl_3dl``."""
    radius = float(radius_m)
    if not math.isfinite(radius) or radius <= 0.0:
        raise ValueError("lightning_keyframe_radius_invalid")
    if not map_points or not ground_points or not poses:
        return []
    map_index = _spatial_index(map_points, radius)
    ground_index = _spatial_index(ground_points, radius)
    keyframes: List[Keyframe] = []
    for pose in poses:
        local_map = _nearby_points(map_index, pose, radius, max_points)
        local_ground = _nearby_points(ground_index, pose, radius, max_points)
        if not local_map or not local_ground:
            continue
        keyframes.append(
            {
                "pose": pose,
                "map": local_map,
                "ground": local_ground,
                "map_base": [_map_to_base(point, pose) for point in local_map],
                "ground_base": [_map_to_base(point, pose) for point in local_ground],
            }
        )
    return keyframes


__all__ = [
    "Keyframe",
    "Point",
    "Pose",
    "build_lightning_keyframes",
    "load_lightning_path",
    "load_pose_pcd",
    "select_key_poses",
]
