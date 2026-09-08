# 山猫M20开发指南（离线保存）

> 来源页面：休眠模式.html

- 
- 
- 
- 
- 休眠模式

本文档介绍山猫 M20 机器人的休眠管理功能，包括进入/退出休眠、自动休眠配置和状态查询。目录1. 休眠模式概述2. 进入休眠 —— basic_server 协议3. 唤醒 —— basic_server 协议4. 自动休眠 —— basic_server 协议4.1 启用自动休眠4.2 禁用自动休眠5. 查询休眠状态 —— basic_server 协议﻿﻿
# 1. 休眠模式概述
休眠模式下，机器人会停止运动并降低功耗，但保持基本通信能力。唤醒后可快速恢复工作状态。适用于长时间待机、低电量保护等场景。软件包版本<V1.1.8：机器人趴下，关闭关节、激光雷达、相机、照明灯、LED指示灯等供电。软件包版本≥V1.1.8：机器人趴下，关闭关节、相机、照明灯、LED指示灯等供电。﻿﻿
# 2. 进入休眠 —— basic_server 协议
调用逻辑建议●自动休眠触发条件：○常规/辅助模式：X 分钟无操作消息（默认 5 分钟，可配置范围 [5, 30]）○导航模式：空闲状态持续 X 分钟●手动休眠仅在趴下状态且处于常规/辅助模式时允许；其他状态下不允许。●唤醒后：机器人保持趴下，灯光保持关闭，摄像头恢复至休眠前状态，模式复位为常规模式。通过 Type=1101 Cmd=6 控制休眠，Sleep 字段设为 true 进入休眠。该指令为请求-响应模式，通过 TCP（端口 30001）或 UDP（端口 30000）发送。文档中出现的所有 Type / Command 均为十进制数字。JSON 请求复制代码9912345678910▶▶▶▶{ "PatrolDevice": { "Type": 1101, "Command": 6, "Time": "2026-05-20 10:00:00", "Items": { "Sleep": true } }}XML 请求复制代码9123456789▶▶▶<?xml version="1.0" encoding="UTF-8"?><PatrolDevice> <Type>1101</Type> <Command>6</Command> <Time>2026-05-20 10:00:00</Time> <Items> <Sleep>1</Sleep> </Items></PatrolDevice>下发控制指令后，请通过休眠状态查询（第 5 节，Type=1101 Cmd=7）确认 Sleep 字段是否已更新为目标值。﻿﻿
# 3. 唤醒 —— basic_server 协议
调用逻辑建议●唤醒后机器人保持趴下姿态。●使用模式复位为常规模式。通过 Type=1101 Cmd=6 退出休眠，Sleep 字段设为 false。JSON 请求复制代码9912345678910▶▶▶▶{ "PatrolDevice": { "Type": 1101, "Command": 6, "Time": "2026-05-20 10:00:00", "Items": { "Sleep": false } }}XML 请求复制代码9123456789▶▶▶<?xml version="1.0" encoding="UTF-8"?><PatrolDevice> <Type>1101</Type> <Command>6</Command> <Time>2026-05-20 10:00:00</Time> <Items> <Sleep>0</Sleep> </Items></PatrolDevice>下发控制指令后，请通过休眠状态查询（第 5 节，Type=1101 Cmd=7）确认 Sleep 字段是否已更新为目标值。﻿﻿
# 4. 自动休眠 —— basic_server 协议
通过 Type=1101 Cmd=6 的 Auto 和 Time 字段配置自动休眠。
## 4.1 启用自动休眠
设置机器人在空闲一段时间后自动进入休眠：JSON 请求复制代码99123456789101112▶▶▶▶{ "PatrolDevice": { "Type": 1101, "Command": 6, "Time": "2026-05-20 10:00:00", "Items": { "Sleep": false, "Auto": true, "Time": 5 } }}XML 请求复制代码991234567891011▶▶▶<?xml version="1.0" encoding="UTF-8"?><PatrolDevice> <Type>1101</Type> <Command>6</Command> <Time>2026-05-20 10:00:00</Time> <Items> <Sleep>0</Sleep> <Auto>1</Auto> <Time>5</Time> </Items></PatrolDevice>| 字段 | 类型 | 说明 |
|---|---|---|
| Sleep | boolean | true=直接进入休眠，false=唤醒 |
| Auto | boolean | true=启用自动休眠，false=禁止自动休眠 |
| Time | int | 空闲超时时间（分钟），范围 [5, 30] |﻿
## 4.2 禁用自动休眠
JSON 请求复制代码9912345678910▶▶▶▶{ "PatrolDevice": { "Type": 1101, "Command": 6, "Time": "2026-05-20 10:00:00", "Items": { "Auto": false } }}XML 请求复制代码9123456789▶▶▶<?xml version="1.0" encoding="UTF-8"?><PatrolDevice> <Type>1101</Type> <Command>6</Command> <Time>2026-05-20 10:00:00</Time> <Items> <Auto>0</Auto> </Items></PatrolDevice>﻿﻿
# 5. 查询休眠状态 —— basic_server 协议
通过 Type=1101 Cmd=7 获取当前休眠状态，该指令为请求-响应模式。JSON 请求复制代码912345678▶▶▶{ "PatrolDevice": { "Type": 1101, "Command": 7, "Time": "2026-05-20 10:00:00", "Items": {} }}XML 请求复制代码9123456▶▶<?xml version="1.0" encoding="UTF-8"?><PatrolDevice> <Type>1101</Type><Command>7</Command> <Time>2026-05-20 10:00:00</Time> <Items></Items></PatrolDevice>JSON 响应复制代码9912345678910111213▶▶▶▶{ "PatrolDevice": { "Type": 1101, "Command": 7, "Time": "2026-05-20 10:00:00.123", "Items": { "Code": "0x0000", "Sleep": false, "Auto": true, "Time": 5 } }}XML 响应复制代码99123456789101112▶▶▶<?xml version="1.0" encoding="UTF-8"?><PatrolDevice> <Type>1101</Type> <Command>7</Command> <Time>2026-05-20 10:00:00.123</Time> <Items> <Code>0x0000</Code> <Sleep>0</Sleep> <Auto>1</Auto> <Time>5</Time> </Items></PatrolDevice>| 字段 | 类型 | 含义 |
|---|---|---|
| Sleep | boolean | 当前是否处于休眠状态 |
| Auto | boolean | 自动休眠是否已启用 |
| Time | uint | 自动休眠超时时间（分钟），范围 [5, 30] |﻿相关文档： basic_server 通信协议总览| 软件开发指南 大纲休眠模式1. 休眠模式概述2. 进入休眠 —— basic_server 协议3. 唤醒 —— basic_server 协议4. 自动休眠 —— basic_server 协议4.1 启用自动休眠4.2 禁用自动休眠5. 查询休眠状态 —— basic_server 协议●