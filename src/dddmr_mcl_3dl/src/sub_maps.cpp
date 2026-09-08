/*
 * Copyright (c) 2016-2020, the mcl_3dl authors
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 *     * Redistributions of source code must retain the above copyright
 *       notice, this list of conditions and the following disclaimer.
 *     * Redistributions in binary form must reproduce the above copyright
 *       notice, this list of conditions and the following disclaimer in the
 *       documentation and/or other materials provided with the distribution.
 *     * Neither the name of the copyright holder nor the names of its
 *       contributors may be used to endorse or promote products derived from
 *       this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
 * LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

#include <mcl_3dl/sub_maps.h>
namespace mcl_3dl
{
SubMaps::SubMaps(std::string name) : Node(name), is_current_ready_(false), 
  prepare_warm_up_(false), is_warm_up_ready_(false), is_initial_(false), key_poses_received_(false),
  sync_request_in_flight_(false), poses_changed_(false), sync_generation_(0), knn_num_of_ground_normals_(20){

  map_voxel_omp_.setNumberOfThreads(4);
  map_voxel_omp_.setLeafSize (0.2, 0.2, 0.2);
  map_voxel_omp_.setSaveLeafLayout(false);

  ground_voxel_omp_.setNumberOfThreads(4);
  ground_voxel_omp_.setLeafSize (0.2, 0.2, 0.2);
  ground_voxel_omp_.setSaveLeafLayout(false);

  map_current_ = pcl::PointCloud<pcl_t>::Ptr(new pcl::PointCloud<pcl_t>());
  ground_current_ = pcl::PointCloud<pcl_t>::Ptr(new pcl::PointCloud<pcl_t>());
  map_warmup_ = pcl::PointCloud<pcl_t>::Ptr(new pcl::PointCloud<pcl_t>());
  ground_warmup_ = pcl::PointCloud<pcl_t>::Ptr(new pcl::PointCloud<pcl_t>());

  clock_ = this->get_clock();
  
  access_ = new sub_maps_mutex_t();

  declare_parameter("pg_map_server_name", rclcpp::ParameterValue(""));
  this->get_parameter("pg_map_server_name", pg_map_server_name_);
  RCLCPP_INFO(this->get_logger(), "pg_map_server_name: %s", pg_map_server_name_.c_str());

  declare_parameter("sub_map_search_radius", rclcpp::ParameterValue(50.0));
  this->get_parameter("sub_map_search_radius", sub_map_search_radius_);
  RCLCPP_INFO(this->get_logger(), "sub_map_search_radius: %.1f", sub_map_search_radius_);

  declare_parameter("sub_map_warmup_trigger_distance", rclcpp::ParameterValue(20.0));
  this->get_parameter("sub_map_warmup_trigger_distance", sub_map_warmup_trigger_distance_);
  RCLCPP_INFO(this->get_logger(), "sub_map_warmup_trigger_distance: %.1f", sub_map_warmup_trigger_distance_);
  
  srv_group_ = this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
  get_key_frame_cloud_client_ = this->create_client<dddmr_sys_core::srv::GetKeyFrameCloud>(
    pg_map_server_name_ + "/get_key_frame_cloud", rmw_qos_profile_services_default, srv_group_);

  sub_key_poses_ = this->create_subscription<geometry_msgs::msg::PoseArray>(
    pg_map_server_name_ + "/key_poses", rclcpp::QoS(rclcpp::KeepLast(1)).transient_local().reliable(), std::bind(&SubMaps::keyPosesCb, this, std::placeholders::_1));

  //@ Latched topic, Create a publisher using the QoS settings to emulate a ROS1 latched topic
  pub_sub_map_ = this->create_publisher<sensor_msgs::msg::PointCloud2>("sub_mapcloud",
              rclcpp::QoS(rclcpp::KeepLast(1)).transient_local().reliable());  

  pub_sub_ground_ = this->create_publisher<sensor_msgs::msg::PointCloud2>("sub_mapground",
                rclcpp::QoS(rclcpp::KeepLast(1)).transient_local().reliable());  

  pub_sub_map_warmup_ = this->create_publisher<sensor_msgs::msg::PointCloud2>("sub_mapcloud_warmup",
              rclcpp::QoS(rclcpp::KeepLast(1)).transient_local().reliable());  

  pub_sub_ground_warmup_ = this->create_publisher<sensor_msgs::msg::PointCloud2>("sub_mapground_warmup",
                rclcpp::QoS(rclcpp::KeepLast(1)).transient_local().reliable());  

  timer_group_ = this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);

  sync_map_timer_ = this->create_wall_timer(1ms, std::bind(&SubMaps::syncMapThread, this), timer_group_);
  warm_up_timer_ = this->create_wall_timer(200ms, std::bind(&SubMaps::warmUpThread, this), timer_group_);
}

SubMaps::~SubMaps(){
  delete access_;
}

void SubMaps::keyPosesCb(const geometry_msgs::msg::PoseArray::SharedPtr msg)
{
  if (msg->poses.empty())
  {
    // The M20Pro asset server intentionally never publishes an empty index;
    // ignore stray empty samples so they cannot wipe a valid keyframe set.
    RCLCPP_WARN_THROTTLE(this->get_logger(), *clock_, 5000, "Ignored empty key_poses message.");
    return;
  }

  // Detect a real map switch.  Re-selecting the same asset republishes
  // identical content and must not discard converged localization state.
  bool changed = msg->poses.size() != last_key_poses_xyz_.size();
  if (!changed)
  {
    for (size_t i = 0; i < msg->poses.size(); i++)
    {
      const auto &p = msg->poses[i].position;
      if (std::abs(p.x - last_key_poses_xyz_[i][0]) > 1e-3 ||
          std::abs(p.y - last_key_poses_xyz_[i][1]) > 1e-3 ||
          std::abs(p.z - last_key_poses_xyz_[i][2]) > 1e-3)
      {
        changed = true;
        break;
      }
    }
  }
  if (!changed && key_poses_received_)
    return;

  last_key_poses_xyz_.clear();
  last_key_poses_xyz_.reserve(msg->poses.size());
  pcl::PointCloud<pcl_t>::Ptr new_poses(new pcl::PointCloud<pcl_t>());
  for (auto i = msg->poses.begin(); i != msg->poses.end(); i++)
  {
    pcl_t pt;
    pt.x = (*i).position.x;
    pt.y = (*i).position.y;
    pt.z = (*i).position.z;
    new_poses->push_back(pt);
    last_key_poses_xyz_.push_back({pt.x, pt.y, pt.z});
  }

  // Only stage the new poses here; the actual swap into poses_pcl_t_ /
  // kdtree_poses_ happens inside applyPendingKeyPoseReset() (syncMapThread)
  // so the measurement path never observes a half-updated keyframe index.
  const size_t previous_count = key_poses_received_ ? (poses_pcl_t_ ? poses_pcl_t_->size() : 0) : 0;
  {
    std::unique_lock<sub_maps_mutex_t> lock(*access_);
    pending_poses_ = new_poses;
    poses_changed_.store(true);
  }
  if (key_poses_received_)
  {
    RCLCPP_INFO(this->get_logger(),
                "Key poses changed (%zu -> %zu keyframes); scheduling sub-map re-sync for the new map asset.",
                previous_count, msg->poses.size());
  }
  key_poses_received_ = true;

  // The sync timer is never cancelled: it stays alive and idles while fully
  // synced, then transparently picks up a pending map-switch on the next
  // tick.  This avoids recreating/reassigning the timer, which would race
  // with the completion branch's bookkeeping under a MultiThreadedExecutor.
}

void SubMaps::applyPendingKeyPoseReset()
{
  // Fast path: the 1ms sync timer idles here when nothing is pending, so the
  // common case must be a cheap atomic check without touching the mutex.
  if (!poses_changed_.load())
    return;
  // Runs inside syncMapThread (timer_group_, mutually exclusive with
  // warmUpThread), so the keyframe vectors are not touched concurrently.
  std::unique_lock<sub_maps_mutex_t> lock(*access_);
  if (!poses_changed_.load())
    return;
  RCLCPP_INFO(this->get_logger(), "Re-syncing sub-maps for new keyframe set (%zu keyframes).",
              pending_poses_ ? pending_poses_->size() : 0);
  cornerCloudKeyFrames_.clear();
  cornerCloudKeyFrames_baselink_.clear();
  surfCloudKeyFrames_.clear();
  surfCloudKeyFrames_baselink_.clear();
  groundCloudKeyFrames_.clear();
  groundCloudKeyFrames_baselink_.clear();
  map_current_->clear();
  ground_current_->clear();
  map_warmup_->clear();
  ground_warmup_->clear();
  is_initial_ = false;
  is_current_ready_ = false;
  is_warm_up_ready_ = false;
  prepare_warm_up_ = false;
  sync_request_in_flight_ = false;
  sync_generation_++;  // invalidate any keyframe fetch in flight for the old map
  poses_pcl_t_ = pending_poses_;
  pending_poses_.reset();
  kdtree_poses_.reset(new pcl::KdTreeFLANN<pcl_t>());
  kdtree_poses_->setInputCloud(poses_pcl_t_);
  poses_changed_.store(false);
}

void SubMaps::syncMapThread(){

  applyPendingKeyPoseReset();

  if(!key_poses_received_)
    return;

  // Fully synced for the current map and no map-switch pending: idle.
  if(is_initial_)
    return;

  if(sync_request_in_flight_)
    return;

  auto request = std::make_shared<dddmr_sys_core::srv::GetKeyFrameCloud::Request>();
  request->key_frame_number = cornerCloudKeyFrames_.size();
  
  if(request->key_frame_number>=poses_pcl_t_->size())
  {
    RCLCPP_INFO(this->get_logger(), "Sub-map keyframe sync complete.");
    RCLCPP_INFO(this->get_logger(), "Sync cloud key frame number: %lu with total size: %lu", cornerCloudKeyFrames_.size(), poses_pcl_t_->size());
    RCLCPP_INFO(this->get_logger(), "Sync surface key frame number: %lu with total size: %lu", surfCloudKeyFrames_.size(), poses_pcl_t_->size());
    RCLCPP_INFO(this->get_logger(), "Sync ground key frame number: %lu with total size: %lu", groundCloudKeyFrames_.size(), poses_pcl_t_->size());
    is_initial_ = true;
    // The sync timer is intentionally NOT cancelled.  It keeps ticking and
    // early-returns while is_initial_ is true, so a later map switch queued
    // via applyPendingKeyPoseReset (which clears is_initial_) resumes syncing
    // without ever needing to recreate the timer.
    return; 
  }

  if (!get_key_frame_cloud_client_->wait_for_service(std::chrono::seconds(1))) {
    RCLCPP_WARN(this->get_logger(), "Service %s/get_key_frame_cloud not available", pg_map_server_name_.c_str());
    return;
  }

  sync_request_in_flight_ = true;
  const uint64_t request_generation = sync_generation_;
  get_key_frame_cloud_client_->async_send_request(request, 
    [this, request_generation](rclcpp::Client<dddmr_sys_core::srv::GetKeyFrameCloud>::SharedFuture future) {
      try {
        if (request_generation != sync_generation_) {
          // A map switch happened while this fetch was in flight; drop the
          // stale keyframe instead of contaminating the new keyframe set.
          sync_request_in_flight_ = false;
          return;
        }
        auto result = future.get();
        pcl::PointCloud<pcl_t> pcl_cloud;
        pcl::PointCloud<pcl_t> pcl_surface_cloud;
        pcl::PointCloud<pcl_t> pcl_ground_cloud;

        pcl::fromROSMsg(result->key_frame_cloud, pcl_cloud);
        if(pcl_cloud.points.size()<1){
          RCLCPP_DEBUG(this->get_logger(), "Empty key frame cloud");
        }
        pcl::fromROSMsg(result->key_frame_surface, pcl_surface_cloud);
        if(pcl_surface_cloud.points.size()<1){
          RCLCPP_DEBUG(this->get_logger(), "Empty key frame surface");
        }

        pcl::fromROSMsg(result->key_frame_ground, pcl_ground_cloud);
        if(pcl_ground_cloud.points.size()<1){
          RCLCPP_DEBUG(this->get_logger(), "Empty key frame ground");
        }

        pcl::PointCloud<pcl_t> pcl_cloud_base_link;
        pcl::PointCloud<pcl_t> pcl_surface_cloud_base_link;
        pcl::PointCloud<pcl_t> pcl_ground_cloud_base_link;

        pcl::fromROSMsg(result->key_frame_cloud, pcl_cloud_base_link);
        if(pcl_cloud_base_link.points.size()<1){
          RCLCPP_DEBUG(this->get_logger(), "Empty key frame cloud base_link");
        }
        pcl::fromROSMsg(result->key_frame_surface, pcl_surface_cloud_base_link);
        if(pcl_surface_cloud.points.size()<1){
          RCLCPP_DEBUG(this->get_logger(), "Empty key frame surface base_link");
        }

        pcl::fromROSMsg(result->key_frame_ground, pcl_ground_cloud_base_link);
        if(pcl_ground_cloud_base_link.points.size()<1){
          RCLCPP_DEBUG(this->get_logger(), "Empty key frame ground base_link");
        }

        static int consecutive_empty_responses = 0;
        if (pcl_cloud.points.size() < 1) {
          consecutive_empty_responses += 1;
          if (consecutive_empty_responses <= 10) {
            RCLCPP_WARN(this->get_logger(), "Key frame %zu cloud deserialized empty; retrying sync.", cornerCloudKeyFrames_.size());
            sync_request_in_flight_ = false;
            return;
          }
          RCLCPP_WARN(this->get_logger(), "Key frame %zu cloud still empty after retries; accepting to keep sync progressing.", cornerCloudKeyFrames_.size());
        }
        consecutive_empty_responses = 0;
        RCLCPP_INFO_THROTTLE(this->get_logger(), *clock_, 1000, "Sync key frame number: %lu with total size: %lu", cornerCloudKeyFrames_.size(), poses_pcl_t_->size());
        cornerCloudKeyFrames_.push_back(pcl_cloud.makeShared());
        surfCloudKeyFrames_.push_back(pcl_surface_cloud.makeShared());
        groundCloudKeyFrames_.push_back(pcl_ground_cloud.makeShared());
        cornerCloudKeyFrames_baselink_.push_back(pcl_cloud_base_link.makeShared());
        surfCloudKeyFrames_baselink_.push_back(pcl_surface_cloud_base_link.makeShared());
        groundCloudKeyFrames_baselink_.push_back(pcl_ground_cloud_base_link.makeShared());
        sync_request_in_flight_ = false;

      } catch (const std::exception &e) {
        sync_request_in_flight_ = false;
        RCLCPP_ERROR(this->get_logger(), "Service call failed: %s", e.what());
      }
    });

}

void SubMaps::warmUpThread(){
  
  if(!is_initial_)
    return;
  
  if(!is_current_ready_){
    mcl_3dl::pcl_t target_pose;
    std::vector<int> pointIdxRadiusSearch;
    std::vector<float> pointRadiusSquaredDistance;
    target_pose.x = robot_pose_.pose.pose.position.x;
    target_pose.y = robot_pose_.pose.pose.position.y;
    target_pose.z = robot_pose_.pose.pose.position.z;
    if(kdtree_poses_->radiusSearch(target_pose, sub_map_search_radius_, pointIdxRadiusSearch, pointRadiusSquaredDistance,0)<1)
    {
      is_current_ready_ = false;
      return;
    }
    map_current_->clear();
    ground_current_->clear();
    for(auto it=pointIdxRadiusSearch.begin(); it!=pointIdxRadiusSearch.end(); it++){
      *map_current_ += (*cornerCloudKeyFrames_[*it]);
      //*map_current_ += (*surfCloudKeyFrames_[*it]);
      *ground_current_ += (*groundCloudKeyFrames_[*it]);
    }

    map_voxel_omp_.setInputCloud(map_current_);
    map_voxel_omp_.setFinalFilter(true);
    map_voxel_omp_.filter(*map_current_);  

    ground_voxel_omp_.setInputCloud(ground_current_);
    ground_voxel_omp_.setFinalFilter(true);
    ground_voxel_omp_.filter(*ground_current_);  

    if (map_current_->empty() || ground_current_->empty()) {
      RCLCPP_WARN(this->get_logger(), "Current sub-map clouds are empty after filtering; retrying on next tick.");
      return;
    }
    kdtree_ground_current_.setInputCloud(ground_current_);
    kdtree_map_current_.setInputCloud(map_current_);   
    //@Normal estimation for ground
    pcl::NormalEstimation<mcl_3dl::pcl_t, pcl::Normal> n;
    pcl::search::KdTree<mcl_3dl::pcl_t>::Ptr tree (new pcl::search::KdTree<mcl_3dl::pcl_t>);
    tree->setInputCloud (ground_current_);
    n.setInputCloud (ground_current_);
    n.setSearchMethod (tree);
    n.setKSearch (knn_num_of_ground_normals_);
    n.compute (normals_ground_current_);

    sensor_msgs::msg::PointCloud2 map_pc;
    pcl::toROSMsg(*map_current_, map_pc);
    map_pc.header.frame_id = "map";
    pub_sub_map_->publish(map_pc);

    sensor_msgs::msg::PointCloud2 ground_pc;
    pcl::toROSMsg(*ground_current_, ground_pc);
    ground_pc.header.frame_id = "map";
    pub_sub_ground_->publish(ground_pc);
    
    current_sub_map_pose_ = robot_pose_;
    RCLCPP_INFO(this->get_logger(), "All essential KD-tree are generated.");
    
    is_current_ready_ = true;
  }
  
  else if(prepare_warm_up_ && !is_warm_up_ready_){
    mcl_3dl::pcl_t target_pose;
    std::vector<int> pointIdxRadiusSearch;
    std::vector<float> pointRadiusSquaredDistance;
    target_pose.x = warm_up_pose_.pose.pose.position.x;
    target_pose.y = warm_up_pose_.pose.pose.position.y;
    target_pose.z = warm_up_pose_.pose.pose.position.z;
    RCLCPP_INFO(this->get_logger(), "Prepare warm up at: %.2f, %.2f, %.2f", target_pose.x, target_pose.y, target_pose.z);
    if(kdtree_poses_->radiusSearch(target_pose, sub_map_search_radius_, pointIdxRadiusSearch, pointRadiusSquaredDistance,0)<1)
    {
      prepare_warm_up_ = false;
      return;
    }
    map_warmup_->clear();
    ground_warmup_->clear();
    for(auto it=pointIdxRadiusSearch.begin(); it!=pointIdxRadiusSearch.end(); it++){
      *map_warmup_ += (*cornerCloudKeyFrames_[*it]);
      //*map_warmup_ += (*surfCloudKeyFrames_[*it]);
      *ground_warmup_ += (*groundCloudKeyFrames_[*it]);
    }

    map_voxel_omp_.setInputCloud(map_warmup_);
    map_voxel_omp_.setFinalFilter(true);
    map_voxel_omp_.filter(*map_warmup_);  

    ground_voxel_omp_.setInputCloud(ground_warmup_);
    ground_voxel_omp_.setFinalFilter(true);
    ground_voxel_omp_.filter(*ground_warmup_);  

    if (map_warmup_->empty() || ground_warmup_->empty()) {
      if (is_current_ready_ && !map_current_->empty() && !ground_current_->empty()) {
        RCLCPP_WARN(this->get_logger(), "Warmup sub-map clouds are empty; falling back to the ready current sub-map.");
        *map_warmup_ = *map_current_;
        *ground_warmup_ = *ground_current_;
      } else {
        RCLCPP_WARN(this->get_logger(), "Warmup sub-map clouds are empty after filtering; retrying on next tick.");
        return;
      }
    }
    kdtree_ground_warmup_.setInputCloud(ground_warmup_);
    kdtree_map_warmup_.setInputCloud(map_warmup_);   
    //@Normal estimation for ground
    pcl::NormalEstimation<mcl_3dl::pcl_t, pcl::Normal> n;
    pcl::search::KdTree<mcl_3dl::pcl_t>::Ptr tree (new pcl::search::KdTree<mcl_3dl::pcl_t>);
    tree->setInputCloud (ground_warmup_);
    n.setInputCloud (ground_warmup_);
    n.setSearchMethod (tree);
    n.setKSearch (knn_num_of_ground_normals_);
    n.compute (normals_ground_warmup_);
    sensor_msgs::msg::PointCloud2 map_pc;
    pcl::toROSMsg(*map_warmup_, map_pc);
    map_pc.header.frame_id = "map";
    pub_sub_map_warmup_->publish(map_pc);

    sensor_msgs::msg::PointCloud2 ground_pc;
    pcl::toROSMsg(*ground_warmup_, ground_pc);
    ground_pc.header.frame_id = "map";
    pub_sub_ground_warmup_->publish(ground_pc);
    
    RCLCPP_INFO(this->get_logger(), "All essential Warmup KD-tree are generated.");
    prepare_warm_up_ = false;
    is_warm_up_ready_ = true;
  }
}

bool SubMaps::isWarmUpReady(){
  return is_warm_up_ready_;
}

void SubMaps::swapKdTree(){
  
  map_current_->clear();
  ground_current_->clear();
  *map_current_ = *map_warmup_;
  *ground_current_ = *ground_warmup_;
  kdtree_map_current_ = kdtree_map_warmup_;
  kdtree_ground_current_ = kdtree_ground_warmup_;
  normals_ground_current_ = normals_ground_warmup_;
  current_sub_map_pose_ = warm_up_pose_;

  sensor_msgs::msg::PointCloud2 map_pc;
  pcl::toROSMsg(*map_warmup_, map_pc);
  map_pc.header.frame_id = "map";
  pub_sub_map_->publish(map_pc);

  sensor_msgs::msg::PointCloud2 ground_pc;
  pcl::toROSMsg(*ground_warmup_, ground_pc);
  ground_pc.header.frame_id = "map";
  pub_sub_ground_->publish(ground_pc);

  is_warm_up_ready_ = false;
  // After a swap the current KD-trees are valid by definition; mark ready so
  // the measurement path resumes.  This matters after a map switch, where the
  // initialpose busy-wait swaps before warmUpThread can rebuild the current
  // sub-map around the (possibly out-of-map) previous robot pose.
  is_current_ready_ = true;
  RCLCPP_INFO(this->get_logger(), "KD-tree swapped.");
}

void SubMaps::setInitialPose(const geometry_msgs::msg::PoseWithCovarianceStamped pose){
  RCLCPP_INFO(this->get_logger(), "Receive initial pose at: %.2f, %.2f, %.2f", pose.pose.pose.position.x, pose.pose.pose.position.y, pose.pose.pose.position.z);
  prepare_warm_up_ = true;
  warm_up_pose_ = pose;
}

void SubMaps::setPose(const geometry_msgs::msg::PoseWithCovarianceStamped pose){
  robot_pose_ = pose;
  double dx = pose.pose.pose.position.x - current_sub_map_pose_.pose.pose.position.x;
  double dy = pose.pose.pose.position.y - current_sub_map_pose_.pose.pose.position.y;
  double dz = pose.pose.pose.position.z - current_sub_map_pose_.pose.pose.position.z;
  if(!is_warm_up_ready_ && sqrt(dx*dx + dy*dy + dz*dz)>=sub_map_warmup_trigger_distance_){
    prepare_warm_up_ = true;
    warm_up_pose_ = pose;
    RCLCPP_INFO_THROTTLE(this->get_logger(), *clock_, 1000, "Warming up sub maps");
  }
}

}