# 山猫M20开发指南（离线保存）

> 来源页面：相机与视频流.html

- 
- 
- 
- 
- 相机与视频流

本文档介绍山猫 M20 的相机硬件参数、状态查询与 RTSP 视频流获取方式，包括通过 VLC、FFmpeg 等方式访问实时视频流。目录1. 概述2. 硬件规格3. 静态外参4. 相机状态查询 —— basic_server协议5. ROS2 数据接口6. 视频流访问6.1 RTSP 视频流地址6.2 使用 VLC 查看视频流7. 相机视频流配置7.1 关键参数7.2 修改后生效﻿﻿
# 1. 概述
山猫 M20 配备前置 + 后置双路摄像头，通过 RTSP 协议输出实时视频流，供上层应用查看、录制和二次开发。重要说明：相机数据仅通过 RTSP 视频流输出，不发布任何 DDS 数据，也不参与感知计算。相机仅供用户实时监控与录像使用。﻿﻿
# 2. 硬件规格
| 项目 | 参数 |
|---|---|
| 摄像头类型 | 前置 + 后置广角相机 |
| 摄像头数量 | 2（前置 + 后置） |
| 接口 | USB |
| 默认视频编码 | H.265 |
| 流媒体协议 | RTSP |
| 默认状态 | 出厂开启 |﻿﻿
# 3. 静态外参
以下为前后广角相机相对于机器人机体坐标系（Base Link）的安装位置：| 传感器 | x (mm) | y (mm) | z (mm) |
|---|---|---|---|
| 前置广角相机 | 376.46 | 0 | 37.38 |
| 后置广角相机 | -376.46 | 0 | 37.38 |坐标系说明：x 轴正方向为机器人正前方，y 轴正方向为左侧，z 轴正方向为上方。前后相机沿 x 轴对称分布，y 方向居中（y=0），高度一致（z=37.38mm）。﻿﻿
# 4. 相机状态查询 —— basic_server协议
相机开关状态通过 Type=1002, Cmd=5（设备状态上报）获取。该上报以 2Hz 频率周期性主动推送，TCP 连接建立后自动接收，UDP 需先发送一次查询请求注册。相机状态位于 Items.DevEnable.Video 字段中：| 字段 | 值 | 含义 |
|---|---|---|
| DevEnable.Video.Front | 0 / 1 | 前置摄像头 关闭/开启 |
| DevEnable.Video.Back | 0 / 1 | 后置摄像头 关闭/开启 |上报数据中 DevEnable.Video 部分示例：复制代码9123456▶▶▶"DevEnable": { "Video": { "Front": 1, "Back": 1 }}﻿﻿
# 5. ROS2 数据接口
注意：相机不发布任何 ROS2/DDS 话题。视频数据仅通过 RTSP 流媒体协议提供。如需在 ROS2 节点中使用视频数据，请通过 RTSP 客户端订阅视频流（参见下方第 6 节）。﻿﻿
# 6. 视频流访问
摄像头视频流通过独立的 RTSP 流媒体服务提供。
## 6.1 RTSP 视频流地址
| 摄像头 | RTSP 地址 |
|---|---|
| 前置摄像头 | ﻿rtsp://10.21.31.103:8554/video1﻿ |
| 后置摄像头 | ﻿rtsp://10.21.31.103:8554/video2﻿ |
## 6.2 使用 VLC 查看视频流

#### 安装 VLC
●Windows: 从 videolan.org 下载并安装●Linux: sudo apt install vlc﻿●macOS: 从 videolan.org 下载
#### 打开网络串流
1.打开 VLC 播放器2.点击 媒体 -> 打开网络串流（或快捷键 Ctrl+N）3.输入 RTSP 地址，例如：
○前置摄像头：rtsp://10.21.31.103:8554/video1﻿○后置摄像头：rtsp://10.21.31.103:8554/video2﻿4.点击 播放﻿
#### 命令行方式
复制代码912345678▶# 打开前置摄像头视频流vlc rtsp://10.21.31.103:8554/video1
# 打开后置摄像头视频流vlc rtsp://10.21.31.103:8554/video2
# 同时打开两路视频（分屏显示）vlc rtsp://10.21.31.103:8554/video1 rtsp://10.21.31.103:8554/video2﻿﻿
# 7. 相机视频流配置
相机推流（推到手柄 APP 端）的分辨率、帧率、编码格式等参数通过修改推流脚本配置。脚本路径（AOS 主机）：复制代码91▶/opt/robot/scripts/board_resources/rtsp_service/push_video.sh﻿
## 7.1 关键参数
脚本中使用 GStreamer 管线推流，以下为核心参数（以前置摄像头为例）：复制代码912345▶gst-launch-1.0 v4l2src device=/dev/video0 \ ! image/jpeg, width=1280, height=720, framerate=30/1 \ ! jpegdec ! videoconvert \ ! mpph265enc rc-mode=0 bps=1800000 bps-max=2000000 qp-min=12 qp-max=45 \ ! rtspclientsink location=rtsp://127.0.0.1:8554/video1 latency=10| 参数 | 默认值 | 说明 |
|---|---|---|
| ﻿width / height﻿ | 1280 / 720 | 分辨率（宽 × 高） |
| ﻿framerate﻿ | 30/1（30fps） | 帧率 |
| 编码器 | ﻿mpph265enc﻿ | H.265 硬件编码（RK3588 MPP） |
| ﻿bps﻿ | 1800000 | 目标码率 1.8 Mbps |
| ﻿bps-max﻿ | 2000000 | 最大码率 2 Mbps |
| ﻿qp-min / qp-max﻿ | 12 / 45 | 量化参数范围（越小画质越好） |
| ﻿latency﻿ | 10 | RTSP 推流延迟（ms） |前置摄像头设备为 /dev/video0，推流地址 rtsp://127.0.0.1:8554/video1；后置摄像头设备为 /dev/video2，推流地址 rtsp://127.0.0.1:8554/video2。﻿
## 7.2 修改后生效
修改 push_video.sh 后，需执行同目录下的重启脚本使配置生效：复制代码91▶sudo /opt/robot/scripts/board_resources/rtsp_service/restart.sh﻿相关文档：ROS 2 / DDS 话题速查 | basic_server 通信协议总览| 软件开发指南 大纲相机与视频流1. 概述2. 硬件规格3. 静态外参4. 相机状态查询 —— basic_server协议5. ROS2 数据接口6. 视频流访问6.1 RTSP 视频流地址6.2 使用 VLC 查看视频流安装 VLC打开网络串流命令行方式7. 相机视频流配置7.1 关键参数7.2 修改后生效3