# DDDMR 三维导航后端第一版

## 当前实现

正式链路在统一任务系统与 DDDMR 之间保留一个协议边界：业务层的三维目标由 `m20pro_dddmr_action_bridge` 转换为 `dddmr_sys_core/action/PToPMoveBase`，DDDMR 的反馈、结果和速度再回传到既有任务与底盘接口。该适配器不承担定位、规划或避障。

DDDMR 的感知输入按 M20Pro 现场链路重新定义，不直接搬运上游传感器节点：

```text
106 /LIDAR/POINTS（原厂 DrDDS，仅 106 读取）
  -> m20pro_edge_scan（边缘过滤/角度聚合，输出保留 xyz 的 PointCloud2）
  -> /m20pro/edge_cloud
  -> 104 dddmr_edge_cloud_adapter
  -> /dddmr/edge_cloud
  -> DDDMR 三维感知与局部规划
```

适配器只输出标准 `x/y/z` 字段，要求 `m20pro_base_link` frame，并用状态话题
`/m20pro/dddmr/edge_cloud/status` 作为运动前门禁。它不会订阅原始点云，也不会
从 `/scan` 伪造高度信息。当前仓库已经固定了 104 侧契约；106 发布端仍需在
具备 DrDDS 头文件和运行库的目标机上编译验证后，才能开启 DDDMR 现场实测。

本次核对的 DDDMR 上游提交为 `1d0367376380205a6a18c0ad7c7c16c9338c96bc`，使用：

```text
/p2p_move_base
dddmr_sys_core/action/PToPMoveBase
```

104 的 ARM/Foxy runtime 原生构建并运行官方 DDDMR 的 `mcl_feature`、`mcl_3dl`、
`perception_3d`、`global_planner` 和 `/p2p_move_base`。Lightning-LM 仅负责建图和
地图资产生成，不能替代这些导航组件。`m20pro_dddmr_p2p_field_proxy` 只保留为明确
标注的测试回退，正式服务禁止选择它。

核心运动链固定为：

```text
/m20pro/floor_goal
  -> floor_manager
  -> /navigate_to_pose_3d
  -> m20pro_dddmr_action_bridge
  -> /p2p_move_base

DDDMR cmd_vel
  -> /dddmr/cmd_vel
  -> m20pro_dddmr_action_bridge（活动目标门禁、有限值检查、限幅、看门狗）
  -> /cmd_vel_nav
  -> m20pro_command_mux
  -> /cmd_vel
  -> m20pro_tcp_bridge
```

### M20Pro 魔改边界

- 复用 M20Pro 的 106 edge_scan 作为唯一三维传感器入口，不引入 DDDMR 自己的激光驱动或原始点云订阅。
- 复用 M20Pro 的 `/GPS` / `/m20pro/gnss/fix` 作为全局锚点输入；Web 只把它压缩成 `navigation_backend.gnss` 的一行辅助说明，用于 3D / 大地图参考，不作为运动授权，也不单列为顶部主状态。
- 复用 104 的 `m20pro_tcp_bridge` 位姿、`map -> odom -> m20pro_base_link` TF 和现有地图身份事务；不启动 DDDMR 自带定位器，直到三维地图资产和定位闭环单独验收。
- 复用 `command_mux` 与现有速度限幅；DDDMR 不能绕过 `/cmd_vel_nav` 直达最终 `/cmd_vel`。
- 104 的 `/scan` 继续服务 Web/录包和历史 2D 基线；v3 不把它当作主导航入口。

DDDMR 不允许直接发布到项目最终 `/cmd_vel`。启动 DDDMR 节点时必须把它原来的 `cmd_vel` 输出改名，例如在其 launch 中加入：

```python
remappings=[("cmd_vel", "/dddmr/cmd_vel")]
```

DDDMR 感知参数也必须使用 M20Pro 的坐标和输入话题。上游示例中的
`base_link`、`lslidar_point_cloud` 和 `odom` 不能原样使用，至少要改成：

```yaml
perception_3d:
  ros__parameters:
    global_frame: "map"
    robot_base_frame: "m20pro_base_link"
    plugins: ["map", "lidar"]
    lidar:
      plugin: "perception_3d::MultiLayerSpinningLidar"
      topic: "/dddmr/edge_cloud"
      is_local_planner: false
      expected_sensor_time: 0.25

local_planner:
  ros__parameters:
    odom_topic: "/odom"
```

`mapcloud`/`mapground` 仍必须来自经过验收的 DDDMR 三维地图资产，不能把当前
二维 PGM 直接改名充数。若运行时没有这两个地图话题，bridge 即使有点云也不
应放行真机运动。

### 上游结果兼容

在上述固定提交中，`p2p_move_base.cpp` 到达目标后会调用 action 的 `succeed()`，但没有给新建的 `PToPMoveBase::Result` 写入 `status=SUCCESS(1)`。因此上游真实成功结果是：

```text
ROS action transport = STATUS_SUCCEEDED (4)
PToPMoveBase.Result.status = RUNNING (0，默认值)
```

桥接仅在 ROS action transport 已明确为 `STATUS_SUCCEEDED` 时兼容结果值 `0`，并发布独立诊断码 `dddmr_goal_succeeded_default_result`。显式结果 `1` 仍发布 `dddmr_goal_succeeded`；结果 `2` 或 transport 为 aborted/canceled 时都按失败处理。这样可以适配当前上游实现，同时不会把取消或中止携带的默认 `0` 误判成成功。

## 后端模式

| 模式 | Nav2 2D（历史兼容） | DDDMR 桥接 | DDDMR 速度 | `floor_manager` action |
| --- | --- | --- | --- | --- |
| `nav2_2d` | 启用 | 不启动 | 禁止 | `/navigate_to_pose` |
| `dddmr_3d` | 规划器/控制器关闭 | 本机或外部启动 | 仅轴运动放行后允许 | `/navigate_to_pose_3d` |

v3 默认是 `dddmr_3d`，本地桥接默认开启。`dddmr_3d` 不是运动授权；只有 `enable_axis_command=true` 且桥接节点 `motion_enabled=true` 时，目标才会被接受。

`dddmr_3d` 模式仍保留 104 的 2D map server，供现有 Web 地图显示和跨层切图事务使用；被关闭的是 Nav2 planner/controller/BT navigator 运动后端，避免两个控制器同时向 `/cmd_vel_nav` 输出。

DDDMR 后端模式会自动启动 `dddmr_map_asset_server` 并加载
`/home/user/.m20pro_web/dddmr_map_assets.yaml`。`enable_dddmr_map_assets`
仅保留为旧脚本兼容参数，不再作为 DDDMR 三维资产链的主门禁；否则直接用
`navigation_backend:=dddmr_3d` 启动时容易漏起 `mapcloud/mapground`。

## 部署方式

104 是 RK3588 ARM、运行 Foxy；v4 Lightning-LM 建图运行时必须在 104 上用 Foxy
原生编译，工作站 Humble 只用于源码和接口验证，不能复制 x86/Humble 的 `install/`
到 104。建议使用独立的 `/home/user/m20pro_dddmr_foxy_ws`，避免覆盖主工作区；
主栈和建图进程仍在同一台 104、同一 Foxy/DDS 环境内运行。

准备 104 runtime：

```bash
cd /home/user/m20pro_real_ros2_ws
./scripts/prepare_dddmr_foxy_runtime.sh /home/user/m20pro_dddmr_foxy_ws
```

脚本会检查 `aarch64` 和 `/opt/ros/foxy/setup.bash`，在目标机原生编译；当前开发机
上的 `scripts/prepare_dddmr_humble_runtime.sh` 只可用于桌面参考，不能部署到 104。

104 主栈选择三维后端，但不启动本地桥接：

```bash
export M20PRO_NAVIGATION_BACKEND=dddmr_3d
export M20PRO_ENABLE_DDDMR_BRIDGE=false
ros2 run m20pro_bringup m20pro_real_full.sh move
```

在已安装 DDDMR 运行时的 104 Foxy 环境启动桥接：

```bash
source /opt/ros/foxy/setup.bash
source /path/to/dddmr/install/setup.bash
source /path/to/m20pro_real_ros2_ws/install/setup.bash
ros2 launch m20pro_bringup m20pro_dddmr_bridge.launch.py \
  enabled:=true \
  motion_enabled:=true
```

两个进程必须处于可互通的 DDS domain，并使用一致的 action/topic 名称。若 DDDMR
与本工程运行在同一个 Foxy 现场环境，也可以使用主 launch 的
`enable_dddmr_bridge:=true`；此时不得再启动第二个同名桥接 action server。
104 Foxy 侧即使已经有 `dddmr_sys_core` 类型，也仍会在 `/p2p_move_base` 不存在时
报告 `dddmr_action_unavailable`，这是正确的运动门禁。

104-only 现场短距离试运行可以先启用内置 field proxy：

```bash
export M20PRO_NAVIGATION_BACKEND=dddmr_3d
export M20PRO_ENABLE_DDDMR_BRIDGE=true
export M20PRO_ENABLE_DDDMR_RUNTIME=true
export M20PRO_DDDMR_RUNTIME_BACKEND=field_proxy
ros2 run m20pro_bringup m20pro_real_full.sh move
```

当前分支的 `m20pro_real_full.sh move` 和 `104_enable_autostart.sh move` 已把上面这组
值作为未显式覆盖时的 DDDMR 默认值；历史 2D 基线仍可在 `main` 中保留。

默认 `field_proxy` 限制单目标距离 `3m`、线速度 `0.18m/s`、角速度 `0.45rad/s`。
它适合在有人值守、空旷地面、能随时停机的条件下验证 Web 目标、DDDMR action、
三维门禁和速度链；不适合验证障碍物绕行、楼梯、大地图或真正 DDDMR 算法。
field proxy 还必须持续看见 `map -> m20pro_base_link` TF；否则 runtime status 会给出
`tf_ready=false/tf_code=field_proxy_tf_unavailable`，`/api/dddmr/field_test` 和
`104_accept_dddmr_field_test.sh` 都必须保持 FAIL，避免第一个短目标下发后才被拒绝。

为了让第一版能在尚未产出正式 DDDMR `mapcloud/mapground` 资产前做现场最小验证，
`move + field_proxy` 会在未显式覆盖时启用 `M20PRO_DDDMR_FIELD_TEST_FLAT_MAP`：
资产服务器发现当前楼层没有可加载的三维资产时，会发布同一张带
`provisional=true/source=field_test_flat_map` 状态的临时平面到 `/mapcloud` 和
`/mapground`。它只用于验证 3m 内短目标的任务链、action 链和速度链，不代表真实
DDDMR 建图、跨楼层、大地图或避障闭环。

8080 的 DDDMR 3D 建图按钮在 v4 接到 104 本机 Lightning 默认命令：`move`
轨道会把 `dddmr_mapping_host=localhost`，start 调用
`scripts/104_dddmr_mapping_control.sh start {floor}`。该脚本在独立 Foxy ARM workspace
启动 `m20pro_bringup/m20pro_lightning_mapping.launch.py`。104 侧不直接消费跨主机原始
`/LIDAR/POINTS`；launch 先由 `lightning_cloud_adapter` 把 `/dddmr/edge_cloud` 转成
Lightning RoboSense 兼容的 `/m20pro/lightning_points`，再与 `/IMU` 一起输入
Lightning-LM。finish 调用 `/lightning/save_map` 与 `/lightning/save_path`，从 Lightning
保存目录 `data/<map_id>/global.pcd` 生成 `map.pcd/ground.pcd/poses.pcd` 后归档到
`/root/lightning_maps`；输出里的 `archive_target` 是后续 `pose_graph_dir` 或三维资产验收登记的来源。只读预览默认不配置这三条命令。
如果 `/lightning/save_map` 返回但没有非空 `global.pcd`，脚本会返回
`ok=false/code=lightning_global_map_missing`；资产适配失败时返回
`ok=false/code=lightning_asset_adaptation_failed`，并保留日志，便于现场查看 `save_log`
和 `asset_log` 后重试或手工排查；不得把空 `archive_target` 当成可登记资产。
前端传入的 `floor/label/note/mapcloud/mapground` 等模板占位值在 Web 后端进入 shell 前
统一经过 `shlex.quote`，避免楼层名或路径中的空格、分号破坏 104 本机命令。

DDDMR 的实际操作仍走现有任务链路，不新增绕过任务系统的直控按钮：

1. 在 104 上先运行 `./scripts/104_accept_dddmr_field_test.sh`。它只读取
   `/api/dddmr/field_test`，旧服务无该接口时回退 `/api/state?debug=0`，复用
   `navigation_backend.field_test.acceptance` 判断最小门禁；PASS 也意味着 field proxy
   已看见 `map -> m20pro_base_link` TF；
   看到 `PASS field_test_ready` 才进入下一步。
2. 如果需要切换系统态，不要手改 `systemd` 文件；直接用
   `./scripts/104_dddmr_field_test_mode.sh enable`
   切到 DDDMR，再重新跑验收脚本。v3 不提供 2D 回退动作；需要稳定 2D 时切回 `main`。
3. 打开 8080 建图页的“DDDMR 运行门禁”，点击“读取 DDDMR”。这个按钮只读调用
   `/api/dddmr/field_test`，不发送任务、速度、重定位或切图命令；看到前端
   `DDDMR PASS`，或命令行 `PASS field_test_ready`，才进入下一步。
4. 打开任务页，按任务列表执行；DDDMR 门禁不再作为任务页单独后端卡片显示。
5. 优先使用 8080 的“生成 DDDMR 近点任务”按钮，或先调用
   `GET /api/dddmr/field_test_task?distance_m=1.0` 预览，再调用
   `POST /api/dddmr/field_test_task` 创建点位和单点任务。这个接口只创建准备数据，
   不会启动任务、切模式、重定位或发布速度；失败时不会落库。
6. 如果不用自动近点入口，也可以手动在当前地图保存一个离机器狗不超过 `3m` 的短距离任务点，
   再生成只包含这个点的单点任务。
7. 从任务列表启动该任务，并全程保持手柄急停可用。
8. 用 `./scripts/104_status.sh` 或 `./scripts/104_diagnose_preflight.sh` 复核
   `field_test`、GNSS、edge-cloud、map_3d 和速度链状态。
   如果需要把现场问题完整反馈给开发侧，优先运行
   `./scripts/104_dddmr_field_test_report.sh`；它只读汇总 `/api/dddmr/field_test`、
   `/api/tasks` 的 `field_test_task_gate`、active task、`selected_map_status`、
   `map_relocalization_required`、`localization_status`、当前位姿新鲜度、edge-cloud、
   map_3d、GNSS、command_mux 和 `nearest_annotations` 最近点距离，不会启动任务、
   切模式、建图或发速度。

后端现在把这条现场操作约束做成统一接口门禁，而不是只靠前端文案：
`GET /api/tasks` 会给每个任务返回 `field_test_task_gate`；`POST /api/tasks`
和 `POST /api/tasks/start` 在 `dddmr_3d + field_proxy` 模式下也会强制检查。
如果任务不是单点、当前机器人位姿不新鲜、首点超过 `runtime.max_goal_distance_m`、
当前固定地图楼层与 DDDMR 三维资产楼层不一致、固定地图 2101 重定位锁未清除、定位未 confirmed，
或 `/api/dddmr/field_test` 验收未通过，接口会返回 `ok=false` 和对应 code
（如 `field_test_single_waypoint_required`、`field_test_pose_unavailable`、
`field_test_goal_too_far`、`field_test_selected_map_not_ready`、
`field_test_map_relocalization_required`、`field_test_localization_not_confirmed`），
不会等到 `/p2p_move_base` action 才拒绝。
v3 任务启动不检查 Nav2 local costmap / odom 对齐；DDDMR 安全证据由 DDDMR 验收、TF、
edge-cloud、mapcloud/mapground、`command_mux` 和 `field_test_task_gate` 统一承担。

`104_accept_dddmr_field_test.sh` 是只读验收脚本，失败码用于现场快速判断阻塞点：
`10` 表示 8080 状态接口不可读，`11` 表示 `field_test.acceptance.ready=false` 且阻塞来自 DDDMR 门禁，
`12` 表示仍有活动任务，`13` 表示无活动任务时速度仲裁器状态缺失或仍报告非零输出。它不创建任务、不启动任务、不发布速度。
脚本在 PASS 和 FAIL 时都会打印 `/api/dddmr/field_test` 返回的 `next_steps`；现场排障应优先按这些步骤处理，再重新读取验收。

验收 PASS 必须同时看到 `command_mux_status`；只要缺少速度仲裁器状态，即使 DDDMR bridge、
field_proxy、edge-cloud 和临时平面资产都 ready，也会返回
`field_test_command_mux_status_missing`；状态超过 3 秒未更新时会返回
`field_test_command_mux_status_stale`。这避免现场启动任务后才发现 `/cmd_vel_nav` 没有被
现有仲裁链接住，或 Web 只拿着已经过期的速度仲裁状态判断 PASS。

验收 PASS 也必须复用 104 既有地图/定位合同：`selected_map_status.ready` 必须为 true，
`map_relocalization_required` 必须为 null，`localization_status.confirmed` 必须为 true。
否则 `/api/dddmr/field_test` 和任务级 `field_test_task_gate` 会分别返回
`field_test_selected_map_not_ready`、`field_test_map_relocalization_required` 或
`field_test_localization_not_confirmed`。这不是新增一套定位系统，而是防止 field_proxy
在 2101 尚未完成或地图失配时用错误的 `map -> m20pro_base_link` TF 开始运动。

近点任务准备接口同样是后端合同，不是前端补丁：`GET /api/dddmr/field_test_task`
只返回建议目标和 `field_test_task_gate`；`POST /api/dddmr/field_test_task` 只创建一个
点位和一个状态为 `ready` 的单点任务，并在创建前复用 `field_test_task_gate`、地图/定位
和栅格可用性检查。它不会调用 `/api/tasks/start`、不会发布 `/p2p_move_base` 目标或
`/cmd_vel`，也不会切换 DDDMR 模式。真正运动仍必须从任务列表启动。

外部交付系统或甲方前端也可以直接调用只读接口：

```bash
curl http://10.21.31.104:8080/api/dddmr/field_test
```

只在返回 `acceptance.ready=true` 后，才把现场短目标测试入口提示为可执行。若返回
`field_proxy_tf_unavailable`，先排查定位/TF 链路，不要创建或启动 DDDMR 任务。

如果当前还不能切换 104 systemd 服务，先用 prepare-only 把新 workspace 构建到
104 的暂存目录，再启动只读预览网页：

```bash
M20PRO_DEPLOY_PREPARE_ONLY=1 M20PRO_DEPLOY_SKIP_EDGE=1 \
  ./scripts/local_deploy_to_test_robot.sh

ssh user@10.21.31.104
M20PRO_WS=/home/user/m20pro_real_ros2_ws.deploy.<时间戳> \
  /home/user/m20pro_real_ros2_ws.deploy.<时间戳>/scripts/104_start_dddmr_preview.sh 18080
```

这个预览入口只启动 DDDMR edge-cloud 适配、三维资产服务、bridge 只读状态和
预览 Web，不做 systemd cutover，不放开运动。它适合现场先核验
`/m20pro/edge_cloud`、`/m20pro/dddmr/edge_cloud/status`、`mapcloud/mapground`
资产、GNSS 状态和前端 DDDMR 面板；如果没有正式三维资产，它会直接显示
`provisional=true` 的“临时平面”，方便先测页面和资产链，不会伪装成正式 DDDMR 资产。

需要后台保持预览时使用：

```bash
./scripts/104_start_dddmr_preview_daemon.sh 18080
./scripts/104_status_dddmr_preview.sh 18080
./scripts/104_stop_dddmr_preview.sh 18080
```

prepare-only 部署会自动维护 `~/.m20pro_dddmr_preview/latest`，所以现场通常不需要手工填
`M20PRO_WS=<timestamp stage>`；只有调试旧 stage 时才显式指定它。

## 安全行为

桥接节点在下列任一条件成立时拒绝目标或取消后端目标，并向 `/cmd_vel_nav` 发布零速度：

- 桥接或运动权限未开启；
- `PToPMoveBase` 消息类型缺失；
- `/p2p_move_base` action server 未就绪；
- DDDMR 三维地图未同时加载非空的瞬态 `mapcloud` 和 `mapground`；
- 已有活动目标；
- DDDMR 速度包含 `NaN` 或无穷值；
- 首条速度超过启动宽限时间仍未出现；
- 活动期间速度刷新超时；
- 后端响应、任务执行或取消超过配置超时；
- 前端取消、DDDMR 失败、异常或节点退出。

速度看门狗使用独立的 `watchdog_period_s`（默认 `0.1s`），不依赖较慢的状态发布周期。若前端在等待 DDDMR 目标响应期间取消或响应超时，桥接会立即结束前端目标，并在迟到的后端目标被接受后补发取消；在此期间速度门禁保持关闭。

桥接状态发布在 `/m20pro/navigation_backend/status`，关键字段包括 `enabled`、`motion_enabled`、`action_type_available`、`action_server_ready`、`edge_cloud_ready`、`map_ready`、`ready`、`goal_active`、`state` 和 `fault_code`。

## CUDA 与硬件

桥接节点不使用 CUDA。上述已审计 DDDMR 核心代码没有 CUDA 强依赖，主要依赖 ROS 2、PCL/点云和 CPU 计算；但这不等于 RK3588 已满足实时性。是否能在 M20Pro 现有计算平台稳定运行，必须用真实点云频率、地图规模和规划负载测试 CPU、内存、时延与温度后才能确定。

## 第一版限制

- 104 侧 edge-cloud 适配和门禁已接入；106 发布保留 xyz 的 edge-cloud 端点尚未在现场编译验证。
- 尚未把完整的三维地图和 DDDMR 定位坐标系接入 DDDMR。
- 尚未生成或加载一张可覆盖多楼层的 DDDMR 三维地图。
- Web 主视图已使用 mapcloud/mapground 抽样做三维点云俯视投影，点位保存包含 z；当前仍不是可自由旋转的完整三维编辑器。
- 现有跨层闭环仍使用 `stair_executor`、原厂楼梯步态和切图事务；DDDMR 当前只替换其入口/出口的 `NavigateToPose` 后端。
- `field_proxy` 只提供短距离低速直达动作链验证，不提供避障、重定位、建图或真正 DDDMR 3D 规划。
- 超大地图的分块、持久化、回环优化、重定位和内存上限尚未实现。
- 尚未在 RK3588、103/104/106 实机链路或真实楼梯上验证，不得作为生产能力宣称。

## 验证

```bash
source /opt/ros/humble/setup.bash
colcon build --packages-select dddmr_sys_core m20pro_navigation m20pro_bringup --symlink-install
source install/setup.bash

python3 scripts/test_dddmr_field_proxy_contract.py
python3 scripts/test_dddmr_sys_core_contract.py
python3 scripts/test_dddmr_navigation_contract.py
python3 scripts/test_dddmr_navigation_wiring.py
python3 scripts/smoke_dddmr_bridge_ros.py
python3 scripts/smoke_dddmr_edge_cloud_ros.py
```

真实 action 合同测试现在使用本工作区生成的 `dddmr_sys_core` 类型：

```bash
source /opt/ros/humble/setup.bash
colcon build --packages-select dddmr_sys_core m20pro_navigation m20pro_bringup \
  --symlink-install
source install/setup.bash
python3 scripts/smoke_dddmr_bridge_action_ros.py
```

该测试使用真实生成的 `PToPMoveBase` 类型和本机假 action server，覆盖上游默认结果成功、显式成功、失败、反馈、速度限幅、前端取消传播、等待后端响应时取消、首条/陈旧速度超时和并发目标拒绝。它验证了桥接协议，不代表 DDDMR 算法、RK3588 实时性或机器狗运动已经通过。
