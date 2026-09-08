"""3D 空间视图数据合同。

把 3D 视口用到的点云抽样与 payload 组装规则收敛成纯函数：

- `pointcloud_xyz_samples`：PointCloud2 原始缓冲 → xyz 抽样（只保留有限点）。
- `pointcloud_sample_payload`：mapcloud / mapground 抽样 payload。
- `live_cloud_payload`：实时障碍点云抽样 payload。
- `map_3d_payload`：`/api/state` 的 `navigation_backend.map_3d` 段，
  也是 `GET /api/3d/spatial_map` 的响应主体。

Web 节点只负责 ROS 订阅与 HTTP 路由；字段形状、抽稀上限和 ready 语义
由本模块与 `scripts/test_spatial_view_contract.py` 锁定。前端 3D 视图
（dashboard.js buildSpatialMap / drawLiveCloud3d）只消费这些字段。
"""

from __future__ import annotations

import math
import struct
import time
from typing import Any, Dict, Iterable, List, Optional

# sensor_msgs/PointField 中可解码的浮点类型。
FLOAT_DATATYPES = {7: "f", 8: "d"}

# mapcloud / mapground 静态地图抽样上限（HTTP 边界保护）。
MAP_SAMPLE_LIMIT = 1800
# 实时点云默认抽样上限（可被 live_cloud_max_points 参数覆盖）。
LIVE_SAMPLE_LIMIT = 350


def _field_attr(field: Any, name: str) -> Any:
    if isinstance(field, dict):
        return field.get(name)
    return getattr(field, name, None)


def _xyz_specs(fields: Iterable[Any]) -> List[tuple]:
    """返回 [(offset, struct_fmt)]；缺 x/y/z 或类型不支持时返回空表。"""
    by_name = {}
    for field in fields or []:
        field_name = _field_attr(field, "name")
        if field_name is not None:
            by_name[str(field_name)] = field
    specs = []
    for axis in ("x", "y", "z"):
        field = by_name.get(axis)
        if field is None:
            return []
        fmt = FLOAT_DATATYPES.get(int(_field_attr(field, "datatype") or 0))
        if not fmt:
            return []
        specs.append((int(_field_attr(field, "offset") or 0), fmt))
    return specs


def pointcloud_xyz_samples(
    data: bytes,
    *,
    width: int,
    height: int,
    point_step: int,
    fields: Iterable[Any],
    is_bigendian: bool = False,
    max_points: int,
    round_digits: int = 3,
) -> List[List[float]]:
    """对 PointCloud2 原始缓冲做有界 xyz 抽样。

    采用 ceil 步长跨点采样，输出点数不超过 `max_points`，
    只保留三个分量均有限的点，坐标按 `round_digits` 位四舍五入。
    """
    try:
        total = min(
            max(0, int(width)) * max(0, int(height)),
            len(bytes(data or b"")) // max(1, int(point_step)),
        )
        specs = _xyz_specs(fields)
        if not specs or total <= 0 or max_points < 1:
            return []
        endian = ">" if is_bigendian else "<"
        raw = bytes(data or b"")
        stride = max(1, int(point_step))
        step = max(1, int(math.ceil(total / max(1, int(max_points)))))
        samples: List[List[float]] = []
        for index in range(0, total, step):
            base = index * stride
            values = [
                struct.unpack_from(endian + fmt, raw, base + offset)[0]
                for offset, fmt in specs
            ]
            if all(math.isfinite(float(value)) for value in values):
                samples.append([round(float(value), round_digits) for value in values])
                if len(samples) >= max_points:
                    break
        return samples
    except (AttributeError, IndexError, TypeError, ValueError, struct.error):
        return []


def pointcloud_xyz_array(
    data: bytes,
    *,
    width: int,
    height: int,
    point_step: int,
    fields: Iterable[Any],
    is_bigendian: bool = False,
    max_points: int = 0,
):
    """Full-resolution xyz decode with a numpy fast path.

    Returns an (N,3) float32 array of finite points.  Large multi-floor maps
    (hundreds of thousands of points) make the pure-python stride loop
    prohibitively slow, so server-side floor detection / picking uses this.
    """
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy ships with the ROS image
        points = _decode_finite_xyz(
            data,
            total=min(max(0, int(width)) * max(0, int(height)),
                      len(bytes(data or b"")) // max(1, int(point_step))),
            point_step=point_step,
            fields=fields,
            is_bigendian=is_bigendian,
        )
        arr = np.asarray(points, dtype=np.float32).reshape(-1, 3) if points else np.zeros((0, 3), dtype=np.float32)
        if max_points and len(arr) > max_points:
            arr = arr[: int(max_points)]
        return arr
    specs = _xyz_specs(fields)
    raw = bytes(data or b"")
    stride = max(1, int(point_step))
    total = min(max(0, int(width)) * max(0, int(height)), len(raw) // stride)
    if not specs or total <= 0:
        return np.zeros((0, 3), dtype=np.float32)
    byteorder = ">" if is_bigendian else "<"
    buf = np.frombuffer(raw, dtype=np.uint8, count=total * stride).reshape(total, stride)
    cols = []
    for offset, fmt in specs:
        itemsize = 4 if fmt == "f" else 8
        dtype = np.dtype(byteorder + ("f4" if fmt == "f" else "f8"))
        cols.append(buf[:, offset:offset + itemsize].copy().view(dtype).reshape(total))
    arr = np.stack(cols, axis=1).astype(np.float32, copy=False)
    finite = np.isfinite(arr).all(axis=1)
    arr = arr[finite]
    if max_points and len(arr) > int(max_points):
        arr = arr[: int(max_points)]
    return arr


def _decode_finite_xyz(
    data: bytes,
    *,
    total: int,
    point_step: int,
    fields: Iterable[Any],
    is_bigendian: bool,
) -> List[tuple]:
    endian = ">" if is_bigendian else "<"
    raw = bytes(data or b"")
    specs = _xyz_specs(fields)
    if not specs or total <= 0:
        return []
    stride = max(1, int(point_step))
    points: List[tuple] = []
    for index in range(total):
        base = index * stride
        values = [
            struct.unpack_from(endian + fmt, raw, base + offset)[0]
            for offset, fmt in specs
        ]
        if all(math.isfinite(float(value)) for value in values):
            points.append(tuple(float(value) for value in values))
    return points


def _voxel_cell_count(points: List[tuple], voxel_size: float) -> int:
    seen = set()
    inv = 1.0 / max(voxel_size, 1e-9)
    for point in points:
        seen.add(
            (
                int(math.floor(point[0] * inv)),
                int(math.floor(point[1] * inv)),
                int(math.floor(point[2] * inv)),
            )
        )
    return len(seen)


def pointcloud_voxel_samples(
    data: bytes,
    *,
    width: int,
    height: int,
    point_step: int,
    fields: Iterable[Any],
    is_bigendian: bool = False,
    max_points: int,
    round_digits: int = 3,
) -> List[List[float]]:
    """对 PointCloud2 原始缓冲做体素网格有界抽稀。

    先解码全部有限 xyz 点，再二分找到满足 `max_points` 的最细体素边长，
    每个体素保留首个点。相比固定步长跨点采样，体素抽稀保持空间均匀覆盖：
    步长采样在拼接顺序的点云上会整段跳过场景区域，前端 3D 视图因此只剩
    一团乱点（2026-08-20 建图稀疏根因）。
    """
    try:
        total = min(
            max(0, int(width)) * max(0, int(height)),
            len(bytes(data or b"")) // max(1, int(point_step)),
        )
        if total <= 0 or max_points < 1:
            return []
        points = _decode_finite_xyz(
            data,
            total=total,
            point_step=point_step,
            fields=fields,
            is_bigendian=is_bigendian,
        )
        if not points:
            return []
        if len(points) <= max_points:
            return [[round(value, round_digits) for value in point] for point in points]
        extent = 0.0
        for axis in range(3):
            axis_values = [point[axis] for point in points]
            extent = max(extent, max(axis_values) - min(axis_values))
        lo = 0.02
        hi = max(extent, lo)
        if _voxel_cell_count(points, lo) <= max_points:
            voxel_size = lo
        else:
            voxel_size = hi
            for _ in range(24):
                mid = (lo + hi) * 0.5
                if _voxel_cell_count(points, mid) <= max_points:
                    voxel_size = mid
                    hi = mid
                else:
                    lo = mid
                if hi - lo < 1e-4:
                    break
        inv = 1.0 / max(voxel_size, 1e-9)
        seen = set()
        samples: List[List[float]] = []
        for point in points:
            key = (
                int(math.floor(point[0] * inv)),
                int(math.floor(point[1] * inv)),
                int(math.floor(point[2] * inv)),
            )
            if key in seen:
                continue
            seen.add(key)
            samples.append([round(value, round_digits) for value in point])
        if len(samples) > max_points:
            step = max(1, int(math.ceil(len(samples) / max(1, int(max_points)))))
            samples = samples[::step][:max_points]
        return samples
    except (AttributeError, IndexError, TypeError, ValueError, struct.error):
        return []


def pointcloud_sample_payload(
    *,
    topic: str,
    width: int,
    height: int,
    point_step: int,
    fields: Iterable[Any],
    data: bytes,
    is_bigendian: bool = False,
    frame_id: str = "",
    max_points: int = MAP_SAMPLE_LIMIT,
    voxel: bool = False,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """mapcloud / mapground 抽样 payload（喂给 map_3d_payload）。

    `voxel=True` 使用体素网格抽稀（静态地图默认），保持空间结构；
    `voxel=False` 保留固定步长采样（兼容旧调用）。
    """
    width = max(0, int(width or 0))
    height = max(0, int(height or 0))
    points = width * height
    sampler = pointcloud_voxel_samples if voxel else pointcloud_xyz_samples
    samples = sampler(
        data,
        width=width,
        height=height,
        point_step=point_step,
        fields=fields,
        is_bigendian=is_bigendian,
        max_points=max_points,
    )
    return {
        "last_update": time.time() if now is None else float(now),
        "ready": points > 0,
        "topic": str(topic or ""),
        "frame_id": str(frame_id or ""),
        "points": points,
        "width": width,
        "height": height,
        "samples": samples,
    }


def live_cloud_payload(
    *,
    samples: List[List[float]],
    stamp_sec: float = 0.0,
    frame_id: str = "",
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """实时障碍点云 payload（/api/state.live_cloud 与 /api/3d/live_cloud 主体）。"""
    samples = list(samples or [])
    return {
        "last_update": time.time() if now is None else float(now),
        "stamp_sec": float(stamp_sec or 0.0),
        "frame_id": str(frame_id or ""),
        "points": len(samples),
        "samples": samples,
    }


def map_3d_payload(
    mapcloud: Optional[Dict[str, Any]],
    mapground: Optional[Dict[str, Any]],
    *,
    mapcloud_topic: str = "",
    mapground_topic: str = "",
) -> Dict[str, Any]:
    """组装 map_3d 段。

    `ready` 当且仅当 mapcloud 与 mapground 同时 ready；
    与 `/api/state` 的 `navigation_backend.map_3d` 字段完全一致。
    """
    mapcloud = mapcloud if isinstance(mapcloud, dict) else None
    mapground = mapground if isinstance(mapground, dict) else None
    mapcloud_ready = bool(mapcloud and mapcloud.get("ready"))
    mapground_ready = bool(mapground and mapground.get("ready"))
    return {
        "ready": bool(mapcloud_ready and mapground_ready),
        "mapcloud_ready": mapcloud_ready,
        "mapground_ready": mapground_ready,
        "mapcloud_points": int((mapcloud or {}).get("points") or 0),
        "mapcloud_samples": list((mapcloud or {}).get("samples") or []),
        "mapground_points": int((mapground or {}).get("points") or 0),
        "mapground_samples": list((mapground or {}).get("samples") or []),
        "mapcloud_frame": str((mapcloud or {}).get("frame_id") or ""),
        "mapground_frame": str((mapground or {}).get("frame_id") or ""),
        "mapcloud_topic": str(mapcloud_topic or ""),
        "mapground_topic": str(mapground_topic or ""),
    }
