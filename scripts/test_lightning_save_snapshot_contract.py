#!/usr/bin/env python3
"""Static contract checks for Lightning's consistent save snapshot."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SLAM = ROOT / "vendor/lightning_lm_deep_robotics/src/core/system/slam.cc"
SLAM_H = ROOT / "vendor/lightning_lm_deep_robotics/src/core/system/slam.h"
LIO = ROOT / "vendor/lightning_lm_deep_robotics/src/core/lio/laser_mapping.cc"
LIO_H = ROOT / "vendor/lightning_lm_deep_robotics/src/core/lio/laser_mapping.h"


def require(text: str, fragment: str, message: str) -> None:
    if fragment not in text:
        raise AssertionError(f"{message}: missing {fragment!r}")


def main() -> None:
    slam = SLAM.read_text(encoding="utf-8")
    slam_h = SLAM_H.read_text(encoding="utf-8")
    lio = LIO.read_text(encoding="utf-8")
    lio_h = LIO_H.read_text(encoding="utf-8")

    save_body = slam[slam.index("bool SlamSystem::SaveMap(const std::string& path)") : slam.index("// ros服务回调，保存轨迹")]
    require(save_body, "lc_->WaitUntilIdle();", "save waits for loop closing")
    require(save_body, "LaserMapping::PoseSnapshot map_poses;", "save creates map pose snapshot")
    require(save_body, "lio_->GetGlobalMap(keyframes, map_poses)", "map uses the captured pose snapshot")
    require(save_body, "SE3 start_pose = map_poses.front();", "tile origin uses the captured pose snapshot")
    require(save_body, "saved_snapshot_poses_.clear();", "failed saves cannot retain an old path snapshot")
    require(save_body, "saved_snapshot_poses_ = std::move(snapshot_poses);", "path snapshot is committed with the map")
    require(save_body, "save_path.back() == '/'", "trailing separators are stripped before path validation")
    require(save_body, ".saving-", "map and path outputs use staging names")
    require(save_body, "std::filesystem::rename(staging_path, final_path", "map output is committed after writing")
    require(save_body, "required map files are missing or empty", "map output validates required files")
    require(slam_h, "Eigen::aligned_allocator<SavedPose>", "saved poses use Eigen-aligned storage")
    require(lio_h, "const PoseSnapshot& poses", "LIO exposes snapshot-based map generation")
    require(lio, "keyframe/pose snapshot size mismatch", "snapshot size is validated")
    require(lio, "poses[i].matrix()", "map transforms use explicit snapshot poses")
    tiled_map = (ROOT / "vendor/lightning_lm_deep_robotics/src/core/maps/tiled_map.cc").read_text(encoding="utf-8")
    tiled_map_h = (ROOT / "vendor/lightning_lm_deep_robotics/src/core/maps/tiled_map.h").read_text(encoding="utf-8")
    require(tiled_map, "cannot write tiled map chunk", "tiled map write failures propagate")
    require(tiled_map, "return SaveToBin(false);", "tiled map conversion returns write status")
    require(tiled_map_h, "bool SaveToBin", "tiled map write status is explicit")

    print("lightning save snapshot contract: ok")


if __name__ == "__main__":
    main()
