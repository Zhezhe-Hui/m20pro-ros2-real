# 山猫M20开发指南（离线保存）

> 来源页面：GNSS.html

- 
- 
- 
- 
- GNSS

本文档介绍山猫 M20 的 GNSS 定位模块与数据获取方式。﻿目录1. 概述2. GNSS 相关接口 —— basic_server 协议3. GNSS 数据获取 — ROS2﻿﻿
# 1. 概述
山猫 M20 配备一体化 GNSS 定位模块，可接通多个卫星系统（GPS、BDS、GLONASS、GALILEO、QZSS）。﻿﻿
# 2. GNSS 相关接口 —— basic_server 协议
GNSS 开关状态和实时定位数据通过 Type=1002, Cmd=5（设备状态上报）获取。该上报以 2Hz 频率周期性主动推送，TCP 连接建立后自动接收，UDP 需先发送一次查询请求注册。GNSS 相关字段有两部分：开关状态 — Items.DevEnable.GPS：| 字段 | 值 | 含义 |
|---|---|---|
| DevEnable.GPS | 0 / 1 | GNSS 关闭/开启 |定位数据 — Items.GPS：| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| GPS.Latitude | float | deg | 纬度（N+, S-） |
| GPS.Longitude | float | deg | 经度（E+, W-） |
| GPS.Speed | float | km/h | 速度 |
| GPS.Course | float | deg | 航向角（从正北起算） |
| GPS.FixQuality | int | — | 0=无效, 1=已固定 |
| GPS.NumSatellites | int | 颗 | 参与定位卫星数 |
| GPS.Altitude | float | m | 海拔 |
| GPS.HDOP | float | — | 水平精度因子 [0.5-99.9] |
| GPS.VDOP | float | — | 垂直精度因子 |
| GPS.PDOP | float | — | 位置精度因子 |
| GPS.VisibleSatellites | int | 颗 | 可见卫星数 |上报数据中 GNSS 相关部分示例：复制代码9912345678910111213▶▶▶"DevEnable": { "GPS": 1},"GPS": { "Latitude": 30.123456, "Longitude": 120.123456, "Speed": 0.5, "Course": 180.0, "FixQuality": 1, "NumSatellites": 12, "Altitude": 15.3, "HDOP": 1.2}﻿﻿
# 3. GNSS 数据获取 — ROS2
| 话题名 | /GPS |
|---|---|
| 说明 | GNSS 定位数据 |
| 消息类型 | drdds/msg/NavSat |
| 频率 | 1Hz |
| 依赖服务 | gps_node |
| 话题可见性 | 仅33网段的主机上可见 |drdds/msg/NavSat 定义如下：复制代码912▶drdds::msg::MetaType header;drdds::msg::NavSatValue data;复制代码91234▶struct MetaType { uint64 frame_id; drdds::msg::Timestamp timestamp;};复制代码99123456789101112131415161718192021222324252627282930313233343536▶struct NavSatValue { @verbatim (language="comment", text= " 纬度（度）") double latitude;
 @verbatim (language="comment", text= " 经度（度）") double longitude;
 @verbatim (language="comment", text= " 地面速度（千米/小时）") double speed;
 @verbatim (language="comment", text= " 航向（度）") double course;
 @verbatim (language="comment", text= " 定位质量") int32 fixquality;
 @verbatim (language="comment", text= " 参与定位的卫星数量") int32 numsatellites;
 @verbatim (language="comment", text= " 海拔高度（米）") double altitude;
 @verbatim (language="comment", text= " 位置精度因子") double pdop;
 @verbatim (language="comment", text= " 水平精度因子") double hdop;﻿相关文档：ROS 2 / DDS 话题速查 | basic_server 通信协议总览| 软件开发指南 大纲GNSS1. 概述2. GNSS 相关接口 —— basic_server 协议3. GNSS 数据获取 — ROS2