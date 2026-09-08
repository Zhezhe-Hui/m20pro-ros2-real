#!/usr/bin/env python3
"""Source checks for the v4 Lightning-LM mapping control wrapper."""

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    script_path = ROOT / "scripts/104_dddmr_mapping_control.sh"
    script = script_path.read_text(encoding="utf-8")
    mapping_launch = (
        ROOT / "src/m20pro_bringup/launch/m20pro_lightning_mapping.launch.py"
    ).read_text(encoding="utf-8")
    mapping_params = (
        ROOT / "src/m20pro_bringup/config/lightning_m20pro_edge_mapping.yaml"
    ).read_text(encoding="utf-8")
    raw_mapping_params = (
        ROOT / "src/m20pro_bringup/config/lightning_m20pro_raw_mapping.yaml"
    ).read_text(encoding="utf-8")
    adapter = (
        ROOT / "src/m20pro_bringup/src/lightning_pcd_asset_adapter.cpp"
    ).read_text(encoding="utf-8")
    cloud_adapter = (
        ROOT / "src/m20pro_bringup/src/lightning_cloud_adapter.cpp"
    ).read_text(encoding="utf-8")
    cmake = (ROOT / "src/m20pro_bringup/CMakeLists.txt").read_text(
        encoding="utf-8"
    )
    package_xml = (ROOT / "src/m20pro_bringup/package.xml").read_text(
        encoding="utf-8"
    )
    autostart = (ROOT / "scripts/104_enable_autostart.sh").read_text(
        encoding="utf-8"
    )
    raw_mapping_control = (
        ROOT / "scripts/lightning_raw_mapping_control.sh"
    ).read_text(encoding="utf-8")
    default_file = (ROOT / "systemd/m20pro-real.default").read_text(
        encoding="utf-8"
    )
    prepare_runtime = (ROOT / "scripts/prepare_dddmr_foxy_runtime.sh").read_text(
        encoding="utf-8"
    )
    chain_script = (ROOT / "scripts/dense_mapping_chain.sh").read_text(
        encoding="utf-8"
    )
    vendor_package = (
        ROOT / "vendor/lightning_lm_deep_robotics/package.xml"
    ).read_text(encoding="utf-8")
    vendor_readme = (
        ROOT / "vendor/lightning_lm_deep_robotics/README.md"
    ).read_text(encoding="utf-8")

    assert not (ROOT / "vendor/dddmr/lego_loam_bor").exists()
    assert not (ROOT / "src/m20pro_bringup/launch/m20pro_dddmr_mapping.launch.py").exists()
    assert not (ROOT / "src/m20pro_bringup/config/dddmr_m20pro_mapping.yaml").exists()

    assert "m20pro_lightning_mapping.launch.py" in script
    assert "/home/user/m20pro_real_ros2_ws_v4" in script
    assert "LIGHTNING_ALGORITHM_PACKAGE" in script
    assert "M20PRO_DDDMR_ALGORITHM_PACKAGE:-${M20PRO_LIGHTNING_ALGORITHM_PACKAGE:-lightning}" in script
    assert "LIGHTNING_SOURCE_CLOUD_TOPIC" in script
    assert "/dddmr/edge_cloud" in script
    assert "/m20pro/lightning_points" in script
    assert "/LIDAR/POINTS + /IMU" in script
    assert 'LIGHTNING_ENABLE_CLOUD_ADAPTER="${M20PRO_LIGHTNING_ENABLE_CLOUD_ADAPTER:-false}"' in script
    assert 'LIGHTNING_SOURCE_CLOUD_TOPIC="${M20PRO_LIGHTNING_SOURCE_CLOUD_TOPIC:-/LIDAR/POINTS}"' in script
    assert "lightning_m20pro_raw_mapping.yaml" in script
    assert "cloud_adapter_enabled=" in script
    assert "/lightning/save_map" in script
    assert "/lightning/save_path" in script
    assert "/save_mapped_point_cloud" not in script
    assert "lightning_pcd_asset_adapter" in script
    assert "lightning_global_map_missing" in script
    assert "lightning_asset_adaptation_failed" in script
    # Save-service readiness is proven by monotonic evidence (persisted
    # marker + the mapper's own creation log line); the bounded DDS probe is
    # only a first-time fallback (one-shot discovery misses existing services
    # under field CPU contention and misreported `starting`).
    assert "save_service_evidence" in script
    assert "save_service_seen" in script
    assert "SavePath service has been created" in script
    assert "backend=lightning_lm" in script
    assert "project_fastdds" in script
    assert 'FASTRTPS_DEFAULT_PROFILES_FILE="${project_fastdds}"' in script
    assert 'source "${project_setup}"' in script
    assert "require_project_mapping_overlay" in script
    assert "lightning_mapping_overlay_mismatch" in script
    assert 'project_package_prefix="${WS_DIR}/install/${MAPPING_PACKAGE}"' in script
    assert 'export AMENT_PREFIX_PATH="${project_package_prefix}:${WS_DIR}/install${AMENT_PREFIX_PATH:+:${AMENT_PREFIX_PATH}}"' in script
    assert 'export COLCON_PREFIX_PATH="${WS_DIR}/install${COLCON_PREFIX_PATH:+:${COLCON_PREFIX_PATH}}"' in script
    assert "mapping_package_prefix=" in script
    assert "ros2_service_wait_call.py" in script
    assert "exists /lightning/save_map" in script
    assert "lightning_source_cloud_missing" in script
    # Source-cloud gate is O(1): publisher heartbeat + live process only.
    # The rclpy DDS subscription fallback was removed (2026-09-01): booting a
    # python participant per status poll measured 16-24s under RK3588 boot
    # load and blew the frontend's 15s timeout, blocking the start button.
    assert 'cloud "${LIGHTNING_SOURCE_CLOUD_TOPIC}"' not in script
    assert "m20pro_dense_cloud_publisher.heartbeat" in script
    assert "source_cloud_chain_alive" in script
    # Alive check needs BOTH a fresh heartbeat and a live publisher process:
    # heartbeat mtime lags chain death by up to 5s (post-stop start race).
    assert script.count('pgrep -f "dddmr_dense_cloud_[p]ublisher"') >= 1
    assert script.count('pgrep -f "raw_lidar_merge_[n]ode"') >= 2
    assert "source_cloud_available_check" in script
    # Start must self-heal an expired/hung dense chain unattended (chain
    # windows die by design; the frontend start button cannot run shell
    # steps). 2026-08-19: user hit "密集数据链未启动或无数据" after expiry.
    assert "ensure_source_cloud_chain" in script
    assert "source_chain_auto_started" in script
    assert "DENSE_CHAIN_WINDOW_S" in script
    assert "M20PRO_DENSE_CHAIN_SKIP_VERIFY=1" in script
    # Chain lifecycle follows the session: finish/cancel stop the high-cost
    # dense chain immediately; the next start self-heals it again. Window is
    # a >=2h backstop (sessions are battery-bound), not a user-facing timer.
    assert "dense_chain_stopped" in script
    assert script.count("dense_mapping_chain.sh\" stop") >= 2
    assert "7200" in script
    # CPU pinning: vendor kernel boots isolcpus=4,5,6,7 and PID1 (thus the
    # whole stack) inherits little-core affinity; the mapping pipeline is
    # explicitly pinned to the idle isolated big cores.
    assert "mapping_cpu_pin_prefix" in script
    assert "M20PRO_MAPPING_CPUS" in script
    assert "taskset -c" in script
    assert "mapping_cpu_pin_prefix" in chain_script
    assert "M20PRO_MAPPING_CPUS" in chain_script
    assert "M20PRO_DENSE_CHAIN_SKIP_VERIFY" in chain_script
    # Chain start must not stack duplicates over a healthy chain, and must
    # clean a stale (alive-but-no-frames) chain before restarting.
    assert "already running with fresh data flow" in chain_script
    assert "stale chain processes present" in chain_script
    # Sourced-environment cache: re-running the triple overlay source on every
    # status call spawned hundreds of ament hook interpreters and exceeded the
    # web gate timeout under field CPU contention.
    assert "ros_env.cache" in script
    assert "env_cache_fingerprint" in script
    assert "build_env_cache" in script
    assert "algorithm_package_prefix=" in script
    assert os.access(script_path, os.X_OK)

    assert "run_slam_online" in mapping_launch
    assert "lightning_cloud_adapter" in mapping_launch
    assert "cloud_adapter_input_topic" in mapping_launch
    assert "lightning_points_topic" in mapping_launch
    assert "m20pro_lightning_slam_online.sh" in mapping_launch
    assert "lightning_m20pro_raw_mapping.yaml" in mapping_launch
    assert 'DeclareLaunchArgument("enable_cloud_adapter", default_value="false")' in mapping_launch
    assert '"cloud_adapter_input_topic", default_value="/LIDAR/POINTS"' in mapping_launch
    assert "m20pro_base_link_to_lidar_link_lightning" in mapping_launch
    assert '"scan_line": 96' in mapping_launch
    assert '"max_points": 30000' in mapping_launch
    assert "lego_loam_bor" not in mapping_launch
    assert 'lidar_topic: "/m20pro/lightning_points"' in mapping_params
    assert "/LIDAR/POINTS" in mapping_params
    assert "scan_line: 96" in mapping_params
    assert "point_filter_num: 1" in mapping_params
    assert "filter_size_scan: 0.25" in mapping_params
    assert "filter_size_map: 0.25" in mapping_params
    assert "ivox_grid_resolution: 0.25" in mapping_params
    assert 'imu_topic: "/IMU"' in mapping_params
    assert "with_ui: false" in mapping_params
    assert "pub_odom: true" in mapping_params
    assert "enable_lidar_loc_rviz: true" in mapping_params
    assert 'rviz_global_map_topic: "/global_map_cloud"' in mapping_params
    assert 'lidar_topic: "/m20pro/lidar_points_dense_ros"' in raw_mapping_params
    assert "m20pro_lightning_raw" in raw_mapping_params
    assert "scan_line: 96" in raw_mapping_params
    # Official-level density keeps the mapper bounded while preserving
    # furniture- and wall-scale geometry.
    assert "point_filter_num: 24" in raw_mapping_params
    assert "filter_size_scan: 0.5" in raw_mapping_params
    assert "filter_size_map: 0.5" in raw_mapping_params
    assert "ivox_grid_resolution: 0.5" in raw_mapping_params
    assert "skip_lidar_num: 0" in raw_mapping_params
    assert "use_imu_orient: false" in raw_mapping_params
    assert "with_loop_closing: true" in raw_mapping_params
    assert "with_g2p5: false" in raw_mapping_params
    assert 'map_path: ./data/m20pro_lightning_raw/' in raw_mapping_params

    assert "add_executable(lightning_cloud_adapter" in cmake
    assert "add_executable(lightning_pcd_asset_adapter" in cmake
    assert "find_package(PCL REQUIRED COMPONENTS common io filters)" in cmake
    assert "scripts/m20pro_lightning_slam_online.sh" in cmake
    assert "/m20pro/lightning/cloud_adapter/status" in cloud_adapter
    assert "timestamp" in cloud_adapter
    assert "ring" in cloud_adapter
    assert "data.size() / cloud->point_step" in cloud_adapter
    assert "readNumericAsUInt16" in cloud_adapter
    assert "readNumericAsDouble" in cloud_adapter
    assert "ring_source" in cloud_adapter
    assert "timestamp_source" in cloud_adapter
    assert "std::stable_sort" in cloud_adapter
    assert "<depend>libpcl-all-dev</depend>" in package_xml
    assert "loadPCDFile" in adapter
    assert "savePCDFileBinary(options.map" in adapter
    assert "binary_compressed" in adapter
    assert "ground_floor_z" in adapter
    assert "Lightning path file has no valid poses" in adapter
    assert "failed to derive ground asset" in adapter

    assert 'DEFAULT_DDDMR_RUNTIME_WS="${WS_DIR}"' in autostart
    assert 'DEFAULT_DDDMR_MAPPING_LAUNCH="m20pro_lightning_mapping.launch.py"' in autostart
    assert 'DEFAULT_DDDMR_ALGORITHM_PACKAGE="lightning"' in autostart
    assert "M20PRO_LIGHTNING_MAPPING_WORK_DIR" in autostart
    assert "RAW_CONFIG_DEFAULT" in raw_mapping_control
    assert "lightning_m20pro_raw_mapping.yaml" in raw_mapping_control
    assert "M20PRO_LIGHTNING_MAPPING_CONFIG" in raw_mapping_control
    assert "/m20pro/lidar_points_dense_ros" in raw_mapping_control
    assert "M20PRO_LIGHTNING_ENABLE_CLOUD_ADAPTER" in raw_mapping_control
    assert "false" in raw_mapping_control
    assert "104_dddmr_mapping_control.sh" in raw_mapping_control
    assert os.access(ROOT / "scripts/lightning_raw_mapping_control.sh", os.X_OK)
    assert "M20PRO_DDDMR_RUNTIME_WS=/home/user/m20pro_real_ros2_ws_v4" in default_file
    assert "M20PRO_DDDMR_MAPPING_LAUNCH=m20pro_lightning_mapping.launch.py" in default_file
    assert "M20PRO_DDDMR_ALGORITHM_PACKAGE=lightning" in default_file
    assert "lightning_raw_mapping_control.sh start {floor}" in default_file
    assert "lightning_raw_mapping_control.sh status {floor}" in default_file
    assert "M20PRO_LIGHTNING_GROUND_HEIGHT_M=0.35" in default_file

    assert "DeepRoboticsLab/lightning-lm-deep-robotics.git" in prepare_runtime
    assert "vendor/lightning_lm_deep_robotics" in prepare_runtime
    assert "thirdparty/glog" in prepare_runtime
    assert "thirdparty/Pangolin" in prepare_runtime
    assert "--packages-up-to" in prepare_runtime
    for package_name in (
        "lightning",
        "lego_loam_bor",
        "mcl_3dl",
        "perception_3d",
        "global_planner",
        "p2p_move_base",
    ):
        assert package_name in prepare_runtime
    assert "ros2 pkg prefix lightning" in prepare_runtime
    assert "vendor/dddmr/lego_loam_bor" not in prepare_runtime
    assert 'cp -a "${ROOT_DIR}/src/m20pro_bringup" "${TARGET}/src/"' not in prepare_runtime
    assert "ros2 pkg prefix m20pro_bringup" not in prepare_runtime

    assert "<name>lightning</name>" in vendor_package
    assert "Lightning-LM Deployment Guide for Deep Robotics M20" in vendor_readme
    assert "BSD 3-Clause License" in (
        ROOT / "vendor/lightning_lm_deep_robotics/LICENSE.txt"
    ).read_text(encoding="utf-8")

    print("Lightning-LM mapping control contract tests passed")


if __name__ == "__main__":
    main()
