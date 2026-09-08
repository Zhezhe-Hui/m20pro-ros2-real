# M20 Pro ROS 2 跨楼层巡检导航系统

跨楼层统一导航的 `feature/unified-navigation-v4-lightning` 是从 v2 的“2D + 3D 导航”分支专门分出的纯 3D 分支，当前只做 DDDMR-only 主链；
`main` 仍是已验证现场基线，Gitee/GitHub 只发布验证后的 `main` 成果。
多人协作约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。

这是面向云深处 M20 Pro 的 ROS 2 二次开发 workspace。当前主要用于：

- 在 104 通用主机上运行 DDDMR-only 现场链路、楼层管理、点云融合和网页操作台；
- 104 订阅上游 edge-cloud，建图/资产登记/导航门禁都收口到 DDDMR 接口；跨层只由统一任务链处理，旧爬楼入口保持停用；
- v4 不再把 Nav2 2D 当作前端主流程；如果需要恢复稳定 2D 基线，切回并部署 `main`；
- 内置 DDDMR 公共接口包 `dddmr_sys_core`，解决 104/Foxy 缺 `PToPMoveBase` 类型的问题，但不内置 DDDMR 规划、定位、建图运行时；
- 对接 103 官方 TCP JSON 协议读取位姿/状态，并在允许时下发运动控制；
- 支持单楼层巡检、多楼层地图切换、巡检点编排、YOLO 检测、U360 雷达巡检和现场录包。

详细调试日志、实测记录、问题排查过程放在：

```text
m20pro日志.md
```

单层导航架构、模块边界和实习生分工放在：

```text
docs/single_floor_navigation_architecture.md
```

正式经典前端、甲方前端和外部功能包对接 API 契约放在：

```text
docs/frontend_api_contract.md
```

现场执行脚本 Word 放在：

```text
/home/fabu/桌面/脚本.docx
```

## 主机分工

| 主机 | 地址 | 作用 |
| --- | --- | --- |
| 103 AOS | `10.21.31.103` | 运动控制、官方 TCP 协议、相机 RTSP |
| 104 GOS | `10.21.31.104` | 运行本工程、DDDMR 三维链路和网页前端 |
| 106 NOS | `10.21.31.106` | 上游定位与 edge-cloud 数据发布 |

104 推荐固定工作区：

```text
/home/user/m20pro_real_ros2_ws
```

104 上进入环境的固定顺序：

```bash
ssh user@10.21.31.104
source /opt/robot/scripts/setup_ros2.sh
su
cd /home/user/m20pro_real_ros2_ws
source install/setup.bash
```

## 编译

104/Foxy：

```bash
source /opt/robot/scripts/setup_ros2.sh
cd /home/user/m20pro_real_ros2_ws
source install/setup.bash
colcon build --packages-select \
  m20pro_bringup \
  m20pro_cloud_bridge \
  m20pro_navigation \
  m20pro_inspection \
  m20pro_radar_inspection \
  --symlink-install
source install/setup.bash
```

上位机只做 real 代码构建检查：

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

说明：本仓库现在按 real-only 维护，模型/URDF/mesh 不放在这里；需要仿真时使用单独的 sim 仓库。

## 现场主入口

现场人员直接使用仓库根目录 `scripts/`，不要和 `src/m20pro_bringup/scripts/` 混用。

```bash
./scripts/104_start_real_shadow.sh         # 启动 real，不放开运动控制
./scripts/104_start_real_move.sh           # 启动 real，放开运动控制（move 默认进入 DDDMR 模式）
./scripts/104_preflight_check.sh move      # 终端备用自检，网页自检异常时使用
./scripts/104_stop_real.sh                 # 停止 real
./scripts/104_record_bag.sh 180 m20_test   # 录包
./scripts/104_enable_autostart.sh move     # 安装开机自启动全量 real（move 默认进入 DDDMR 模式）
./scripts/104_dddmr_field_test_mode.sh enable   # 明确切到 DDDMR 3D 模式
./scripts/local_deploy_to_test_robot.sh     # 整狗部署；可配 M20PRO_DEPLOY_REAL_MODE=move|shadow
./scripts/104_verify_dddmr_field_test_deploy.sh  # 只读确认 8080 已部署 DDDMR 按钮/API
./scripts/104_autostart_status.sh          # 查看自启动服务状态
./scripts/104_disable_autostart.sh         # 关闭并移除自启动服务
```

如果当前开发环境不能直连 104，可先运行 `./scripts/local_make_104_source_bundle.sh`
生成源码包、104 本机安装脚本和 `windows_deploy_104_bundle.ps1`。从 Windows
PowerShell 可直接执行 `powershell -ExecutionPolicy Bypass -File ./windows_deploy_104_bundle.ps1 -Host user@10.21.31.104`；
需要同时重启 106 edge scan 以刷新 DDS 发现时加 `-RestartEdge106`，
要求 DDDMR acceptance 必须 ready 才算成功时加 `-RequireFieldReady`。
脚本会先把 bundle / sha256 / installer staging 到 Windows 本机 temp 目录，再 scp 到 104，
避免直接从 WSL 共享路径传输时的兼容问题。
从 Linux/macOS 终端也可手工 scp 后执行 `104_install_source_bundle.sh`。这些入口仍复用 `104_install_staged_workspace.sh`，
保留同一套备份、构建、systemd 和失败回滚逻辑。

诊断和开发入口只在排查时使用：

```bash
./scripts/104_diagnose_preflight.sh
./scripts/104_check_edge_scan.sh
./scripts/104_status.sh                    # 包含 DDDMR 结论
./scripts/104_accept_dddmr_field_test.sh   # DDDMR 低速短目标实测前只读验收
./scripts/104_dddmr_field_test_report.sh   # 只读汇总 DDDMR 验收、地图定位、任务门禁和 3D/GNSS/速度链状态
./scripts/104_start_web.sh                 # 仅开发预览网页，不用于真机测试
./scripts/104_stop_web.sh
```

DDDMR 短目标实测的后端只读接口是 `GET /api/dddmr/field_test`；脚本和前端都以
`navigation_backend.field_test.acceptance.ready` 作为最终开测门禁，并展示/打印接口
返回的 `next_steps`，现场无需再从原始 JSON 里人工找处理步骤。
对当前 `field_proxy` 后端，PASS 还要求 runtime 持续看见 `map -> m20pro_base_link`
TF；否则会返回 `field_proxy_tf_unavailable`，不能启动短目标任务。
PASS 还要求 104 已收到 `command_mux_status` 且 `output_nonzero=false`；若返回
`field_test_command_mux_status_missing`、`field_test_command_mux_status_stale` 或
`blocked_by=command_mux`，说明速度仲裁状态链还不可验证，不能开始 DDDMR 任务。
PASS 还要求当前固定地图楼层与已加载的 DDDMR 三维资产楼层一致、`map_relocalization_required=null`、
`localization_status.confirmed=true`；若返回 `field_test_selected_map_not_ready`、
`field_test_map_relocalization_required` 或 `field_test_localization_not_confirmed`，
先完成地图同步和开发手册 2101 重定位，不要创建/启动 field_proxy 任务。
8080 的基础自检和三维空间状态来自同一组只读证据，不创建任务、不发布速度、不重定位、不切图。
`104_dddmr_field_test_report.sh` 是同一套接口的只读现场报告：一次性打印
`/api/dddmr/field_test`、`/api/tasks` 里的 `field_test_task_gate`、当前 active task、
`selected_map_status`、`map_relocalization_required`、`localization_status`、当前位姿新鲜度、
edge-cloud、mapcloud/mapground、GNSS、command_mux 摘要，以及 `nearest_annotations`
最近点距离，便于把 DDDMR 问题完整反馈回来。
辅助 GNSS 由 104 把上游 `/GPS` 适配为 `/m20pro/gnss/fix`，只用于三维/大地图参考，
不作为短目标运动授权，也不在前端顶栏单列。
整狗部署脚本会在 edge scan 基础验收后打印该接口的 ready/reason/blockers；需要把它作为
强制部署门禁时设置 `M20PRO_DEPLOY_REQUIRE_DDDMR_FIELD_TEST=1`。
当前 `move + field_proxy` 现场轨道会在缺少正式 DDDMR `mapcloud/mapground` 资产时启用
`M20PRO_DDDMR_FIELD_TEST_FLAT_MAP` 临时平面 fallback，让第一轮 3m 内低速短测能验证任务、
action 和速度链；前端会标成“临时平面”，它不代表正式三维建图、大地图或跨楼层能力已完成。
同一限制已经做进后端任务接口：`GET /api/tasks` 会返回 `field_test_task_gate`，
`POST /api/tasks` 和 `POST /api/tasks/start` 在 `dddmr_3d + field_proxy` DDDMR 模式下会硬性要求
验收通过、地图/定位前置条件满足、当前位姿新鲜、任务为单点且首点距离不超过 runtime 的 `max_goal_distance_m`。
这保证甲方前端或脚本不能绕过 8080 界面直接启动超距/多点 field_proxy 任务。
8080 也提供“生成 DDDMR 近点任务”准备入口；后端接口是 `GET/POST /api/dddmr/field_test_task`。
`GET` 只根据当前已确认位姿预览前方短目标，`POST` 只创建一个点位和一个 `ready` 单点任务，
不会启动任务、不会切模式、不会重定位、不会发布速度。创建仍复用同一个
`field_test_task_gate`、地图和定位合同；不满足门禁时直接返回 `ok=false` 且不落库。
v3 不把 Nav2 local costmap / odom 对齐作为任务启动条件；安全证据由
`field_test.acceptance`、TF、edge-cloud、
mapcloud/mapground、`command_mux` 和 `field_test_task_gate` 承担。

8080 的 DDDMR 3D 建图入口在 v4 `move`/autostart 下默认接到 Lightning-LM：后端在
104 本机调用 `scripts/104_dddmr_mapping_control.sh`，在 104 原生 Foxy ARM workspace
启动 `m20pro_bringup/m20pro_lightning_mapping.launch.py`。104 默认不跨主机订阅原始
`/LIDAR/POINTS`；launch 会把已验证的 `/dddmr/edge_cloud` 转成 Lightning 需要的
RoboSense 兼容点云 `/m20pro/lightning_points`，再与 `/IMU` 一起送入 Lightning-LM。
保存时调用 `/lightning/save_map` 和
`/lightning/save_path`，再由 `lightning_pcd_asset_adapter` 从 `global.pcd` 生成
前端资产 `map.pcd/ground.pcd/poses.pcd` 并归档到 `/root/lightning_maps`。
如果 Lightning 没有输出非空 `global.pcd`，会返回 `lightning_global_map_missing`；
如果资产适配失败则返回 `lightning_asset_adaptation_failed`，不会把空
`archive_target` 伪装成可登记资产。
Web 后端会对建图命令模板中的楼层名和路径占位值做 shell quoting，避免现场输入破坏命令。
只读预览默认不配置该命令，避免非 DDDMR 状态下触发 3D 建图运动。

## 现场参数统一配置

现场允许调整的点云、三维导航、跨层路线元数据、遥控和定位稳定性参数只有一个源文件：

```text
src/m20pro_bringup/config/m20pro_field_profile.yaml
```

修改后必须先检查再整体应用：

```bash
./scripts/apply_field_profile.sh --check
./scripts/apply_field_profile.sh
```

应用入口会拒绝任务执行期间换参，先校验字段、范围和参数耦合，再按完整部署流程同时更新 106 和 104。106 的 `/etc/m20pro-edge-scan-106.env` 是自动生成物，不可手工编辑。配置 SHA-256 仅用于部署诊断，不作为节点启动或任务运行的门禁；系统不提供旧参数热切换。

当前 schema v5 共开放 73 个现场参数，其中 `navigation` 30 个、`teleoperation` 7 个；导航按 `controller / goal / progress / local_planner / costmap / global_planner` 分组，遥控统一配置速度上限、指令租约和仲裁看门狗。`localization` 还统一配置原厂手柄运动证据和起立/趴下姿态过渡判定。`stair_transition` 统一配置楼梯速度、指令频率、步态等待、阶段超时和共享平台定位参数；106 原厂地图激活超时也由此直接传给 Web 切图事务。旧楼梯感知、扫描选择器和 `floor_manager.use_stairs()` 运动入口保持停用；跨层任务只由统一任务中的单一 `stair_executor` 执行。

导航减速度在统一配置中填写正数幅值，运行时自动转换成 DWB 要求的负值；同一最大线速度同时驱动 `max_vel_x/max_speed_xy`，同一障碍、清障和膨胀参数同时驱动局部与全局代价地图。校验器会拒绝停止阈值大于最大速度、发布频率高于刷新频率、清障范围小于障碍范围以及定位阈值相互冲突等组合。

在上位机拉回 104 录包：

```bash
./scripts/local_pull_bags.sh
```

现场真机测试只走全量 real 启动：`104_start_real_shadow.sh` 或 `104_start_real_move.sh`。全量 real 会拉起 tcp_bridge、DDDMR 三维桥接、地图资产服务和网页前端；`/scan` 只保留给观察、录包和兼容诊断。

任务前必须在网页自检、`/api/state` 或 `104_check_edge_scan.sh` 中确认 edge-cloud 新鲜、frame 为 `m20pro_base_link` 且保留有限三维点。感知不通时网页仍可用，但 DDDMR 任务门禁会禁止运动。

104 正式主栈固定使用 `project_udp` profile，接收 106 发布的轻量 `/scan` 和保留 z 的
`/m20pro/edge_cloud`，不订阅跨主机原始 `/LIDAR/POINTS`。开机脚本只会用 `fuser`
保护性清理没有进程占用的陈旧 `fastrtps_*` SHM 文件。

选择 `dddmr_3d` 时，106 edge scan 还会发布同一处理进程生成的 `/m20pro/edge_cloud`（保留真实 `x/y/z`）；104 只通过 `dddmr_edge_cloud_adapter` 规范化为 `/dddmr/edge_cloud`。这条三维输入链与 `/scan` 并行，不能用 `/scan` 反解替代，也不会让 DDDMR 直接订阅原始 `/LIDAR/POINTS`。

`104_start_real_move.sh` 会放开运动控制，只能在现场有人看护、手柄急停可用时执行。
启动后打开网页，等待状态栏“自检”从“启动中”更新为自动自检结果。服务启动 12 秒后会
执行首次基础自检，之后每 300 秒自动刷新，用于确认全量系统、网页、106 edge-cloud 和
原厂状态链路；定位、三维资产、DDDMR 动作服务和速度门禁必须在测试场地继续确认。
`104_start_web.sh` 只用于开发预览网页界面，不能作为现场任务流程。

## 开机自启动

104 可以安装 `m20pro-real.service`，开机后自动启动全量 real 系统和网页前端，但不会自动执行任务。手柄或笔记本连上机器狗网络后访问 `http://10.21.31.104:8080`，先确认状态栏的自动自检结果；到测试场地后从“定位”进入重定位，导航项恢复正常后再标点和开始任务。

安装自启动：

```bash
ssh user@10.21.31.104
source /opt/robot/scripts/setup_ros2.sh
su
cd /home/user/m20pro_real_ros2_ws
./scripts/104_enable_autostart.sh move
systemctl start m20pro-real.service
./scripts/104_autostart_status.sh
```

停用自启动：

```bash
su
cd /home/user/m20pro_real_ros2_ws
./scripts/104_disable_autostart.sh
```

自启动服务只启动本工程，不修改原厂 multicast/FastDDS 服务。`move` 模式会把运动控制链路准备好，但任务仍必须在网页中人工点击开始。

自启动只消费 `/scan`。点云未就绪时，网页仍应起来并在顶部“点云/自检”状态和任务流程中显示感知链路故障；恢复时先用 `./scripts/104_check_edge_scan.sh` 确认样本。默认环境变量应保持：

```text
M20PRO_FASTDDS_PROFILE=project_udp
M20PRO_CLEAN_STALE_FASTDDS_SHM=1
M20PRO_SCAN_TOPIC=/scan
```

YOLO 模型在 x86_64 上位机由 `best.pt` 导出 ONNX，再用 RKNN Toolkit2 编译为 RK3588 FP16 模型。104 只安装 RKNNLite 和 `librknnrt`，不安装或运行 Torch。正式配置为：

```text
M20PRO_ENABLE_INSPECTION=true
M20PRO_INSPECTION_BACKEND=rknn
M20PRO_INSPECTION_MODEL_PATH=/home/user/m20pro_real_ros2_ws/install/m20pro_inspection/share/m20pro_inspection/models/best_rk3588_fp16.rknn
M20PRO_INSPECTION_CLASS_NAMES_PATH=/home/user/m20pro_real_ros2_ws/install/m20pro_inspection/share/m20pro_inspection/models/labels_zh.txt
```

转换环境固定为 Ultralytics 8.3.40、CPU Torch 2.4.1、ONNX 1.16.1 和 RKNN Toolkit2 2.3.2，执行 `scripts/convert_yolo_to_rknn.py` 可重复生成模型。104 的 YOLO 进程默认休眠，前端先打开前摄像头，再启用 YOLO；进程启动 RTSP 最新帧线程和 NPU 推理，线程持续排空 30fps 源流且只保留最新帧，NPU 启用后按 3Hz 消费，避免推理积压旧画面。原始 H.264 视频保持 30fps 硬件解码；检测页把检测框用 Canvas 叠加在同一个 H.264 视频上，并以轻量检测接口刷新 JSON，不再传输第二路 ROS Image/MJPEG。当前类别为：未戴安全帽、未穿安全背心、跌倒、火灾、现场杂乱、配电箱打开。

104 重装运行时使用 `scripts/104_install_rknn_runtime.sh`。脚本默认从 `/tmp` 读取 RKNNLite 2.3.2 arm64 wheel、`librknnrt.so` 和模型，安装后会执行一次 NPU 初始化检查。

## 现场复盘

现场任务问题统一用 rosbag 复盘，不再依赖前端 watcher、ready-check 或失败快照脚本。

104 上录包：

```bash
./scripts/104_record_bag.sh 180 field_task
```

上位机拉回录包：

```bash
./scripts/local_pull_bags.sh
```

网页顶部“录包”状态栏也可以直接管理 104 上的历史录包：打开后可刷新列表、查看大小/时长/消息数、改名、删除或下载。下载得到的 `tar.gz` 解压后仍是标准 rosbag 目录；正在写入的当前录包不能改名或删除。

`m20pro_real_full.sh move` 会在 `/tmp` 生成运行时参数文件，把 `m20pro_tcp_bridge.enable_axis_command` 明确覆盖为 `true`；在没有额外覆盖时，它默认进入 DDDMR 模式。`shadow` 会覆盖为 `false` 并保持只读观察。这样不会改动原始 `m20pro_real.yaml`，也能避免 Foxy 中节点专属参数压过 launch 参数的问题。

## 启动方式

真机测试推荐用脚本启动。开一个 104 终端，按固定环境顺序进入后执行：

```bash
./scripts/104_start_real_shadow.sh
```

只读模式用于看定位、地图、点云、路径和网页任务逻辑，不放开运动控制。

确认现场安全、手柄急停可用后，运动模式执行：

```bash
./scripts/104_start_real_move.sh
```

终端自检脚本作为备用排查工具。网页自检异常、或现场需要保存终端输出时再另开 104 终端执行：

```bash
ssh user@10.21.31.104
source /opt/robot/scripts/setup_ros2.sh
su
cd /home/user/m20pro_real_ros2_ws
source install/setup.bash
./scripts/104_preflight_check.sh move
```

正常作业时，浏览器访问 `http://10.21.31.104:8080`，等待状态栏显示自动基础自检结果。基础自检失败时先处理基础链路；如果基础自检通过但提示“导航待重定位后确认”，从“定位”进入重定位，再看定位、`/scan`、代价地图和导航状态是否恢复正常。

开发预览网页：

```bash
ros2 launch m20pro_bringup m20pro_web_dashboard.launch.py port:=8080
```

这只适合改前端样式或检查页面是否能打开。真机重定位、标点、下发任务必须在全量 real 启动后操作。

浏览器访问：

```text
http://10.21.31.104:8080
```

`127.0.0.1:8080` 只表示“当前这台机器自己访问自己”。前端跑在 104 上时，笔记本或手柄访问必须用 `10.21.31.104:8080`。

## 网页操作流程

真机测试时，网页前端是全量 real 系统的一部分，跑在 104 上。笔记本、手柄或调试电脑连接机器狗 WiFi/机器狗内网后访问 `http://10.21.31.104:8080`。

基本流程：

1. `建图`：填写项目、区域、地图名称和现场楼层；点击“开始建图”时，后端先查询 DDDMR 运行包和建图状态，再建立当前楼层会话。
2. `建图`：结束采集后点击“结束建图”。前端通过 `/api/mapping/*` 维护会话，后端执行 DDDMR start/finish 命令；成功结果归档到 104，不触发 106 地图拉取。
3. 验收建图产物后，通过 `POST /api/dddmr/map_assets` 登记真实 `mapcloud/mapground` PCD；保存目录本身只作为 `pose_graph_dir` 来源，不会伪装成可发布的 PCD 资产。
4. 顶部 `地图`：查看当前地图，或在展开浮层中切换要查看和标点的楼层地图。
5. 左侧空间视图：查看 `mapcloud/mapground` 的三维点云俯视投影、机器人位姿、任务点和路径；v3 前端不提供二维栅格修饰工具。
6. 顶部 `定位`：如果机器人位置不准，打开浮层后在地图上拖箭头并执行网页重定位；重定位成功后 DDDMR 门禁会自动刷新。
7. `标点`：在地图上按住并拖出箭头，保存任务点、过渡点、充电点及楼梯语义点。
8. `任务`：按当前楼层地图编排任务并执行；必要时从任务状态面板停止当前任务。

当前网页一次显示一张楼层的三维空间地图。跨楼层计划与 `stair_executor` 合同仍保留，但 v3 当前轮次必须先完成单层纯三维启动、建图、定位、TF、edge-cloud 和地图发布实测；在这些基础链路通过前，不把跨层流程标记为现场验收完成。完整设计边界见 [docs/cross_floor_navigation.md](docs/cross_floor_navigation.md)。

地图可在地图浮层删除；当前地图、任务执行期间和跨楼层路线引用的地图受保护。删除普通地图会同步清理 104 上的点位、任务和建图会话引用，不会删除独立保存的雷达历史结果，也不会自动删除 106 原厂地图包。需要清理 106 时必须先确认 `active` 不指向目标包，再精确删除对应原厂目录。

仓库不再内置固定楼层模板，前端地图库只展示 104 已归档的真实业务地图。新建图任务必须填写现场实际楼层；登记新楼层只建立项目元数据，不是普通地图库白名单，也不会自动生成楼梯/电梯路线。普通地图按自身 `floor` 身份选择、标点和重定位；跨楼层路线必须使用实测坐标单独配置。

多楼层建图时，“现场楼层”表示本次项目要建立的全部楼层集合，不是机器狗实时所在楼层。系统按输入顺序把第一层设为初始建图步骤；完成并归档当前层后，再从真实步骤列表切换下一层。

完整现场流程、四点含义、上下行配置和失败边界见 [docs/cross_floor_navigation.md](docs/cross_floor_navigation.md)。

当前 v4 前端以三维空间视图、建图会话和统一任务操作为主；状态来自 edge-cloud、mapcloud/mapground、定位和 field_proxy，详见 [docs/dddmr_navigation_v1.md](docs/dddmr_navigation_v1.md)。前/后摄像头画面仍保留为按需打开的现场辅助视图。

## 视频画面

网页上的前/后摄像头来自 103 的 RTSP：

```text
rtsp://10.21.31.103:8554/video1
rtsp://10.21.31.103:8554/video2
```

103 的 USB 摄像头在 1280x720 MJPEG 下按硬件支持的 30 fps 采集，并输出 30 fps H.264 Constrained Baseline（GOP 15）。104 的独立 MediaMTX 网关按需拉取 RTSP，只做封装转换，不解码、不缩放、不转 JPEG；网页优先通过 WebRTC/WHEP 播放 H.264，协商失败时回退到收紧缓存的低延迟 HLS。生产链路为：

```text
103 camera -> Rockchip H.264 -> RTSP -> 104 MediaMTX remux -> WebRTC/WHEP -> browser
                                              \-> LL-HLS fallback -> browser
```

在 103 上使用 `scripts/103_set_camera_fps.sh` 固化采集和输出帧率。修改前会保留原配置备份，且不会自动重启推流：

```bash
sudo bash scripts/103_set_camera_fps.sh 30
```

前端只在点击“打开”后创建 WebRTC/WHEP 接收器，关闭或切换相机时销毁 PeerConnection 和 WHEP 会话，使 104 网关停止无消费者的上游拉流；浏览器不再经过 HLS 分片缓存。若 WebRTC 的 ICE/网络条件不满足，Hls.js 回退播放器使用绝对秒数追直播，延迟超过 2 秒会直接跳到直播点。`web_dashboard` 的 `enable_camera_proxy` 必须保持为 `false`，生产进程中不应存在摄像头 FFmpeg/MJPEG 转码。

如果现场仍加载旧页面，先强制刷新网页，推荐 `Ctrl+F5`，确认浏览器加载的是当前版本脚本：

```text
/static/dashboard.js?v=20260817-camera-webrtc-low-latency
```

如果强刷新后仍然有明显长延时，优先检查 103 源码流、编码 GOP、104 网关和网络链路：

```bash
systemctl status m20pro-camera-webrtc-104.service
curl http://127.0.0.1:8888/video1/index.m3u8
curl http://127.0.0.1:8889/video1/
pgrep -af '[f]fmpeg .*rtsp://10.21.31.103' || true
```

YOLO 独立消费同一条 H.264 RTSP，在推理进程内只解码一次；网页只接收检测 JSON 并在同一条原始视频上绘制边框，禁止从网页帧或 MJPEG 代理取图。104 网关当前为 MediaMTX v1.20.0，WebRTC 信令使用 `8889/TCP`，ICE 媒体使用 `8189/UDP+TCP`；如果通过内网穿透提供给客户，必须同时转发 8889 和 8189，并把可公网访问的 IP/域名加入 `webrtcAdditionalHosts`，或在网关配置可达的 TURN 服务，否则前端会自动回退 HLS。

网页重定位以“定位”面板的最终结论为准：`/initialpose` 只是网页侧触发动作，开发手册 TCP `2101/1` 回执也只是必要证据之一，不能单独算成功。现场必须看到“重定位成功”，任务区才允许开始任务。执行任务时不能重定位；需要先停止当前任务，再打开“定位”，在地图上拖箭头并点击 `执行重定位`。

如果网页箭头方向看起来不对，不要直接改 180 度偏置。先检查：

1. 顶部状态栏里的 `定位` 是否正常。
2. `/m20pro_tcp_bridge/map_pose` 的 yaw 是否和实际朝向一致。
3. `/ODOM` 是否有 `inf/nan` 或明显漂移。
4. 当前加载地图是否就是机器狗所在环境。

只有定位源头正确、地图正确、仅网页绘制方向不一致时，才调整前端显示逻辑。默认 `robot_pose_display_yaw_offset_rad=0.0`，不做猜测性旋转。

## 巡检点字段

巡检点不是单纯的 x/y 坐标。每个点位应明确：

| 字段 | 含义 |
| --- | --- |
| `label` | 点位名称，给现场人员和巡检报告使用 |
| `area` / `room` | 区域、房间或构件部位 |
| `result_file_prefix` | 昂锐雷达、YOLO 等检测结果落盘时使用的文件名前缀 |
| `pose.x/y/z/yaw` | 地图坐标和到点朝向，yaw 单位 rad |
| `manual_point_type` | 手册点位类型：`transition`、`task`、`charge` |
| `dwell_s` | 到点后停留秒数 |
| `vendor_navigation` | 原厂单点导航任务字段 |

网页标点以地图箭头为唯一坐标源：按下位置作为点位，向机器狗到点后应面对的方向拖动，松开后自动形成 `x/y/yaw`；也可以直接采用当前机器人实时位姿。页面只显示取点结果，不再提供容易与地图草稿不一致的手工坐标输入。

按《山猫 M20 系列软件开发手册》：

```text
PointInfo=0  过渡点
PointInfo=1  任务点
PointInfo=3  充电点
Gait=12      平地敏捷步态
Gait=14      爬楼梯步态
Speed=1      低速
Manner=0     前进行走
ObsMode=0    开启停避障
NavMode=1    自主导航
```

默认策略：

- 任务点：`PointInfo=1`，默认停留 `5s`；
- 过渡点：`PointInfo=0`，默认停留 `0s`；
- 充电点：`PointInfo=3`，必须放在任务最后。
- 爬楼梯点和出楼梯点作为有向跨层路线的入口与出口；步态与速度由唯一 `stair_executor` 按路线方向统一下发，不由点位名称触发旧链路。
- 所有点位固定 `Manner=0`、`ObsMode=0`、`NavMode=1`；前端和外部 API 都不能关闭避障或切回直线导航，只保留步态和速度为可配置字段。

任务执行时会发布：

```text
/m20pro/floor_goal
/m20pro/active_waypoint
/m20pro/stop_task
```

`/m20pro/active_waypoint` 是轻量 JSON，包含当前任务阶段、目标位姿、剩余停留时间和 `waypoint` 点位语义。昂锐雷达检测节点应优先使用这里的 `waypoint.result_file_prefix`、`waypoint.room`、`waypoint.scan_point` 和 `waypoint.radar.scans` 命名并区分扫描结果。

## 网页人工接管

状态栏“遥控”用于自主任务无法继续时的低速脱困。点击“人工接管”会先终止当前任务，再将速度仲裁器从自主导航切到遥控；结束接管后保持运动锁定，旧任务不会自动恢复，只有重新开始任务才会再次放行三维导航。

遥控指令只在 `move` 模式且速度仲裁器就绪时生效。按键松开立即发零速度；浏览器失焦、页面隐藏、网络中断或心跳超过 `teleoperation.command_timeout_s` 时自动停车并锁定导航。楼梯三维感知会话活跃时禁止网页遥控，台阶上脱困必须使用原厂手柄并由现场人员看护。

DDDMR、遥控和最终执行速度分别使用 `/cmd_vel_nav`、`/cmd_vel_teleop` 和 `/cmd_vel`；只有 `m20pro_command_mux` 可以向最终 `/cmd_vel` 输出。未部署 VPN、身份认证和访问控制前，不得将这组运动 API 直接暴露到公网。

遥控弹层用一个姿态按钮在“起立/趴下”之间切换。`m20pro_tcp_bridge` 按开发手册发送心跳并接收原厂 2Hz `Type=1002/Command=6` 主动基础状态，从 `BasicStatus.MotionState` 生成唯一项目姿态话题；趴下/阻尼/空闲状态显示“起立”，站立/标准运动/敏捷运动状态显示“趴下”，状态缺失或超过 3 秒时显示“姿态未知”并禁止误下发。起立/趴下会先结束网页接管、锁定速度，再通过原厂 `Type=2/Command=22` 下发 `MotionParam=1/4`；软急停下发 `MotionParam=2`，同时停止任务并保持锁定。中央方块按钮仅发送零速并保持接管，与改变本体状态的软急停语义不同。原厂手柄不经过本项目仲裁器，不能与网页遥控同时操作。

状态栏电量可展开查看电压、电流、温度、电池 MOS/保护状态和电流方向判断；103 原厂当前未提供可用的独立充电状态查询接口，因此不伪造“充电中”状态。“一键充电”先由三维导航到当前地图唯一充电点，再由 104 通过 TCP 桥向 103 下发原厂 `Type=1003/Command=1`、强制 `PointInfo=3` 的充电导航命令；只有收到原厂明确回执后任务才结束。没有充电点或存在多个充电点时，系统拒绝执行，不猜测充电桩位置。充电请求和回执分别记录在 `/m20pro/charge_command`、`/m20pro_tcp_bridge/charge_result`。

雷达扫描计划示例：

```json
{
  "waypoint": {
    "building": "3栋",
    "unit": "1单元",
    "house": "2008户",
    "floor": "F20",
    "room": "客厅",
    "scan_point": "P01",
    "result_file_prefix": "3栋_1单元_2008户_F20_客厅_P01",
    "radar": {
      "enabled": true,
      "scans": [
        {"mode": "measuring", "label": "实测实量", "result_suffix": "measure"},
        {"mode": "modeling", "label": "点云建模", "result_suffix": "cloud", "artifact_policy": "manual_import", "manual_measure_required": true}
      ]
    }
  }
}
```

## U360 雷达巡检

雷达巡检包默认不启动；需要接入 U360RSE/UCL360 时，在全量 real 启动前设置环境变量：

```bash
export M20PRO_ENABLE_RADAR_INSPECTION=true
export M20PRO_RADAR_BACKEND=u360_http
export M20PRO_RADAR_SCAN_MODE=measuring      # 或 modeling
export M20PRO_RADAR_DEVICE_URL=http://192.168.107.72:8080
export M20PRO_RADAR_OUTPUT_DIR=/home/user/m20pro_radar_results
./scripts/104_start_real_move.sh
```

节点订阅 `/m20pro/active_waypoint`，任务点进入 `dwelling` 阶段后触发扫描，并发布：

```text
/m20pro/radar_inspection/status
/m20pro/radar_inspection/result
/m20pro/radar_inspection/events
```

网页标点时可以为每个任务点选择“不触发雷达 / 仅实测实量 / 仅点云建模 / 实测实量 + 点云建模”。测量模式下默认在 U360 进入 `analyzing` 后允许机器人去下一个点，最终结果继续后台收集；点云建模模式如果设备不能直接返回点云文件，会把该次扫描标记为 `pending_import`，由人工从雷达导出点云工程后在任务卡片点击“登记点云”填入路径。

网页“检测”页会显示最近一次雷达扫描和结构化测量结果；任务列表按任务点展示对应雷达结果、点云登记状态和人工回填状态。任务卡片提供 `雷达JSON` / `雷达CSV` 导出，也可以直接访问：

```bash
curl -o radar_task.json "http://127.0.0.1:8080/api/radar/task_export?task_id=<task_id>&format=json"
curl -o radar_task.csv  "http://127.0.0.1:8080/api/radar/task_export?task_id=<task_id>&format=csv"
```

人工登记接口：

```bash
curl -X POST http://127.0.0.1:8080/api/radar/artifact \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"<task_id>","run_id":"<run_id>","artifact_path":"/path/to/u360/project"}'

curl -X POST http://127.0.0.1:8080/api/radar/manual_measurement \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"<task_id>","run_id":"<run_id>","measurements":[{"name":"开关高度","value":"1.32m"}]}'
```

## 真机测试顺序

当前实测顺序：

1. 本工程 real 只读测试：全量启动，不放开运动控制，确认点云、定位、地图、路径、网页状态。
2. 同楼层真导航：使用 `104_start_real_move.sh` 全量启动，基础自检通过后在测试场地重定位；导航项正常后再做短距离、长距离和避障连续测试。
3. 最小跨层验收：先只配置两层、一条上行路线和每层一个近距离任务点；用 `104_start_real_move.sh` 启动，确认入口、上楼、平台切图重定位、出口和目标点的完整顺序。上行单程通过后再配置反向路线测试下楼，下楼使用后退。

同楼层真导航必须录包。出现原地转圈、明显偏航、贴障碍物、路径穿墙、地图和当前位置明显不匹配时，立即点击网页停止任务或使用手柄急停。

## 关键文件

```text
src/m20pro_bringup/config/m20pro_real.yaml            # 104 真机基础参数
src/m20pro_bringup/config/nav2_params_real.yaml       # main/v2 历史兼容参数，v3 不启用
src/m20pro_bringup/config/map_manifest.yaml           # 项目内置地图清单（正式默认为空）
src/m20pro_bringup/config/runtime_navigation.yaml     # 默认无路线运行时配置
docs/cross_floor_navigation.md                        # 正式跨楼层建图、配置和测试流程
docs/dddmr_navigation_v1.md                          # DDDMR 第一版边界、部署和限制
src/dddmr_sys_core/                                  # DDDMR 公共 action/srv 和枚举 core 兼容包
src/m20pro_bringup/maps/                              # 启动底图和开发资产；业务地图保存在 104 归档
src/m20pro_cloud_bridge/m20pro_cloud_bridge/web_dashboard_node.py
src/m20pro_cloud_bridge/m20pro_cloud_bridge/static/   # 前端 HTML/CSS/JS
src/m20pro_radar_inspection/                          # U360 雷达巡检节点
src/m20pro_cloud_bridge/m20pro_cloud_bridge/*_contract.py
src/m20pro_navigation/m20pro_navigation/floor_manager.py
src/m20pro_navigation/m20pro_navigation/dddmr_nav2_bridge_node.py  # DDDMR action adapter implementation
src/m20pro_navigation/m20pro_navigation/tcp_bridge_node.py
docs/single_floor_navigation_architecture.md          # 单层导航架构和拆分边界
```

拆分后的代码按功能看更容易：

- 前端界面和视频显示：`static/dashboard.html`、`static/dashboard.css`、`static/dashboard.js`。
- HTTP/ROS 集成和现场副作用：`web_dashboard_node.py`。
- 地图读取、选图、派生地图和启动同步：`map_*_contract.py`、`startup_map_sync_contract.py`。
- 重定位结论和导航 readiness：`localization_contract.py`、`navigation_readiness_contract.py`。
- 任务创建、启动、当前点推进和任务/雷达接口：`task_*_contract.py`、`active_task_contract.py`、`active_waypoint_contract.py`。
- 三维桥接状态、路径终点匹配和运行进展判断：`nav_status_contract.py`、`task_plan_contract.py`、`task_progress_contract.py`。
- 感知、自检、运行时守护和 ROS 消息转换：`perception_contract.py`、`preflight_contract.py`、`web_runtime_contract.py`、`ros_message_contract.py`。

如果要继续分工开发，优先按这些功能边界改对应 contract 和测试；`web_dashboard_node.py` 主要保留实际 ROS 发布、订阅、HTTP 接口和落盘。

## Package

| Package | 作用 |
| --- | --- |
| `m20pro_bringup` | launch、参数、地图、RViz、脚本 |
| `m20pro_navigation` | TCP 桥、楼层管理、目标桥、健康检查 |
| `m20pro_cloud_bridge` | 网页操作台 |
| `m20pro_inspection` | YOLOv8/RKNN 巡检检测 |
| `m20pro_radar_inspection` | U360 雷达任务点扫描与结果导出 |

说明：real-only 仓库已移除 `m20pro_description` 和 sim 启动链路。真机运行使用 `m20pro_base_link` 主链路，不再依赖 URDF/mesh、`robot_state_publisher` 或零关节发布器；仿真模型资源留在 sim 仓库维护。

## 常用检查命令

edge scan：

```bash
./scripts/104_check_edge_scan.sh
```

DDDMR 三维链路：

```bash
ros2 topic echo /m20pro/navigation_backend/status --once
ros2 topic echo /m20pro/dddmr/edge_cloud/status --once
ros2 topic echo /m20pro/dddmr/map/status --once
ros2 topic info /mapcloud
ros2 topic info /mapground
```

位姿和 TF：

```bash
ros2 topic echo /m20pro_tcp_bridge/map_pose
ros2 run tf2_ros tf2_echo map m20pro_base_link
```

网页接口：

```bash
curl http://localhost:8080/healthz
curl http://localhost:8080/api/state
curl http://localhost:8080/api/tasks
```

## 地图来源

DDDMR 楼层资产清单：

```text
/home/user/.m20pro_web/dddmr_map_assets.yaml
```

104 建图结果默认归档到：

```text
/root/dddmr_bags
```

网页建图使用 `scripts/104_dddmr_mapping_control.sh` 启动、查询、保存和取消 DDDMR 建图。
finish 成功只证明建图目录已经归档；验收后的 `mapcloud/mapground` PCD 必须显式登记到
资产清单，资产服务器按楼层热加载并发布 `/mapcloud`、`/mapground`。v3 前端不会调用
历史 `/api/mapping/import_active_map`，也不会把 YAML/PGM 占据栅格当作三维资产。

## 注意事项

- 不要把原厂导航任务和本工程 DDDMR 轴指令同时用于控制机器狗。
- 真机第一次测试先用 `enable_axis_command:=false`。
- `scripts/` 是现场人工脚本入口。
- `src/m20pro_bringup/scripts/` 是 ROS package 内部脚本。
- README 只保留上手和使用说明；过程记录统一写入仓库根目录 `m20pro日志.md`。
