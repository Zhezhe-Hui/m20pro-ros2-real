cmake_minimum_required(VERSION 3.5)
project(m20pro_bringup)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(PCL REQUIRED COMPONENTS common io filters)

add_executable(dddmr_edge_cloud_adapter src/dddmr_edge_cloud_adapter.cpp)
ament_target_dependencies(dddmr_edge_cloud_adapter rclcpp sensor_msgs std_msgs)

add_executable(lightning_cloud_adapter src/lightning_cloud_adapter.cpp)
ament_target_dependencies(lightning_cloud_adapter rclcpp sensor_msgs std_msgs)

add_executable(lightning_pcd_asset_adapter src/lightning_pcd_asset_adapter.cpp)
target_include_directories(lightning_pcd_asset_adapter PRIVATE ${PCL_INCLUDE_DIRS})
target_link_libraries(lightning_pcd_asset_adapter ${PCL_LIBRARIES})

install(TARGETS dddmr_edge_cloud_adapter lightning_cloud_adapter lightning_pcd_asset_adapter
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY config launch maps rviz
  DESTINATION share/${PROJECT_NAME}
)

install(PROGRAMS
  scripts/m20pro_visual_joint_state_publisher.py
  scripts/m20pro_map_viz_republisher.py
  scripts/m20pro_real_nav.sh
  scripts/m20pro_real_full.sh
  scripts/m20pro_real_web.sh
  scripts/m20pro_record_real.sh
  scripts/m20pro_lightning_slam_online.sh
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
