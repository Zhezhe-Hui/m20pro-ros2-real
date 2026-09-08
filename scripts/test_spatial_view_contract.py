#!/usr/bin/env python3
"""Contract tests for spatial_view_contract (3D 视图数据层接口化)."""

import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0, str(ROOT / "src" / "m20pro_cloud_bridge")
)

from m20pro_cloud_bridge.spatial_view_contract import (  # noqa: E402
    LIVE_SAMPLE_LIMIT,
    MAP_SAMPLE_LIMIT,
    live_cloud_payload,
    map_3d_payload,
    pointcloud_sample_payload,
    pointcloud_voxel_samples,
    pointcloud_xyz_samples,
)

NOW = 1720000001.0
FLOAT32 = 7
FLOAT64 = 8


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError("%s: expected %r, got %r" % (message, expected, actual))


def assert_true(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def xyz_fields(offsets=(0, 4, 8), datatype=FLOAT32):
    return [
        {"name": name, "datatype": datatype, "offset": offset}
        for name, offset in zip(("x", "y", "z"), offsets)
    ]


def pack_cloud(rows, datatype=FLOAT32, bigendian=False):
    endian = ">" if bigendian else "<"
    fmt = "f" if datatype == FLOAT32 else "d"
    point_size = 3 * struct.calcsize(fmt)
    data = b"".join(struct.pack(endian + fmt * 3, *row) for row in rows)
    return data, point_size


def test_decode_float32_roundtrip() -> None:
    rows = [[1.0, 2.0, 3.0], [4.25, -5.5, 6.125]]
    data, point_size = pack_cloud(rows)
    samples = pointcloud_xyz_samples(
        data, width=2, height=1, point_step=point_size, fields=xyz_fields(),
        max_points=10,
    )
    assert_equal(samples, [[1.0, 2.0, 3.0], [4.25, -5.5, 6.125]], "float32 xyz")


def test_decode_float64_bigendian() -> None:
    rows = [[0.5, -0.25, 1.75]]
    data, point_size = pack_cloud(rows, datatype=FLOAT64, bigendian=True)
    samples = pointcloud_xyz_samples(
        data, width=1, height=1, point_step=point_size,
        fields=xyz_fields(offsets=(0, 8, 16), datatype=FLOAT64),
        is_bigendian=True, max_points=10,
    )
    assert_equal(samples, [[0.5, -0.25, 1.75]], "float64 bigendian xyz")


def test_decode_stride_respects_max_points() -> None:
    rows = [[float(i), 0.0, 0.0] for i in range(5000)]
    data, point_size = pack_cloud(rows)
    samples = pointcloud_xyz_samples(
        data, width=5000, height=1, point_step=point_size, fields=xyz_fields(),
        max_points=100,
    )
    assert_true(len(samples) <= 100, "stride sample bounded by max_points")
    assert_true(len(samples) >= 90, "stride sample keeps coverage")
    assert_equal(samples[0], [0.0, 0.0, 0.0], "stride starts at first point")


def test_voxel_sample_bounded_and_uniform() -> None:
    rows = [[float(i) * 0.01, 0.0, 0.0] for i in range(5000)]
    data, point_size = pack_cloud(rows)
    samples = pointcloud_voxel_samples(
        data, width=5000, height=1, point_step=point_size, fields=xyz_fields(),
        max_points=100,
    )
    assert_true(len(samples) <= 100, "voxel sample bounded by max_points")
    xs = [point[0] for point in samples]
    assert_true(min(xs) <= 0.5 and max(xs) >= 49.0, "voxel sample spans full extent")


def test_voxel_keeps_interleaved_clusters_stride_loses() -> None:
    # Concatenated map clouds interleave scene regions; fixed-stride sampling
    # with an even step drops entire regions (the 2026-08-20 sparse-map root
    # cause). Voxel decimation must keep both clusters.
    rows = []
    for i in range(2000):
        if i % 2 == 0:
            rows.append([0.0, float(i) * 0.001, 0.0])
        else:
            rows.append([100.0, float(i) * 0.001, 0.0])
    data, point_size = pack_cloud(rows)
    stride = pointcloud_xyz_samples(
        data, width=2000, height=1, point_step=point_size, fields=xyz_fields(),
        max_points=50,
    )
    voxel = pointcloud_voxel_samples(
        data, width=2000, height=1, point_step=point_size, fields=xyz_fields(),
        max_points=50,
    )
    assert_equal({point[0] for point in stride}, {0.0}, "stride keeps one cluster only")
    assert_equal(
        sorted({point[0] for point in voxel}), [0.0, 100.0],
        "voxel keeps both clusters",
    )


def test_voxel_passthrough_small_clouds() -> None:
    rows = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    data, point_size = pack_cloud(rows)
    samples = pointcloud_voxel_samples(
        data, width=2, height=1, point_step=point_size, fields=xyz_fields(),
        max_points=10,
    )
    assert_equal(samples, [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], "small cloud passes through")


def test_pointcloud_sample_payload_voxel_flag() -> None:
    rows = []
    for i in range(2000):
        if i % 2 == 0:
            rows.append([0.0, float(i) * 0.001, 0.0])
        else:
            rows.append([100.0, float(i) * 0.001, 0.0])
    data, point_size = pack_cloud(rows)
    payload = pointcloud_sample_payload(
        topic="/mapcloud", width=2000, height=1, point_step=point_size,
        fields=xyz_fields(), data=data, max_points=50, voxel=True,
    )
    assert_equal(
        sorted({point[0] for point in payload["samples"]}), [0.0, 100.0],
        "payload voxel=True uses voxel decimation",
    )


def test_decode_filters_non_finite() -> None:
    rows = [[1.0, 2.0, 3.0], [float("nan"), 0.0, 0.0], [0.0, float("inf"), 0.0], [7.0, 8.0, 9.0]]
    data, point_size = pack_cloud(rows)
    samples = pointcloud_xyz_samples(
        data, width=4, height=1, point_step=point_size, fields=xyz_fields(),
        max_points=10,
    )
    assert_equal(samples, [[1.0, 2.0, 3.0], [7.0, 8.0, 9.0]], "non-finite filtered")


def test_decode_rejects_bad_shapes() -> None:
    data, point_size = pack_cloud([[1.0, 2.0, 3.0]])
    missing_z = [f for f in xyz_fields() if f["name"] != "z"]
    assert_equal(
        pointcloud_xyz_samples(data, width=1, height=1, point_step=point_size,
                               fields=missing_z, max_points=10),
        [], "missing z field",
    )
    int_fields = [{"name": n, "datatype": 1, "offset": o} for n, o in (("x", 0), ("y", 1), ("z", 2))]
    assert_equal(
        pointcloud_xyz_samples(data, width=1, height=1, point_step=point_size,
                               fields=int_fields, max_points=10),
        [], "non-float datatype",
    )
    assert_equal(
        pointcloud_xyz_samples(b"", width=1, height=1, point_step=point_size,
                               fields=xyz_fields(), max_points=10),
        [], "empty buffer",
    )


def test_pointcloud_sample_payload_ready_semantics() -> None:
    rows = [[1.0, 2.0, 3.0]]
    data, point_size = pack_cloud(rows)
    payload = pointcloud_sample_payload(
        topic="/mapcloud", width=1, height=1, point_step=point_size,
        fields=xyz_fields(), data=data, frame_id="map", now=NOW,
    )
    assert_equal(payload["ready"], True, "ready when points>0")
    assert_equal(payload["points"], 1, "points count")
    assert_equal(payload["topic"], "/mapcloud", "topic passthrough")
    assert_equal(payload["frame_id"], "map", "frame passthrough")
    assert_equal(payload["last_update"], NOW, "explicit now")
    assert_equal(payload["samples"], [[1.0, 2.0, 3.0]], "samples passthrough")

    empty = pointcloud_sample_payload(
        topic="/mapcloud", width=0, height=0, point_step=point_size,
        fields=xyz_fields(), data=b"", now=NOW,
    )
    assert_equal(empty["ready"], False, "not ready when empty")
    assert_equal(empty["samples"], [], "empty samples")


def test_pointcloud_sample_payload_map_limit() -> None:
    rows = [[float(i), 0.0, 0.0] for i in range(MAP_SAMPLE_LIMIT + 500)]
    data, point_size = pack_cloud(rows)
    payload = pointcloud_sample_payload(
        topic="/mapcloud", width=len(rows), height=1, point_step=point_size,
        fields=xyz_fields(), data=data, now=NOW,
    )
    assert_true(
        len(payload["samples"]) <= MAP_SAMPLE_LIMIT,
        "map sample bounded by MAP_SAMPLE_LIMIT",
    )


def test_live_cloud_payload_shape() -> None:
    samples = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    payload = live_cloud_payload(samples=samples, stamp_sec=12.5, frame_id="base_link", now=NOW)
    assert_equal(payload["last_update"], NOW, "live last_update")
    assert_equal(payload["stamp_sec"], 12.5, "stamp passthrough")
    assert_equal(payload["frame_id"], "base_link", "frame passthrough")
    assert_equal(payload["points"], 2, "points=len(samples)")
    assert_equal(payload["samples"], samples, "samples passthrough")
    assert_true(
        LIVE_SAMPLE_LIMIT == 350,
        "live default limit stays 350 for HTTP/canvas budget",
    )


def test_map_3d_payload_ready_requires_both() -> None:
    cloud = {"ready": True, "points": 120, "samples": [[1.0, 2.0, 3.0]], "frame_id": "map"}
    ground = {"ready": True, "points": 80, "samples": [[0.0, 0.0, 0.0]], "frame_id": "map"}
    payload = map_3d_payload(
        cloud, ground, mapcloud_topic="/mapcloud", mapground_topic="/mapground",
    )
    assert_equal(payload["ready"], True, "ready when both ready")
    assert_equal(payload["mapcloud_points"], 120, "mapcloud points")
    assert_equal(payload["mapground_points"], 80, "mapground points")
    assert_equal(payload["mapcloud_samples"], [[1.0, 2.0, 3.0]], "mapcloud samples")
    assert_equal(payload["mapcloud_frame"], "map", "mapcloud frame")
    assert_equal(payload["mapground_frame"], "map", "mapground frame")
    assert_equal(payload["mapcloud_topic"], "/mapcloud", "mapcloud topic")
    assert_equal(payload["mapground_topic"], "/mapground", "mapground topic")

    half = map_3d_payload(cloud, None)
    assert_equal(half["ready"], False, "ready requires mapground")
    assert_equal(half["mapcloud_ready"], True, "mapcloud still ready")
    assert_equal(half["mapground_ready"], False, "mapground missing")
    assert_equal(half["mapground_points"], 0, "mapground points default")
    assert_equal(half["mapground_samples"], [], "mapground samples default")
    assert_equal(half["mapground_frame"], "", "mapground frame default")

    garbage = map_3d_payload("bad", ["bad"])
    assert_equal(garbage["ready"], False, "non-dict inputs tolerated")
    assert_equal(garbage["mapcloud_points"], 0, "non-dict points default")


def test_node_wiring_keeps_state_and_new_endpoints() -> None:
    node_src = (
        ROOT / "src" / "m20pro_cloud_bridge" / "m20pro_cloud_bridge" / "web_dashboard_node.py"
    ).read_text(encoding="utf-8")
    for marker in (
        'from .spatial_view_contract import',
        '"/api/3d/spatial_map"',
        '"/api/3d/live_cloud"',
        '"map_3d": map_3d_payload(',
        'self._state["live_cloud"] = live_cloud_payload(',
    ):
        assert_true(marker in node_src, "node wiring contains %s" % marker)
    dashboard_src = (
        ROOT / "src" / "m20pro_cloud_bridge" / "m20pro_cloud_bridge" / "static" / "dashboard.js"
    ).read_text(encoding="utf-8")
    for marker in (
        "map_3d",
        "live_cloud",
    ):
        assert_true(marker in dashboard_src, "dashboard still consumes %s" % marker)


if __name__ == "__main__":
    test_decode_float32_roundtrip()
    test_decode_float64_bigendian()
    test_decode_stride_respects_max_points()
    test_voxel_sample_bounded_and_uniform()
    test_voxel_keeps_interleaved_clusters_stride_loses()
    test_voxel_passthrough_small_clouds()
    test_pointcloud_sample_payload_voxel_flag()
    test_decode_filters_non_finite()
    test_decode_rejects_bad_shapes()
    test_pointcloud_sample_payload_ready_semantics()
    test_pointcloud_sample_payload_map_limit()
    test_live_cloud_payload_shape()
    test_map_3d_payload_ready_requires_both()
    test_node_wiring_keeps_state_and_new_endpoints()
    print("spatial view contract tests passed")
