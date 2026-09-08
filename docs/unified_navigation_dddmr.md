# 统一导航与 DDDMR 边界

## 统一任务模型

系统不区分“单层导航引擎”和“跨层导航引擎”。两者共用同一个 `unified_navigation_plan`：

```text
unified_navigation_plan
  floor_segments: [map + ordered waypoints]
  transitions:    [directed stair connector]
```

单层是 `floor_segments` 只有一项、`transitions` 为空的最小输入。跨层只在连续楼层段之间增加有向连接边，不复制任务队列、点位库或地图库。

任务保存点位 ID，并缓存连续楼层段、地图 ID 和有向路线 ID 的紧凑投影。每次启动前从现有点位库和路线表重建该投影，不把历史快照变成第二份几何真值；任务执行期间禁止修改点位和路线。

## 当前运动边界

```text
平地：106 edge-cloud -> 104 DDDMR perception/planner -> /navigate_to_pose_3d
楼梯：stair_executor -> 原厂楼梯步态 + 低速直行
切层：目标楼层 DDDMR 资产切换 + 目标层 2101
```

唯一 `stair_executor` 负责入口三维导航、步态切换、楼梯直行、平台停车、切图请求、出口三维导航和恢复平地步态。已删除 `stair_action_orchestrator`，旧 `floor_manager.use_stairs()` 保持停用，不形成两套运动链。

`stair_executor` 只向现有 `/cmd_vel_nav` 发布楼梯段速度，下游仍由 `command_mux` 处理仲裁和看门狗。上楼正向，下楼后退。入口和出口通过统一 `/navigate_to_pose_3d` action 进入 DDDMR 桥接链。

地图切换只在共享重叠停车区进行，不在地图边界线上进行。目标楼层的 DDDMR 资产和定位所需数据必须在任务前预置，停车后切换楼层上下文并在目标图的 `target_platform` 自动执行 2101。运行时不下载地图，也不建立第二套定位器。

`m20pro_real_full.sh shadow` 是只读状态，不启动楼梯运动。`m20pro_real_full.sh move` 随轴运动能力启动楼梯执行器。原始 launch 参数默认仍为 `false`，避免只开执行器却没有 103 运动链。

## DDDMR 的使用方式

v3 把 DDDMR 作为主导航链路，不替换 Web、统一任务、`floor_manager`、`stair_executor` 或 `command_mux`。现有业务层继续使用统一任务目标，由受保护的桥接节点转换为 DDDMR `/p2p_move_base` action；DDDMR 速度必须先改名为 `/dddmr/cmd_vel`，桥接节点只在已接受的活动目标期间将限幅后的速度转发到 `/cmd_vel_nav`。

```text
106 原厂 DrDDS /LIDAR/POINTS
  -> 106 edge_scan（高度过滤、角度聚合、保留 xyz）
  -> /m20pro/edge_cloud（处理后的 PointCloud2）
  -> 104 dddmr_edge_cloud_adapter（frame/有限值/新鲜度/点数门禁）
  -> /dddmr/edge_cloud
  -> DDDMR perception/local planner

Web / unified task / stair_executor
  -> floor_manager -> /navigate_to_pose_3d
  -> dddmr_action_bridge -> /p2p_move_base
  -> /dddmr/cmd_vel -> /cmd_vel_nav
  -> command_mux -> /cmd_vel -> M20 TCP bridge
```

这里的 `/m20pro/edge_cloud` 不是原始 `/LIDAR/POINTS`，也不是把
`/scan` 反解成点云。它必须保留 106 edge_scan 选出的有效 `x/y/z`，并且在
`m20pro_base_link` 坐标系下发布。104 适配器拒绝缺少 `z`、坐标系不一致、
有限点过少或数据过期的帧；因此 DDDMR 没有有效三维观测时不会接受运动目标。

v4 底层 launch 默认进入 `dddmr_3d + official`。Lightning-LM 仅在独立建图入口运行；正式定位、感知、规划、避障和 P2P 执行均为官方 DDDMR。`field_proxy` 是测试回退，不得用于现场验收。第一版的部署、安全边界和测试命令见 [dddmr_navigation_v1.md](dddmr_navigation_v1.md)。

`src/dddmr_sys_core` 只固定 DDDMR 的公共 action/srv 与枚举 core，让 104
Foxy 主栈能生成 `PToPMoveBase` 类型并暴露明确状态。它不包含 DDDMR planner、
mapper、local planner 或 `/p2p_move_base` action server；没有真实 server 时后端应显示
`dddmr_action_unavailable`，不能放行运动。

第一轮现场可测版本增加了 `field_proxy` runtime。它是 `/p2p_move_base` 的低速短距离
兼容 action server，使用现有 `map -> m20pro_base_link` TF 做点到点直达控制，速度仍从
`/dddmr/cmd_vel` 进入 bridge 和 `command_mux`。它的价值是让 Web、DDDMR action、
edge-cloud、三维地图门禁和速度链能在场地上闭环测试；它不是 DDDMR 3D 规划器，
不能代表跨楼层、大地图或避障能力。

为降低第一轮实测的资产阻塞，`move + field_proxy` 可使用
`M20PRO_DDDMR_FIELD_TEST_FLAT_MAP` 临时平面 fallback：没有正式 `mapcloud/mapground`
时，资产服务器会发布带 `provisional=true` 的短测平面并在前端标成“临时平面”。
这只放行 field_proxy 的 3m 内低速通路验证，不能作为正式 DDDMR 三维地图资产。
任务接口也已按同一事实源收口：`GET /api/tasks` 暴露 `field_test_task_gate`，
`POST /api/tasks` 和 `POST /api/tasks/start` 会在 field_proxy DDDMR 模式下拦截
验收未过、地图不一致、2101 重定位锁未清除、定位未 confirmed、非单点、当前位姿不新鲜
或首点超距的任务。这样 Web 前端、甲方前端和
交付脚本都走同一套可测门禁。
8080 的“生成 DDDMR 近点任务”只是这套任务模型的便捷入口：`GET /api/dddmr/field_test_task`
只预览当前位姿前方短目标，`POST /api/dddmr/field_test_task` 只创建普通点位和 `ready`
单点任务，并复用 `field_test_task_gate`、三维地图和定位合同；它不启动任务、不发
DDDMR 目标或速度、不切模式。真正运动仍从任务列表进入统一任务执行链。

v4 3D 建图入口默认在 104 本机执行，不在 106 上执行。move/autostart 轨道把前端
`/api/dddmr/mapping/start|finish|cancel` 接到 `scripts/104_dddmr_mapping_control.sh`：
start 在 104 原生 Foxy ARM workspace 启动 `m20pro_bringup/m20pro_lightning_mapping.launch.py`，
通过 `lightning_cloud_adapter` 把 104 已验证可见的 `/dddmr/edge_cloud` 转成
Lightning RoboSense 兼容的 `/m20pro/lightning_points`，并与 `/IMU` 一起输入
Lightning-LM；finish 调用 `/lightning/save_map` 和
`/lightning/save_path`，再把 `global.pcd` 适配成非空 `map.pcd/ground.pcd/poses.pcd`
并归档到 `/root/lightning_maps`。这保证 v4 建图算法已经从旧 DDDMR LeGO mapper
切换到官方 Lightning-LM。

GNSS 只作为辅助锚点：现场前端会把 `/GPS` 与 `/m20pro/gnss/fix` 压缩成
`navigation_backend.gnss` 的一行辅助说明，通常可见为 `source_topic=/GPS`、
`fix_topic=/m20pro/gnss/fix` 这类只读提示；它只用于 3D / 大地图参考，不作为
运动授权，也不在顶栏单列。

选择 `dddmr_3d` 时，104 会随三维后端自动启动
DDDMR 资产服务器并加载当前 Web 数据目录中的 `dddmr_map_assets.yaml`。
资产服务器不再依赖额外开关放行，避免现场直接切后端时漏发
`mapcloud/mapground`。

这次接入不代表三维导航闭环已经完成。DDDMR 点云输入、`mapcloud/mapground`
三维地图、真实 DDDMR `/p2p_move_base`、定位、坐标系和 M20Pro 真机能力还需要逐项接通和
验证；当前跨层任务仍由既有 `stair_executor` 与切图事务执行。

106 上的 `terrain_guard` 保留为可选只读观测：

```text
106 /LIDAR/POINTS -> terrain_guard -> 轻量地形状态
```

它不跨主机传原始点云，不修改 DDDMR 地图或规划输入，首轮也不阻止楼梯执行。等最小闭环跑通且观测数据证明它能稳定识别真实风险后，再评估是否接入停止条件。

## 开发顺序

1. 先跑通两层、一条上行路线的最小真机闭环。
2. 确认入口、步态、平台停车、切图重定位、出口和继续任务的顺序真实可运行。
3. 再测试反向下楼、往返和多连接边任务。
4. 根据实测录包确认真实失效模式，逐项加固。
5. 最后才把 106 地形观测结果接入楼梯停止逻辑。

## 当前不做

- 不重写业务层去调用 DDDMR 私有接口。
- 不在 104 订阅 106 原始 `/LIDAR/POINTS`；只接收 edge_scan 的轻量 PointCloud2。
- 不把 `/scan` 转回 PointCloud2 充当三维输入。
- 不恢复旧楼梯扫描选择器。
- 不并行运行两个楼梯执行器或两个任务队列。
- 不在首次真机闭环前叠加 terrain 强制门禁、额外路线认证或新仲裁层。
