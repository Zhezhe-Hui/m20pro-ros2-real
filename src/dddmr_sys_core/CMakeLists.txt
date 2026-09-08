cmake_minimum_required(VERSION 3.5)
project(dddmr_sys_core)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(ament_cmake REQUIRED)
find_package(action_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(tf2_ros REQUIRED)

set(dependencies
  action_msgs
  builtin_interfaces
  geometry_msgs
  nav_msgs
  rclcpp
  rclcpp_action
  sensor_msgs
  std_msgs
  tf2_ros
)

rosidl_generate_interfaces(${PROJECT_NAME}
  "action/PToPMoveBase.action"
  "action/GetPlan.action"
  "action/RecoveryBehaviors.action"
  "action/TagDocking.action"
  "srv/GetKeyFrameCloud.srv"
  DEPENDENCIES builtin_interfaces geometry_msgs nav_msgs sensor_msgs std_msgs
)

include_directories(include)

add_library(dddmr_sys_core_enum SHARED
  src/dddmr_enum_states.cpp
)

ament_target_dependencies(dddmr_sys_core_enum
  ${dependencies}
)

rosidl_target_interfaces(dddmr_sys_core_enum
  ${PROJECT_NAME} "rosidl_typesupport_cpp"
)

install(TARGETS
  dddmr_sys_core_enum
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(DIRECTORY include/
  DESTINATION include/
)

ament_export_include_directories(include)
ament_export_libraries(dddmr_sys_core_enum)
ament_export_dependencies(${dependencies})
ament_export_dependencies(rosidl_default_runtime)

ament_package()
