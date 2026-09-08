# 山猫M20开发指南（离线保存）

> 来源页面：定位模块.html

- 
- 
- 
- 
- 定位模块

本文档介绍山猫 M20 定位模块的使用方法和开发接口。仅 M20 Pro 支持定位功能，M20 标准版未包含本章节功能。目录1. 概述2. 输出话题3. 定位状态监测3.1 basic_server 协议（Type=2002 Cmd=1）3.2 ROS2 方式4. 定位初始化（用户告诉机器人位置）4.1 basic_server 协议（Type=2101 Cmd=1）4.2 ROS2 方式5. 获取机器人位姿5.1 basic_server 协议（Type=1007 Cmd=2）5.2 ROS2 方式﻿﻿
# 1. 概述
定位模块（localization.service）运行在 NOS 上，融合 LiDAR + IMU 数据，在已建地图上进行实时位姿估计。能力边界：●只可在已构建的地图上进行定位●地图场景变化较大时可能引发定位丢失●激光雷达失效时定位失效﻿﻿
# 2. 输出话题
| 话题 | 消息类型 | 说明 |
|---|---|---|
| ﻿/ODOM﻿ | nav_msgs/Odometry | 定位位姿（map 坐标系），导航核心输入 |
| ﻿/LOC_BODY_POINTS﻿ | sensor_msgs/PointCloud2 | 机身坐标系点云（base_link） |
| ﻿/ALIGNED_POINTS﻿ | sensor_msgs/PointCloud2 | 配准后地图坐标系点云 |
| ﻿/FULL_CLOUD_MAP﻿ | sensor_msgs/PointCloud2 | 全局地图点云（可视化，降采样） |
| ﻿/LOCATION_STATUS﻿ | drdds/msg/LocationStatus | 定位详细状态（总状态/输入源/丢失检测） |
| ﻿/LOCATION_STATUS/MATCHING_ERROR﻿ | std_msgs/Float64MultiArray | [matching_error, inlier_ratio] 匹配质量量化 |
| ﻿/tf﻿ | tf2_msgs/TFMessage | map → base_link 实时变换 |﻿﻿
# 3. 定位状态监测

## 3.1 basic_server 协议（Type=2002 Cmd=1）
文档中出现的所有 Type / Command 均为十进制数字。JSON 请求复制代码912345678▶▶▶{ "PatrolDevice": { "Type": 2002, "Command": 1, "Time": "2023-01-01 00:00:00", "Items": {} }}JSON 响应复制代码991234567891011▶▶▶▶{ "PatrolDevice": { "Type": 2002, "Command": 1, "Time": "2023-01-01 00:00:00", "Items": { "Location": 1, "ObsState": 0.0 } }}| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| Location | int | — | 定位状态：0=正常，1=丢失 |
| ObsState | int | — | 避障状态：0=无障碍物，1=有障碍物处于避障 |﻿
## 3.2 ROS2 方式
复制代码912345▶# 查看定位状态话题ros2 topic echo /LOCATION_STATUS
# 查看匹配误差ros2 topic echo /LOCATION_STATUS/MATCHING_ERROR其中 /LOCATION_STATUS 的消息结构为 drdds/msg/LocationStatus：复制代码991234567891011121314151617181920212223▶MetaType header uint64 frame_id Timestamp timestamp int32 sec uint32 nsecLocationStatusValue data uint8 total_status # 状态码 ExecStatusValue exec_val uint8 overtime uint8 numeric_error uint8 timestamp_error LossStatusValue loss_val uint8 odom_error uint8 leg_odom_error uint8 matching_error uint8 pub_error InputStatusValue input_val uint8 lidar uint8 imu uint8 leg_odom uint8 rtk uint8 tag uint8 reflective_striptotal_status 为定位状态码：| 状态码 | 含义 | 处理方式 |
|---|---|---|
| 0 | 未初始化 | 使用定位初始化指令或 drmap apply 后初始化 |
| 1 | 正常 | 无需处理 |
| 2 | 低质量 | matching_error 增大或 inlier_ratio 下降，注意观察 |
| 3 | 丢失 | 立即停止导航，重新初始化定位 |话题 /LOCATION_STATUS/MATCHING_ERROR 以 std_msgs/Float64MultiArray 发布一维数组，包含两个数值：| data 索引 | 字段名 | 含义 | 正常参考值 |
|---|---|---|---|
| data[0] | matching_error | 当前帧点云与地图的匹配误差 | 越小越好，> 0.25 视为异常 |
| data[1] | inlier_ratio | 配准内点比例（有效匹配点占比） | 越高越好，﻿﻿
# 4. 定位初始化（用户告诉机器人位置）
定位初始化用于在定位丢失或需要重新设定机器人位姿时执行，需要用户自行下发位姿数据。
## 4.1 basic_server 协议（Type=2101 Cmd=1）
JSON 请求复制代码9912345678910111213▶▶▶▶{ "PatrolDevice": { "Type": 2101, "Command": 1, "Time": "2026-05-20 10:00:00", "Items": { "PosX": 0.0, "PosY": 0.0, "PosZ": 0.0, "Yaw": 0.0 } }}XML 请求复制代码99123456789101112▶▶▶<?xml version="1.0" encoding="UTF-8"?><PatrolDevice> <Type>2101</Type> <Command>1</Command> <Time>2026-05-20 10:00:00</Time> <Items> <PosX>0.0</PosX> <PosY>0.0</PosY> <PosZ>0.0</PosZ> <Yaw>0.0</Yaw> </Items></PatrolDevice>| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| PosX | float | m | 机器人在地图坐标系下需要重新定位的 X 坐标 |
| PosY | float | m | 机器人在地图坐标系下需要重新定位的 Y 坐标 |
| PosZ | float | m | 机器人在地图坐标系下需要重新定位的 Z 坐标（通常设为 0） |
| Yaw | float | rad | 机器人在地图坐标系下绕 Z 轴旋转的姿态角 |响应复制代码9123456789▶▶▶▶{ "PatrolDevice": { "Type": 2101, "Command": 1, "Items": { "ErrorCode": 0 } }}| ErrorCode | 含义 |
|---|---|
| 0 | 执行成功 |
| 1 | 执行失败 |﻿
## 4.2 ROS2 方式
方式一：发布 /initialpose 话题通过 /initialpose 话题发布 geometry_msgs/msg/PoseWithCovarianceStamped 消息，为定位重置当前位姿。由于定位需要一些时间，建议间隔 3s 后再确认定位状态 /LOCATION_STATUS 是否已收敛为正常。方式二：RViz2 中手动重置在 RViz2 中使用 2D Pose Estimate 工具，在地图上点击并拖动设置机器人的位姿，具体参考软件使用指南。﻿﻿
# 5. 获取机器人位姿

## 5.1 basic_server 协议（Type=1007 Cmd=2）
JSON 请求复制代码912345678▶▶▶{ "PatrolDevice": { "Type": 1007, "Command": 2, "Time": "2026-05-20 10:00:00", "Items": {} }}JSON 响应复制代码9912345678910111213141516▶▶▶▶{ "PatrolDevice": { "Type": 1007, "Command": 2, "Time": "2026-05-20 10:00:00", "Items": { "Location": 0, "PosX": 1.23, "PosY": -0.45, "PosZ": 0.0, "Roll": 0.0, "Pitch": 0.0, "Yaw": 1.57 } }}| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| Location | int | — | 定位状态：0=正常，1=丢失 |
| PosX / PosY / PosZ | float | m | 机器人在地图坐标系下的坐标 |
| Roll / Pitch / Yaw | float | rad | 机器人在地图坐标系下的姿态角度 |
## 5.2 ROS2 方式
通过 /ODOM 话题获取位姿（nav_msgs/Odometry，10Hz）。相关文档：软件使用指南 | 建图与地图管理| ROS 2 / DDS 话题速查﻿大纲定位模块1. 概述2. 输出话题3. 定位状态监测3.1 basic_server 协议（Type=2002 Cmd=1）3.2 ROS2 方式4. 定位初始化（用户告诉机器人位置）4.1 basic_server 协议（Type=2101 Cmd=1）4.2 ROS2 方式5. 获取机器人位姿5.1 basic_server 协议（Type=1007 Cmd=2）5.2 ROS2 方式