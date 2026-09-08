#include <pcl/common/transforms.h>
#include <yaml-cpp/yaml.h>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <sstream>

#include "common/options.h"
#include "core/lightning_math.hpp"
#include "laser_mapping.h"
#include "ui/pangolin_window.h"
#include "wrapper/ros_utils.h"

namespace lightning {

bool LaserMapping::Init(const std::string &config_yaml) {
    LOG(INFO) << "init laser mapping from " << config_yaml;
    if (!LoadParamsFromYAML(config_yaml)) {
        return false;
    }

    // localmap init (after LoadParams)
    ivox_ = std::make_shared<IVoxType>(ivox_options_);

    // esekf init
    ESKF::Options eskf_options;
    eskf_options.max_iterations_ = fasterlio::NUM_MAX_ITERATIONS;
    eskf_options.epsi_ = 1e-3 * Eigen::Matrix<double, 23, 1>::Ones();
    eskf_options.lidar_obs_func_ = [this](NavState &s, ESKF::CustomObservationModel &obs) { ObsModel(s, obs); };
    eskf_options.orientation_obs_func_ = [this](NavState &s, ESKF::CustomObservationModel &obs) { OriObsModel(s, obs); };
    eskf_options.use_aa_ = use_aa_;
    kf_.Init(eskf_options);
    kf_imu_.Init(eskf_options);

    return true;
}

bool LaserMapping::LoadParamsFromYAML(const std::string &yaml_file) {
    // get params from yaml
    int lidar_type, ivox_nearby_type;
    double gyr_cov, acc_cov, b_gyr_cov, b_acc_cov;
    double filter_size_scan;
    Vec3d lidar_T_wrt_IMU;
    Mat3d lidar_R_wrt_IMU;

    auto yaml = YAML::LoadFile(yaml_file);
    try {
        fasterlio::NUM_MAX_ITERATIONS = yaml["fasterlio"]["max_iteration"].as<int>();
        fasterlio::ESTI_PLANE_THRESHOLD = yaml["fasterlio"]["esti_plane_threshold"].as<float>();

        filter_size_scan = yaml["fasterlio"]["filter_size_scan"].as<float>();
        filter_size_map_min_ = yaml["fasterlio"]["filter_size_map"].as<float>();
        keep_first_imu_estimation_ = yaml["fasterlio"]["keep_first_imu_estimation"].as<bool>();
        gyr_cov = yaml["fasterlio"]["gyr_cov"].as<float>();
        acc_cov = yaml["fasterlio"]["acc_cov"].as<float>();
        b_gyr_cov = yaml["fasterlio"]["b_gyr_cov"].as<float>();
        b_acc_cov = yaml["fasterlio"]["b_acc_cov"].as<float>();
        preprocess_->Blind() = yaml["fasterlio"]["blind"].as<double>();
        preprocess_->TimeScale() = yaml["fasterlio"]["time_scale"].as<double>();
        lidar_type = yaml["fasterlio"]["lidar_type"].as<int>();
        preprocess_->NumScans() = yaml["fasterlio"]["scan_line"].as<int>();
        preprocess_->PointFilterNum() = yaml["fasterlio"]["point_filter_num"].as<int>();
        extrinsic_est_en_ = yaml["fasterlio"]["extrinsic_est_en"].as<bool>();
        extrinT_ = yaml["fasterlio"]["extrinsic_T"].as<std::vector<double>>();
        extrinR_ = yaml["fasterlio"]["extrinsic_R"].as<std::vector<double>>();

        ivox_options_.resolution_ = yaml["fasterlio"]["ivox_grid_resolution"].as<float>();
        ivox_nearby_type = yaml["fasterlio"]["ivox_nearby_type"].as<int>();
        use_aa_ = yaml["fasterlio"]["use_aa"].as<bool>();
        use_imu_orient_ = yaml["system"]["use_imu_orient"] ? yaml["system"]["use_imu_orient"].as<bool>() : false;

        skip_lidar_num_ = yaml["fasterlio"]["skip_lidar_num"].as<int>();
        enable_skip_lidar_ = skip_lidar_num_ > 0;

        // 2026-08-21 关键帧密度可配 + 时间兜底 + 发散保护阈值。
        // 全部带原厂默认值回退, 旧 yaml 无需改动即可运行。
        if (yaml["fasterlio"]["kf_dis_th"]) {
            options_.kf_dis_th_ = yaml["fasterlio"]["kf_dis_th"].as<double>();
        }
        if (yaml["fasterlio"]["kf_angle_th_deg"]) {
            options_.kf_angle_th_ = yaml["fasterlio"]["kf_angle_th_deg"].as<double>() * M_PI / 180.0;
        }
        if (yaml["fasterlio"]["kf_time_th"]) {
            options_.kf_time_th_ = yaml["fasterlio"]["kf_time_th"].as<double>();
        }
        if (yaml["fasterlio"]["diverge_pos_bound_m"]) {
            options_.diverge_pos_bound_m_ = yaml["fasterlio"]["diverge_pos_bound_m"].as<double>();
        }
        if (yaml["fasterlio"]["diverge_vel_bound_mps"]) {
            options_.diverge_vel_bound_mps_ = yaml["fasterlio"]["diverge_vel_bound_mps"].as<double>();
        }
        if (yaml["fasterlio"]["diverge_fast_streak"]) {
            options_.diverge_fast_streak_ = yaml["fasterlio"]["diverge_fast_streak"].as<int>();
        }
        if (yaml["fasterlio"]["diverge_no_effect_frames"]) {
            options_.diverge_no_effect_frames_ = yaml["fasterlio"]["diverge_no_effect_frames"].as<int>();
        }
        if (const char* health_env = std::getenv("M20PRO_LIGHTNING_HEALTH_FILE")) {
            health_file_path_ = health_env;
        }

        float height_max = yaml["roi"]["height_max"].as<float>();
        float height_min = yaml["roi"]["height_min"].as<float>();

        preprocess_->SetHeightROI(height_max, height_min);

    } catch (...) {
        LOG(ERROR) << "bad conversion";
        return false;
    }

    LOG(INFO) << "lidar_type " << lidar_type;
    if (lidar_type == 1) {
        preprocess_->SetLidarType(LidarType::AVIA);
        LOG(INFO) << "Using AVIA Lidar";
    } else if (lidar_type == 2) {
        preprocess_->SetLidarType(LidarType::VELO32);
        LOG(INFO) << "Using Velodyne 32 Lidar";
    } else if (lidar_type == 3) {
        preprocess_->SetLidarType(LidarType::OUST64);
        LOG(INFO) << "Using OUST 64 Lidar";
    } else if (lidar_type == 4) {
        preprocess_->SetLidarType(LidarType::RoboSense);
        LOG(INFO) << "Using RoboSense Lidar";
    } else {
        LOG(WARNING) << "unknown lidar_type";
        return false;
    }

    if (ivox_nearby_type == 0) {
        ivox_options_.nearby_type_ = IVoxType::NearbyType::CENTER;
    } else if (ivox_nearby_type == 6) {
        ivox_options_.nearby_type_ = IVoxType::NearbyType::NEARBY6;
    } else if (ivox_nearby_type == 18) {
        ivox_options_.nearby_type_ = IVoxType::NearbyType::NEARBY18;
    } else if (ivox_nearby_type == 26) {
        ivox_options_.nearby_type_ = IVoxType::NearbyType::NEARBY26;
    } else {
        LOG(WARNING) << "unknown ivox_nearby_type, use NEARBY18";
        ivox_options_.nearby_type_ = IVoxType::NearbyType::NEARBY18;
    }

    voxel_scan_.setLeafSize(filter_size_scan, filter_size_scan, filter_size_scan);

    lidar_T_wrt_IMU = math::VecFromArray<double>(extrinT_);
    lidar_R_wrt_IMU = math::MatFromArray<double>(extrinR_);

    p_imu_->SetExtrinsic(lidar_T_wrt_IMU, lidar_R_wrt_IMU);
    p_imu_->SetGyrCov(Vec3d(gyr_cov, gyr_cov, gyr_cov));
    p_imu_->SetAccCov(Vec3d(acc_cov, acc_cov, acc_cov));
    p_imu_->SetGyrBiasCov(Vec3d(b_gyr_cov, b_gyr_cov, b_gyr_cov));
    p_imu_->SetAccBiasCov(Vec3d(b_acc_cov, b_acc_cov, b_acc_cov));

    return true;
}

LaserMapping::LaserMapping(Options options) : options_(options) {
    preprocess_.reset(new PointCloudPreprocess());
    p_imu_.reset(new ImuProcess());
}

void LaserMapping::SetInitPose(const SE3 &pose) {
    LOG(INFO) << "initial pose lio: " << pose.so3().unit_quaternion().coeffs().transpose();
    auto x = kf_imu_.GetX();
    x.rot_ = SO3(pose.unit_quaternion());
    x.pos_ = pose.translation();
    kf_imu_.ChangeX(x);

    x = kf_.GetX();
    x.rot_ = SO3(pose.unit_quaternion());
    x.pos_ = pose.translation();
    kf_.ChangeX(x);

    LOG(INFO) << "set initial translatoin in laser mapping: " << pose.translation().transpose();
}

void LaserMapping::ProcessIMU(const lightning::IMUPtr &imu) {
    publish_count_++;

    double timestamp = imu->timestamp;

    UL lock(mtx_buffer_);
    // A delayed or duplicated sample must never rewind the prediction clock.
    // Clearing the already synchronized buffer here loses the temporal bridge
    // needed by the next lidar scan and causes large negative/positive dt jumps.
    if (timestamp <= last_timestamp_imu_) {
        LOG(WARNING) << "discard stale imu sample, dt=" << timestamp - last_timestamp_imu_;
        return;
    }

    if (p_imu_->IsIMUInited()) {
        /// 更新最新imu状态
        kf_imu_.Predict(timestamp - last_timestamp_imu_, p_imu_->Q_, imu->angular_velocity, imu->linear_acceleration);

        // 使用 IMU 朝向观测进行更新。
        // 这里将观测方差固定为 0.01 rad^2（约 0.1 rad ≈ 5.7° 的 1σ 误差），作为中等精度 IMU 的经验值。
        // 若使用更高/更低精度的 IMU，可根据陀螺噪声特性离线标定后调整该值，以平衡预测与观测的权重。
        if (use_imu_orient_) {
            kf_imu_.Update(ESKF::ObsType::ORIENTATION, 0.01);
        }

        // LOG(INFO) << "newest wrt lidar: " << timestamp - kf_.GetX().timestamp_;

        /// 更新ui
        if (ui_) {
            ui_->UpdateNavState(kf_imu_.GetX());
        }
    }

    last_timestamp_imu_ = timestamp;
    {
        UL imu_state_lock(mtx_imu_state_);
        last_imu_ = imu;
    }

    imu_buffer_.emplace_back(imu);
}

bool LaserMapping::Run() {
    if (!SyncPackages()) {
        LOG(WARNING) << "sync package failed";
        return false;
    }

    /// IMU process, kf prediction, undistortion
    p_imu_->Process(measures_, kf_, scan_undistort_);

    if (!scan_undistort_ || scan_undistort_->empty()) {
        LOG(WARNING) << "No point, skip this scan!";
        return false;
    }

    /// the first scan
    if (flg_first_scan_) {
        LOG(INFO) << "first scan pts: " << scan_undistort_->size();

        state_point_ = kf_.GetX();
        scan_down_world_->resize(scan_undistort_->size());
        for (int i = 0; i < scan_undistort_->size(); i++) {
            PointBodyToWorld(scan_undistort_->points[i], scan_down_world_->points[i]);
        }
        ivox_->AddPoints(scan_down_world_->points);

        first_lidar_time_ = measures_.lidar_end_time_;
        state_point_.timestamp_ = lidar_end_time_;
        flg_first_scan_ = false;
        return true;
    }

    if (enable_skip_lidar_) {
        skip_lidar_cnt_++;
        skip_lidar_cnt_ = skip_lidar_cnt_ % skip_lidar_num_;

        if (skip_lidar_cnt_ != 0) {
            /// 更新UI中的内容
            if (ui_) {
                ui_->UpdateNavState(kf_.GetX());
                ui_->UpdateScan(scan_undistort_, kf_.GetX().GetPose());
            }

            return false;
        }
    }

    // LOG(INFO) << "LIO get cloud at beg: " << std::setprecision(14) << measures_.lidar_begin_time_
    //           << ", end: " << measures_.lidar_end_time_;

    // 断流阈值必须与 skip_lidar_num 联动: 该检查只在被处理(未跳过)的扫描上
    // 执行, 相邻处理帧的标称间隔为 (skip+1)/雷达频率(约10Hz)。skip>0 时沿用
    // 固定 0.5s 会把正常跳帧误报为断流 (2026-08-19 实测 skip=4 时逐帧误报)。
    // 取标称间隔 5 倍裕量; 真实断流(间隔无界增长)仍会被捕获。
    const double lidar_gap_threshold =
        std::max(0.5, 0.1 * (skip_lidar_num_ + 1) * 5.0);
    if (last_lidar_time_ > 0 && (measures_.lidar_begin_time_ - last_lidar_time_) > lidar_gap_threshold) {
        LOG(ERROR) << "检测到雷达断流，时长：" << (measures_.lidar_begin_time_ - last_lidar_time_);
    }

    last_lidar_time_ = measures_.lidar_begin_time_;

    flg_EKF_inited_ = (measures_.lidar_begin_time_ - first_lidar_time_) >= fasterlio::INIT_TIME;

    /// downsample
    voxel_scan_.setInputCloud(scan_undistort_);
    voxel_scan_.filter(*scan_down_body_);

    int cur_pts = scan_down_body_->size();
    if (cur_pts < 5) {
        LOG(WARNING) << "Too few points, skip this scan!" << scan_undistort_->size() << ", " << scan_down_body_->size();
        return false;
    }
    
    if (cur_pts < (scan_undistort_->size() * 0.1)) {
        /// 降采样太狠了,有效点数不够，用

        auto v = voxel_scan_;
        v.setLeafSize(0.1, 0.1, 0.1);
        v.setInputCloud(scan_undistort_);
        v.filter(*scan_down_body_);
        cur_pts = scan_down_body_->size();
    }

    scan_down_world_->resize(cur_pts);
    nearest_points_.resize(cur_pts);

    Timer::Evaluate(
        [&, this]() {
            // 成员变量预分配
            residuals_.resize(cur_pts, 0);
            point_selected_surf_.resize(cur_pts, 1);
            plane_coef_.resize(cur_pts, Vec4f::Zero());

            auto old_state = kf_.GetX();

            if (use_imu_orient_) {
                kf_.Update(ESKF::ObsType::ORIENTATION, 0.01);
            }

            kf_.Update(ESKF::ObsType::LIDAR, 1e-3);
            state_point_ = kf_.GetX();

            if (keep_first_imu_estimation_ && all_keyframes_.size() < 5 &&
                (old_state.rot_.inverse() * state_point_.rot_).log().norm() > 0.3 * M_PI / 180) {
                kf_.ChangeX(old_state);
                state_point_ = old_state;

                LOG(INFO) << "set state as prediction";
            }

            SE3 delta = old_state.GetPose().inverse() * state_point_.GetPose();
            LOG(INFO) << "delta norm: " << delta.translation().norm() << ", " << delta.so3().log().norm() * 180 / M_PI;

            // LOG(INFO) << "old yaw: " << old_state.rot_.angleZ() << ", new: " << state_point_.rot_.angleZ();

            state_point_.timestamp_ = measures_.lidar_end_time_;
            euler_cur_ = state_point_.rot_;
            pos_lidar_ = state_point_.pos_ + state_point_.rot_ * state_point_.offset_t_lidar_;
        },
        "IEKF Solve and Update");

    CheckDivergence();

    // update local map
    Timer::Evaluate([&, this]() { MapIncremental(); }, "    Incremental Mapping");
    LOG(INFO) << "[ mapping ]: In num: " << scan_undistort_->points.size() << " down " << cur_pts
              << " Map grid num: " << ivox_->NumValidGrids() << " effect num : " << effect_feat_num_;
    // printf("\rlaser_mapping.cc:251] [ mapping ]: In num: %lu down %d Map grid num: %lu effect num : %d            ",
    //        scan_undistort_->points.size(), cur_pts, ivox_->NumValidGrids(), effect_feat_num_);
    // fflush(stdout);

    /// keyframes
    /// 发散后禁止新增关键帧: 发散位姿每帧跳变远超 kf_dis_th, 会把每一帧都
    /// 变成关键帧 (2026-08-21 16:47 会话 43 分钟积累 4925 个垃圾关键帧),
    /// 内存随存档需求爆炸且存档结果无意义。
    if (!diverged_ && last_kf_ == nullptr) {
        MakeKF();
    } else if (!diverged_) {
        SE3 last_pose = last_kf_->GetLIOPose();
        SE3 cur_pose = state_point_.GetPose();
        if ((last_pose.translation() - cur_pose.translation()).norm() > options_.kf_dis_th_ ||
            (last_pose.so3().inverse() * cur_pose.so3()).log().norm() > options_.kf_angle_th_) {
            MakeKF();
        } else if (!options_.is_in_slam_mode_ && (state_point_.timestamp_ - last_kf_->GetState().timestamp_) > 2.0) {
            MakeKF();
        } else if (options_.is_in_slam_mode_ && options_.kf_time_th_ > 0 &&
                   (state_point_.timestamp_ - last_kf_->GetState().timestamp_) > options_.kf_time_th_) {
            // 建图模式时间兜底: 静止/缓慢挪动时也按固定间隔留关键帧, 让同一
            // 场景的多视角观测进入存档 (对原地小幅移动补洞有用)。
            MakeKF();
        }
    }

    /// 更新kf_for_imu. IMU callbacks may continue while this scan is solved.
    {
        UL lock(mtx_buffer_);
        kf_imu_ = kf_;
        if (!measures_.imu_.empty()) {
            double t = measures_.imu_.back()->timestamp;
            for (auto &imu : imu_buffer_) {
                double dt = imu->timestamp - t;
                if (dt <= 0.0) {
                    continue;
                }
                kf_imu_.Predict(dt, p_imu_->Q_, imu->angular_velocity, imu->linear_acceleration);
                t = imu->timestamp;
            }
        }
    }

    if (ui_) {
        ui_->UpdateScan(scan_undistort_, state_point_.GetPose());
    }

    return true;
}

void LaserMapping::MakeKF() {
    // 2026-08-13 关键帧存储修复: 原实现把未抽稀的 scan_undistort_ 存入关键帧,
    // 走动建图时内存与存档体积随关键帧数爆炸 (每帧 3 万+ 点 × 上千关键帧),
    // 最终 save_map 超时/失败。改为存入体素抽稀后的 scan_down_body_ 副本
    // (地图密度由 filter_size_scan 控制), 内存与存档缩小约 14 倍; v4 配置下
    // 关键帧点云只被 GetGlobalMap 存档消费 (loop_closing/g2p5 均关闭)。
    // 注意 Foxy/PCL 1.10 的 CloudPtr 是 boost::shared_ptr。
    CloudPtr kf_cloud(new PointCloudType(*scan_down_body_));
    Keyframe::Ptr kf = std::make_shared<Keyframe>(kf_id_++, kf_cloud, state_point_);

    if (last_kf_) {
        // LOG(INFO) << "last kf lio: " << last_kf_->GetLIOPose().translation().transpose()
        //           << ", opt: " << last_kf_->GetOptPose().translation().transpose();

        /// opt pose 用之前的递推
        SE3 delta = last_kf_->GetLIOPose().inverse() * kf->GetLIOPose();
        kf->SetOptPose(last_kf_->GetOptPose() * delta);
    } else {
        kf->SetOptPose(kf->GetLIOPose());
    }

    kf->SetState(state_point_);

    LOG(INFO) << "LIO: create kf " << kf->GetID() << ", state: " << state_point_.pos_.transpose()
              << ", kf opt pose: " << kf->GetOptPose().translation().transpose()
              << ", lio pose: " << kf->GetLIOPose().translation().transpose();

    // printf("\033[34m\rlaser_mapping.cc:302] LIO: create kf %d, state: [%.3f, %.3f, %.3f], kf opt pose: [%.3f, %.3f, %.3f]\033[0m           ",
    //        kf->GetID(), state_point_.pos_.x(), state_point_.pos_.y(), state_point_.pos_.z(),
    //        kf->GetOptPose().translation().x(), kf->GetOptPose().translation().y(), kf->GetOptPose().translation().z());
    // fflush(stdout);

    if (options_.is_in_slam_mode_) {
        all_keyframes_.emplace_back(kf);
    }

    last_kf_ = kf;
}

void LaserMapping::ProcessPointCloud2(const sensor_msgs::msg::PointCloud2::SharedPtr &msg) {
    UL lock(mtx_buffer_);
    Timer::Evaluate(
        [&, this]() {
            scan_count_++;
            double timestamp = ToSec(msg->header.stamp);
            if (timestamp <= last_timestamp_lidar_) {
                LOG(ERROR) << "discard stale lidar sample, dt: " << timestamp - last_timestamp_lidar_;
                return;
            }
            LOG(INFO) << "get cloud at " << std::setprecision(14) << timestamp
                      << ", latest imu: " << last_timestamp_imu_;

            // printf("\rlaser_mapping.cc:324] get cloud at %.14f, latest imu: %.14f           ", timestamp, last_timestamp_imu_);
            // fflush(stdout);

            CloudPtr cloud(new PointCloudType());
            preprocess_->Process(msg, cloud);

            lidar_buffer_.push_back(cloud);
            time_buffer_.push_back(timestamp);
            last_timestamp_lidar_ = timestamp;
        },
        "Preprocess (Standard)");
}

void LaserMapping::ProcessPointCloud2(const livox_ros_driver2::msg::CustomMsg::SharedPtr &msg) {
    UL lock(mtx_buffer_);
    Timer::Evaluate(
        [&, this]() {
            scan_count_++;
            double timestamp = ToSec(msg->header.stamp);
            if (timestamp <= last_timestamp_lidar_) {
                LOG(ERROR) << "discard stale lidar sample, dt: " << timestamp - last_timestamp_lidar_;
                return;
            }

            // LOG(INFO) << "get cloud at " << std::setprecision(14) << timestamp
            //           << ", latest imu: " << last_timestamp_imu_;

            CloudPtr cloud(new PointCloudType());
            preprocess_->Process(msg, cloud);

            lidar_buffer_.push_back(cloud);
            time_buffer_.push_back(timestamp);
            last_timestamp_lidar_ = timestamp;
        },
        "Preprocess (Standard)");
}

void LaserMapping::ProcessPointCloud2(CloudPtr cloud) {
    UL lock(mtx_buffer_);
    Timer::Evaluate(
        [&, this]() {
            scan_count_++;

            double timestamp = math::ToSec(cloud->header.stamp);
            if (timestamp <= last_timestamp_lidar_) {
                LOG(ERROR) << "discard stale lidar sample, dt: " << timestamp - last_timestamp_lidar_;
                return;
            }

            lidar_buffer_.push_back(cloud);
            time_buffer_.push_back(timestamp);
            last_timestamp_lidar_ = timestamp;
        },
        "Preprocess (Standard)");
}

bool LaserMapping::SyncPackages() {
    UL lock(mtx_buffer_);
    if (lidar_buffer_.empty() || imu_buffer_.empty()) {
        return false;
    }

    /*** push a lidar scan ***/
    if (!lidar_pushed_) {
        measures_.scan_ = lidar_buffer_.front();
        measures_.lidar_begin_time_ = time_buffer_.front();

        if (measures_.scan_->points.size() <= 1) {
            LOG(WARNING) << "Too few input point cloud!";
            lidar_end_time_ = measures_.lidar_begin_time_ + lidar_mean_scantime_;
        } else if (measures_.scan_->points.back().timestamp / double(1000) < 0.5 * lidar_mean_scantime_) {
            lidar_end_time_ = measures_.lidar_begin_time_ + lidar_mean_scantime_;
        } else {
            scan_num_++;
            lidar_end_time_ = measures_.lidar_begin_time_ + measures_.scan_->points.back().timestamp / double(1000);
            lidar_mean_scantime_ +=
                (measures_.scan_->points.back().timestamp / double(1000) - lidar_mean_scantime_) / scan_num_;
        }

        lo::lidar_time_interval = lidar_mean_scantime_;

        measures_.lidar_end_time_ = lidar_end_time_;
        lidar_pushed_ = true;
    }

    if (last_timestamp_imu_ < lidar_end_time_) {
        return false;
    }

    /*** push imu_ data, and pop from imu_ buffer ***/
    double imu_time = imu_buffer_.front()->timestamp;
    measures_.imu_.clear();
    while ((!imu_buffer_.empty()) && (imu_time < lidar_end_time_)) {
        imu_time = imu_buffer_.front()->timestamp;
        if (imu_time > lidar_end_time_) {
            break;
        }

        measures_.imu_.push_back(imu_buffer_.front());

        imu_buffer_.pop_front();
    }

    lidar_buffer_.pop_front();
    time_buffer_.pop_front();
    lidar_pushed_ = false;

    // LOG(INFO) << "sync: " << std::setprecision(14) << measures_.lidar_begin_time_ << ", " <<
    // measures_.lidar_end_time_;

    return true;
}

void LaserMapping::MapIncremental() {
    PointVector points_to_add;
    PointVector point_no_need_downsample;

    size_t cur_pts = scan_down_body_->size();
    points_to_add.reserve(cur_pts);
    point_no_need_downsample.reserve(cur_pts);

    std::vector<size_t> index(cur_pts);
    for (size_t i = 0; i < cur_pts; ++i) {
        index[i] = i;
    }

    std::for_each(index.begin(), index.end(), [&](const size_t &i) {
        /* transform to world frame */
        PointBodyToWorld(scan_down_body_->points[i], scan_down_world_->points[i]);

        /* decide if need add to map */
        PointType &point_world = scan_down_world_->points[i];
        if (!nearest_points_[i].empty() && flg_EKF_inited_) {
            const PointVector &points_near = nearest_points_[i];

            Eigen::Vector3f center =
                ((point_world.getVector3fMap() / filter_size_map_min_).array().floor() + 0.5) * filter_size_map_min_;

            Eigen::Vector3f dis_2_center = points_near[0].getVector3fMap() - center;

            if (fabs(dis_2_center.x()) > 0.5 * filter_size_map_min_ &&
                fabs(dis_2_center.y()) > 0.5 * filter_size_map_min_ &&
                fabs(dis_2_center.z()) > 0.5 * filter_size_map_min_) {
                point_no_need_downsample.emplace_back(point_world);
                return;
            }

            bool need_add = true;
            float dist = math::calc_dist(point_world.getVector3fMap(), center);
            if (points_near.size() >= fasterlio::NUM_MATCH_POINTS) {
                for (int readd_i = 0; readd_i < fasterlio::NUM_MATCH_POINTS; readd_i++) {
                    if (math::calc_dist(points_near[readd_i].getVector3fMap(), center) < dist + 1e-6) {
                        need_add = false;
                        break;
                    }
                }
            }

            if (need_add) {
                points_to_add.emplace_back(point_world);  // FIXME 这并发可能有点问题
            }
        } else {
            points_to_add.emplace_back(point_world);
        }
    });

    Timer::Evaluate(
        [&, this]() {
            ivox_->AddPoints(points_to_add);
            ivox_->AddPoints(point_no_need_downsample);
        },
        "    IVox Add Points");
}

/**
 * Lidar point cloud registration
 * will be called by the eskf custom observation model
 * compute point-to-plane residual here
 * @param s kf state
 * @param ekfom_data H matrix
 */
void LaserMapping::OriObsModel(NavState &s, ESKF::CustomObservationModel &obs) {
    IMUPtr latest_imu;
    {
        UL lock(mtx_imu_state_);
        latest_imu = last_imu_;
    }
    if (latest_imu == nullptr) {
        obs.valid_ = false;
        return;
    }

    // r = log(R_meas^-1 * R_est)
    Quatd q_meas = latest_imu->orientation;
    SO3 R_meas(q_meas);
    SO3 R_est = s.rot_;
    obs.h_x_ = Eigen::Matrix<double, 3, 23>::Zero();
    // The rotation Jacobian is linearized assuming small orientation errors:
    // for r = log(R_meas^{-1} * R_est), dr/d(delta_theta) ≈ I_3 when delta_theta is small.
    // This identity approximation may become inaccurate for large orientation discrepancies,
    // potentially affecting filter consistency or convergence in such cases.
    obs.residual_ = (R_meas.inverse() * R_est).log();

    if (obs.residual_.norm() > 0.5) { // 约 28.6 度
        LOG(WARNING) << "IMU orientation residual is too large: " << obs.residual_.norm()
                     << ". q_est: " << R_est.unit_quaternion().coeffs().transpose()
                     << ", q_meas: " << q_meas.coeffs().transpose();
        
        if (!flg_EKF_inited_) {
            LOG(INFO) << "EKF not inited, forcing state to match IMU orientation";
            s.rot_ = R_meas;
            obs.residual_.setZero();
        }
    }

    obs.h_x_ = Eigen::Matrix<double, 3, 23>::Zero();
    obs.h_x_.block<3, 3>(0, 3) = Mat3d::Identity();
}
// void QuaternionObsModel(NavState &s, ESKF::CustomObservationModel &obs,   
//                        const Quatd& measured_quat) {  
//     // 获取当前状态的四元数  
//     Quatd current_quat = s.rot_;  
      
//     // 计算四元数误差 (可以使用对数映射)  
//     Quatd error_quat = measured_quat.inverse() * current_quat;  
//     Vec3d error_vec = math::QuatToLog(error_quat);  
      
//     // 设置残差 (3维：roll, pitch, yaw误差)  
//     obs.residual_.resize(3);  
//     obs.residual_ = error_vec;  
      
//     // 设置雅可比矩阵 (3x23，只对旋转部分有偏导)  
//     obs.h_x_ = Eigen::MatrixXd::Zero(3, 23);  
//     obs.h_x_.block<3, 3>(0, 3) = Eigen::Matrix3d::Identity();  // 对旋转的偏导  
// }
void LaserMapping::ObsModel(NavState &s, ESKF::CustomObservationModel &obs) {
    int cnt_pts = scan_down_body_->size();

    std::vector<size_t> index(cnt_pts);
    for (size_t i = 0; i < index.size(); ++i) {
        index[i] = i;
    }

    Timer::Evaluate(
        [&, this]() {
            Mat3f R_wl = (s.rot_ * s.offset_R_lidar_).matrix().cast<float>();
            Vec3f t_wl = (s.rot_ * s.offset_t_lidar_ + s.pos_).cast<float>();

            std::for_each(std::execution::par_unseq, index.begin(), index.end(), [&](const size_t &i) {
                PointType &point_body = scan_down_body_->points[i];
                PointType &point_world = scan_down_world_->points[i];

                /* transform to world frame */
                Vec3f p_body = point_body.getVector3fMap();
                point_world.getVector3fMap() = R_wl * p_body + t_wl;
                point_world.intensity = point_body.intensity;

                auto &points_near = nearest_points_[i];
                points_near.clear();

                /** Find the closest surfaces in the map **/
                // if (obs.converge_) {
                ivox_->GetClosestPoint(point_world, points_near, fasterlio::NUM_MATCH_POINTS);
                point_selected_surf_[i] = points_near.size() >= fasterlio::MIN_NUM_MATCH_POINTS;
                if (point_selected_surf_[i]) {
                    point_selected_surf_[i] =
                        math::esti_plane(plane_coef_[i], points_near, fasterlio::ESTI_PLANE_THRESHOLD);
                }

                if (point_selected_surf_[i]) {
                    auto temp = point_world.getVector4fMap();
                    temp[3] = 1.0;
                    float pd2 = plane_coef_[i].dot(temp);

                    bool valid_corr = p_body.norm() > 81 * pd2 * pd2;
                    if (valid_corr) {
                        point_selected_surf_[i] = true;
                        residuals_[i] = pd2;
                    } else {
                        point_selected_surf_[i] = false;
                    }
                }
            });
        },
        "    ObsModel (Lidar Match)");

    effect_feat_num_ = 0;

    corr_pts_.resize(cnt_pts);
    corr_norm_.resize(cnt_pts);
    for (int i = 0; i < cnt_pts; i++) {
        if (point_selected_surf_[i]) {
            corr_norm_[effect_feat_num_] = plane_coef_[i];
            corr_pts_[effect_feat_num_] = scan_down_body_->points[i].getVector4fMap();
            corr_pts_[effect_feat_num_][3] = residuals_[i];

            effect_feat_num_++;
        }
    }
    corr_pts_.resize(effect_feat_num_);
    corr_norm_.resize(effect_feat_num_);

    if (effect_feat_num_ < 1) {
        obs.valid_ = false;
        LOG(WARNING) << "No Effective Points!";
        return;
    }

    Timer::Evaluate(
        [&, this]() {
            /*** Computation of Measurement Jacobian matrix H and measurements vector ***/
            obs.h_x_ = Eigen::MatrixXd::Zero(effect_feat_num_, 12);  // 23
            obs.residual_.resize(effect_feat_num_);

            index.resize(effect_feat_num_);
            const Mat3f off_R = s.offset_R_lidar_.matrix().cast<float>();
            const Vec3f off_t = s.offset_t_lidar_.cast<float>();
            const Mat3f Rt = s.rot_.matrix().transpose().cast<float>();

            std::for_each(std::execution::par_unseq, index.begin(), index.end(), [&](const size_t &i) {
                Vec3f point_this_be = corr_pts_[i].head<3>();
                Mat3f point_be_crossmat = math::SKEW_SYM_MATRIX(point_this_be);
                Vec3f point_this = off_R * point_this_be + off_t;
                Mat3f point_crossmat = math::SKEW_SYM_MATRIX(point_this);

                /*** get the normal vector of closest surface/corner ***/
                Vec3f norm_vec = corr_norm_[i].head<3>();

                /*** calculate the Measurement Jacobian matrix H ***/
                Vec3f C(Rt * norm_vec);
                Vec3f A(point_crossmat * C);

                if (extrinsic_est_en_) {
                    Vec3f B(point_be_crossmat * off_R.transpose() * C);
                    obs.h_x_.block<1, 12>(i, 0) << norm_vec[0], norm_vec[1], norm_vec[2], A[0], A[1], A[2], B[0], B[1],
                        B[2], C[0], C[1], C[2];
                } else {
                    obs.h_x_.block<1, 12>(i, 0) << norm_vec[0], norm_vec[1], norm_vec[2], A[0], A[1], A[2], 0.0, 0.0,
                        0.0, 0.0, 0.0, 0.0;
                }

                /*** Measurement: distance to the closest surface/corner ***/
                /// 增加了cauchy's robust kernel
                float res = -corr_pts_[i][3];
                float rho, drho;

                const float delta = 2.0;
                const float dsqr = delta * delta;
                const float dsqr_inv = 1.0 / dsqr;

                if (res >= 0) {
                    rho = dsqr * std::log(1 + res * dsqr_inv);
                    drho = 1.0 / (1 + res * dsqr_inv);
                } else {
                    rho = -dsqr * std::log(1 - res * dsqr_inv);
                    drho = 1.0 / (1 - res * dsqr_inv);
                }

                obs.residual_(i) = rho;
                obs.h_x_.block<1, 12>(i, 0) = obs.h_x_.block<1, 12>(i, 0).eval() * drho;

                // obs.residual_(i) = res;
            });
        },
        "    ObsModel (IEKF Build Jacobian)");

    /// 填入中位数平方误差
    std::vector<double> res_sq2;
    for (size_t i = 0; i < cnt_pts; ++i) {
        if (point_selected_surf_[i]) {
            double r = residuals_[i];
            res_sq2.emplace_back(r * r);
        }
    }

    if (!res_sq2.empty()) {
        std::sort(res_sq2.begin(), res_sq2.end());
        obs.lidar_residual_mean_ = res_sq2[res_sq2.size() / 2];
        obs.lidar_residual_max_ = res_sq2[res_sq2.size() - 1];
        // LOG(INFO) << "residual mean: " << obs.lidar_residual_mean_ << ", max: " << obs.lidar_residual_max_
        //           << ", 85%: " << res_sq2[res_sq2.size() * 0.85];
    }
}

///////////////////////////  private method /////////////////////////////////////////////////////////////////////

void LaserMapping::CheckDivergence() {
    const double now_ts = state_point_.timestamp_;
    const Vec3d pos = state_point_.pos_;

    if (!diverged_) {
        // 1) 位置绝对界限: 室内建图不可能距原点数百米。
        if (pos.norm() > options_.diverge_pos_bound_m_) {
            diverged_ = true;
            std::ostringstream oss;
            oss << "position out of bounds: " << pos.transpose()
                << " (bound " << options_.diverge_pos_bound_m_ << " m)";
            diverge_reason_ = oss.str();
        }

        // 2) 帧间等效速度: 机器狗物理极速约 2m/s, 持续超阈即判散。
        if (last_div_check_valid_ && now_ts > last_div_check_ts_) {
            const double dt = now_ts - last_div_check_ts_;
            const double v = (pos - last_div_check_pos_).norm() / dt;
            if (v > options_.diverge_vel_bound_mps_) {
                fast_motion_streak_++;
            } else {
                fast_motion_streak_ = 0;
            }
            if (fast_motion_streak_ >= options_.diverge_fast_streak_) {
                diverged_ = true;
                std::ostringstream oss;
                oss << "sustained impossible velocity: " << v << " m/s (bound "
                    << options_.diverge_vel_bound_mps_ << " m/s, streak "
                    << fast_motion_streak_ << ") at " << pos.transpose();
                diverge_reason_ = oss.str();
            }
        }

        // 3) 连续无有效匹配: 发散后 "No Effective Points" 刷屏且地图不再增长。
        if (effect_feat_num_ <= 0) {
            no_effect_streak_++;
        } else {
            no_effect_streak_ = 0;
        }
        if (no_effect_streak_ >= options_.diverge_no_effect_frames_) {
            diverged_ = true;
            std::ostringstream oss;
            oss << "no effective matching points for " << no_effect_streak_
                << " consecutive frames at " << pos.transpose();
            diverge_reason_ = oss.str();
        }

        if (diverged_) {
            LOG(ERROR) << "LIO DIVERGENCE DETECTED: " << diverge_reason_
                       << " - keyframe creation disabled, save will be rejected";
        }
    }

    last_div_check_ts_ = now_ts;
    last_div_check_pos_ = pos;
    last_div_check_valid_ = true;

    UpdateHealthFile();
}

void LaserMapping::UpdateHealthFile() {
    if (health_file_path_.empty()) {
        return;
    }
    // 节流: 正常态 1Hz, 判散后立即写。
    const double wall = std::chrono::duration_cast<std::chrono::duration<double>>(
                            std::chrono::system_clock::now().time_since_epoch())
                            .count();
    if (!diverged_ && wall - last_health_write_ts_ < 1.0) {
        return;
    }
    last_health_write_ts_ = wall;

    std::ostringstream oss;
    oss << "state=" << (diverged_ ? "diverged" : "ok")
        << " kf=" << (last_kf_ ? last_kf_->GetID() : 0)
        << " pos=" << state_point_.pos_.transpose()
        << " ts=" << std::fixed << std::setprecision(3) << state_point_.timestamp_
        << " wall=" << wall;
    if (diverged_) {
        oss << " reason=" << diverge_reason_;
    }
    oss << "\n";

    // 原子写: 临时文件 + rename, 读取方不会看到半行。
    const std::string tmp_path = health_file_path_ + ".tmp";
    std::ofstream out(tmp_path);
    if (!out) {
        return;
    }
    out << oss.str();
    out.close();
    std::rename(tmp_path.c_str(), health_file_path_.c_str());
}

CloudPtr LaserMapping::GetGlobalMap(bool use_lio_pose, bool use_voxel, float res) {
    PoseSnapshot poses;
    poses.reserve(all_keyframes_.size());
    for (const auto& kf : all_keyframes_) {
        poses.emplace_back(use_lio_pose ? kf->GetLIOPose() : kf->GetOptPose());
    }
    return GetGlobalMap(all_keyframes_, poses, use_voxel, res);
}

CloudPtr LaserMapping::GetGlobalMap(const std::vector<Keyframe::Ptr>& keyframes,
                                    const PoseSnapshot& poses,
                                    bool use_voxel,
                                    float res) {
    CloudPtr global_map(new PointCloudType);

    if (keyframes.size() != poses.size()) {
        LOG(ERROR) << "cannot build global map: keyframe/pose snapshot size mismatch, keyframes="
                   << keyframes.size() << ", poses=" << poses.size();
        return global_map;
    }

    pcl::VoxelGrid<PointType> voxel;
    voxel.setLeafSize(res, res, res);

    for (size_t i = 0; i < keyframes.size(); ++i) {
        const auto& kf = keyframes[i];
        CloudPtr cloud = kf->GetCloud();

        CloudPtr cloud_filter(new PointCloudType);

        if (use_voxel) {
            voxel.setInputCloud(cloud);
            voxel.filter(*cloud_filter);

        } else {
            cloud_filter = cloud;
        }

        CloudPtr cloud_trans(new PointCloudType);

        pcl::transformPointCloud(*cloud_filter, *cloud_trans, poses[i].matrix());

        *global_map += *cloud_trans;

        // LOG(INFO) << "kf " << kf->GetID() << ", pose: " << kf->GetOptPose().translation().transpose();
    }

    CloudPtr global_map_filtered(new PointCloudType);
    if (use_voxel) {
        voxel.setInputCloud(global_map);
        voxel.filter(*global_map_filtered);
    } else {
        global_map_filtered = global_map;
    }

    global_map_filtered->is_dense = false;
    global_map_filtered->height = 1;
    global_map_filtered->width = global_map_filtered->size();

    LOG(INFO) << "global map: " << global_map_filtered->size();

    return global_map_filtered;
}

void LaserMapping::SaveMap() {
    /// 保存地图
    auto global_map = GetGlobalMap(true);

    pcl::io::savePCDFileBinaryCompressed("./data/lio.pcd", *global_map);

    LOG(INFO) << "lio map is saved to ./data/lio.pcd";
}

CloudPtr LaserMapping::GetRecentCloud() {
    UL lock(mtx_buffer_);
    if (lidar_buffer_.empty()) {
        return nullptr;
    }

    return lidar_buffer_.front();
}

SE3 LaserMapping::GetOptPose() const {
    if (last_kf_ == nullptr) {
        return state_point_.GetPose();
    }

    // 基于当前帧相对lastKF的LIO位姿，得到回环后的位姿
    SE3 delta = last_kf_->GetLIOPose().inverse() * state_point_.GetPose();
    return last_kf_->GetOptPose() * delta;
}

}  // namespace lightning
