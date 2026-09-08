#!/usr/bin/env python3
"""Offline geometry checks for the Lightning-LM to DDDMR MCL adapter."""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/m20pro_navigation"))

from m20pro_navigation.lightning_mcl_map_adapter import (  # noqa: E402
    build_lightning_keyframes,
    load_lightning_path,
    load_pose_pcd,
    select_key_poses,
)


def _write_ascii_pcd(path: Path, rows: list[tuple[float, float, float]]) -> None:
    payload = "\n".join("%.3f %.3f %.3f" % row for row in rows)
    path.write_text(
        "\n".join(
            (
                "VERSION .7",
                "FIELDS x y z",
                "SIZE 4 4 4",
                "TYPE F F F",
                "COUNT 1 1 1",
                "WIDTH %d" % len(rows),
                "HEIGHT 1",
                "POINTS %d" % len(rows),
                "DATA ascii",
                payload,
                "",
            )
        ),
        encoding="ascii",
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="m20pro_lightning_mcl_") as tmp:
        root = Path(tmp)
        path_file = root / "path.txt"
        path_file.write_text(
            "# timestamp x y z qx qy qz qw\n"
            "1.0 0 0 0 0 0 0 2\n"
            "2.0 2 0 0 0 0 0.70710678 0.70710678\n",
            encoding="ascii",
        )
        poses = load_lightning_path(path_file)
        assert len(poses) == 2
        assert poses[0] == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        assert select_key_poses(poses, 8) == poses

        fallback_file = root / "poses.pcd"
        _write_ascii_pcd(fallback_file, [(0.0, 0.0, 0.0), (0.0, 2.0, 0.0)])
        fallback = load_pose_pcd(fallback_file)
        assert len(fallback) == 2
        assert math.isclose(fallback[0][5], math.sin(math.pi / 4.0), abs_tol=1e-6)
        assert math.isclose(fallback[0][6], math.cos(math.pi / 4.0), abs_tol=1e-6)

    map_points = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (2.0, 1.0, 0.0)]
    ground_points = [(0.5, 0.0, -0.1), (2.0, 0.0, -0.1)]
    keyframes = build_lightning_keyframes(
        map_points,
        ground_points,
        poses,
        radius_m=2.1,
        max_points=0,
    )
    assert len(keyframes) == 2
    assert set(keyframes[0]["map"]) <= set(map_points)
    assert set(keyframes[0]["ground"]) <= set(ground_points)
    # The second pose has +90 deg yaw. A map point one metre ahead maps to
    # one metre right in the robot-base frame after inverse transformation.
    point_at_pose = (2.0, 1.0, 0.0)
    index = keyframes[1]["map"].index(point_at_pose)
    transformed = keyframes[1]["map_base"][index]
    assert math.isclose(transformed[0], 1.0, abs_tol=1e-6)
    assert math.isclose(transformed[1], 0.0, abs_tol=1e-6)
    assert math.isclose(transformed[2], 0.0, abs_tol=1e-6)
    assert build_lightning_keyframes([], ground_points, poses, radius_m=2.0, max_points=0) == []


if __name__ == "__main__":
    main()
    print("Lightning-LM MCL map adapter tests passed")
