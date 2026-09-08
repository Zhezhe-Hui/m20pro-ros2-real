# 山猫M20开发指南（离线保存）

> 来源页面：关节.html

- 
- 
- 
- 
- 关节

本文档介绍山猫 M20 的 16 个关节电机的硬件参数、关节顺序、数据获取方法与温度监控。目录1. 概述2. 硬件参数2.1 关节参数2.2 机械尺寸3. 关节顺序（16 关节）4. 关节参数读取 — basic_server 通信协议4.1 协议说明4.2 MotorStatus 字段（关节状态）5. 关节参数读取和控制指令下发 — ROS26. 关节温度监控 — basic_server 通信协议6.1 协议说明6.2 DeviceTemperature 字段6.3 读取示例7. 关节错误码﻿﻿
# 1. 概述
山猫 M20 共有 16 个关节，分布于 4 条腿：| 腿命名 | 说明 |
|---|---|
| FL | 左前腿 |
| FR | 右前腿 |
| HL | 左后腿 |
| HR | 右后腿 |每条腿 4 个关节：| 关节命名 | 说明 |
|---|---|
| HipX | 侧摆关节 |
| HipY | 髋关节 |
| Knee | 膝关节 |
| Wheel | 轮关节 |﻿﻿
# 2. 硬件参数

## 2.1 关节参数
| 关节参数 | 运动范围/峰值转速 | 峰值扭矩 |
|---|---|---|
| 髋侧摆(HipX) | -35°~25° | 76Nm@72V |
| 髋前摆(HipY) | -140°~140° | 76Nm@72V |
| 膝关节(Knee) | 22°~328° | 76Nm@72V |
| 足轮(Foot) | 68rad/s@72V | 21.6Nm@72V |﻿
## 2.2 机械尺寸
﻿﻿| 连杆参数 | 数值 | 说明 |
|---|---|---|
| 长度(Lbody) | 0.82m | 身体总长度 |
| 髋前后间距(Lhip) | 0.625m | 前后髋关节中心距离 |
| 髋左右间距(Whip) | 0.137m | 左右髋关节中心的距离 |
| 宽度(Wbody) | 0.506m | 身体总宽度 |﻿﻿| 连杆参数 | 数值 | 说明 |
|---|---|---|
| 足部宽度(L1) | 0.104m | 髋侧摆关节中心与大腿平面距离 |
| 大腿长度(L2) | 0.25m | 髋前摆关节中心与膝关节中心在XZ平面上的投影距离 |
| 膝关节宽度(L3) | 0.029m | 大腿平面与小腿平面距离 |
| 小腿长度(L4) | 0.25m | 膝关节中心与足部关节中心在XZ平面上的投影距离 |
| 足部宽度(L5) | 0.073m | 小腿平面与足部关节距离 |
| 足部轮胎直径 | 0.18m | 足部缓冲件直径 |﻿﻿
# 3. 关节顺序（16 关节）
所有关节数组均按以下固定顺序排列，索引 0~15 对应 16 个关节：| 索引 | 名称 | 说明 |
|---|---|---|
| 0 | LeftFrontHipX | 左前侧摆关节 |
| 1 | LeftFrontHipY | 左前髋关节 |
| 2 | LeftFrontKnee | 左前膝关节 |
| 3 | LeftFrontWheel | 左前轮关节 |
| 4 | RightFrontHipX | 右前侧摆关节 |
| 5 | RightFrontHipY | 右前髋关节 |
| 6 | RightFrontKnee | 右前膝关节 |
| 7 | RightFrontWheel | 右前轮关节 |
| 8 | LeftBackHipX | 左后侧摆关节 |
| 9 | LeftBackHipY | 左后髋关节 |
| 10 | LeftBackKnee | 左后膝关节 |
| 11 | LeftBackWheel | 左后轮关节 |
| 12 | RightBackHipX | 右后侧摆关节 |
| 13 | RightBackHipY | 右后髋关节 |
| 14 | RightBackKnee | 右后膝关节 |
| 15 | RightBackWheel | 右后轮关节 |Left = 电池仓侧；Back = 硬急停按钮侧。﻿﻿
# 4. 关节参数读取 — basic_server 通信协议

## 4.1 协议说明
| 属性 | 值 |
|---|---|
| Type | 1002 |
| Command | 4 |
| 上报频率 | 10Hz（主动上报） |
| 数据路径 | Items.MotorStatus |文档中出现的所有 Type / Command 均为十进制数字。﻿
## 4.2 MotorStatus 字段（关节状态）
MotorStatus 包含关节位置和速度数据：| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| Joint[] | float[16] | rad或rad/s | 16 个关节角度/转速（按第 3 节顺序） |HipX、HipY、Knee关节上报的数据为角度（rad）；Wheel关节上报的数据为转速（rad/s）。﻿﻿
# 5. 关节参数读取和控制指令下发 — ROS2
关节相关的 ROS2 话题为 rl_deploy 运动控制部署节点使用的自定义话题，在 31 和 33 网段的主机上均可订阅：| 话题 | 消息类型 | 说明 |
|---|---|---|
| ﻿/JOINTS_DATA﻿ | drdds/msg/JointsData | 关节状态反馈（位置、速度） |
| ﻿/JOINTS_CMD﻿ | drdds/msg/JointsDataCmd | 关节控制指令下发 |运控算法开发的具体操作，参考开源项目 M20 SDK Deploy。﻿﻿
# 6. 关节温度监控 — basic_server 通信协议

## 6.1 协议说明
| 属性 | 值 |
|---|---|
| Type | 1002 |
| Command | 5 |
| 上报频率 | 2Hz（主动上报） |
| 数据路径 | Items.DeviceTemperature |文档中出现的所有 Type / Command 均为十进制数字。﻿
## 6.2 DeviceTemperature 字段
| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| Motor[] | float[16] | ℃ | 16 个关节电机温度（按第 3 节顺序） |
| Driver[] | float[16] | ℃ | 16 个关节驱动器温度（按第 3 节顺序） |﻿
## 6.3 读取示例
该上报以 2Hz 频率周期性主动推送，需客户端持续发送心跳。上报数据中 DeviceTemperature 部分示例：复制代码9123456▶▶▶▶"DeviceTemperature": { "Motor": [42.1, 43.5, 45.2, 38.0, 41.8, 42.9, 44.8, 37.5, 40.3, 41.7, 43.6, 36.8, 41.0, 42.3, 44.1, 37.2], "Driver": [39.5, 40.2, 41.8, 35.1, 38.9, 40.0, 41.5, 34.8, 38.1, 39.4, 40.9, 34.2, 38.6, 39.8, 41.2, 34.5]}﻿﻿
# 7. 关节错误码
关节相关异常通过 Type=1002 Cmd=3（错误状态上报，2Hz + 变更时额外上报）返回。以下为关节相关错误码：| 错误码（十六进制） | 含义 | 级别 |
|---|---|---|
| 0x8001 | 电机温度警告（Motor temp warning） | 警告 |
| 0x8002 | 电机温度过高保护（Motor temp over-high protection） | 保护 |
| 0x8003 | 电机温度致命切断（Motor temp fatal cutoff） | 故障 |
| 0x8007 | 关节驱动器过温（Joint driver overtemp） | 保护 |
| 0x8008 | 驱动器欠压（Driver undervoltage） | 保护 |
| 0x8009 | 驱动器过压（Driver overvoltage） | 保护 |
| 0x8012 | 关节驱动器通信超时（Joint driver comm timeout） | 故障 |
| 0x8016 | 编码器无数值（Encoder no value） | 故障 |
| 0x8020 | 驱动器过流（Driver overcurrent） | 保护 |
| 0x8021 | 温度传感器断连（Temp sensor disconnected） | 故障 |
| 0x8022 | 关节角度超限（Joint angle over limit） | 保护 |
| 0x8024 | 关节数据 NaN（Joint data NaN） | 故障 |
| 0x8025 | 关节数据更新错误（Joint data update error） | 故障 |
| 0x8027 | 机身姿态错误（Body attitude error） | 保护 |
| 0x8028 | 驱动器状态错误（Driver status error） | 故障 |
| 0x8029 | 运动姿态错误（Motion attitude error） | 保护 |
| 0x8030 | 关节驱动器过温警告（Joint driver overtemp warning） | 警告 |完整错误码列表及处理方法参见 错误码与异常处理。﻿相关文档：ROS 2 / DDS 话题速查 | basic_server 通信协议总览| 软件开发指南 大纲关节1. 概述2. 硬件参数2.1 关节参数2.2 机械尺寸3. 关节顺序（16 关节）4. 关节参数读取 — basic_server 通信协议4.1 协议说明4.2 MotorStatus 字段（关节状态）5. 关节参数读取和控制指令下发 — ROS26. 关节温度监控 — basic_server 通信协议6.1 协议说明6.2 DeviceTemperature 字段6.3 读取示例7. 关节错误码