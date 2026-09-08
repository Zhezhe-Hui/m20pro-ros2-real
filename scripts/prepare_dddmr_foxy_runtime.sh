#!/usr/bin/env bash
set -euo pipefail

# v4 M20Pro runtime builder.
#
# Build this natively on the 104 RK3588/Foxy host.  The resulting workspace
# contains Lightning-LM for mapping and the official DDDMR runtime for MCL,
# perception, global planning and P2P navigation. Do not copy a Humble/x86
# install tree to the robot: ROS 2 distro and CPU ABI must match the target.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-${M20PRO_DDDMR_RUNTIME_WS:-/home/user/m20pro_dddmr_foxy_ws}}"
ROS_DISTRO_NAME="${M20PRO_DDDMR_RUNTIME_DISTRO:-${M20PRO_LIGHTNING_RUNTIME_DISTRO:-foxy}}"
TARGET_ARCH="${M20PRO_LIGHTNING_TARGET_ARCH:-${M20PRO_DDDMR_TARGET_ARCH:-aarch64}}"
SOURCE_REPO="${M20PRO_LIGHTNING_SOURCE_REPO:-https://github.com/DeepRoboticsLab/lightning-lm-deep-robotics.git}"
SOURCE_REF="${M20PRO_LIGHTNING_SOURCE_REF:-31ce5190bb2dc9c8be99a572fe2413380ad60cd6}"
SOURCE_ROOT="${M20PRO_LIGHTNING_SOURCE_ROOT:-${ROOT_DIR}/vendor/lightning_lm_deep_robotics}"
ACKERMANN_MSGS_SOURCE_ROOT="${ROOT_DIR}/src/ackermann_msgs"
DDDMR_SOURCE_REPO="${M20PRO_OFFICIAL_DDDMR_SOURCE_REPO:-https://github.com/dfl-rlab/dddmr_navigation.git}"
DDDMR_SOURCE_REF="${M20PRO_OFFICIAL_DDDMR_SOURCE_REF:-1d0367376380205a6a18c0ad7c7c16c9338c96bc}"
DDDMR_SOURCE_ROOT="${M20PRO_OFFICIAL_DDDMR_SOURCE_ROOT:-${ROOT_DIR}/vendor/dddmr_navigation}"
DDDMR_FOXY_ROSIDL_PATCH="${ROOT_DIR}/scripts/patches/dddmr_navigation/foxy_rosidl_typesupport.patch"
DDDMR_FOXY_PERCEPTION_PATCH="${ROOT_DIR}/scripts/patches/dddmr_navigation/foxy_perception_3d.patch"
DDDMR_FOXY_PCL_PATCH="${ROOT_DIR}/scripts/patches/dddmr_navigation/foxy_pcl_version.patch"
DDDMR_FOXY_ACKERMANN_PATCH="${ROOT_DIR}/scripts/patches/dddmr_navigation/foxy_ackermann_msgs_dependency.patch"
DDDMR_FOXY_LEGO_LOAM_BAG_TOOLS_PATCH="${ROOT_DIR}/scripts/patches/dddmr_navigation/foxy_lego_loam_bag_tools.patch"
DDDMR_FOXY_MCL_TF_TIMESTAMP_PATCH="${ROOT_DIR}/scripts/patches/dddmr_navigation/foxy_mcl_tf_timestamp.patch"
DDDMR_FOXY_MCL_INITIALPOSE_WARMUP_PATCH="${ROOT_DIR}/scripts/patches/dddmr_navigation/foxy_mcl_initialpose_warmup.patch"
DDDMR_FOXY_MCL_SUBMAPS_EMPTY_GUARD_PATCH="${ROOT_DIR}/scripts/patches/dddmr_navigation/foxy_mcl_submaps_empty_guard.patch"
FOXY_COMPAT_ROOT="${ROOT_DIR}/scripts/foxy_compat"
BUILD_THIRDPARTY="${M20PRO_LIGHTNING_BUILD_THIRDPARTY:-1}"
PARALLEL_WORKERS="${M20PRO_LIGHTNING_COLCON_WORKERS:-3}"
LOCAL_PREFIX="${TARGET}/thirdparty_install"
TMP_ROOT="$(mktemp -d /tmp/m20pro_lightning_runtime.XXXXXX)"
trap 'rm -rf "${TMP_ROOT}"' EXIT

if [[ "$(uname -m)" != "${TARGET_ARCH}" && "${M20PRO_LIGHTNING_ALLOW_FOREIGN_ARCH:-0}" != "1" ]]; then
  echo "native ARM build required: host=$(uname -m), target=${TARGET_ARCH}" >&2
  echo "run this script on 104/RK3588, or set M20PRO_LIGHTNING_ALLOW_FOREIGN_ARCH=1 only for an explicit cross-build" >&2
  exit 23
fi
if [[ -e "${TARGET}" ]]; then
  echo "target already exists; choose a new path or remove it explicitly: ${TARGET}" >&2
  exit 20
fi
ROS_SETUP="/opt/ros/${ROS_DISTRO_NAME}/setup.bash"
if [[ ! -f "${ROS_SETUP}" ]]; then
  echo "ROS 2 ${ROS_DISTRO_NAME} is required: ${ROS_SETUP}" >&2
  exit 21
fi
for command_name in cmake colcon cp git make mkdir; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "${command_name} is required" >&2
    exit 2
  }
done
if command -v dpkg-query >/dev/null 2>&1; then
  if ! dpkg-query -W -f='${Status}' libgflags-dev 2>/dev/null | grep -q "install ok installed"; then
    echo "libgflags-dev is required by Lightning-LM app targets; install it on the target host first:" >&2
    echo "  sudo apt install -y libgflags-dev" >&2
    exit 25
  fi
fi

mkdir -p "${TARGET}/src"
if [[ -d "${ACKERMANN_MSGS_SOURCE_ROOT}" && -f "${ACKERMANN_MSGS_SOURCE_ROOT}/package.xml" ]]; then
  cp -a "${ACKERMANN_MSGS_SOURCE_ROOT}" "${TARGET}/src/ackermann_msgs"
fi
if [[ -d "${SOURCE_ROOT}" && -f "${SOURCE_ROOT}/package.xml" ]]; then
  cp -a "${SOURCE_ROOT}" "${TARGET}/src/lightning-lm-deep-robotics"
else
  git clone --depth 1 "${SOURCE_REPO}" "${TMP_ROOT}/lightning-lm-deep-robotics"
  git -C "${TMP_ROOT}/lightning-lm-deep-robotics" checkout "${SOURCE_REF}"
  cp -a "${TMP_ROOT}/lightning-lm-deep-robotics" "${TARGET}/src/lightning-lm-deep-robotics"
fi

# Keep the official navigation source isolated from the application workspace.
# 104 usually has no Internet route, so accept a fixed offline source export
# from the upper computer. The runtime still builds only the production 3D
# chain and never launches upstream LeGO-LOAM mapping, because Lightning-LM is
# the sole mapper.
if [[ -d "${DDDMR_SOURCE_ROOT}/src/dddmr_mcl_3dl" && \
      -d "${DDDMR_SOURCE_ROOT}/src/dddmr_p2p_move_base" ]]; then
  cp -a "${DDDMR_SOURCE_ROOT}" "${TARGET}/src/dddmr_navigation"
else
  git clone "${DDDMR_SOURCE_REPO}" "${TARGET}/src/dddmr_navigation"
  git -C "${TARGET}/src/dddmr_navigation" checkout --detach "${DDDMR_SOURCE_REF}"
fi

# Official DDDMR currently uses a rosidl CMake helper introduced after Foxy.
# Apply the smallest source-compatible shim only to the isolated Foxy runtime;
# the generated actions/services and the navigation algorithms remain upstream.
if [[ "${ROS_DISTRO_NAME}" == "foxy" ]]; then
  [[ -f "${DDDMR_FOXY_ROSIDL_PATCH}" ]] || {
    echo "missing Foxy DDDMR rosidl compatibility patch: ${DDDMR_FOXY_ROSIDL_PATCH}" >&2
    exit 28
  }
  patch --batch --forward -d "${TARGET}/src/dddmr_navigation" -p1 \
    < "${DDDMR_FOXY_ROSIDL_PATCH}"
  [[ -f "${DDDMR_FOXY_PERCEPTION_PATCH}" ]] || {
    echo "missing Foxy DDDMR perception compatibility patch: ${DDDMR_FOXY_PERCEPTION_PATCH}" >&2
    exit 30
  }
  patch --batch --forward -d "${TARGET}/src/dddmr_navigation" -p1 \
    < "${DDDMR_FOXY_PERCEPTION_PATCH}"
  [[ -f "${DDDMR_FOXY_PCL_PATCH}" ]] || {
    echo "missing Foxy DDDMR PCL compatibility patch: ${DDDMR_FOXY_PCL_PATCH}" >&2
    exit 31
  }
  patch --batch --forward -d "${TARGET}/src/dddmr_navigation" -p1 \
    < "${DDDMR_FOXY_PCL_PATCH}"
  [[ -f "${DDDMR_FOXY_ACKERMANN_PATCH}" ]] || {
    echo "missing Foxy DDDMR ackermann dependency patch: ${DDDMR_FOXY_ACKERMANN_PATCH}" >&2
    exit 32
  }
  patch --batch --forward -d "${TARGET}/src/dddmr_navigation" -p1 \
    < "${DDDMR_FOXY_ACKERMANN_PATCH}"
  [[ -f "${DDDMR_FOXY_LEGO_LOAM_BAG_TOOLS_PATCH}" ]] || {
    echo "missing Foxy DDDMR lego_loam bag tools patch: ${DDDMR_FOXY_LEGO_LOAM_BAG_TOOLS_PATCH}" >&2
    exit 33
  }
  patch --batch --forward -d "${TARGET}/src/dddmr_navigation" -p1 \
    < "${DDDMR_FOXY_LEGO_LOAM_BAG_TOOLS_PATCH}"
  [[ -f "${DDDMR_FOXY_MCL_TF_TIMESTAMP_PATCH}" ]] || {
    echo "missing Foxy DDDMR MCL TF timestamp patch: ${DDDMR_FOXY_MCL_TF_TIMESTAMP_PATCH}" >&2
    exit 34
  }
  patch --batch --forward -d "${TARGET}/src/dddmr_navigation" -p1 \
    < "${DDDMR_FOXY_MCL_TF_TIMESTAMP_PATCH}"
  [[ -f "${DDDMR_FOXY_MCL_INITIALPOSE_WARMUP_PATCH}" ]] || {
    echo "missing Foxy DDDMR MCL initialpose warm-up patch: ${DDDMR_FOXY_MCL_INITIALPOSE_WARMUP_PATCH}" >&2
    exit 35
  }
  patch --batch --forward -d "${TARGET}/src/dddmr_navigation" -p1 \
    < "${DDDMR_FOXY_MCL_INITIALPOSE_WARMUP_PATCH}"
  [[ -f "${DDDMR_FOXY_MCL_SUBMAPS_EMPTY_GUARD_PATCH}" ]] || {
    echo "missing Foxy DDDMR MCL sub-maps empty guard patch: ${DDDMR_FOXY_MCL_SUBMAPS_EMPTY_GUARD_PATCH}" >&2
    exit 36
  }
  patch --batch --forward -d "${TARGET}/src/dddmr_navigation" -p1 \
    < "${DDDMR_FOXY_MCL_SUBMAPS_EMPTY_GUARD_PATCH}"
  [[ -f "${FOXY_COMPAT_ROOT}/include/tf2_eigen/tf2_eigen.hpp" && \
     -f "${FOXY_COMPAT_ROOT}/include/tf2_geometry_msgs/tf2_geometry_msgs.hpp" && \
     -f "/opt/ros/${ROS_DISTRO_NAME}/include/tf2_eigen/tf2_eigen.h" ]] || {
    echo "Foxy tf2 compatibility headers are unavailable" >&2
    exit 29
  }
  mkdir -p "${TARGET}/foxy_compat"
  cp -a "${FOXY_COMPAT_ROOT}/." "${TARGET}/foxy_compat/"
  find "${TARGET}/src/dddmr_navigation/src" \
    -type f \( -name "*.cpp" -o -name "*.cc" -o -name "*.hpp" -o -name "*.h" \) \
    -print0 | xargs -0 perl -0pi -e \
      's|(std::make_shared<tf2_ros::CreateTimerROS>\(\n\s*this->get_node_base_interface\(\),\n\s*this->get_node_timers_interface\(\)),\n\s*[A-Za-z0-9_]+_group_\);|$1);|g'
  find "${TARGET}/src/dddmr_navigation/src/dddmr_local_planner" \
    -type f \( -name "*.cpp" -o -name "*.cc" -o -name "*.hpp" -o -name "*.h" \) \
    -print0 | xargs -0 perl -0pi -e \
      's/rclcpp::PARAMETER_STRING_ARRAY/std::vector<std::string>{}/g; s/rclcpp::PARAMETER_DOUBLE_ARRAY/std::vector<double>{}/g'
  if [[ -f "${TARGET}/src/dddmr_navigation/src/dddmr_lego_loam/lego_loam_bor/include/transforms.hpp" ]]; then
    perl -0pi -e 's/cloud_out\.assign \(cloud_in\.begin \(\), cloud_in\.end \(\), cloud_in\.width\);/cloud_out = cloud_in;/g' \
      "${TARGET}/src/dddmr_navigation/src/dddmr_lego_loam/lego_loam_bor/include/transforms.hpp"
  fi
  if [[ -f "${TARGET}/src/dddmr_navigation/src/dddmr_mcl_3dl/src/sub_maps.cpp" ]]; then
    perl -0pi -e \
      's|map_current_ = std::make_shared<pcl::PointCloud<pcl_t>>\(\);|map_current_ = pcl::PointCloud<pcl_t>::Ptr(new pcl::PointCloud<pcl_t>());|g;
       s|ground_current_ = std::make_shared<pcl::PointCloud<pcl_t>>\(\);|ground_current_ = pcl::PointCloud<pcl_t>::Ptr(new pcl::PointCloud<pcl_t>());|g;
       s|map_warmup_ = std::make_shared<pcl::PointCloud<pcl_t>>\(\);|map_warmup_ = pcl::PointCloud<pcl_t>::Ptr(new pcl::PointCloud<pcl_t>());|g;
       s|ground_warmup_ = std::make_shared<pcl::PointCloud<pcl_t>>\(\);|ground_warmup_ = pcl::PointCloud<pcl_t>::Ptr(new pcl::PointCloud<pcl_t>());|g' \
      "${TARGET}/src/dddmr_navigation/src/dddmr_mcl_3dl/src/sub_maps.cpp"
    perl -0pi -e \
      's|bool b_initialized_;|bool b_initialized_;\n  bool sync_request_in_flight_;|g' \
      "${TARGET}/src/dddmr_navigation/src/dddmr_mcl_3dl/include/mcl_3dl/sub_maps.h"
    perl -0pi -e \
      's|service_map_name_\(service_map_name\), knn_num_of_ground_normals_|service_map_name_(service_map_name), sync_request_in_flight_(false), knn_num_of_ground_normals_|g;
       s|(void subMapManager::syncMapThread\(\)\{\n\s*if\(cornerCloudKeyFrames_\.size\(\) >= cornerCloudKeyFramesNum_\)\n\s*return;)|$1\n  if(sync_request_in_flight_)\n    return;|g;
       s|(using GetKeyFrameCloud = dddmr_sys_core::srv::GetKeyFrameCloud;\n\s*auto req = std::make_shared<GetKeyFrameCloud::Request>\(\);\n\s*req->index = cornerCloudKeyFrames_\.size\(\);)|$1\n  sync_request_in_flight_ = true;|g;
       s|(cornerCloudKeyFrames_\.push_back\(featureCloud\);\n\s*groundCloudKeyFrames_\.push_back\(groundCloud\);)|$1\n        sync_request_in_flight_ = false;|g;
       s|(RCLCPP_ERROR\(node_->get_logger\(\), "Exception while sync map: %s", e\.what\(\)\);)|$1\n        sync_request_in_flight_ = false;|g' \
      "${TARGET}/src/dddmr_navigation/src/dddmr_mcl_3dl/src/sub_maps.cpp"
  fi
  if [[ -f "${TARGET}/src/dddmr_navigation/src/dddmr_mcl_3dl/src/mcl_3dl.cpp" ]]; then
    perl -0pi -e \
      's|map2odom_trans_\.transform\.translation\s*=\s*tf2::toMsg\(\s*tf2::Vector3\(\s*map_pos\.x_,\s*map_pos\.y_,\s*map_pos\.z_\s*\)\s*\);|map2odom_trans_.transform.translation.x = map_pos.x_;\n  map2odom_trans_.transform.translation.y = map_pos.y_;\n  map2odom_trans_.transform.translation.z = map_pos.z_;|g' \
      "${TARGET}/src/dddmr_navigation/src/dddmr_mcl_3dl/src/mcl_3dl.cpp"
  fi
  if [[ -d "${TARGET}/src/dddmr_navigation/src/dddmr_p2p_move_base" ]]; then
    p2p_root="${TARGET}/src/dddmr_navigation/src/dddmr_p2p_move_base"
    perl -0pi -e       's|void global_planner_client_goal_response_callback\(const rclcpp_action::ClientGoalHandle<dddmr_sys_core::action::GetPlan>::SharedPtr & goal_handle\);|void global_planner_client_goal_response_callback(std::shared_future<rclcpp_action::ClientGoalHandle<dddmr_sys_core::action::GetPlan>::SharedPtr> goal_handle_future);|g'       "${p2p_root}/include/p2p_move_base/p2p_global_plan_manager.h"
    perl -0pi -e       's|void P2PGlobalPlanManager::global_planner_client_goal_response_callback\(const rclcpp_action::ClientGoalHandle<dddmr_sys_core::action::GetPlan>::SharedPtr & goal_handle\)
\{|void P2PGlobalPlanManager::global_planner_client_goal_response_callback(std::shared_future<rclcpp_action::ClientGoalHandle<dddmr_sys_core::action::GetPlan>::SharedPtr> goal_handle_future)
{
  auto goal_handle = goal_handle_future.get();|g'       "${p2p_root}/src/p2p_global_plan_manager.cpp"
    perl -0pi -e       's|void recovery_behaviors_client_goal_response_callback\(const rclcpp_action::ClientGoalHandle<dddmr_sys_core::action::RecoveryBehaviors>::SharedPtr & goal_handle\);|void recovery_behaviors_client_goal_response_callback(std::shared_future<rclcpp_action::ClientGoalHandle<dddmr_sys_core::action::RecoveryBehaviors>::SharedPtr> goal_handle_future);|g'       "${p2p_root}/include/p2p_move_base/p2p_move_base.h"
    perl -0pi -e       's|void P2PMoveBase::recovery_behaviors_client_goal_response_callback\(const rclcpp_action::ClientGoalHandle<dddmr_sys_core::action::RecoveryBehaviors>::SharedPtr & goal_handle\)
\{|void P2PMoveBase::recovery_behaviors_client_goal_response_callback(std::shared_future<rclcpp_action::ClientGoalHandle<dddmr_sys_core::action::RecoveryBehaviors>::SharedPtr> goal_handle_future)
{
  auto goal_handle = goal_handle_future.get();|g'       "${p2p_root}/src/p2p_move_base.cpp"
  fi
fi

set +u
# shellcheck disable=SC1090
source "${ROS_SETUP}"
set -u

export CMAKE_PREFIX_PATH="${LOCAL_PREFIX}:${CMAKE_PREFIX_PATH:-}"
export LD_LIBRARY_PATH="${LOCAL_PREFIX}/lib:${LOCAL_PREFIX}/lib64:${LD_LIBRARY_PATH:-}"

build_cmake_project() {
  local source_dir="$1"
  local build_dir="$2"
  shift 2
  cmake -S "${source_dir}" -B "${build_dir}" \
    -DCMAKE_INSTALL_PREFIX="${LOCAL_PREFIX}" \
    -DCMAKE_BUILD_TYPE=Release "$@"
  cmake --build "${build_dir}" --parallel "${PARALLEL_WORKERS}"
  cmake --install "${build_dir}"
}

LIGHTNING_SRC="${TARGET}/src/lightning-lm-deep-robotics"
if [[ "${BUILD_THIRDPARTY}" == "1" ]]; then
  mkdir -p "${LOCAL_PREFIX}"
  if [[ -d "${LIGHTNING_SRC}/thirdparty/glog" ]]; then
    build_cmake_project \
      "${LIGHTNING_SRC}/thirdparty/glog" \
      "${TARGET}/build_glog" \
      -DBUILD_SHARED_LIBS=ON \
      -DBUILD_TESTING=OFF
    if [[ ! -d "${LOCAL_PREFIX}/lib/cmake/glog" && \
          ! -d "${LOCAL_PREFIX}/lib64/cmake/glog" ]]; then
      echo "vendored glog was not installed in the isolated runtime prefix" >&2
      exit 26
    fi
  fi
  if [[ -d "${LIGHTNING_SRC}/thirdparty/Pangolin" ]]; then
    build_cmake_project \
      "${LIGHTNING_SRC}/thirdparty/Pangolin" \
      "${TARGET}/build_pangolin" \
      -DBUILD_EXAMPLES=OFF \
      -DBUILD_TOOLS=OFF \
      -DCMAKE_CXX_FLAGS="-Wno-error"
  fi
fi

cd "${TARGET}"
export MAKEFLAGS="-j${PARALLEL_WORKERS}"
FOXY_CMAKE_ARGS=()
if [[ "${ROS_DISTRO_NAME}" == "foxy" ]]; then
  FOXY_CMAKE_ARGS+=("-DCMAKE_CXX_FLAGS=-I${TARGET}/foxy_compat/include")
fi
colcon build \
  --merge-install \
  --symlink-install \
  --parallel-workers "${PARALLEL_WORKERS}" \
  --executor sequential \
  --packages-up-to \
    lightning \
    lego_loam_bor \
    mcl_3dl \
    perception_3d \
    global_planner \
    p2p_move_base \
  --cmake-args -DCMAKE_BUILD_TYPE=Release -DTRT_ENABLED=OFF -DLEGO_LOAM_BOR_BUILD_BAG_TOOLS=OFF "${FOXY_CMAKE_ARGS[@]}"

set +u
# shellcheck disable=SC1091
source "${TARGET}/install/setup.bash"
set -u
[[ "${ROS_DISTRO:-}" == "${ROS_DISTRO_NAME}" ]] || {
  echo "built workspace reports ROS_DISTRO=${ROS_DISTRO:-unset}, expected ${ROS_DISTRO_NAME}" >&2
  exit 24
}
ros2 pkg prefix lightning >/dev/null
for package_name in lego_loam_bor mcl_3dl perception_3d global_planner p2p_move_base; do
  ros2 pkg prefix "${package_name}" >/dev/null
done
for executable_spec in \
  "lego_loam_bor:mcl_feature" \
  "mcl_3dl:mcl_3dl" \
  "perception_3d:perception_3d_ros_node" \
  "global_planner:global_planner_node" \
  "p2p_move_base:p2p_move_base_node"; do
  package_name="${executable_spec%%:*}"
  executable_name="${executable_spec##*:}"
  ros2 pkg executables "${package_name}" | awk -v executable="${executable_name}" \
    '$2 == executable { found = 1 } END { exit(found ? 0 : 1) }' || {
      echo "required official DDDMR executable is missing: ${package_name}/${executable_name}" >&2
      exit 27
    }
done

echo "[prepare_dddmr_foxy_runtime] target=${TARGET}"
echo "[prepare_dddmr_foxy_runtime] distro=${ROS_DISTRO_NAME} arch=$(uname -m)"
echo "[prepare_dddmr_foxy_runtime] lightning=${SOURCE_REPO} ref=${SOURCE_REF}"
echo "[prepare_dddmr_foxy_runtime] dddmr=${DDDMR_SOURCE_REPO} ref=${DDDMR_SOURCE_REF}"
if [[ -d "${DDDMR_SOURCE_ROOT}/src/dddmr_mcl_3dl" ]]; then
  echo "[prepare_dddmr_foxy_runtime] dddmr_source=offline:${DDDMR_SOURCE_ROOT}"
fi
echo "[prepare_dddmr_foxy_runtime] ready: set M20PRO_DDDMR_RUNTIME_WS=${TARGET}"
