# 山猫M20开发指南（离线保存）

> 来源页面：IMU.html

- 
- 
- 
- 
- IMU

本文档介绍山猫 M20 的 IMU 硬件参数、安装标定、坐标变换以及数据获取方式。目录1. 硬件参数2. 安装位置3. 坐标变换4. 数据获取 —— ROS25. 数据获取 —— basic_server 通信协议6. 状态检查﻿﻿
# 1. 硬件参数
| 参数 | 规格 |
|---|---|
| 类型 | 6 轴 IMU（3 轴加速度计 + 3 轴陀螺仪） |
| 应用 | 高性能运动跟踪、姿态估计 |
| 数据话题频率 | 200Hz |﻿﻿
# 2. 安装位置
IMU 相对于 base_link 坐标系的安装位置如下：| 传感器 | X (mm) | Y (mm) | Z (mm) |
|---|---|---|---|
| IMU | 63.2 | -26.8 | -43.5 |﻿﻿
# 3. 坐标变换
IMU 芯片的安装姿态相对于 base_link 存在 绕 X 轴 90 度旋转（roll = pi/2），因此在将 IMU 原始数据映射到 base_link 坐标系时需要进行轴变换：●
### 加速度计轴变换：
复制代码9123▶acc_x (base_link) = acc_x_originalacc_y (base_link) = -acc_z_originalacc_z (base_link) = acc_y_original●
### 陀螺仪轴变换：
复制代码9123▶gyro_x (base_link) = gyro_x_originalgyro_y (base_link) = -gyro_z_originalgyro_z (base_link) = gyro_y_original上述变换已在 AOS 端驱动层自动完成。通过 ROS2 /IMU 话题获取的数据已经是变换后对齐到 base_link 坐标系的值，开发者无需再手动转换。﻿﻿
# 4. 数据获取 —— ROS2
IMU 数据通过以下 ROS2 话题发布（对外可见话题，31+33 网段均可访问）：| 话题名 | sensor_msgs/msg/Imu |
|---|---|
| 说明 | IMU 数据（已坐标变换） |
| 消息类型 | sensor_msgs/msg/Imu |
| 频率 | 200Hz |
| 依赖服务 | yesense.service |
| 话题可见性 | 31+33网段的主机上可见 |复制代码912345▶# 查看 IMU 数据ros2 topic echo /IMU
# 确认发布频率ros2 topic hz /IMU # 预期 200Hz内部话题说明：系统内部还存在 /IMU_YESENSE（AOS 本地原始数据，200Hz）、/IMU_DATA（含欧拉角扩展字段）和 /IMU_DATA_10HZ（降频 10Hz 版本）等话题，这些为内部调试使用，不在对外接口清单中，不建议二次开发依赖。﻿﻿
# 5. 数据获取 —— basic_server 通信协议
IMU 姿态信息通过 Type=1002, Cmd=4（运动状态上报）获取。该上报以 10Hz 频率周期性主动推送，TCP 连接建立后自动接收，UDP 需先发送一次查询请求注册。姿态数据位于 Items.MotionStatus 字段中：| 字段 | 单位 | 说明 |
|---|---|---|
| MotionStatus.Roll | rad | 机身横滚角 |
| MotionStatus.Pitch | rad | 机身俯仰角 |
| MotionStatus.Yaw | rad | 机身偏航角 |
| MotionStatus.OmegaZ | rad/s | 偏航角速度 |注意：basic_server 通信协议提供的是经过融合处理后的姿态信息，非原始 IMU 数据。如需原始 200Hz 加速度计和陀螺仪数据，请使用 ROS2 /IMU 话题。上报数据中 MotionStatus 部分示例：复制代码9123456▶▶"MotionStatus": { "Roll": 0.012, "Pitch": -0.005, "Yaw": 1.234, "OmegaZ": 0.001}﻿﻿
# 6. 状态检查
IMU 没有独立的开关控制——不存在 basic_server 指令用于启用或禁用 IMU。IMU 随 AOS 上电自动运行，持续输出数据。可通过以下方式确认 IMU 工作状态：| 检查方式 | 方法 | 预期结果 |
|---|---|---|
| ROS2 话题频率 | ﻿ros2 topic hz /IMU﻿ | 稳定 ~200Hz |
| basic_server 姿态上报 | 检查 Type=1002 Cmd=4 返回 | Roll/Pitch/Yaw/OmegaZ 持续更新 |如果 /IMU 话题频率明显低于 200Hz 或无数据输出，请检查：1.AOS 是否正常上电2.IMU 驱动进程是否存活（AOS 侧检查）﻿相关文档：ROS 2 / DDS 话题速查 | basic_server 通信协议总览| 软件开发指南 大纲IMU1. 硬件参数2. 安装位置3. 坐标变换加速度计轴变换：陀螺仪轴变换：4. 数据获取 —— ROS25. 数据获取 —— basic_server 通信协议6. 状态检查