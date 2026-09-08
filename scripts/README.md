# M20Pro现场常用脚本

这些脚本是给现场人员直接执行的快捷入口，避免每次测试都手敲长命令。

约定：
- 仓库根目录 `scripts/` 是人工入口。
- `src/m20pro_bringup/scripts/` 是 ROS 包内部脚本，不作为现场人员主要入口。
- 现场文档 `/home/fabu/桌面/脚本.docx` 中默认引用的就是本目录脚本。
- 104 的 2D/3D 双工作区创建与切换见 `docs/104_dual_workspace.md`；使用
  `104_switch_workspace.sh {2d|3d|status}`，最后一次选择会随开机恢复。

在104上使用时，先按固定顺序进入环境；`104_diagnose_preflight.sh` 和
`104_preflight_check.sh` 也可以在上位机仓库根目录直接执行，脚本会优先
SSH 到 `user@10.21.31.104` 并在 104 上检查：

```bash
ssh user@10.21.31.104
source /opt/robot/scripts/setup_ros2.sh
su
cd /home/user/m20pro_real_ros2_ws_v4
./scripts/104_switch_workspace.sh status
```

现场主入口：

```bash
./scripts/104_start_real_shadow.sh
./scripts/104_start_real_move.sh
./scripts/104_preflight_check.sh move
./scripts/104_stop_real.sh
./scripts/104_record_bag.sh 180 m20_test
./scripts/104_enable_autostart.sh move
./scripts/104_autostart_status.sh
./scripts/104_disable_autostart.sh
```

诊断和开发入口：

```bash
./scripts/104_diagnose_preflight.sh
./scripts/104_check_edge_scan.sh
./scripts/104_goal_mode_battery_gate.py
./scripts/104_status.sh
./scripts/104_accept_dddmr_field_test.sh
./scripts/104_start_web.sh
./scripts/104_start_dddmr_preview.sh 18080
./scripts/104_start_dddmr_preview_daemon.sh 18080
./scripts/104_status_dddmr_preview.sh 18080
./scripts/104_stop_dddmr_preview.sh 18080
./scripts/104_stop_web.sh
```

在上位机拉回104录包：

```bash
./scripts/local_pull_bags.sh
```

第二台测试机代码同步：

```bash
# 先在上位机 git pull；该入口会部署 106 edge scan，再事务更新 104
./scripts/local_deploy_to_test_robot.sh

# 未来当 104 能直接访问公司 GitLab 后，在 104 上执行
./scripts/104_update_from_gitlab.sh

# 如果公司 GitLab 不通，但测试机能访问 Gitee 部署镜像
./scripts/104_update_from_mirror.sh
```

现场参数只修改 `src/m20pro_bringup/config/m20pro_field_profile.yaml`：

```bash
./scripts/apply_field_profile.sh --check  # 只校验，不接触机器狗
./scripts/apply_field_profile.sh          # 空闲时原子更新 106 和 104
```

schema v5 共 73 个现场参数，其中 `navigation` 30 个、`teleoperation` 7 个，覆盖速度/加速度、纯旋转最低有效速度、到点、卡住判定、DWB 采样、局部/全局代价地图、全局规划、遥控限速、失联停车、跨层执行与定位稳定性。旧楼梯感知参数和无消费者的入口距离参数已删除。不要直接编辑 106 的 `/etc/m20pro-edge-scan-106.env`、Nav2 参数占位符或定位参数占位符；整狗部署会从唯一现场参数文件按固定顺序同步 106 和 104，任务运行中不支持热更新。

说明：
- 真机只用 `104_start_real_shadow.sh` 或 `104_start_real_move.sh` 全量启动。
- 全量 real 会同时拉起 tcp_bridge、Nav2 和网页前端；感知唯一输入是 106 edge scan 发布的 `/scan`。
- 任务前通过网页自检、`/api/state` 或 `104_check_edge_scan.sh` 确认 `/scan` 新鲜、frame 正确且有效距离足够。
- 服务启动 12 秒后自动执行基础自检，之后每 300 秒刷新；结果显示在网页顶部状态栏，用于确认全量系统、网页、106 edge scan 和原厂状态链路。
- U360 雷达巡检默认关闭；需要联动任务点扫描时，启动前设置 `M20PRO_ENABLE_RADAR_INSPECTION=true`、`M20PRO_RADAR_BACKEND=u360_http` 和 `M20PRO_RADAR_DEVICE_URL=http://192.168.107.72:8080`。结果默认写到 `M20PRO_RADAR_OUTPUT_DIR`，未设置时使用 `/home/user/m20pro_radar_results`。
- 定位、`/scan`、代价地图和 Nav2 生命周期需要到测试场地重定位后再确认；网页自检会把未重定位前的 costmap/Nav2 延后启动显示为信息项，不再作为 WARN 阻塞重定位。
- `104_preflight_check.sh move` 是终端备用基础自检；网页自检异常、或现场需要保存终端输出时使用。104 正式服务和诊断终端都应使用项目 UDP-only FastDDS 配置；104 不再观察或转发原始点云。
- `104_diagnose_preflight.sh` 是只读诊断汇总：会收集网页自检、DDDMR / GNSS（/GPS、/m20pro/gnss/fix）/ edge-cloud / 三维地图摘要、点云/scan/costmap、新版 Nav2 启动门、辅助模式状态字段和最近日志，不会下发运动、步态或辅助模式命令。
- `104_diagnose_preflight.sh` 会打印 104 的默认路由、DNS、Git 状态、`/scan` 和 Nav2 状态。
- `104_accept_dddmr_field_test.sh` 是 DDDMR 的只读验收门：默认读取 `http://127.0.0.1:8080/api/dddmr/field_test`，旧服务无该接口时回退 `/api/state?debug=0`，复用 `navigation_backend_summary.py` 判断 `field_test.acceptance.ready`、活动任务和速度仲裁输出，并打印接口返回的 `next_steps`；返回 `PASS field_test_ready` 后，才进入前端任务页做 3m 内单点低速实测。它不会创建/启动/停止任务，不会发布运动、步态、重定位或切图命令。上位机直连查看 104 时也可以传入 `http://10.21.31.104:8080`。
- `104_dddmr_field_test_report.sh` 是只读 DDDMR 报告：汇总 `/api/dddmr/field_test`、`/api/tasks` 的 `field_test_task_gate`、active task、`selected_map_status`、`map_relocalization_required`、`localization_status`、当前位姿新鲜度、edge-cloud、map_3d、GNSS、command_mux 和 `nearest_annotations` 最近点距离，方便把现场问题完整反馈给开发侧；它不会创建/启动/停止任务，不会切模式、建图、重定位或发布速度。
- 8080 建图页“DDDMR 运行门禁”里的“读取 DDDMR”按钮调用同一个只读接口，现场可以不用终端也能看到 PASS/FAIL、阻塞项和下一步；它和脚本一样不下发任何运动类命令。
- `104_goal_mode_battery_gate.py` 现在只作为电量显示探针：只读查询 `http://10.21.31.104:8080/api/state` 并打印当前电量参考值；不会因为低电或读不到电量返回失败，不会调用 `/api/tasks/start`，不会发布 `/m20pro/floor_goal`，不会重定位，不会发运动命令。
- 现场任务问题统一录 rosbag 复盘，不再使用前端 watcher、ready-check、失败快照或 smoke 脚本作为正式流程。录包用 `./scripts/104_record_bag.sh 180 <label>`，上位机拉回用 `./scripts/local_pull_bags.sh`。
- 历史前端 watcher/ready-check/analyzer/smoke 脚本已删除，不再作为维护对象。

- 重定位排查以网页“定位”面板、`localization_status` 和开发手册 TCP `2101/1` 回执为准；不要再用“106 是否收到 `/initialpose`”作为成功判断。
- 当前地图、重定位和录包都从网页顶部状态栏进入，不再占用独立侧栏面板。
- `104_start_web.sh` 只用于开发预览网页界面，不会拉起 tcp_bridge/Nav2，不能作为现场任务流程。
- `127.0.0.1:8080` 只适合在运行前端的那台机器本机自测。
- `shadow` 不放开运动控制。
- `move` 会放开运动控制，现场必须有人看护，并准备手柄急停。
- 这些脚本不重启原厂 multicast 服务。
- `104_stop_web.sh` 只停止单独预览网页。
- `104_stop_real.sh` 停止本工程 real launch，不停止原厂服务。
- 录包脚本会记录 `/m20pro/active_waypoint`，里面包含当前任务阶段、目标位姿、停留时间和点位语义字段。
- `104_enable_autostart.sh move` 安装开机自启动全量 real；move 默认进入 DDDMR 轨道，服务只拉起系统和网页，不会自动执行任务。
- `104_dddmr_field_test_mode.sh enable|restart|accept|status` 是 104 上的 DDDMR 切换入口；v4 只进入 DDDMR 3D 模式，不提供 2D 回退动作。
- `104_autostart_status.sh` 查看自启动服务、8080 端口、DDDMR 结论、GNSS（/GPS、/m20pro/gnss/fix）/ edge-cloud / 三维地图摘要和最近日志。
- `104_verify_dddmr_field_test_deploy.sh` 是部署后的只读合同验收：确认 8080 前端已经包含“生成 DDDMR 近点任务”按钮，JS 调用了 `/api/dddmr/field_test_task`，后端暴露 `/api/dddmr/field_test`、`/api/dddmr/field_test_task` 和带 `field_test_task_gate` 的任务列表；它不会创建/启动任务，不会切模式、建图、重定位或发布速度。
- `test_windows_deploy_104_bundle_runtime.py` 是 Windows PowerShell 部署入口的运行时冒烟：它会执行 `windows_deploy_104_bundle.ps1 -DryRun -RestartEdge106 -RequireFieldReady`，确认脚本能正确解析 bundle、staging、runner、revision、ssh 命令和 temp 清理；它不访问 104，不会传包，也不会下发任何运动类命令。
- DDDMR 的短距离实测仍走现有任务链路：在当前地图保存 3m 内任务点，生成单点任务，再从任务列表启动；不要新增或使用绕过任务系统的直控入口。
- `GET /api/tasks`、`POST /api/tasks` 和 `POST /api/tasks/start` 在 `dddmr_3d + field_proxy` DDDMR 模式下统一使用 `field_test_task_gate`，硬性限制为 DDDMR 验收通过、`selected_map_status.ready=true`、`map_relocalization_required=null`、`localization_status.confirmed=true`、当前位姿新鲜、单点、首点距离不超过 runtime `max_goal_distance_m`；不要在外部脚本里绕开这个接口直接发目标。
- 8080 建图页提供“生成 DDDMR 近点任务”按钮；对应 `GET/POST /api/dddmr/field_test_task`。`GET` 只预览当前已确认位姿前方短目标，`POST` 只创建一个点位和一个 `ready` 单点任务，不会启动任务、切模式、重定位或发布速度；不满足 `field_test_task_gate`、地图/定位或栅格合同时不落库。
- Nav2 local costmap / odom 对齐校验只用于 Nav2-backed 任务；`dddmr_3d + field_proxy` 不经过 Nav2 controller/local costmap，启动时不能因为缺少 Nav2 local costmap 被挡住，安全门禁改由 DDDMR 验收和 `field_test_task_gate` 承担。
- `field_proxy` DDDMR PASS 还要求 `/api/dddmr/field_test` 里的 runtime `tf_ready=true`，即 104 能持续看见 `map -> m20pro_base_link` TF；若显示 `field_proxy_tf_unavailable`，先修定位/TF 链路，不要启动短目标任务。
- DDDMR PASS 还要求已经收到新鲜的 `command_mux_status` 且 `output_nonzero=false`；若显示 `field_test_command_mux_status_missing`、`field_test_command_mux_status_stale` 或 `blocked_by=command_mux`，先修速度仲裁状态链，不要启动短目标任务。
- DDDMR PASS 同时要求当前固定地图一致、2101 重定位锁已清除、定位已确认；若显示 `field_test_selected_map_not_ready`、`field_test_map_relocalization_required` 或 `field_test_localization_not_confirmed`，先处理 8080 地图/定位面板，不要启动短目标任务。
- `104_dddmr_mapping_control.sh` 在 v4 是 104 本机 Lightning-LM 3D 建图的底层控制器；start 在 104 原生 Foxy ARM workspace 启动 `m20pro_bringup/m20pro_lightning_mapping.launch.py`，finish 调用 `/lightning/save_map` 与 `/lightning/save_path`，要求由 `global.pcd` 适配出的 `map.pcd/ground.pcd/poses.pcd` 非空后才归档到 `/root/lightning_maps`。它会先 source `/opt/robot/scripts/setup_ros2.sh` 并保留原厂 `/opt/robot/fastdds.xml`，避免 104 跨主机 raw 大点云只见 topic、不进样本。
- `lightning_raw_mapping_control.sh` 是默认前端/autostart 建图入口：它把 `M20PRO_LIGHTNING_MAPPING_CONFIG` 指向 `lightning_m20pro_raw_mapping.yaml`，把 `M20PRO_LIGHTNING_SOURCE_CLOUD_TOPIC` 设为 `/m20pro/lidar_points_dense_ros`，并关闭 cloud adapter，让 Lightning-LM 使用密云全字段 relay 的原生 RoboSense 点云和 `/IMU`。旧 `/dddmr/edge_cloud -> /m20pro/lightning_points` 仍保留为显式兼容/诊断入口；直接使用跨主机原始 `/LIDAR/POINTS` 只适合明确验证 raw DDS 可达性时手动覆盖。
- `move + field_proxy` 首版可使用 `M20PRO_DDDMR_FIELD_TEST_FLAT_MAP` 临时平面 fallback，在没有正式 DDDMR `mapcloud/mapground` 资产时只为 3m 内低速短测补齐三维地图门禁；前端会显示“临时平面”，不得把它登记为正式三维地图或大地图能力。
- `104_disable_autostart.sh` 停止并移除自启动服务。
- `local_deploy_to_test_robot.sh` 是整狗部署入口：先用最小文件集在 106 编译、安装并启用 edge scan，再把上位机源码同步到 104 暂存目录；停服务切换后只在最终 `/home/user/m20pro_real_ros2_ws` 路径执行 `colcon --symlink-install`，失败自动恢复上一工作区和 systemd 配置。
- 如果当前开发环境到不了 104，但另一台电脑可以 SSH/SCP 到 104，先运行 `./scripts/local_make_104_source_bundle.sh` 生成源码包、`104_install_source_bundle.sh` 和 `windows_deploy_104_bundle.ps1`。Linux/macOS 终端可把包和 installer 传到 104 后运行 `M20PRO_BUNDLE_REVISION='<revision>' bash ./104_install_source_bundle.sh ./<bundle>.tgz /home/user/m20pro_real_ros2_ws move`；Windows PowerShell 可直接运行 `powershell -ExecutionPolicy Bypass -File ./windows_deploy_104_bundle.ps1 -Host user@10.21.31.104`，脚本会先在本机 temp 目录做 staging 再 scp，避免 WSL 共享路径兼容问题；需要刷新 106 发现时加 `-RestartEdge106`，要求 DDDMR 验收必须 ready 才返回成功时加 `-RequireFieldReady`。这些入口最终都调用同一个 `104_install_staged_workspace.sh`，不会绕过备份、构建、systemd 和失败回滚。
- 如果当前只想先把 104 的可切换版本准备好，不切服务，可以设置 `M20PRO_DEPLOY_PREPARE_ONLY=1`；它会在 104 上构建暂存 workspace 并写入修订号，但不会做 sudo cutover。
- `104_start_dddmr_preview.sh` 用于不切现网服务的 DDDMR 只读预览：默认使用 `M20PRO_WS` 指向的 workspace，在 `18080` 端口启动 DDDMR edge-cloud 适配、三维资产服务、bridge 只读状态和预览网页；`navigation_backend` 固定为 `dddmr_3d`，不会放开运动，并且默认会在缺少正式 `mapcloud/mapground` 时显示“临时平面”。
- `104_resolve_dddmr_preview_port.sh` 是预览端口的共享解析器，`104_status.sh`、`104_status_dddmr_preview.sh` 和 `104_stop_dddmr_preview.sh` 都走同一套规则，优先用显式端口/环境变量，其次用最新存活的 `preview_*.pid`，最后才回退默认端口。
- `104_start_dddmr_preview_daemon.sh`、`104_status_dddmr_preview.sh` 和 `104_stop_dddmr_preview.sh` 是同一预览的后台启停入口；PID 和日志写到 `~/.m20pro_dddmr_preview/`，停止时只清理该预览进程组，不碰 8080 正式服务。
- `local_deploy_to_test_robot.sh` 在 `M20PRO_DEPLOY_PREPARE_ONLY=1` 时会额外更新 `~/.m20pro_dddmr_preview/latest` 指向最新 stage；因此现场可以直接运行 `./scripts/104_start_dddmr_preview_daemon.sh 18080`，不用手工输入 timestamp。
- 刚用 prepare-only 生成的 stage 可以这样预览：`M20PRO_WS=/home/user/m20pro_real_ros2_ws.deploy.<时间戳> ./scripts/104_start_dddmr_preview.sh 18080`。
- `local_deploy_to_test_robot.sh` 在接触主机前校验唯一现场参数文件，按 106→104→106 的固定顺序同步和验收；106 的 env 只由该文件生成，不再保留可编辑模板。
- 104 网页订阅者起来后，部署入口会重启一次 106 edge publisher，并要求 `/api/state` 明确返回 `edge_scan`、`m20pro_base_link` 和至少 20 个有效距离才算完成。不要只同步 104，也不要把暂存目录中的 symlink install 直接改名投入运行。
- 整狗部署通过基础 edge scan 验收后，还会读取 `/api/dddmr/field_test` 并打印 `DDDMR ready/reason/blocked_by/provisional/source`；默认只提示不阻断部署，若本次部署必须作为 DDDMR 交付门禁，设置 `M20PRO_DEPLOY_REQUIRE_DDDMR_FIELD_TEST=1`，不通过时返回 16 并保留上一工作区备份。
- `local_deploy_edge_scan_to_106.sh` 是只补装 106 edge 组件的维护入口；正常整狗更新直接运行 `local_deploy_to_test_robot.sh`。
- 如果 104 上 `/home/user/m20pro_real_ros2_ws` 不是 git 工作区，`git pull` 不会工作；先用 `104_diagnose_preflight.sh` 确认 `git_repo=yes/no`，非 git 工作区继续用上位机 `local_deploy_to_test_robot.sh`，或在网络稳定后用 `104_update_from_gitlab.sh`/`104_update_from_mirror.sh` 转成 git 工作区。
- 如果 104 需要通过 103 上网，104 必须能拿到默认路由和 DNS，103 自己也必须有 Wi-Fi/上游默认路由、IPv4 转发、NAT 和 dnsmasq；只看到 104 能 ping 到 `10.21.31.103` 不等于能访问 GitHub。
- `104_update_from_gitlab.sh` 是 104 直连 GitLab 后使用的更新入口；如果当前网络访问不到 `git.fabu.ai`，先不要用它。
- `104_update_from_mirror.sh` 是机器狗无法访问公司 GitLab 时的直接更新入口，默认只拉取 Gitee 部署镜像 `git@gitee.com:gggghw/m20pro-ros2-real.git` 的已验证 `main`。
- Gitee 部署镜像是私有仓库。每台机器狗首次使用前，必须把 104 的公钥加入该仓库的只读部署公钥；脚本优先使用既有 `/home/user/.ssh/id_ed25519_m20pro_test_gitlab` 私钥，该文件不存在时由 SSH 使用 104 的标准密钥，不生成第二套密钥。
- 三个仓库职责固定：GitLab 是公司开发源，允许保留开发分支；GitHub 是个人成果仓库，只保留 `main`；Gitee 是机器狗部署镜像，也只保留经过验证的 `main`。
