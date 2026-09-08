#!/usr/bin/env python3
"""Source contract for RoboSense scan-time normalization."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "vendor/lightning_lm_deep_robotics/src/core/lio/pointcloud_preprocess.cc"


def require(text: str, needle: str, message: str) -> None:
    if needle not in text:
        raise AssertionError(message)


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    handler = text.split("void PointCloudPreprocess::RobosenseHandler", 1)[1]
    require(handler, "std::min_element", "scan origin must inspect all point timestamps")
    require(handler, "msg->header.stamp.sec", "scan origin must use the ROS header stamp")
    require(handler, "first_point_time - header_time <= 0.5", "header must be range gated")
    require(handler, "std::stable_sort", "RoboSense points must be ordered before SyncPackages")
    sort_pos = handler.index("std::stable_sort")
    width_pos = handler.rfind("cloud_out_.width")
    if sort_pos >= width_pos:
        raise AssertionError("point ordering must happen before the cloud enters the LIO queue")
    print("lightning RoboSense time contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
