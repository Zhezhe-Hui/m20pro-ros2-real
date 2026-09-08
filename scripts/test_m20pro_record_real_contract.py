#!/usr/bin/env python3
"""Static contract checks for the v4 real-machine bag recorder."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORD_SCRIPT = ROOT / "src/m20pro_bringup/scripts/m20pro_record_real.sh"


def main() -> None:
    script = RECORD_SCRIPT.read_text(encoding="utf-8")

    assert "REQUESTED_TOPICS=(" in script
    assert "TOPICS=()" in script
    assert "SKIPPED_TOPICS=()" in script
    assert "grep -Fxq --" in script
    assert "selected ${#TOPICS[@]} visible topics" in script
    assert "M20PRO_RECORD_GUARD_QOS_RELIABILITY" in script
    assert "--qos-reliability" in script

    for topic in (
        "/LIDAR/POINTS",
        "/IMU",
        "/m20pro/lightning_points",
        "/m20pro/lightning/cloud_adapter/status",
        "/lightning/odom",
        "/lightning/nav_state",
        "/lightning/path",
        "/current_scan_cloud",
        "/global_map_cloud",
        "/dddmr/edge_cloud",
        "/m20pro/dddmr/edge_cloud/status",
        "/mapcloud",
        "/mapground",
    ):
        assert topic in script

    for old_topic in (
        "/laser_odom_to_init",
        "/aft_mapped_to_init",
        "/cloud_keypose_6d",
        "/key_poses",
        "/pose_graph",
        "/lego_loam/m2ci",
        "/lego_loam/c2s",
    ):
        assert old_topic not in script

    assert "timeout --signal=INT --kill-after=15s" in script
    assert 'if [[ "${RC}" -eq 124 ]]; then' in script
    assert 'recording completed after ${DURATION_S}s' in script

    print("m20pro Lightning real bag recorder contract tests passed")


if __name__ == "__main__":
    main()
