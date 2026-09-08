//
// Created by xiang on 25-5-6.
//

#include "core/system/slam.h"
#include "core/g2p5/g2p5.h"
#include "core/lio/laser_mapping.h"
#include "core/loop_closing/loop_closing.h"
#include "core/maps/tiled_map.h"
#include "ui/pangolin_window.h"
#include "wrapper/ros_utils.h"

#include <yaml-cpp/yaml.h>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <cmath>
#include <opencv2/opencv.hpp>

namespace {

std::string SaveToken() {
    return std::to_string(
        std::chrono::steady_clock::now().time_since_epoch().count());
}

struct StagingDirectoryGuard {
    std::filesystem::path path;
    bool committed = false;

    ~StagingDirectoryGuard() {
        if (!committed) {
            std::error_code error;
            std::filesystem::remove_all(path, error);
        }
    }
};

}  // namespace

namespace lightning {

SlamSystem::SlamSystem(lightning::SlamSystem::Options options) : options_(options) {
    /// handle ctrl-c
    signal(SIGINT, lightning::debug::SigHandle);
}

bool SlamSystem::Init(const std::string& yaml_path) {
    lio_ = std::make_shared<LaserMapping>();
    if (!lio_->Init(yaml_path)) {
        LOG(ERROR) << "failed to init lio module";
        return false;
    }

    auto yaml = YAML::LoadFile(yaml_path);
    options_.with_loop_closing_ = yaml["system"]["with_loop_closing"].as<bool>();
    options_.with_visualization_ = yaml["system"]["with_ui"].as<bool>();
    options_.with_2dvisualization_ = yaml["system"]["with_2dui"].as<bool>();
    options_.pub_tf_ = yaml["system"]["pub_tf"] ? yaml["system"]["pub_tf"].as<bool>() : false;
    options_.pub_odom_ = yaml["system"]["pub_odom"] ? yaml["system"]["pub_odom"].as<bool>() : false;
    options_.with_gridmap_ = yaml["system"]["with_g2p5"].as<bool>();
    options_.step_on_kf_ = yaml["system"]["step_on_kf"].as<bool>();
    options_.log_pose_opt_ = yaml["system"]["log_pose_opt"] ? yaml["system"]["log_pose_opt"].as<bool>() : false;
    options_.enable_lidar_rviz_ = yaml["system"]["enable_lidar_loc_rviz"] ? yaml["system"]["enable_lidar_loc_rviz"].as<bool>() : false;
    options_.enable_path_rviz_ = yaml["system"]["enable_path_rviz"] ? yaml["system"]["enable_path_rviz"].as<bool>() : false;
    options_.use_imu_init_ = yaml["system"]["use_imu_orient"] ? yaml["system"]["use_imu_orient"].as<bool>() : false;
    if(options_.enable_lidar_rviz_ && !options_.enable_path_rviz_) {
        options_.enable_path_rviz_ = true; // 发布路径时会包含位姿信息，方便调试
    }

    LOG(INFO) << "SlamSystem Options: "
              << "\n  online_mode: " << options_.online_mode_
              << "\n  with_cc: " << options_.with_cc_
              << "\n  with_gridmap: " << options_.with_gridmap_
              << "\n  with_loop_closing: " << options_.with_loop_closing_
              << "\n  with_visualization: " << options_.with_visualization_
              << "\n  with_2dvisualization: " << options_.with_2dvisualization_
              << "\n  pub_odom: " << options_.pub_odom_
              << "\n  pub_tf: " << options_.pub_tf_
              << "\n  enable_lidar_rviz: " << options_.enable_lidar_rviz_
              << "\n  enable_path_rviz: " << options_.enable_path_rviz_
              << "\n  step_on_kf: " << options_.step_on_kf_
              << "\n  log_pose_opt: " << options_.log_pose_opt_
              << "\n  use_imu_init: " << options_.use_imu_init_;

    if (yaml["system"]["map_path"]) {
        std::string map_path = yaml["system"]["map_path"].as<std::string>();
        if (map_path.back() == '/') {
            map_path.pop_back();
        }
        size_t last_slash = map_path.find_last_of('/');
        if (last_slash != std::string::npos) {
            map_name_ = map_path.substr(last_slash + 1);
        } else {
            map_name_ = map_path;
        }
    } else {
        map_name_ = "new_map";
    }
    LOG(INFO) << "map name: " << map_name_;

    /// loop closing
    if (options_.with_loop_closing_) {
        LOG(INFO) << "slam with loop closing";
        LoopClosing::Options options;
        options.online_mode_ = options_.online_mode_;
        lc_ = std::make_shared<LoopClosing>(options);
        lc_->Init(yaml_path);
    }

    if (options_.with_visualization_) {
        LOG(INFO) << "slam with 3D UI";
        ui_ = std::make_shared<ui::PangolinWindow>();
        ui_->Init();

        lio_->SetUI(ui_);
    }

    if (options_.with_gridmap_) {
        g2p5::G2P5::Options opt;
        opt.online_mode_ = options_.online_mode_;

        g2p5_ = std::make_shared<g2p5::G2P5>(opt);
        g2p5_->Init(yaml_path);

        if (options_.with_loop_closing_) {
            /// 当发生回环时，触发一次重绘
            lc_->SetLoopClosedCB([this]() { g2p5_->RedrawGlobalMap(); });
        }

        if (options_.with_2dvisualization_) {
            g2p5_->SetMapUpdateCallback([this](g2p5::G2P5MapPtr map) {
                cv::Mat image = map->ToCV();
                cv::imshow("map", image);

                if (options_.step_on_kf_) {
                    cv::waitKey(0);

                } else {
                    cv::waitKey(10);
                }
            });
        }
    }

    if (options_.online_mode_) {
        LOG(INFO) << "online mode, creating ros2 node ... ";

        /// subscribers
        node_ = std::make_shared<rclcpp::Node>("lightning_slam");

        imu_topic_ = yaml["common"]["imu_topic"].as<std::string>();
        cloud_topic_ = yaml["common"]["lidar_topic"].as<std::string>();
        livox_topic_ = yaml["common"]["livox_lidar_topic"].as<std::string>();

        // A full M20Pro cloud can take longer to optimize than its publish
        // period on RK3588. Retaining ten reliable cloud samples makes the
        // executor process stale scans with future IMU data and destabilizes
        // LIO. Keep only the newest cloud, while retaining a deep reliable
        // IMU queue so scans can still be deskewed after a long update.
        rclcpp::QoS imu_qos(rclcpp::KeepLast(1000));
        imu_qos.reliable().durability_volatile();
        rclcpp::QoS cloud_qos(rclcpp::KeepLast(1));
        cloud_qos.best_effort().durability_volatile();
        imu_callback_group_ = node_->create_callback_group(
            rclcpp::CallbackGroupType::MutuallyExclusive);
        cloud_callback_group_ = node_->create_callback_group(
            rclcpp::CallbackGroupType::MutuallyExclusive);
        rclcpp::SubscriptionOptions imu_options;
        imu_options.callback_group = imu_callback_group_;
        rclcpp::SubscriptionOptions cloud_options;
        cloud_options.callback_group = cloud_callback_group_;

        imu_sub_ = node_->create_subscription<sensor_msgs::msg::Imu>(
            imu_topic_, imu_qos, [this](sensor_msgs::msg::Imu::SharedPtr msg) {
                IMUPtr imu = std::make_shared<IMU>();
                imu->timestamp = ToSec(msg->header.stamp);
                imu->linear_acceleration =
                    Vec3d(msg->linear_acceleration.x, msg->linear_acceleration.y, msg->linear_acceleration.z);
                imu->angular_velocity =
                    Vec3d(msg->angular_velocity.x, msg->angular_velocity.y, msg->angular_velocity.z);
                imu->orientation =
                    Quatd(msg->orientation.w, msg->orientation.x, msg->orientation.y, msg->orientation.z);

                ProcessIMU(imu);
            }, imu_options);

        cloud_sub_ = node_->create_subscription<sensor_msgs::msg::PointCloud2>(
            cloud_topic_, cloud_qos, [this](sensor_msgs::msg::PointCloud2::SharedPtr cloud) {
                Timer::Evaluate([&]() { ProcessLidar(cloud); }, "Proc Lidar", true);
            }, cloud_options);

        livox_sub_ = node_->create_subscription<livox_ros_driver2::msg::CustomMsg>(
            livox_topic_, cloud_qos, [this](livox_ros_driver2::msg::CustomMsg ::SharedPtr cloud) {
                Timer::Evaluate([&]() { ProcessLidar(cloud); }, "Proc Lidar", true);
            }, cloud_options);

        if (options_.enable_lidar_rviz_) {
            std::string scan_topic = yaml["system"]["rviz_current_scan_topic"] ? yaml["system"]["rviz_current_scan_topic"].as<std::string>() : "lightning/current_scan";
            std::string map_topic = yaml["system"]["rviz_global_map_topic"] ? yaml["system"]["rviz_global_map_topic"].as<std::string>() : "lightning/global_map";
            cloud_pub_ = node_->create_publisher<sensor_msgs::msg::PointCloud2>(scan_topic, 10);
            map_pub_ = node_->create_publisher<sensor_msgs::msg::PointCloud2>(map_topic, 1);
        }

        if (options_.enable_path_rviz_) {
            path_pub_ = node_->create_publisher<nav_msgs::msg::Path>("lightning/path", 10);
        }

        if (options_.pub_odom_) {
            odom_pub_ = node_->create_publisher<nav_msgs::msg::Odometry>("lightning/odom", 10);
            nav_state_pub_ = node_->create_publisher<msg::NavState>("lightning/nav_state", 10);
        }

        if (options_.pub_tf_) {
            tf_broadcaster_ = std::make_shared<tf2_ros::TransformBroadcaster>(node_);
        }

        savemap_service_ = node_->create_service<SaveMapService>(
            "lightning/save_map", [this](const SaveMapService::Request::SharedPtr req,
                                         SaveMapService::Response::SharedPtr res) { SaveMap(req, res); });

        savepath_service_ = node_->create_service<srv::SavePath>(
            "lightning/save_path", [this](const srv::SavePath::Request::SharedPtr req,
                                          srv::SavePath::Response::SharedPtr res) { SavePath(req, res); });

        LOG(INFO) << "SavePath service has been created.";
    }

    return true;
}

SlamSystem::~SlamSystem() {
    if (ui_) {
        ui_->Quit();
    }
}

void SlamSystem::StartSLAM(std::string map_name) {
    if (!map_name.empty()) {
        map_name_ = map_name;
    }
    running_ = true;
}

void SlamSystem::SaveMap(const SaveMapService::Request::SharedPtr request,
                         SaveMapService::Response::SharedPtr response) {
    try {
        map_name_ = request->map_id;
        std::string save_path = "./data/" + map_name_ + "/";
        bool saved = SaveMap(save_path);
        if (saved) {
            response->response = 0;
        } else if (lio_ && lio_->IsDiverged()) {
            response->response = 4;
        } else {
            response->response = 3;
        }
    } catch (const std::exception& error) {
        LOG(ERROR) << "save map service failed: " << error.what();
        response->response = 3;
    } catch (...) {
        LOG(ERROR) << "save map service failed with an unknown exception";
        response->response = 3;
    }
}

bool SlamSystem::SaveMap(const std::string& path) {
    std::lock_guard<std::mutex> lock(lidar_process_mutex_);
    std::lock_guard<std::mutex> imu_lock(imu_process_mutex_);
    if (!lio_) {
        LOG(ERROR) << "cannot save map: Lightning LIO is not initialized";
        return false;
    }
    running_.store(false);
    saved_snapshot_poses_.clear();
    if (lio_->IsDiverged()) {
        LOG(ERROR) << "cannot save map: LIO diverged, map content is invalid";
        return false;
    }
    if (lc_) {
        LOG(INFO) << "waiting for loop closing queue before saving";
        lc_->WaitUntilIdle();
    }
    const auto keyframes = lio_->GetAllKeyframes();
    if (keyframes.empty()) {
        LOG(ERROR) << "cannot save map: no keyframes were produced";
        return false;
    }

    LaserMapping::PoseSnapshot map_poses;
    std::vector<SavedPose, Eigen::aligned_allocator<SavedPose>> snapshot_poses;
    map_poses.reserve(keyframes.size());
    snapshot_poses.reserve(keyframes.size());
    for (const auto& keyframe : keyframes) {
        SavedPose saved_pose;
        saved_pose.timestamp = keyframe->GetState().timestamp_;
        saved_pose.pose = options_.with_loop_closing_ ? keyframe->GetOptPose() : keyframe->GetLIOPose();
        map_poses.emplace_back(saved_pose.pose);
        snapshot_poses.emplace_back(saved_pose);
    }

    std::string save_path = path.empty() ? "./data/" + map_name_ + "/" : path;
    // The save_map service only passes map_id, so the default path keeps a
    // trailing separator.  std::filesystem::path("dir/").filename() is empty,
    // which would reject every save; strip separators before validating.
    while (save_path.size() > 1 &&
           (save_path.back() == '/' || save_path.back() == '\\')) {
        save_path.pop_back();
    }
    const std::filesystem::path final_path(save_path);
    if (final_path.filename().empty()) {
        LOG(ERROR) << "cannot save map: invalid destination path " << save_path;
        return false;
    }
    const std::filesystem::path parent_path =
        final_path.parent_path().empty() ? std::filesystem::path(".") : final_path.parent_path();
    const std::string token = SaveToken();
    const std::filesystem::path staging_path =
        parent_path / (final_path.filename().string() + ".saving-" + token);
    std::error_code filesystem_error;
    std::filesystem::create_directories(staging_path, filesystem_error);
    if (filesystem_error) {
        LOG(ERROR) << "cannot create map staging directory " << staging_path << ": "
                   << filesystem_error.message();
        return false;
    }
    StagingDirectoryGuard staging_guard{staging_path};
    const std::string staging_path_string = staging_path.string();

    // auto global_map_no_loop = lio_->GetGlobalMap(true);
    auto global_map = lio_->GetGlobalMap(keyframes, map_poses);
    // auto global_map_raw = lio_->GetGlobalMap(!options_.with_loop_closing_, false, 0.1);
    if (!global_map || global_map->empty()) {
        LOG(ERROR) << "cannot save map: global point cloud is empty";
        return false;
    }

    for (const auto &point : global_map->points) {
        if (!std::isfinite(point.x) || !std::isfinite(point.y) || !std::isfinite(point.z)) {
            LOG(ERROR) << "cannot save map: global point cloud contains non-finite coordinates";
            return false;
        }
    }

    LOG(INFO) << "slam map saving to staging directory " << staging_path_string;

    TiledMap::Options tm_options;
    tm_options.map_path_ = staging_path_string;

    TiledMap tm(tm_options);
    SE3 start_pose = map_poses.front();
    if (!tm.ConvertFromFullPCD(global_map, start_pose, staging_path_string)) {
        LOG(ERROR) << "failed to convert global point cloud to tiled map";
        return false;
    }

    if (pcl::io::savePCDFileBinaryCompressed(staging_path_string + "/global.pcd", *global_map) != 0) {
        LOG(ERROR) << "failed to write global point cloud to " << staging_path_string;
        return false;
    }
    // pcl::io::savePCDFileBinaryCompressed(save_path + "/global_no_loop.pcd", *global_map_no_loop);
    // pcl::io::savePCDFileBinaryCompressed(save_path + "/global_raw.pcd", *global_map_raw);

    if (options_.with_gridmap_) {
        /// 存为ROS兼容的模式
        if (!g2p5_ || !g2p5_->GetNewestMap()) {
            LOG(ERROR) << "cannot save map: 2D grid map is not ready";
            return false;
        }
        auto map = g2p5_->GetNewestMap()->ToROS();
        const int width = map.info.width;
        const int height = map.info.height;

        cv::Mat nav_image(height, width, CV_8UC1);
        for (int y = 0; y < height; ++y) {
            const int rowStartIndex = y * width;
            for (int x = 0; x < width; ++x) {
                const int index = rowStartIndex + x;
                int8_t data = map.data[index];
                if (data == 0) {                                   // Free
                    nav_image.at<uchar>(height - 1 - y, x) = 255;  // White
                } else if (data == 100) {                          // Occupied
                    nav_image.at<uchar>(height - 1 - y, x) = 0;    // Black
                } else {                                           // Unknown
                    nav_image.at<uchar>(height - 1 - y, x) = 128;  // Gray
                }
            }
        }

        if (!cv::imwrite(staging_path_string + "/map.pgm", nav_image)) {
            LOG(ERROR) << "failed to write map.pgm";
            return false;
        }

        /// yaml
        std::ofstream yamlFile(staging_path_string + "/map.yaml");
        if (!yamlFile.is_open()) {
            LOG(ERROR) << "failed to write map.yaml";
            return false;
        }

        try {
            YAML::Emitter emitter;
            emitter << YAML::BeginMap;
            emitter << YAML::Key << "image" << YAML::Value << "map.pgm";
            emitter << YAML::Key << "mode" << YAML::Value << "trinary";
            emitter << YAML::Key << "width" << YAML::Value << map.info.width;
            emitter << YAML::Key << "height" << YAML::Value << map.info.height;
            emitter << YAML::Key << "resolution" << YAML::Value << float(0.05);
            std::vector<double> orig{map.info.origin.position.x, map.info.origin.position.y, 0};
            emitter << YAML::Key << "origin" << YAML::Value << orig;
            emitter << YAML::Key << "negate" << YAML::Value << 0;
            emitter << YAML::Key << "occupied_thresh" << YAML::Value << 0.65;
            emitter << YAML::Key << "free_thresh" << YAML::Value << 0.25;

            emitter << YAML::EndMap;

            yamlFile << emitter.c_str();
            yamlFile.flush();
            if (!yamlFile) {
                yamlFile.close();
                return false;
            }
            yamlFile.close();
            if (yamlFile.fail()) {
                return false;
            }
        } catch (...) {
            yamlFile.close();
            return false;
        }
    }

    const auto has_content = [](const std::filesystem::path& file_path) {
        std::error_code error;
        return std::filesystem::is_regular_file(file_path, error) &&
               !error && std::filesystem::file_size(file_path, error) > 0 && !error;
    };
    if (!has_content(staging_path / "index.txt") || !has_content(staging_path / "global.pcd")) {
        LOG(ERROR) << "cannot commit map: required map files are missing or empty";
        return false;
    }

    const std::filesystem::path backup_path =
        parent_path / (final_path.filename().string() + ".previous-" + token);
    std::filesystem::remove_all(backup_path, filesystem_error);
    if (filesystem_error) {
        LOG(ERROR) << "cannot remove stale map backup " << backup_path << ": "
                   << filesystem_error.message();
        return false;
    }
    filesystem_error.clear();
    const bool final_exists = std::filesystem::exists(final_path, filesystem_error);
    if (filesystem_error) {
        LOG(ERROR) << "cannot inspect existing map " << final_path << ": "
                   << filesystem_error.message();
        return false;
    }
    if (final_exists) {
        std::filesystem::rename(final_path, backup_path, filesystem_error);
        if (filesystem_error) {
            LOG(ERROR) << "cannot stage existing map " << final_path << ": "
                       << filesystem_error.message();
            return false;
        }
    }
    filesystem_error.clear();
    std::filesystem::rename(staging_path, final_path, filesystem_error);
    if (filesystem_error) {
        LOG(ERROR) << "cannot commit map " << final_path << ": "
                   << filesystem_error.message();
        std::error_code restore_error;
        if (std::filesystem::exists(backup_path, restore_error)) {
            std::filesystem::rename(backup_path, final_path, restore_error);
            if (restore_error) {
                LOG(ERROR) << "cannot restore previous map " << final_path << ": "
                           << restore_error.message();
            }
        }
        return false;
    }
    staging_guard.committed = true;
    std::filesystem::remove_all(backup_path, filesystem_error);
    if (filesystem_error) {
        LOG(WARNING) << "cannot remove previous map backup " << backup_path << ": "
                     << filesystem_error.message();
    }
    saved_snapshot_poses_ = std::move(snapshot_poses);
    LOG(INFO) << "map saved";
    return true;
}

// ros服务回调，保存轨迹
// 如果请求里没有指定路径，则默认保存在./data/下，文件名为path_年月日时分秒.txt
// ros2 service call /lightning/save_path lightning/srv/SavePath
void SlamSystem::SavePath(const srv::SavePath::Request::SharedPtr request, srv::SavePath::Response::SharedPtr response) {
    try {
        std::string save_path = request->file_path;
        bool success = SavePath(save_path);
        response->success = success;
        if (success) {
            response->message = "Path saved successfully. Total poses: " + std::to_string(path_.poses.size());
        } else {
            response->message = "Failed to save path.";
        }
    } catch (const std::exception& error) {
        LOG(ERROR) << "save path service failed: " << error.what();
        response->success = false;
        response->message = "Failed to save path.";
    } catch (...) {
        LOG(ERROR) << "save path service failed with an unknown exception";
        response->success = false;
        response->message = "Failed to save path.";
    }
}

bool SlamSystem::SavePath(const std::string& path) {
    std::lock_guard<std::mutex> lock(lidar_process_mutex_);
    std::lock_guard<std::mutex> imu_lock(imu_process_mutex_);
    std::string save_path = path;
    if (save_path.empty()) {
        char time_str[64];
        time_t now = time(nullptr);
        strftime(time_str, sizeof(time_str), "%Y%m%d_%H%M%S", localtime(&now));
        save_path = "./data/path_" + std::string(time_str) + ".txt";
    }

    const std::filesystem::path final_path(save_path);
    if (final_path.filename().empty()) {
        LOG(ERROR) << "Failed to save path: invalid destination path " << save_path;
        return false;
    }
    const std::filesystem::path parent_path =
        final_path.parent_path().empty() ? std::filesystem::path(".") : final_path.parent_path();
    const std::filesystem::path temporary_path =
        parent_path / (final_path.filename().string() + ".saving-" + SaveToken());
    std::ofstream file(temporary_path);
    if (!file.is_open()) {
        LOG(ERROR) << "Failed to open temporary path file: " << temporary_path;
        return false;
    }
    file << "timestamp px py pz qx qy qz qw\n";
    if (!saved_snapshot_poses_.empty()) {
        for (const auto& saved_pose : saved_snapshot_poses_) {
            const auto q = saved_pose.pose.unit_quaternion();
            file << std::fixed << std::setprecision(9) << saved_pose.timestamp << " "
                 << std::setprecision(5) << saved_pose.pose.translation().x() << " "
                 << saved_pose.pose.translation().y() << " "
                 << saved_pose.pose.translation().z() << " "
                 << q.x() << " " << q.y() << " " << q.z() << " " << q.w() << "\n";
        }
    } else {
        for (const auto& pose : path_.poses) {
            file << std::fixed << std::setprecision(5)
                 << pose.header.stamp.sec << "." << std::setfill('0') << std::setw(9) << pose.header.stamp.nanosec << " "
                 << pose.pose.position.x << " " << pose.pose.position.y << " " << pose.pose.position.z << " "
                 << pose.pose.orientation.x << " " << pose.pose.orientation.y << " "
                 << pose.pose.orientation.z << " " << pose.pose.orientation.w << "\n";
        }
    }

    file.flush();
    if (!file) {
        file.close();
        std::error_code cleanup_error;
        std::filesystem::remove(temporary_path, cleanup_error);
        LOG(ERROR) << "Failed to flush path file: " << temporary_path;
        return false;
    }
    file.close();
    if (file.fail()) {
        std::error_code cleanup_error;
        std::filesystem::remove(temporary_path, cleanup_error);
        LOG(ERROR) << "Failed to close path file: " << temporary_path;
        return false;
    }
    std::error_code rename_error;
    std::filesystem::rename(temporary_path, final_path, rename_error);
    if (rename_error) {
        std::error_code cleanup_error;
        std::filesystem::remove(temporary_path, cleanup_error);
        LOG(ERROR) << "Failed to commit path file " << final_path << ": "
                   << rename_error.message();
        return false;
    }
    const size_t pose_count = saved_snapshot_poses_.empty() ? path_.poses.size() : saved_snapshot_poses_.size();
    LOG(INFO) << "Path saved to " << save_path << ". Total poses: " << pose_count;
    return true;
}


void SlamSystem::ProcessIMU(const lightning::IMUPtr& imu) {
    std::lock_guard<std::mutex> lock(imu_process_mutex_);
    if (running_ == false) {
        return;
    }

    if (options_.use_imu_init_ && !imu_inited_) {
        LOG(INFO) << "Auto-initializing slam pose from IMU orientation (ENU): "
                  << imu->orientation.coeffs().transpose();
        lio_->SetInitPose(SE3(imu->orientation, Vec3d::Zero()));
        imu_inited_ = true;
    }

    lio_->ProcessIMU(imu);
}

void SlamSystem::ProcessLidar(const sensor_msgs::msg::PointCloud2::SharedPtr& cloud) {
    std::lock_guard<std::mutex> lock(lidar_process_mutex_);
    if (running_ == false) {
        return;
    }

    lio_->ProcessPointCloud2(cloud);
    lio_->Run();
    if (lio_->IsDiverged()) {
        running_.store(false);
        LOG(ERROR) << "LIO diverged; stopping live mapping input";
        return;
    }

    if (options_.log_pose_opt_) {
        auto state = lio_->GetState();
        auto q = state.rot_.unit_quaternion();
        
        char log_buf[256];
        snprintf(log_buf, sizeof(log_buf), 
                "lio pose: [%.4f, %.4f, %.4f]\tq: [%.4f, %.4f, %.4f, %.4f]\tvelocity: [%.3f, %.3f, %.3f]m/s",
                state.pos_.x(), state.pos_.y(), state.pos_.z(),
                q.x(), q.y(), q.z(), q.w(),
                state.vel_.x(), state.vel_.y(), state.vel_.z());
        LOG(INFO) << log_buf;

        // printf("\rslam.cc:266] pose: [%.4f, %.4f, %.4f], q: [%.4f, %.4f, %.4f, %.4f], vel: [%.4f, %.4f, %.4f]           ", 
        //        state.pos_.x(), state.pos_.y(), state.pos_.z(),
        //        q.w(), q.x(), q.y(), q.z(),
        //        state.vel_.x(), state.vel_.y(), state.vel_.z());
        // fflush(stdout);
    }
    static uint8_t count = 0;
    if (nav_state_pub_ != nullptr) {
        auto state = lio_->GetState();
        // 真正的回环后的位姿，而非EKF的里程计位姿
        SE3 pose_opt = lio_->GetOptPose();
        auto q_opt = pose_opt.unit_quaternion();

        msg::NavState ns;
        ns.header.stamp = cloud->header.stamp;
        ns.header.frame_id = "map";
        ns.pose.position.x = pose_opt.translation().x();
        ns.pose.position.y = pose_opt.translation().y();
        ns.pose.position.z = pose_opt.translation().z();
        ns.pose.orientation.x = q_opt.x();
        ns.pose.orientation.y = q_opt.y();
        ns.pose.orientation.z = q_opt.z();
        ns.pose.orientation.w = q_opt.w();
        ns.velocity.x = state.vel_.x();
        ns.velocity.y = state.vel_.y();
        ns.velocity.z = state.vel_.z();
        ns.confidence = 1.0;
        ns.pose_is_ok = true;
        nav_state_pub_->publish(ns);

        if (tf_broadcaster_ != nullptr) {
            geometry_msgs::msg::TransformStamped tf_msg;
            tf_msg.header = ns.header;
            tf_msg.child_frame_id = "lidar_link";
            tf_msg.transform.translation.x = ns.pose.position.x;
            tf_msg.transform.translation.y = ns.pose.position.y;
            tf_msg.transform.translation.z = ns.pose.position.z;
            tf_msg.transform.rotation = ns.pose.orientation;
            tf_broadcaster_->sendTransform(tf_msg);
        }

        if (odom_pub_ != nullptr) {
            nav_msgs::msg::Odometry odom;
            odom.header = ns.header;
            odom.child_frame_id = "lidar_link";
            odom.pose.pose = ns.pose;
            odom.twist.twist.linear = ns.velocity;
            odom_pub_->publish(odom);
        }

        if (options_.enable_path_rviz_ && path_pub_ != nullptr) {
            geometry_msgs::msg::PoseStamped ps;
            if(count<10){
                LOG(INFO) << "publishing path pose: ["
                          << ns.pose.position.x << ", " << ns.pose.position.y << ", " << ns.pose.position.z<< "]";
                count++;
            }
            ps.header = cloud->header;
            ps.pose = ns.pose;
            path_.header = ns.header;
            path_.poses.push_back(ps);
            path_pub_->publish(path_);
        }
    } else if (options_.enable_path_rviz_) {
        // 离线模式或未启用 pub_odom 时，手动维护 path_
        SE3 pose_opt = lio_->GetOptPose();
        auto q_opt = pose_opt.unit_quaternion();

        geometry_msgs::msg::PoseStamped ps;
        ps.header = cloud->header;
        ps.header.frame_id = "map";
        ps.pose.position.x = pose_opt.translation().x();
        ps.pose.position.y = pose_opt.translation().y();
        ps.pose.position.z = pose_opt.translation().z();
        ps.pose.orientation.x = q_opt.x();
        ps.pose.orientation.y = q_opt.y();
        ps.pose.orientation.z = q_opt.z();
        ps.pose.orientation.w = q_opt.w();

        if (count < 10) {
            LOG(INFO) << "recording path pose (no pub): [" << ps.pose.position.x << ", " << ps.pose.position.y
                      << ", " << ps.pose.position.z << "]";
            count++;
        }

        path_.header = ps.header;
        path_.poses.push_back(ps);
    } 

    if (options_.enable_lidar_rviz_ && cloud_pub_ != nullptr) {
        auto scan_world = lio_->GetScanDownWorld();
        if (scan_world && !scan_world->empty()) {
            sensor_msgs::msg::PointCloud2 scan_msg;
            pcl::toROSMsg(*scan_world, scan_msg);
            scan_msg.header.frame_id = "map";
            scan_msg.header.stamp = cloud->header.stamp;
            cloud_pub_->publish(scan_msg);
        }
    }

    auto kf = lio_->GetKeyframe();
    if (kf != cur_kf_) {
        cur_kf_ = kf;
    } else {
        return;
    }

    if (cur_kf_ == nullptr) {
        return;
    }

    if (options_.with_loop_closing_) {
        lc_->AddKF(cur_kf_);
    }

    if (options_.with_gridmap_) {
        g2p5_->PushKeyframe(cur_kf_);
    }

    if (ui_) {
        ui_->UpdateKF(cur_kf_);
    }

    if (map_pub_ != nullptr) {
        static int kf_count = 0;
        if (kf_count++ % 3 == 0) { // 每3个关键帧发布一个全局地图
            auto global_map = lio_->GetGlobalMap(!options_.with_loop_closing_);
            sensor_msgs::msg::PointCloud2 ros_map;
            pcl::toROSMsg(*global_map, ros_map);
            ros_map.header.frame_id = "map";
            ros_map.header.stamp = node_->now();
            map_pub_->publish(ros_map);
        }
    }
}

void SlamSystem::ProcessLidar(const livox_ros_driver2::msg::CustomMsg::SharedPtr& cloud) {
    std::lock_guard<std::mutex> lock(lidar_process_mutex_);
    if (running_ == false) {
        return;
    }

    lio_->ProcessPointCloud2(cloud);
    lio_->Run();
    if (lio_->IsDiverged()) {
        running_.store(false);
        LOG(ERROR) << "LIO diverged; stopping live mapping input";
        return;
    }

    if (options_.log_pose_opt_) {
        auto state = lio_->GetState();
        auto q = state.rot_.unit_quaternion();
        
        char log_buf[256];
        snprintf(log_buf, sizeof(log_buf), 
                "lio pose: [%.4f, %.4f, %.4f]\tq: [%.4f, %.4f, %.4f, %.4f]\tvelocity: [%.3f, %.3f, %.3f]m/s",
                state.pos_.x(), state.pos_.y(), state.pos_.z(),
                q.x(), q.y(), q.z(), q.w(),
                state.vel_.x(), state.vel_.y(), state.vel_.z());
        LOG(INFO) << log_buf;

        // printf("\rslam.cc:374] pose: [%.4f, %.4f, %.4f], q: [%.4f, %.4f, %.4f, %.4f], vel: [%.4f, %.4f, %.4f]           ", 
        //        state.pos_.x(), state.pos_.y(), state.pos_.z(),
        //        q.w(), q.x(), q.y(), q.z(),
        //        state.vel_.x(), state.vel_.y(), state.vel_.z());
        // fflush(stdout);
    }
    static uint8_t count = 0;
    if (nav_state_pub_ != nullptr) {
        auto state = lio_->GetState();
        // 真正的回环后的位姿，而非EKF的里程计位姿
        SE3 pose_opt = lio_->GetOptPose();
        auto q_opt = pose_opt.unit_quaternion();

        msg::NavState ns;
        ns.header.stamp = cloud->header.stamp;
        ns.header.frame_id = "map";
        ns.pose.position.x = pose_opt.translation().x();
        ns.pose.position.y = pose_opt.translation().y();
        ns.pose.position.z = pose_opt.translation().z();
        ns.pose.orientation.x = q_opt.x();
        ns.pose.orientation.y = q_opt.y();
        ns.pose.orientation.z = q_opt.z();
        ns.pose.orientation.w = q_opt.w();
        ns.velocity.x = state.vel_.x();
        ns.velocity.y = state.vel_.y();
        ns.velocity.z = state.vel_.z();
        ns.confidence = 1.0;
        ns.pose_is_ok = true;
        nav_state_pub_->publish(ns);

        if (tf_broadcaster_ != nullptr) {
            geometry_msgs::msg::TransformStamped tf_msg;
            tf_msg.header = ns.header;
            tf_msg.child_frame_id = "lidar_link";
            tf_msg.transform.translation.x = ns.pose.position.x;
            tf_msg.transform.translation.y = ns.pose.position.y;
            tf_msg.transform.translation.z = ns.pose.position.z;
            tf_msg.transform.rotation = ns.pose.orientation;
            tf_broadcaster_->sendTransform(tf_msg);
        }

        if (odom_pub_ != nullptr) {
            nav_msgs::msg::Odometry odom;
            odom.header = ns.header;
            odom.child_frame_id = "lidar_link";
            odom.pose.pose = ns.pose;
            odom.twist.twist.linear = ns.velocity;
            odom_pub_->publish(odom);
        }

        if (options_.enable_path_rviz_ && path_pub_ != nullptr) {
            geometry_msgs::msg::PoseStamped ps;
            ps.header = cloud->header;
            ps.pose = ns.pose;
            path_.header = ns.header;
            path_.poses.push_back(ps);
            path_pub_->publish(path_);
        }
    }else if (options_.enable_path_rviz_) {
        // 离线模式或未启用 pub_odom 时，手动维护 path_
        SE3 pose_opt = lio_->GetOptPose();
        auto q_opt = pose_opt.unit_quaternion();

        geometry_msgs::msg::PoseStamped ps;
        ps.header = cloud->header;
        ps.header.frame_id = "map";
        ps.pose.position.x = pose_opt.translation().x();
        ps.pose.position.y = pose_opt.translation().y();
        ps.pose.position.z = pose_opt.translation().z();
        ps.pose.orientation.x = q_opt.x();
        ps.pose.orientation.y = q_opt.y();
        ps.pose.orientation.z = q_opt.z();
        ps.pose.orientation.w = q_opt.w();

        if (count < 10) {
            LOG(INFO) << "recording path pose (no pub): [" << ps.pose.position.x << ", " << ps.pose.position.y
                      << ", " << ps.pose.position.z << "]";
            count++;
        }

        path_.header = ps.header;
        path_.poses.push_back(ps);
    }

    if (options_.enable_lidar_rviz_ && cloud_pub_ != nullptr) {
        auto scan_world = lio_->GetScanDownWorld();
        if (scan_world && !scan_world->empty()) {
            sensor_msgs::msg::PointCloud2 scan_msg;
            pcl::toROSMsg(*scan_world, scan_msg);
            scan_msg.header.frame_id = "map";
            scan_msg.header.stamp = cloud->header.stamp;
            cloud_pub_->publish(scan_msg);
        }
    }

    auto kf = lio_->GetKeyframe();
    if (kf != cur_kf_) {
        cur_kf_ = kf;
    } else {
        return;
    }

    if (cur_kf_ == nullptr) {
        return;
    }

    if (options_.with_loop_closing_) {
        lc_->AddKF(cur_kf_);
    }

    if (options_.with_gridmap_) {
        g2p5_->PushKeyframe(cur_kf_);
    }

    if (ui_) {
        ui_->UpdateKF(cur_kf_);
    }

    if (map_pub_ != nullptr) {
        static int kf_count_livox = 0;
        if (kf_count_livox++ % 3 == 0) { // 每3个关键帧发布一个全局地图
            auto global_map = lio_->GetGlobalMap(!options_.with_loop_closing_);
            sensor_msgs::msg::PointCloud2 ros_map;
            pcl::toROSMsg(*global_map, ros_map);
            ros_map.header.frame_id = "map";
            ros_map.header.stamp = node_->now();
            map_pub_->publish(ros_map);
        }
    }
}

void SlamSystem::Spin() {
    if (options_.online_mode_ && node_ != nullptr) {
        // Keep IMU delivery independent from the long point-cloud callback.
        // LaserMapping serializes cloud updates, while its input buffers are
        // protected separately so IMU samples remain timestamp-continuous.
        rclcpp::executors::MultiThreadedExecutor executor(
            rclcpp::ExecutorOptions(), 3);
        executor.add_node(node_);
        executor.spin();
    }
}

}  // namespace lightning
