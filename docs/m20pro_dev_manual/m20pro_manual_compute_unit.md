# 山猫M20开发指南（离线保存）

> 来源页面：计算单元.html

- 
- 
- 
- 
- 计算单元

本文档介绍山猫 M20 各个主机的计算单元状态监控方法。目录1. 概述2. 硬件参数3. 状态获取 — basic_server3.1 协议说明3.2 CPU 字段说明3.3 读取示例4. CPU 异常告警﻿﻿
# 1. 概述
山猫 M20 配备2~3台独立的 RK3588 计算单元。各主机的 CPU 使用率、温度和频率信息通过 basic_server 协议 Type=1002 Cmd=5（设备状态上报，2Hz）周期性返回。多主机架构说明参见 软件系统架构说明。﻿﻿
# 2. 硬件参数
| 参数 | 规格 |
|---|---|
| SoC | RK3588（ARM） |
| CPU | 4x Cortex-A76（大核）+ 4x Cortex-A55（小核） |
| 内存 | 16GB LPDDR4x（每台） |﻿﻿
# 3. 状态获取 — basic_server

## 3.1 协议说明
| 属性 | 值 |
|---|---|
| Type | 1002 |
| Command | 5 |
| 上报频率 | 2Hz（主动上报） |
| 数据路径 | Items.CPU |文档中出现的所有 Type / Command 均为十进制数字。﻿
## 3.2 CPU 字段说明
﻿CPU 字段包含三台主机的状态（GOS 仅有 M20 Pro 返回有效值）：| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| CPU.AOS.Temperature | float | ℃ | AOS CPU 温度 |
| CPU.AOS.FrequencyInt | int | % | AOS A55 小核使用率 |
| CPU.AOS.FrequencyApp | int | % | AOS A76 大核使用率 |
| CPU.NOS.Temperature | float | ℃ | NOS CPU 温度 |
| CPU.NOS.FrequencyInt | int | % | NOS A55 小核使用率 |
| CPU.NOS.FrequencyApp | int | % | NOS A76 大核使用率 |
| CPU.GOS.Temperature | float | ℃ | GOS CPU 温度（仅 Pro） |
| CPU.GOS.FrequencyInt | int | % | GOS A55 小核使用率（仅 Pro） |
| CPU.GOS.FrequencyApp | int | % | GOS A76 大核使用率（仅 Pro） |﻿
## 3.3 读取示例
该上报以 2Hz 频率周期性主动推送，TCP 连接建立后自动接收，UDP 需先发送一次查询请求注册。上报数据中 CPU 部分示例：复制代码912345▶▶"CPU": { "AOS": { "Temperature": 62.5, "FrequencyInt": 45, "FrequencyApp": 78 }, "NOS": { "Temperature": 58.3, "FrequencyInt": 32, "FrequencyApp": 65 }, "GOS": { "Temperature": 55.1, "FrequencyInt": 20, "FrequencyApp": 42 }}﻿﻿
# 4. CPU 异常告警
当 CPU 使用率或温度过高时，系统会通过 Type=1002 Cmd=3（错误状态上报）报告以下错误码：| 错误码（十六进制） | 含义 | 级别 |
|---|---|---|
| 0x8201 | CPU 使用率高警告 | 警告 |
| 0x8202 | CPU 温度高警告 | 警告 |
| 0x8211 | CPU 使用率高保护 | 保护 |
| 0x8212 | CPU 温度高保护 | 保护 |完整错误码列表参见 错误码与异常处理。
### 处理建议
●警告级别：系统仍在正常运行，建议减少计算负载或等待散热●保护级别：系统会自行触发软急停保护●可通过 SSH 登录对应主机，使用 top / htop 查看进程级 CPU 使用详情﻿相关文档：ROS 2 / DDS 话题速查 | basic_server 通信协议总览| 软件开发指南 大纲计算单元1. 概述2. 硬件参数3. 状态获取 — basic_server3.1 协议说明3.2 CPU 字段说明3.3 读取示例4. CPU 异常告警处理建议