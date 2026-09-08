"""Pure helpers for DDDMR static map asset parsing.

This module intentionally avoids ROS imports so offline contract tests can
exercise the PCD loader and path splitting logic without sourcing a ROS 2
environment.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Any, Iterable, List, Sequence, Tuple


def _finite_xyz(points: Iterable[Sequence[Any]], max_points: int) -> List[Tuple[float, float, float]]:
    accepted: List[Tuple[float, float, float]] = []
    for raw in points:
        if len(raw) < 3:
            continue
        try:
            x, y, z = (float(raw[0]), float(raw[1]), float(raw[2]))
        except (TypeError, ValueError, OverflowError):
            continue
        if not all(math.isfinite(value) for value in (x, y, z)):
            continue
        accepted.append((x, y, z))
        if max_points > 0 and len(accepted) >= max_points:
            break
    return accepted


def _parse_pcd(path: Path, max_points: int) -> List[Tuple[float, float, float]]:
    """Read x/y/z from ASCII or uncompressed binary PCD files."""
    raw = path.read_bytes()
    header_end = -1
    offset = 0
    for line in raw.splitlines(keepends=True):
        offset += len(line)
        if line.strip().upper().startswith(b"DATA "):
            header_end = offset
            break
    if header_end <= 0:
        raise ValueError("pcd_data_header_missing")
    header = raw[:header_end].decode("ascii", errors="strict").splitlines()
    data_mode = ""
    fields: List[str] = []
    sizes: List[int] = []
    types: List[str] = []
    counts: List[int] = []
    for line in header:
        tokens = line.strip().split()
        if not tokens:
            continue
        key = tokens[0].upper()
        if key == "FIELDS":
            fields = tokens[1:]
        elif key == "SIZE":
            sizes = [int(value) for value in tokens[1:]]
        elif key == "TYPE":
            types = tokens[1:]
        elif key == "COUNT":
            counts = [int(value) for value in tokens[1:]]
        elif key == "DATA" and len(tokens) > 1:
            data_mode = tokens[1].lower()
    if not fields or not sizes or not types:
        raise ValueError("pcd_xyz_fields_missing")
    if len(counts) != len(fields):
        counts = [1] * len(fields)
    try:
        x_index, y_index, z_index = (fields.index("x"), fields.index("y"), fields.index("z"))
    except ValueError as exc:
        raise ValueError("pcd_xyz_fields_missing") from exc
    if data_mode == "ascii":
        text = raw[header_end:].decode("ascii", errors="strict")
        rows = (line.split() for line in text.splitlines() if line.strip())
        return _finite_xyz(
            ((row[x_index], row[y_index], row[z_index]) for row in rows), max_points
        )
    if data_mode != "binary":
        raise ValueError("pcd_data_mode_unsupported")
    offsets: List[int] = []
    offset = 0
    for size, count in zip(sizes, counts):
        offsets.append(offset)
        offset += int(size) * int(count)
    point_step = offset
    if point_step <= 0:
        raise ValueError("pcd_point_step_invalid")

    data = raw[header_end:]

    def read_number(position: int, field_index: int) -> float:
        size = int(sizes[field_index])
        type_code = str(types[field_index]).upper()
        if size == 4 and type_code == "F":
            return float(struct.unpack_from("<f", data, position)[0])
        if size == 8 and type_code == "F":
            return float(struct.unpack_from("<d", data, position)[0])
        raise ValueError("pcd_xyz_type_unsupported")

    points: List[Tuple[float, float, float]] = []
    for position in range(0, len(data) - point_step + 1, point_step):
        try:
            point = (
                read_number(position + offsets[x_index], x_index),
                read_number(position + offsets[y_index], y_index),
                read_number(position + offsets[z_index], z_index),
            )
        except (struct.error, ValueError):
            continue
        if all(math.isfinite(value) for value in point):
            points.append(point)
            if max_points > 0 and len(points) >= max_points:
                break
    return points


def _split_paths(value: Any) -> List[Path]:
    if isinstance(value, (list, tuple)):
        values = value
    else:
        values = str(value or "").split(",")
    return [Path(str(item).strip()).expanduser() for item in values if str(item).strip()]


__all__ = [
    "_finite_xyz",
    "_parse_pcd",
    "_split_paths",
]
