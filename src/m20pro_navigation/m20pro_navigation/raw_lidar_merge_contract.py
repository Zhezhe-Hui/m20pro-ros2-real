"""Pure contracts for pairing and validating the two raw M20 lidar streams."""

from __future__ import annotations

import bisect
import math
import struct
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:
    import numpy
except ImportError:
    numpy = None


FLOAT32 = 7
FLOAT64 = 8


def point_count(message: Any) -> int:
    return int(message.width) * int(message.height)


def field_signature(fields: Sequence[Any]) -> Tuple[Tuple[str, int, int, int], ...]:
    return tuple(
        (
            str(field.name),
            int(field.offset),
            int(field.datatype),
            int(field.count),
        )
        for field in fields
    )


def merge_payloads_by_timestamp(
    first_payload: bytes,
    second_payload: bytes,
    point_step: int,
    timestamp_offset: int,
    is_bigendian: bool,
) -> bytes:
    """Concatenate two clouds and restore global scan-time ordering."""
    step = int(point_step)
    if step <= 0:
        raise ValueError("point_step must be positive")
    if int(timestamp_offset) < 0 or int(timestamp_offset) + 8 > step:
        raise ValueError("timestamp field is outside point layout")
    payload = bytes(first_payload) + bytes(second_payload)
    if len(payload) % step != 0:
        raise ValueError("payload is not aligned to point_step")
    count = len(payload) // step
    if count <= 1:
        return payload
    if numpy is None:
        records = [
            payload[index * step:(index + 1) * step]
            for index in range(count)
        ]
        byte_order = ">" if bool(is_bigendian) else "<"
        records.sort(
            key=lambda record: struct.unpack_from(
                byte_order + "d", record, int(timestamp_offset)
            )[0]
        )
        return b"".join(records)
    raw = numpy.frombuffer(payload, dtype=numpy.uint8).reshape(count, step)
    byte_order = ">" if bool(is_bigendian) else "<"
    timestamp_dtype = numpy.dtype(byte_order + "f8")
    timestamps = numpy.ndarray(
        shape=(count,),
        dtype=timestamp_dtype,
        buffer=raw,
        offset=int(timestamp_offset),
        strides=(step,),
    )
    order = numpy.argsort(timestamps, kind="stable")
    if bool(numpy.array_equal(order, numpy.arange(count))):
        return payload
    return numpy.ascontiguousarray(raw[order]).tobytes()


def validate_cloud_payload(
    data: bytes,
    width: int,
    height: int,
    point_step: int,
    fields: Sequence[Any],
    is_bigendian: bool,
    header_stamp_s: float,
    *,
    max_point_time_offset_s: float = 0.25,
    max_scan_span_s: float = 0.25,
) -> Optional[str]:
    count = int(width) * int(height)
    step = int(point_step)
    if count <= 0:
        return "empty_cloud"
    if step <= 0:
        return "invalid_point_step"
    required = {str(field.name): field for field in fields}
    for name in ("x", "y", "z", "intensity", "ring", "timestamp"):
        if name not in required:
            return "missing_%s_field" % name
    for name in ("x", "y", "z", "intensity"):
        field = required[name]
        if int(field.datatype) != FLOAT32 or int(field.count) != 1:
            return "invalid_%s_field" % name
        if int(field.offset) + 4 > step:
            return "%s_field_out_of_bounds" % name
    ring = required["ring"]
    if int(ring.count) != 1 or int(ring.offset) + 2 > step:
        return "invalid_ring_field"
    timestamp = required["timestamp"]
    timestamp_offset = int(timestamp.offset)
    if int(timestamp.datatype) != FLOAT64 or int(timestamp.count) != 1:
        return "invalid_timestamp_field"
    if timestamp_offset + 8 > step:
        return "timestamp_field_out_of_bounds"
    expected_bytes = count * step
    payload = bytes(data)
    if len(payload) < expected_bytes:
        return "truncated_payload"
    byte_order = ">" if bool(is_bigendian) else "<"
    if numpy is not None:
        timestamp_dtype = numpy.dtype(byte_order + "f8")
        raw = numpy.frombuffer(payload[:expected_bytes], dtype=numpy.uint8)
        values = numpy.ndarray(
            shape=(count,),
            dtype=timestamp_dtype,
            buffer=raw,
            offset=timestamp_offset,
            strides=(step,),
        )
        if values.size == 0 or not bool(numpy.isfinite(values).all()):
            return "invalid_point_timestamps"
        minimum = float(values.min())
        maximum = float(values.max())
    else:
        minimum = math.inf
        maximum = -math.inf
        for index in range(count):
            value = struct.unpack_from(
                byte_order + "d", payload, index * step + timestamp_offset
            )[0]
            if not math.isfinite(value):
                return "invalid_point_timestamps"
            minimum = min(minimum, value)
            maximum = max(maximum, value)
    if maximum < minimum or maximum - minimum > float(max_scan_span_s):
        return "point_timestamp_span_exceeded"
    if not math.isfinite(float(header_stamp_s)) or float(header_stamp_s) <= 0:
        return "invalid_header_stamp"
    tolerance = float(max_point_time_offset_s)
    if minimum < float(header_stamp_s) - tolerance or maximum > float(header_stamp_s) + tolerance:
        return "point_timestamp_outside_scan"
    return None


@dataclass(frozen=True)
class TimestampPair:
    front: Any
    rear: Any
    delta_ns: int
    output_stamp_ns: int


@dataclass(frozen=True)
class _QueuedCloud:
    stamp_ns: int
    sequence: int
    item: Any


class LidarPairBuffer:
    """Bounded, timestamp-based pairing for independent front/rear streams."""

    def __init__(self, max_queue: int = 8, sync_window_s: float = 0.02) -> None:
        if int(max_queue) < 1:
            raise ValueError("max_queue must be positive")
        if float(sync_window_s) <= 0:
            raise ValueError("sync_window_s must be positive")
        self.max_queue = int(max_queue)
        self.sync_window_ns = int(round(float(sync_window_s) * 1e9))
        self._queues: Dict[str, List[_QueuedCloud]] = {"front": [], "rear": []}
        self._sequence = 0
        self._last_output_stamp_ns: Optional[int] = None
        self.dropped_stale = 0
        self.dropped_unmatched = 0
        self.dropped_overflow = 0
        self.dropped_nonmonotonic_output = 0

    @property
    def last_output_stamp_ns(self) -> Optional[int]:
        return self._last_output_stamp_ns

    def add(self, key: str, stamp_ns: int, item: Any) -> List[TimestampPair]:
        if key not in self._queues:
            raise ValueError("unknown lidar side: %s" % key)
        stamp = int(stamp_ns)
        if stamp <= 0:
            self.dropped_stale += 1
            return []
        if self._last_output_stamp_ns is not None and stamp <= self._last_output_stamp_ns:
            self.dropped_stale += 1
            return []
        queue = self._queues[key]
        stamps = [entry.stamp_ns for entry in queue]
        position = bisect.bisect_right(stamps, stamp)
        queue.insert(position, _QueuedCloud(stamp, self._sequence, item))
        self._sequence += 1
        while len(queue) > self.max_queue:
            queue.pop(0)
            self.dropped_overflow += 1
        return self._drain()

    def _drain(self) -> List[TimestampPair]:
        result: List[TimestampPair] = []
        while self._queues["front"] and self._queues["rear"]:
            front_queue = self._queues["front"]
            rear_queue = self._queues["rear"]
            best: Optional[Tuple[int, int, int, int]] = None
            for front_index, front in enumerate(front_queue):
                for rear_index, rear in enumerate(rear_queue):
                    candidate = (
                        abs(front.stamp_ns - rear.stamp_ns),
                        min(front.stamp_ns, rear.stamp_ns),
                        front.sequence,
                        rear.sequence,
                    )
                    if best is None or candidate < best:
                        best = candidate
            if best is not None and best[0] <= self.sync_window_ns:
                front_index = next(
                    index for index, entry in enumerate(front_queue)
                    if entry.sequence == best[2]
                )
                rear_index = next(
                    index for index, entry in enumerate(rear_queue)
                    if entry.sequence == best[3]
                )
                front = front_queue.pop(front_index)
                rear = rear_queue.pop(rear_index)
                output_stamp = min(front.stamp_ns, rear.stamp_ns)
                if (
                    self._last_output_stamp_ns is not None
                    and output_stamp <= self._last_output_stamp_ns
                ):
                    self.dropped_nonmonotonic_output += 1
                    continue
                self._last_output_stamp_ns = output_stamp
                result.append(
                    TimestampPair(
                        front=front.item,
                        rear=rear.item,
                        delta_ns=best[0],
                        output_stamp_ns=output_stamp,
                    )
                )
                continue
            front_oldest = front_queue[0].stamp_ns
            rear_oldest = rear_queue[0].stamp_ns
            front_newest = front_queue[-1].stamp_ns
            rear_newest = rear_queue[-1].stamp_ns
            if front_oldest < rear_newest - self.sync_window_ns:
                front_queue.pop(0)
                self.dropped_unmatched += 1
                continue
            if rear_oldest < front_newest - self.sync_window_ns:
                rear_queue.pop(0)
                self.dropped_unmatched += 1
                continue
            break
        return result
