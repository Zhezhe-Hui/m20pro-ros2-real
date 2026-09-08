# 山猫M20开发指南（离线保存）

> 来源页面：照明灯.html

- 
- 
- 
- 
- 照明灯

本文档介绍山猫 M20 机身前后照明灯的控制方法。前后照明灯可独立开关。目录1. 概述2. 设备控制2.1 参数说明2.2 开启前照明灯2.3 开启后照明灯3. 状态查询﻿﻿
# 1. 概述
山猫 M20 配备前后两路照明灯。前后灯可独立控制，也可同时开关。照明灯通过 basic_server 通信协议 Type=1101, Cmd=2 控制。﻿﻿
# 2. 设备控制
照明灯开关通过 Type=1101, Cmd=2（设备控制）命令操作。该命令为请求-响应模式：通过 TCP 或 UDP 发送控制指令，机器人收到后执行并返回响应报文。前后照明灯通过 Front 和 Back 字段独立控制，值为 0（关闭）或 1（开启）。
## 2.1 接口说明
| Type字段值 | Command字段值 | 消息类型 |
|---|---|---|
| 1101 | 2 | 照明灯 |文档中出现的所有 Type / Command 均为十进制数字。JSON格式请求：复制代码991234567891011▶▶▶▶{ "PatrolDevice": { "Type": 1101, "Command": 2, "Time": "2023-01-01 00:00:00", "Items": { "Front": 0, "Back": 0 } }}XML格式请求：复制代码9912345678910▶▶▶<?xml version="1.0" encoding="UTF-8"?><PatrolDevice> <Type>1101</Type> <Command>2</Command> <Time>2023-01-01 00:00:00</Time> <Items> <Front>0</Front> <Back>0</Back> </Items></PatrolDevice>| 字段 | 值 | 含义 |
|---|---|---|
| Front | 0 | 前灯光关闭 |
| Front | 1 | 前灯光开启 |
| Back | 0 | 后灯光关闭 |
| Back | 1 | 后灯光开启 |﻿
## 2.2 开启前照明灯
复制代码991234567891011▶▶▶▶{ "PatrolDevice": { "Type": 1101, "Command": 2, "Time": "2026-05-20 10:00:00", "Items": { "Front": 1, "Back": 0 } }}复制代码9912345678910▶▶▶<?xml version="1.0" encoding="UTF-8"?><PatrolDevice> <Type>1101</Type> <Command>2</Command> <Time>2026-05-20 10:00:00</Time> <Items> <Front>1</Front> <Back>0</Back> </Items></PatrolDevice>﻿
## 2.3 开启后照明灯
复制代码991234567891011▶▶▶▶{ "PatrolDevice": { "Type": 1101, "Command": 2, "Time": "2026-05-20 10:00:00", "Items": { "Front": 0, "Back": 1 } }}复制代码9912345678910▶▶▶<?xml version="1.0" encoding="UTF-8"?><PatrolDevice> <Type>1101</Type> <Command>2</Command> <Time>2026-05-20 10:00:00</Time> <Items> <Front>0</Front> <Back>1</Back> </Items></PatrolDevice>下发控制指令后，请通过状态查询（第 3 节）确认 Led.Fill.Front / Led.Fill.Back 字段是否已更新为目标值。﻿﻿
# 3. 状态查询
照明灯的开关状态通过 Type=1002, Cmd=5（设备状态上报）获取。该上报以 2Hz 频率周期性主动推送，TCP 连接建立后自动接收，UDP 需先发送一次查询请求注册。照明灯状态位于 Items.Led.Fill 字段中：| 字段 | 值 | 含义 |
|---|---|---|
| Led.Fill.Front | 0 / 1 | 前照明灯 关闭/开启 |
| Led.Fill.Back | 0 / 1 | 后照明灯 关闭/开启 |上报数据中 Led 部分示例：复制代码9123456▶▶▶"Led": { "Fill": { "Front": 1, "Back": 1 }}﻿相关文档：ROS 2 / DDS 话题速查 | basic_server 通信协议总览| 软件开发指南 大纲照明灯1. 概述2. 设备控制2.1 接口说明2.2 开启前照明灯2.3 开启后照明灯3. 状态查询