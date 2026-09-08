#!/usr/bin/env python3
"""Contract tests for raw front/rear lidar pairing and timestamps."""

from __future__ import annotations

import struct
import sys
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "m20pro_navigation"))

from m20pro_navigation.raw_lidar_merge_contract import (  # noqa: E402
    LidarPairBuffer,
    field_signature,
    merge_payloads_by_timestamp,
    point_count,
    validate_cloud_payload,
)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fields():
    return [
        SimpleNamespace(name="x", offset=0, datatype=7, count=1),
        SimpleNamespace(name="y", offset=4, datatype=7, count=1),
        SimpleNamespace(name="z", offset=8, datatype=7, count=1),
        SimpleNamespace(name="intensity", offset=12, datatype=7, count=1),
        SimpleNamespace(name="ring", offset=16, datatype=4, count=1),
        SimpleNamespace(name="timestamp", offset=18, datatype=8, count=1),
    ]


def cloud(stamp_ns: int):
    return SimpleNamespace(stamp_ns=stamp_ns)


def test_pairs_same_cycle_without_crossing() -> None:
    buffer = LidarPairBuffer(max_queue=4, sync_window_s=0.02)
    assert_true(buffer.add("front", 1_000_000_000, cloud(1_000_000_000)) == [], "front waits")
    assert_true(buffer.add("front", 1_100_000_000, cloud(1_100_000_000)) == [], "second front waits")
    pairs = buffer.add("rear", 1_101_000_000, cloud(1_101_000_000))
    assert_true(len(pairs) == 1, "nearest same-cycle frame pairs")
    assert_true(pairs[0].front.stamp_ns == 1_100_000_000, "does not pair older cycle")
    assert_true(pairs[0].delta_ns == 1_000_000, "pair delta is retained")

    buffer.add("rear", 1_300_000_000, cloud(1_300_000_000))
    assert_true(buffer.dropped_unmatched >= 1, "unmatchable old frame is dropped")


def test_output_stamp_is_monotonic() -> None:
    buffer = LidarPairBuffer(max_queue=4, sync_window_s=0.02)
    first = buffer.add("front", 2_000_000_000, cloud(2_000_000_000))
    assert_true(first == [], "first front waits")
    assert_true(len(buffer.add("rear", 2_001_000_000, cloud(2_001_000_000))) == 1, "first pair")
    assert_true(buffer.add("front", 1_900_000_000, cloud(1_900_000_000)) == [], "late front rejected")
    assert_true(buffer.dropped_stale == 1, "late frame counted")


def test_payload_contract() -> None:
    point_step = 26
    point_data = b"".join(
        struct.pack("<ffffH", 1.0, 2.0, 3.0, 4.0, 7)
        + struct.pack("<d", 10.005 + index * 0.001)
        for index in range(3)
    )
    message_fields = fields()
    assert_true(point_count(SimpleNamespace(width=1, height=3)) == 3, "width*height count")
    assert_true(validate_cloud_payload(
        point_data, 1, 3, point_step, message_fields, False, 10.0
    ) is None, "valid XYZIRT payload")
    assert_true(validate_cloud_payload(
        point_data[:-1], 1, 3, point_step, message_fields, False, 10.0
    ) == "truncated_payload", "truncated payload rejected")
    invalid_time = bytearray(point_data)
    invalid_time[18:26] = struct.pack("<d", 10.5)
    assert_true(validate_cloud_payload(
        bytes(invalid_time), 1, 3, point_step, message_fields, False, 10.0
    ) == "point_timestamp_span_exceeded", "bad scan span rejected")
    assert_true(len(field_signature(message_fields)) == 6, "layout signature is complete")


def test_merge_restores_global_point_time_order() -> None:
    point_step = 26

    def payload(points):
        return b"".join(
            struct.pack("<ffffH", float(index), 0.0, 0.0, 1.0, 1)
            + struct.pack("<d", timestamp)
            for index, timestamp in points
        )

    merged = merge_payloads_by_timestamp(
        payload([(1, 10.10), (2, 10.20)]),
        payload([(3, 10.05), (4, 10.15)]),
        point_step,
        18,
        False,
    )
    xs = [
        struct.unpack_from("<f", merged, index * point_step)[0]
        for index in range(4)
    ]
    timestamps = [
        struct.unpack_from("<d", merged, index * point_step + 18)[0]
        for index in range(4)
    ]
    assert_true(xs == [3.0, 1.0, 4.0, 2.0], "points are globally time ordered")
    assert_true(timestamps == sorted(timestamps), "timestamps are monotonic")


def main() -> int:
    tests = [
        test_pairs_same_cycle_without_crossing,
        test_output_stamp_is_monotonic,
        test_payload_contract,
        test_merge_restores_global_point_time_order,
    ]
    for test in tests:
        test()
        print("ok - %s" % test.__name__)
    print("PASS raw_lidar_merge contract (%d tests)" % len(tests))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
