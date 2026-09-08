#!/usr/bin/env python3
"""Contract tests for dense_cloud_delevel (vendor dense stream 姿态补偿根治).

Field evidence (2026-08-20, 见 m20pro日志.md): /LIDAR/POINTS interleaves
merged (attitude-leveled) + front/rear single-lidar frames; Lightning needs
one rigid stream.  These tests pin the restore contract.
"""

import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "m20pro_navigation"))

from m20pro_navigation.dense_cloud_delevel import (  # noqa: E402
    BACK_HEMISPHERE_X_MAX,
    FRAME_EMPTY,
    FRAME_FRONT_ONLY,
    FRAME_MERGED,
    FRAME_REAR_ONLY,
    FRONT_HEMISPHERE_X_MIN,
    ImuAttitudeTracker,
    apply_matrix_to_xyz_buffer,
    classify_hemispheres,
    delevel_matrix,
    roll_pitch_from_accel,
    roll_pitch_from_accel_samples,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def assert_close(actual, expected, tolerance, message):
    if abs(actual - expected) > tolerance:
        raise AssertionError("%s: %r not within %r of %r" % (message, actual, tolerance, expected))


def test_roll_pitch_from_accel():
    # Static M20 reading: gravity on +z, slight nose-down pitch.
    roll, pitch = roll_pitch_from_accel(-0.2465, -0.0217, 9.8302)
    assert_close(math.degrees(pitch), 1.44, 0.05, "pitch from static accel")
    assert_close(math.degrees(roll), -0.13, 0.05, "roll from static accel")
    # Pure roll: gravity leaks into +y.
    roll, pitch = roll_pitch_from_accel(0.0, 9.81 * math.sin(math.radians(5)),
                                        9.81 * math.cos(math.radians(5)))
    assert_close(math.degrees(roll), 5.0, 1e-6, "pure roll recovery")
    assert_close(pitch, 0.0, 1e-9, "no pitch under pure roll")


def test_sample_filtering_rejects_gait_spikes():
    samples = [(-0.25, -0.02, 9.83)] * 20 + [(30.0, 0.0, 0.0)] * 5
    estimate = roll_pitch_from_accel_samples(samples)
    assert_true(estimate is not None, "enough clean samples survive")
    roll, pitch, used, total = estimate
    assert_true(total == 25 and used == 20, "spikes rejected by norm gate")
    assert_close(math.degrees(pitch), 1.46, 0.05, "attitude unaffected by spikes")
    few = roll_pitch_from_accel_samples([(30.0, 0.0, 0.0)] * 10)
    assert_true(few is None, "all-rejected window returns None")


def test_classify_hemispheres():
    assert_true(classify_hemispheres(26000, 26000, 53000) == FRAME_MERGED, "both hemispheres")
    assert_true(classify_hemispheres(28000, 2, 28338) == FRAME_FRONT_ONLY, "front only")
    assert_true(classify_hemispheres(1, 71000, 71909) == FRAME_REAR_ONLY, "rear only")
    assert_true(classify_hemispheres(0, 0, 0) == FRAME_EMPTY, "empty frame")
    assert_true(classify_hemispheres(10, 10, 50000) == FRAME_EMPTY, "depleted frame")


def test_delevel_matrix_restores_body_floor_normal():
    # A leveled frame sees the floor normal as (0,0,1).  After undoing the
    # leveling with the body attitude, the normal must equal the body-frame
    # gravity direction (-sin pitch, cos pitch sin roll, cos pitch cos roll),
    # matching the rigid front-frame ground fits (a=+tan pitch, b=-tan roll).
    roll = math.radians(0.156)
    pitch = math.radians(1.459)
    mat = delevel_matrix(roll, pitch)
    # R @ (0,0,1) is the third column: row-major indices 2, 5, 8.
    nx = mat[2]
    ny = mat[5]
    nz = mat[8]
    assert_close(nx, -math.sin(pitch), 1e-9, "normal x")
    assert_close(ny, math.cos(pitch) * math.sin(roll), 1e-9, "normal y")
    assert_close(nz, math.cos(pitch) * math.cos(roll), 1e-9, "normal z")
    # Leveling then de-leveling is identity.
    import numpy
    r = numpy.asarray(mat, dtype=numpy.float64).reshape(3, 3)
    level = numpy.linalg.inv(r)
    assert_true(numpy.allclose(r @ level, numpy.eye(3)), "inverse round trip")


def test_apply_matrix_round_trip_point_step_26():
    import numpy
    point_step = 26
    points = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
              (2.5, -1.3, 0.7), (0.0, 0.0, 0.0)]
    buf = bytearray()
    for x, y, z in points:
        buf += struct.pack("<fff", x, y, z)
        buf += b"\x00" * (point_step - 12)
    roll, pitch = math.radians(2.0), math.radians(-3.0)
    forward = delevel_matrix(roll, pitch)
    # Delevel = Rx(-roll) Ry(-pitch); its inverse is Ry(pitch) Rx(roll) --
    # build it explicitly (rotations do not commute).
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    inverse = (
        cp, sr * sp, cr * sp,
        0.0, cr, -sr,
        -sp, sr * cp, cr * cp,
    )
    once = apply_matrix_to_xyz_buffer(bytes(buf), point_step, forward)
    twice = apply_matrix_to_xyz_buffer(once, point_step, inverse)
    back = numpy.frombuffer(bytearray(twice), dtype=numpy.uint8).reshape(-1, point_step)
    xyz_back = numpy.frombuffer(back[:, 0:12].tobytes(), dtype=numpy.float32).reshape(-1, 3)
    origin = numpy.asarray(points, dtype=numpy.float32)
    assert_true(bool(numpy.allclose(xyz_back, origin, atol=1e-6)),
                "rotation round trip restores coordinates")
    flat = numpy.frombuffer(bytearray(once), dtype=numpy.uint8).reshape(-1, point_step)
    xyz = numpy.frombuffer(flat[:, 0:12].tobytes(), dtype=numpy.float32).reshape(-1, 3)
    # x-axis point must have moved (rotation actually applied).
    assert_true(abs(xyz[0][0] - 1.0) > 1e-3 or abs(xyz[0][2]) > 1e-3,
                "rotation changed geometry")
    # zero point stays zero; trailing bytes untouched
    assert_true(tuple(xyz[4]) == (0.0, 0.0, 0.0), "invalid return untouched")
    assert_true(once[12:26] == buf[12:26], "non-xyz bytes preserved")


def test_tracker_stamp_lookup():
    tracker = ImuAttitudeTracker()
    base = 1000.0
    for i in range(200):  # 200 Hz for one second, static nose-down attitude
        tracker.add(base + i * 0.005, -0.2465, -0.0217, 9.8302)
    estimate = tracker.roll_pitch_at(base + 0.5, window_s=0.3, lookahead_s=0.05)
    assert_true(estimate is not None, "window has samples")
    roll, pitch, used = estimate
    assert_close(math.degrees(pitch), 1.44, 0.05, "tracker pitch")
    assert_true(used >= 10, "min samples honored")
    # Far future stamp: no samples in window, but skew fallback within 0.5s
    # of the newest sample must not apply -> None (chain must fail closed).
    assert_true(tracker.roll_pitch_at(base + 10.0) is None, "stale window rejected")
    # Clock skew: stamp slightly ahead of latest IMU still resolves.
    estimate = tracker.roll_pitch_at(base + 1.0 + 0.2, window_s=0.3, lookahead_s=0.05)
    assert_true(estimate is not None, "skew fallback resolves near-future stamp")


def test_tracker_dynamic_gait_rejection():
    tracker = ImuAttitudeTracker()
    base = 2000.0
    # 150 Hz: alternate clean static samples with hard gait spikes.
    for i in range(150):
        t = base + i / 150.0
        if i % 3 == 0:
            tracker.add(t, 25.0, -12.0, 3.0)  # norm >> gravity
        else:
            tracker.add(t, -0.2465, -0.0217, 9.8302)
    estimate = tracker.roll_pitch_at(base + 0.5, window_s=0.3, lookahead_s=0.05)
    assert_true(estimate is not None, "clean samples survive gait")
    roll, pitch, used = estimate
    assert_close(math.degrees(pitch), 1.44, 0.1, "gait spikes excluded")


def main():
    tests = [
        test_roll_pitch_from_accel,
        test_sample_filtering_rejects_gait_spikes,
        test_classify_hemispheres,
        test_delevel_matrix_restores_body_floor_normal,
        test_apply_matrix_round_trip_point_step_26,
        test_tracker_stamp_lookup,
        test_tracker_dynamic_gait_rejection,
    ]
    for test in tests:
        test()
        print("ok - %s" % test.__name__)
    print("PASS dense_cloud_delevel contract (%d tests)" % len(tests))


if __name__ == "__main__":
    main()
