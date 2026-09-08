"""Attitude de-leveling contract for the M20 vendor dense cloud stream.

Root cause (field-verified 2026-08-20, see m20pro日志.md): the vendor
rsdriver publishes three interleaved frame families on /LIDAR/POINTS, all
claiming frame_id=lidar_link:

  merged   front+rear stitched cloud (~10 Hz) -- attitude-leveled by the
           driver (per-frame ground tilt ~0.5 deg while the body pitch is
           1.47 deg), i.e. the driver applies dynamic attitude compensation.
           The development manual only documents static extrinsics.
  front    front lidar only (~1 Hz)  -- rigid in body frame (ground tilt
           tracks body attitude 1:1).
  rear     rear lidar only (~0.5 Hz) -- also leveled, single sensor.

Lightning-LM assumes ONE rigid sensor plus IMU motion deskew
(vendor/lightning_lm_deep_robotics/src/core/lio/imu_processing.hpp).
Feeding it leveled frames makes its deskew double-compensate (vertical
streaks while walking), and the interleaved single-lidar frames break the
fixed-extrinsic assumption.  This module restores the contract:

  1. classify each frame by its x-extent geometry (front lidar sits at
     x=+0.32028, rear at x=-0.32028 in base_link, manual "静态外参");
  2. drop single-lidar frames (their content is contained in merged ones);
  3. rotate merged frames back into the body frame with the accelerometer
     roll/pitch at the frame stamp, undoing the driver leveling so the
     mapper deskew sees rigid geometry.

Pure contract module (no ROS imports) so contract tests run anywhere.
numpy is only required for the bulk byte-buffer transform.
"""

import math
from collections import deque
from typing import Iterable, List, Optional, Sequence, Tuple

# Gravity-norm gate for accelerometer samples: walking gait spikes and
# sensor dropouts are rejected before averaging.
ACCEL_NORM_MIN = 8.0
ACCEL_NORM_MAX = 11.8

# Front/rear lidar x positions in base_link (manual: 静态外参 ±0.32028).
# A point further forward than +0.25 can only come from the front lidar's
# hemisphere; further back than -0.25 only from the rear hemisphere.
FRONT_HEMISPHERE_X_MIN = 0.25
BACK_HEMISPHERE_X_MAX = -0.25

# A frame counts as containing a hemisphere when at least this fraction of
# its points lie in it (merged frames carry tens of thousands of points, so
# even a depleted hemisphere clears 0.5% easily; single-lidar frames have
# essentially zero points on the far side).
HEMISPHERE_MIN_FRACTION = 0.005

FRAME_MERGED = "merged"
FRAME_FRONT_ONLY = "front_only"
FRAME_REAR_ONLY = "rear_only"
FRAME_EMPTY = "empty"


def roll_pitch_from_accel(
    ax: float, ay: float, az: float
) -> Tuple[float, float]:
    """Body roll/pitch (rad) from a base_link-aligned accelerometer.

    M20 /IMU is already axis-mapped to base_link (manual m20pro_manual_imu.md);
    at rest it reads ~+9.81 m/s^2 on z.  With R = Ry(pitch) Rx(roll) the
    body-to-world rotation, specific force is g*(-sin(pitch),
    cos(pitch) sin(roll), cos(pitch) cos(roll)).
    """
    roll = math.atan2(ay, az)
    pitch = math.atan2(-ax, math.sqrt(ay * ay + az * az))
    return roll, pitch


def roll_pitch_from_accel_samples(
    samples: Iterable[Sequence[float]],
    norm_min: float = ACCEL_NORM_MIN,
    norm_max: float = ACCEL_NORM_MAX,
    min_samples: int = 3,
) -> Optional[Tuple[float, float, int, int]]:
    """Average attitude over raw accel triplets, rejecting dynamic outliers.

    Returns (roll, pitch, used_count, total_count) or None when too few
    samples survive the gravity-norm gate.
    """
    sum_ax = sum_ay = sum_az = 0.0
    used = 0
    total = 0
    for sample in samples:
        total += 1
        ax, ay, az = float(sample[0]), float(sample[1]), float(sample[2])
        norm = math.sqrt(ax * ax + ay * ay + az * az)
        if not (norm_min <= norm <= norm_max):
            continue
        sum_ax += ax
        sum_ay += ay
        sum_az += az
        used += 1
    if used < min_samples:
        return None
    roll, pitch = roll_pitch_from_accel(sum_ax / used, sum_ay / used, sum_az / used)
    return roll, pitch, used, total


def classify_hemispheres(
    front_count: int, back_count: int, total: int,
    min_fraction: float = HEMISPHERE_MIN_FRACTION,
) -> str:
    """Classify a frame from how many points sit in each lidar hemisphere."""
    if total <= 0:
        return FRAME_EMPTY
    has_front = front_count >= total * min_fraction
    has_back = back_count >= total * min_fraction
    if has_front and has_back:
        return FRAME_MERGED
    if has_front:
        return FRAME_FRONT_ONLY
    if has_back:
        return FRAME_REAR_ONLY
    return FRAME_EMPTY


def delevel_matrix(roll: float, pitch: float) -> Tuple[float, ...]:
    """Row-major 3x3 rotation undoing driver leveling.

    Leveling applied p_lvl = Ry(pitch) Rx(roll) p_body; the inverse is
    Rx(-roll) Ry(-pitch).  Verified against the rigid front frames: a floor
    normal (0,0,1) in the leveled frame maps to (-sin pitch, cos pitch
    sin roll, cos pitch cos roll), i.e. plane slopes a=+tan(pitch),
    b=-tan(roll) -- matching the measured front-frame ground plane.
    """
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    # Rx(-roll) @ Ry(-pitch)
    return (
        cp, 0.0, -sp,
        sr * sp, cr, sr * cp,
        cr * sp, -sr, cr * cp,
    )


def apply_matrix_to_xyz_buffer(
    data: bytes, point_step: int, matrix: Sequence[float]
) -> bytes:
    """Rotate xyz (offset 0, three float32) of every point in-place.

    point_step need not divide 4 (vendor dense frames use 26); the xyz
    prefix of every point is contiguous little-endian float32.  Invalid
    returns (0,0,0 / NaN) stay where they are under a linear map.
    Returns new bytes; the input buffer is not modified.
    """
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - runtime hosts have it
        raise RuntimeError("numpy is required for dense cloud de-leveling") from exc
    if point_step < 12:
        raise ValueError("point_step too small for xyz prefix: %d" % point_step)
    buf = bytearray(data)
    flat = numpy.frombuffer(buf, dtype=numpy.uint8)
    if flat.size % point_step != 0:
        raise ValueError("buffer size %d not a multiple of point_step %d" % (flat.size, point_step))
    points = flat.reshape(-1, point_step)
    xyz = numpy.frombuffer(points[:, 0:12].tobytes(), dtype=numpy.float32).reshape(-1, 3)
    rot = numpy.asarray(matrix, dtype=numpy.float64).reshape(3, 3)
    rotated = xyz.astype(numpy.float64) @ rot.T
    points[:, 0:12] = rotated.astype("<f4").view(numpy.uint8).reshape(-1, 12)
    return bytes(buf)


class ImuAttitudeTracker:
    """Rolling window of raw IMU samples -> roll/pitch at any timestamp."""

    def __init__(self, capacity: int = 1600) -> None:
        self._samples: deque = deque(maxlen=int(capacity))

    def add(self, stamp: float, ax: float, ay: float, az: float) -> None:
        self._samples.append((float(stamp), float(ax), float(ay), float(az)))

    def __len__(self) -> int:
        return len(self._samples)

    def latest_stamp(self) -> Optional[float]:
        return self._samples[-1][0] if self._samples else None

    def roll_pitch_at(
        self,
        stamp: float,
        window_s: float = 0.30,
        lookahead_s: float = 0.05,
        min_samples: int = 10,
        skew_fallback_s: float = 0.5,
    ) -> Optional[Tuple[float, float, int]]:
        """Attitude at `stamp`: mean over [stamp-window, stamp+lookahead].

        Returns (roll, pitch, used_samples) or None.  If the window is empty
        but recent samples exist within skew_fallback_s (clock skew between
        the lidar stamp domain and the IMU), the newest window ending at the
        latest sample is used instead of failing the whole chain.
        """
        if not self._samples:
            return None
        lo = stamp - float(window_s)
        hi = stamp + float(lookahead_s)
        picked = [s[1:] for s in self._samples if lo <= s[0] <= hi]
        if len(picked) < min_samples:
            latest = self._samples[-1][0]
            if 0 <= stamp - latest <= skew_fallback_s:
                picked = [s[1:] for s in self._samples if latest - window_s <= s[0] <= latest]
        if not picked:
            return None
        estimate = roll_pitch_from_accel_samples(picked, min_samples=min_samples)
        if estimate is None:
            return None
        return estimate[0], estimate[1], estimate[2]
