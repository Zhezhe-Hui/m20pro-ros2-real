# 山猫M20开发指南（离线保存）

> 来源页面：电池.html

- 
- 
- 
- 
- 电池

本文档介绍山猫 M20 双电池系统的参数、状态监控方法与异常处理。目录1. 概述2. 硬件参数3. 状态获取 — basic_server3.1 协议说明3.2 BatteryList 字段（数组形式）3.3 BatteryStatus 字段（聚合状态）3.4 读取示例4. 电池异常告警4.1 电池异常错误码4.2 component 字段5. 自主充电﻿﻿
# 1. 概述
山猫 M20 配备双电池系统（前电池 + 后电池），通过 basic_server 协议 Type=1002 Cmd=5（设备状态上报，2Hz）周期性返回电池电压、电量、温度和充电状态。﻿﻿
# 2. 硬件参数
| 参数 | 规格 |
|---|---|
| 电池数量 | 2 |
| 额定电压 | 72V |
| 容量 | 4.5 Ah |
| 充电电压 | 100V~240V AC |
| 充电器 | 84V/3A |
| 充电时间 | 1.5h~2h（完全充电） |﻿﻿
# 3. 状态获取 — basic_server

## 3.1 协议说明
| 属性 | 值 |
|---|---|
| Type | 1002 |
| Command | 5 |
| 上报频率 | 2Hz（主动上报） |
| 数据路径 | Items.BatteryStatus 和 Items.BatteryList |文档中出现的所有 Type / Command 均为十进制数字。﻿
## 3.2 BatteryList 字段（数组形式）
本字段以数组形式上报双电池的状态，从软件包版本≥1.1.8开始支持。| 编号 | 位置 | 说明 |
|---|---|---|
| BatteryList[0] | 后电池 | 靠近硬急停按钮一侧 |
| BatteryList[1] | 前电池 | 远离硬急停按钮一侧 || 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| Voltage | float | V | 电池电压 |
| BatteryLevel | int | % | 剩余电量 [0, 100] |
| battery_temperature | float | C | 电池温度 |
| charge | bool | — | 是否正在充电 |
| serial | string | — | 电池序列号 |﻿
## 3.3 BatteryStatus 字段（聚合状态）
| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| VoltageLeft | float | V | 左侧电池电压 |
| VoltageRight | float | V | 右侧电池电压 |
| BatteryLevelLeft | int | % | 左侧电池电量 |
| BatteryLevelRight | int | % | 右侧电池电量 |
| battery_temperatureLeft | float | C | 左侧电池温度 |
| battery_temperatureRight | float | C | 右侧电池温度 |
| chargeLeft | bool | — | 左侧是否充电 |
| chargeRight | bool | — | 右侧是否充电 |BatteryStatus 中的 Left/Right 命名：Right = 靠近硬急停按钮一侧。﻿
## 3.4 读取示例
该上报以 2Hz 频率周期性主动推送，TCP 连接建立后自动接收，UDP 需先发送一次查询请求注册。上报数据中电池部分示例：复制代码9912345678910▶▶▶"BatteryList": [ { "Voltage": 54.2, "BatteryLevel": 78, "battery_temperature": 32.5, "charge": false, "serial": "BAT-001" }, { "Voltage": 54.0, "BatteryLevel": 76, "battery_temperature": 31.8, "charge": false, "serial": "BAT-002" }],"BatteryStatus": { "VoltageLeft": 54.2, "VoltageRight": 54.0, "BatteryLevelLeft": 78, "BatteryLevelRight": 76, "battery_temperatureLeft": 32.5, "battery_temperatureRight": 31.8, "chargeLeft": false, "chargeRight": false}﻿﻿
# 4. 电池异常告警

## 4.1 电池异常错误码
电池异常通过 Type=1002 Cmd=3（错误状态上报）返回：| 错误码（十六进制） | 含义 | 级别 |
|---|---|---|
| 0x8102 | 电池电量低警告 | 警告 |
| 0x8103 | 电池电量保护 | 保护 |
| 0x8106 | 电池最低电压保护 | 保护 |
| 0x8107 | 电池放电过温保护 | 保护 |
| 0x8108 | 电池单体欠压 | 警告 |
| 0x8112 | 电池放电低温保护 | 保护 |
| 0x8115 | 电池充电过温保护 | 保护 |
| 0x8116 | 电池充电低温保护 | 保护 |
| 0x8117 | 电池单体过压 | 警告 |
| 0x8118 | 电池包过压 | 保护 |
| 0x8119 | 电池包欠压 | 保护 |
| 0x8120 | 电池充电过流 | 保护 |
| 0x8121 | 电池放电过流 | 保护 |
| 0x8122 | 短路保护 | 保护 |
| 0x8123 | 电池前端 IC 错误 | 故障 |
| 0x8124 | 电池软件 MOS 锁定 | 故障 |
| 0x8125 | 电池放电高温警告 | 警告 |
| 0x8126 | 电池放电低温警告 | 警告 |
| 0x8127 | 电池充电高温警告 | 警告 |
| 0x8128 | 电池充电低温警告 | 警告 |
| 0x8129 | 电池最低电压警告 | 警告 |﻿
## 4.2 component 字段
错误上报的 component 字段为位域，用于定位故障电池：| 位 | 含义 | 说明 |
|---|---|---|
| bit 0 | 后电池 | 靠近硬急停按钮一侧 |
| bit 1 | 前电池 | 远离硬急停按钮一侧 |完整错误码列表参见 错误码与异常处理。﻿﻿
# 5. 自主充电
自主充电的详细控制参见 自主充电。﻿相关文档：ROS 2 / DDS 话题速查 | basic_server 通信协议总览| 软件开发指南 大纲电池1. 概述2. 硬件参数3. 状态获取 — basic_server3.1 协议说明3.2 BatteryList 字段（数组形式）3.3 BatteryStatus 字段（聚合状态）3.4 读取示例4. 电池异常告警4.1 电池异常错误码4.2 component 字段5. 自主充电