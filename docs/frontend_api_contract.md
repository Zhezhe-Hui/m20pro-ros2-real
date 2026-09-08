# M20Pro 前端 API 对接契约

更新时间：2026-08-19 CST

本文档是“M20 Pro ROS 2 跨楼层巡检导航系统”正式经典前端、甲方前端和外部功能包对接 104 Web 后端的接口契约。接口实现位于 `m20pro_cloud_bridge.web_dashboard_node`。以后新增、删除或修改接口字段时，必须同步更新本文档。

## 基本约定

- 默认服务地址：`http://10.21.31.104:8080`
- 请求格式：`Content-Type: application/json; charset=utf-8`
- 响应格式：JSON
- CORS：当前允许 `*`
- 成功响应通常包含：

```json
{"ok": true}
```

- 失败响应通常为 HTTP 400，并包含：

```json
{"ok": false, "message": "错误说明", "code": "optional_code"}
```

- `GET /api/state` 可能返回较大的实时状态；甲方前端常规轮询建议用 `GET /api/state?debug=0`。
- 不要解析网页 DOM，不要读取前端本地变量。外部系统只依赖本文档列出的 API 字段。

## 地图身份模型

地图身份是当前最重要的契约，前端不要自己猜。

| 字段 | 含义 | 使用建议 |
| --- | --- | --- |
| `selected_map_id` | 操作员显式选择的楼层地图记录；选择当前三维空间地图时为 `null` | 只用于显示当前选择 |
| `working_map_id` | 点位和任务真正使用的楼层地图记录，跨重启保存 | 用于解释断电重启后使用哪张业务地图 |
| `effective_map_id` | 后端解析出的当前有效业务地图 ID | 点位、任务、雷达联动优先使用它 |

规则：

1. 如果显式选择固定地图，`effective_map_id = selected_map_id`。
2. v3 的 `selected_map_status` 比较所选楼层与当前 DDDMR 资产楼层，不比较占据栅格尺寸。
3. 当前三维空间地图没有可解析的业务地图记录时，`effective_map_id = null`，前端不得保存点位或显示其他地图的旧点位。
4. 选择当前三维空间地图不会清除 `working_map_id`，也不会清除 `map_relocalization_required`。
5. v3 的正式主视图只使用 `navigation_backend.map_3d` 中的三维点云抽样；历史占据栅格不参与显示或导航门禁。
6. 项目 `floors` 是建图项目元数据，不是普通地图库白名单；普通地图只要自身楼层格式合法，就可以选择、绑定点位和重定位。
7. 只有跨楼层路线与跨楼层任务使用严格路线楼层注册表。前端不得用项目楼层列表拒绝普通地图。

甲方前端最推荐的做法：

```text
启动页面 -> GET /api/state
拿到 effective_map_id
用 /api/annotations?map_id=live_map 或 /api/annotations?map_id=<effective_map_id> 取点位
用 /api/tasks?map_id=live_map 或 /api/tasks?map_id=<effective_map_id> 取任务
```

## 状态接口

### GET `/healthz`

健康检查。

响应：

```json
{"ok": true}
```

### GET `/api/state`

读取机器人、地图、定位、任务、感知、视频代理等实时状态。

查询参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `debug` | `1` | `0` 时不返回事件和 topic 明细，适合高频轮询 |

稳定字段：

| 字段 | 说明 |
| --- | --- |
| `ok` | 固定为 `true` |
| `node_time` / `node_time_text` | 104 Web 节点时间 |
| `selected_map_id` | 显式选中的固定地图，实时显示时为 `null` |
| `working_map_id` | 当前工作地图 |
| `effective_map_id` | 当前有效地图 |
| `selected_map_status` | 当前有效地图楼层与 DDDMR 三维资产楼层是否一致 |
| `map_relocalization_required` | 切图后是否必须重新 2101 重定位 |
| `localization_status` | 重定位是否真正确认 |
| `relocalization_attempt` | 最近一次网页重定位事务（`pending`/`confirmed`/`failed`）；失败事务会覆盖旧的成功状态 |
| `pose` | 当前地图坐标系下机器人位姿 |
| `pose_fresh` / `pose_age_sec` | 位姿是否新鲜 |
| `floor` | 当前楼层 |
| `scan` | 兼容观察用 `/scan` 摘要和前端激光轮廓点，不作为三维导航门禁 |
| `live_cloud` | 实时障碍点云抽样（`/dddmr/edge_cloud`，默认 ≤350 点）；字段与 `GET /api/3d/live_cloud` 的 `live_cloud` 一致；3D 视图的俯视轮廓切片使用它，不作为导航门禁 |
| `path` | 当前规划路径，用于画导航线 |
| `active_task` | 当前正在执行的任务状态，空闲时为 `null` |
| `floor_switch_transaction` | 当前/最近一次跨楼层切图事务；包含 `request_id`、`route_id`、`plan_id`、`map_epoch` 和 `state`（`SWITCHING_MAP`/`RELOCALIZING`/`COMMITTED`/`FAILED`）；切图或重定位失败时任务停止，新任务可在人工确认地图并重定位后重新执行 |
| `active_waypoint` | 当前任务点 JSON 字符串和解析结果 |
| `charge_command_result` | 最近一次原厂充电导航请求的 JSON 回执；只在充电任务阶段使用 |
| `detections` | YOLO 检测结果，来自 `/m20pro_yolov8_inspection/detections` |
| `inspection_status` | YOLO 检测节点运行状态，来自 `/m20pro_yolov8_inspection/status` |
| `camera_proxy` | 前后相机代理状态 |
| `battery` | 电量显示信息，只用于展示，不作为软件阻断条件；`count` 和 `packs` 只统计原厂电池数组中存在有效遥测的电池，断开的全零占位槽位不会计入 |
| `motion_state` | 原厂基础状态中的当前运动姿态和 `last_update`；前端仅使用 3 秒内的新鲜值切换起立/趴下 |
| `preflight` | 最近一次自检结果 |
| `navigation_backend` | 当前 DDDMR 运行证据；v3 前端只按 DDDMR 门禁解释，不再显示 2D 回退后端 |
| `dddmr_map_assets` | DDDMR 三维资产清单、状态话题和命令模板的汇总；前端应把它当成三维建图/资产管理唯一事实源 |
| `navigation_backend.field_test` | DDDMR 运行轨道的归纳结论；`ready=true` 只表示 DDDMR 运行门禁满足 |
| `navigation_backend.field_test.acceptance` | 现场短目标实测的最终门禁；它把 `field_test.ready`、地图一致性、2101 重定位锁、定位确认、活动任务和速度仲裁统一收口，`ready=true` 才能开始短距离点测；`blocked_by` 可同时列出多个阻塞项 |
| `navigation_backend.command_mux` | 速度仲裁器摘要；`field_test.acceptance` 会直接引用它的 `mode`、`reason` 和 `output_nonzero` |

`navigation_backend` 的关键字段：

```json
{
  "backend": "dddmr_3d",
  "ready": false,
  "motion_enabled": false,
  "reason": "dddmr_motion_disabled",
  "runtime": {
    "seen": true,
    "backend": "field_proxy",
    "ready": true,
    "state": "idle",
    "code": null,
    "decision": null,
    "distance_m": null,
    "max_goal_distance_m": 3.0
  },
  "edge_cloud": {
    "ready": true,
    "frame_id": "m20pro_base_link",
    "finite_points": 850,
    "age_s": 0.12
  },
  "gnss": {
    "ready": true,
    "source_topic": "/GPS",
    "fix_topic": "/m20pro/gnss/fix",
    "latitude": 30.123456,
    "longitude": 120.123456,
    "altitude_m": 18.5,
    "speed_kmh": 0.8,
    "course_deg": 91.0,
    "num_satellites": 10,
    "visible_satellites": 16,
    "pdop": 1.2,
    "hdop": 1.0,
    "vdop": 1.7
  },
  "map_3d": {
    "ready": false,
    "mapcloud_ready": false,
    "mapground_ready": false,
    "mapcloud_points": 0,
    "mapcloud_samples": [],
    "mapground_points": 0,
    "mapground_samples": [],
    "mapcloud_frame": "map",
    "mapground_frame": "map",
    "mapcloud_topic": "/mapcloud",
    "mapground_topic": "/mapground"
  },
  "field_test": {
    "ready": false,
    "reason": "dddmr_motion_disabled",
    "mode": "move",
    "runtime_backend": "field_proxy",
    "notes": [],
    "acceptance": {
      "ready": false,
      "reason": "field_test_active_task_running",
      "blocked_by": ["active_task"],
      "field_test_ready": false,
      "field_test_reason": "dddmr_motion_disabled",
      "mode": "move",
      "runtime_backend": "field_proxy",
      "active_task": {"seen": true, "running": true, "task_id": "task_001", "status": "running", "task_name": "", "multi_floor": false},
      "command_mux": {"seen": true, "mode": "navigation", "reason": "task_start", "output_nonzero": false, "updated_at": 1720000000.0, "age_s": 0.2, "stale": false}
    }
  },
  "command_mux": {
    "seen": true,
    "mode": "navigation",
    "reason": "task_start",
    "output_nonzero": false,
    "updated_at": 1720000000.0
  },
  "action_server_ready": false
}
```

前端只有在 `edge_cloud.ready`、`map_3d.mapcloud_ready`、`map_3d.mapground_ready`、动作服务和运动授权都满足时，才可显示 DDDMR 三维门禁通过。DDDMR 对外只有 `dddmr_3d`；是否允许运动由 `motion_enabled`、`field_test.acceptance.ready` 和任务链路共同决定。

如果 `runtime.backend == "field_proxy"`，前端必须按“现场低速代理”展示。这只证明
`/p2p_move_base` action 和速度链可测，不代表真实 DDDMR 3D planner 已接入。
同时必须读取并展示 `runtime.tf_ready/tf_code`：只有 `tf_ready == true` 时，
field proxy 才能把 `/p2p_move_base` 目标转换到当前机身位姿；若为
`field_proxy_tf_unavailable`，前端和验收按钮都必须显示阻塞，不能提示可开测。

如果 `dddmr_map_assets.status.provisional == true` 或 `source == "field_test_flat_map"`，
前端必须标成“临时平面/仅用于 field_proxy 短测”。它可以让第一版现场短目标测试通过
三维地图门禁，但不能被展示为正式 DDDMR 建图结果、大地图或跨楼层能力。

如果 `field_test.acceptance.ready == true`，前端和验收脚本可以把当前状态解释为“可做现场低速短目标测试”；它仍不代表跨楼层、大地图、避障或真实 DDDMR 算法已完成。
`field_test.ready` 只是 DDDMR 运行门禁，不足以单独放行短测；活动任务必须为空，并且必须已经收到
新鲜 `command_mux_status`，确认速度仲裁器存在且 `output_nonzero=false`。缺少 `command_mux_status`
时，标准阻塞原因是 `field_test_command_mux_status_missing`；状态超过 3 秒未更新时，
标准阻塞原因是 `field_test_command_mux_status_stale`。前端不得在这两种情况下显示为可开测。
同时必须满足 `selected_map_status.ready == true`、`map_relocalization_required == null`、
`localization_status.confirmed == true`。地图失配、固定地图仍要求 2101、定位未确认时，
标准原因分别是 `field_test_selected_map_not_ready`、`field_test_map_relocalization_required`
和 `field_test_localization_not_confirmed`；前端应直接引导操作员处理地图/定位面板，不要提示可开测。
对 `field_proxy` 后端，`field_test.ready` 还必须包含 `map -> m20pro_base_link` TF 可用；
缺 TF 时标准原因是 `field_proxy_tf_unavailable`。
第一版现场短目标测试不新增绕过任务系统的独立 DDDMR 运动按钮。前端应在任务页提示操作员：
在当前地图保存 `runtime.max_goal_distance_m` 以内的短距离任务点，生成单点任务，再从任务列表启动。
这样目标下发、停止任务、速度仲裁和日志仍走既有任务链路。
经典 8080 前端可以提供“生成 DDDMR 近点任务”准备按钮，但它必须调用
`/api/dddmr/field_test_task` 创建普通点位和普通任务，不得直接发送 DDDMR 目标。
该按钮文案必须明确“不会启动任务”，创建后仍由任务列表手动启动。
在 `dddmr_3d + field_proxy` DDDMR 模式下，后端会统一生成 `field_test_task_gate`：
`GET /api/tasks` 的每个任务都会带该字段，`POST /api/tasks` 和
`POST /api/tasks/start` 也会强制检查。`field_test_task_gate.applies == true`
且 `ready == false` 时，前端不得允许启动任务；常见 `code` 包括
`field_test_acceptance_not_ready`、`field_test_single_waypoint_required`、
`field_test_pose_unavailable`、`field_test_goal_too_far`、
`field_test_selected_map_not_ready`、`field_test_map_relocalization_required`
和 `field_test_localization_not_confirmed`。这个限制只作用于
第一版 field_proxy 短测，不是历史 2D 基线或未来真实 DDDMR planner 的长期限制。

`navigation_backend.gnss` 直接对应手册里的 `/GPS` 卫星定位参数组；它只作为跨楼层 / 大地图的
辅助锚点，默认前端应压缩成一行可用性说明，不再在顶栏单列，也不要求把纬度、经度、海拔、
地速、航向和 DOP 展开成主信息。

经典 8080 前端的默认工作视图也应保持收口：主界面先给“当前模式 / 现在怎么做 / 是否可开测”的
概览，DDDMR 3D 资产登记、建图命令和详细运行证据放到可展开的高级区里，避免把操作入口和诊断
信息摊成一整屏。“现在怎么做”必须把后端原因码翻译成操作动作，例如定位/TF 缺失时提示先打开
“定位”完成重定位，edge-cloud 缺失时提示先查上游点云，速度仲裁异常时提示先确认
command_mux；不能只把 `field_proxy_tf_unavailable` 这类内部码原样丢给现场操作员。DDDMR 面板还必须
提供一个对应的主按钮，默认在“打开定位 / 切到 DDDMR / 生成近点任务 / 读取 DDDMR”之间自动切换，
让现场不需要自己猜下一步点哪个；切模式、读取和建点等次级动作应收进高级区，默认视图只保留主流程。
重定位成功后，前端应自动重读一次 DDDMR 只读接口，确保按钮和门禁文案立即刷新，不让现场停在旧的 FAIL 状态。

现场实测前的命令行验收入口是 `./scripts/104_accept_dddmr_field_test.sh`。它只读取
`/api/dddmr/field_test`，旧服务无该接口时回退 `/api/state?debug=0`，并复用
`navigation_backend.field_test.acceptance` 结论，同时在 PASS 和 FAIL 时打印接口返回的
`next_steps`；前端不需要实现一套
独立判据，也不应该新增绕过任务系统的 DDDMR 直控接口。

经典 8080 前端在建图页“DDDMR 运行门禁”提供“读取 DDDMR”按钮。该按钮也只读调用
`GET /api/dddmr/field_test`，把 `acceptance.ready`、`blocked_by`、`next_steps`
和 `field_test.notes` 原样展示；它不得创建任务、启动任务、发布速度、执行重定位或切图。
甲方前端如果要实现同类入口，也必须复用这个接口和判据。
104 现场如果需要完整反馈问题，可运行 `104_dddmr_field_test_report.sh`；它只读汇总
`/api/dddmr/field_test`、`/api/tasks` 的 `field_test_task_gate`、active task、
`selected_map_status`、`map_relocalization_required`、`localization_status`、当前位姿新鲜度、
edge-cloud、map_3d、辅助 GNSS、command_mux 摘要和 `nearest_annotations` 最近点距离，
不调用任何 POST/DELETE/运动接口。

### GET `/api/dddmr/field_test`

只读返回 DDDMR 验收状态，供命令行、甲方前端和交付系统统一判断是否可以开始
3m 内低速短目标测试。它不创建任务、不启动任务、不发布速度。

响应核心字段：

```json
{
  "ok": true,
  "api": "/api/dddmr/field_test",
  "navigation_backend": {
    "backend": "dddmr_3d",
    "runtime": {"backend": "field_proxy", "ready": true, "tf_ready": true, "tf_code": "field_proxy_tf_ready"},
    "field_test": {"acceptance": {"ready": true}}
  },
  "field_test": {"ready": true, "acceptance": {"ready": true, "blocked_by": []}},
  "acceptance": {"ready": true, "reason": "field_test_acceptance_ready", "blocked_by": []},
  "active_task": null,
  "command_mux_status": {"parsed": {"mode": "navigation", "output_nonzero": false}},
  "dddmr_map_assets": {"workspace": {"ready_floor_count": 1}},
  "next_steps": ["在当前地图保存 runtime.max_goal_distance_m 以内的短距离任务点"]
}
```

兼容别名：`GET /api/dddmr/field_test/acceptance`。

### GET `/api/dddmr/field_test_task`

只预览一个 DDDMR 近点任务，不落库、不启动任务、不发布速度。它根据当前
已确认位姿、`distance_m`/`lateral_m` 和当前 `runtime.max_goal_distance_m` 生成建议目标，
并用同一个 `field_test_task_gate` 判断是否允许创建。

推荐：

```text
GET /api/dddmr/field_test_task?distance_m=1.0
```

响应核心字段：

```json
{
  "ok": true,
  "api": "/api/dddmr/field_test_task",
  "created": false,
  "suggestion": {"map_id": "map_f1", "pose": {"x": 1.0, "y": 0.0, "z": 0.0, "yaw": 0.0}},
  "field_test_task_gate": {"applies": true, "ready": true, "code": "field_test_task_ready"},
  "next_steps": ["确认无误后调用 POST /api/dddmr/field_test_task 创建点位和单点任务"]
}
```

### POST `/api/dddmr/field_test_task`

创建一个 DDDMR 近点点位和一个只包含该点的 `ready` 任务。它不会调用
`/api/tasks/start`，不会发送 `/p2p_move_base` 目标，不会发布 `/cmd_vel`，也不会切模式、
建图或重定位。真正运动仍必须从任务列表启动。

请求体：

```json
{"distance_m": 1.0, "lateral_m": 0.0}
```

创建前后端会复用 `field_test_task_gate`、当前楼层三维资产/2101 定位确认和
普通 `/api/tasks` 创建合同。不满足条件时返回 `ok=false`，携带 `code`、
`field_test_task_gate` 或 `validation`，并且不创建点位、不创建任务。超过第一版距离限制时
标准 code 是 `field_test_goal_too_far`。

成功响应会返回：

```json
{
  "ok": true,
  "api": "/api/dddmr/field_test_task",
  "created": true,
  "annotation": {"id": "point_xxx", "source": "dddmr_field_test_task"},
  "task": {"id": "task_xxx", "status": "ready", "annotation_ids": ["point_xxx"]},
  "field_test_task_gate": {"ready": true, "code": "field_test_task_ready"}
}
```

### GET `/api/dddmr/field_test_mode`

只读返回当前 DDDMR 系统模式和可用的切换入口。v3 前端只显示 DDDMR
状态，不再提供 2D 回退入口；真正的运动仍以 `field_test.acceptance.ready`
和既有任务链路为门禁。

### POST `/api/dddmr/field_test_mode`

切换 104 当前系统模式。请求体：

```json
{"action":"enable"}
```

`action` 只接受 `enable`。后端只负责调度
104 本机的 DDDMR 模式切换脚本并返回 `queued=true`；前端必须提示这是一次会重启服务的
操作，不能把它当作立即完成的状态。响应会同时给出 `target_mode`（systemd real mode）
和 `target.navigation_backend` / `target.axis_command_enabled`，用于前端明确显示切换目标；
v3 的目标后端固定为 `dddmr_3d`，不得在前端重新暴露其他后端切换。

`navigation_backend.gnss` 直接继承手册中的 GPS/GNSS 参数组，支持平铺字段、嵌套 `GPS` 分组和
`Items` 包裹形态；前端把它当成 3D / 大地图的全局辅助锚点即可，默认只显示一行可用性说明，
不再单独占顶栏。

定位成功判断：

```text
localization_status.confirmed == true
map_relocalization_required == null
selected_map_status.ready == true
```

不要把“调用过 `/api/localization/initialpose`”当成成功。只有后端返回确认成功，且状态接口也确认成功，才算真正重定位成功。若 `relocalization_attempt.status=failed`，旧的地图位姿不能继续作为本次重定位成功依据。

## 3D 空间视图接口

3D 视图数据层的正式接口。数据规则（点云抽稀上限、ready 语义、字段形状）由
`m20pro_cloud_bridge.spatial_view_contract` 锁定，`/api/state` 内嵌字段与下列
专属端点同源同形，甲方前端可任选其一。

### `navigation_backend.map_3d` / `GET /api/3d/spatial_map` 字段表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ready` | bool | mapcloud 与 mapground 同时 ready 才为 `true`；3D 视图数据可用门禁 |
| `mapcloud_ready` / `mapground_ready` | bool | 两路地图点云各自是否收到有效消息 |
| `mapcloud_points` / `mapground_points` | int | 原始点云总点数（width×height），不是抽样数 |
| `mapcloud_samples` / `mapground_samples` | `[[x,y,z]]` | 有界抽样（≤1800 点，只含有限点，3 位小数），用于 3D 视口渲染 |
| `mapcloud_frame` / `mapground_frame` | string | 点云坐标系 frame_id |
| `mapcloud_topic` / `mapground_topic` | string | 来源话题 |

### GET `/api/3d/spatial_map`

读取当前 3D 空间地图数据段，与 `/api/state` 的 `navigation_backend.map_3d` 完全一致（单一事实源）。

响应示例：

```json
{
  "ok": true,
  "map_3d": {
    "ready": true,
    "mapcloud_ready": true,
    "mapground_ready": true,
    "mapcloud_points": 1349135,
    "mapcloud_samples": [[0.1, 0.2, 0.3]],
    "mapground_points": 982112,
    "mapground_samples": [[0.0, 0.0, 0.0]],
    "mapcloud_frame": "map",
    "mapground_frame": "map",
    "mapcloud_topic": "/mapcloud",
    "mapground_topic": "/mapground"
  }
}
```

### GET `/api/3d/live_cloud`

读取当前实时障碍点云抽样（来源话题由 `live_cloud_topic` 参数配置，默认 `/dddmr/edge_cloud`）。
与 `/api/state.live_cloud` 完全一致；未收到消息时 `live_cloud` 为 `null`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `live_cloud.last_update` | float | 后端收到消息的本地时间（秒） |
| `live_cloud.stamp_sec` | float | 消息头时间戳（秒） |
| `live_cloud.frame_id` | string | 坐标系，通常为机体坐标系；前端按当前位姿变换到地图系 |
| `live_cloud.points` | int | 抽样点数（= `samples` 长度，默认 ≤350） |
| `live_cloud.samples` | `[[x,y,z]]` | 机体坐标系下的抽样点 |

响应示例：

```json
{
  "ok": true,
  "live_cloud": {
    "last_update": 1720000001.0,
    "stamp_sec": 1720000000.85,
    "frame_id": "m20pro_base_link",
    "points": 348,
    "samples": [[0.52, 0.11, 0.03]]
  }
}
```

使用约定：

1. 3D 视图的俯视激光轮廓由 `live_cloud` 在体坐标系切片得到，不依赖原厂 2D `/scan`。
2. `live_cloud` 超过 3 秒未更新视为过期，前端不再渲染。
3. 抽稀上限只影响 HTTP 传输与画布开销，不改变任何导航门禁。

## 雷达接口

雷达前端优先使用以下 JSON API，不需要读取后端结果目录或解析网页 DOM。

### GET `/api/radar/status`

读取雷达模块最新状态、最新结果和结果目录。

稳定字段：

| 字段 | 说明 |
| --- | --- |
| `ok` | 固定为 `true` |
| `results_dir` | 雷达结果根目录 |
| `latest_parsed` | 最新 `/m20pro/radar_inspection/status` 或 result 的解析 JSON |
| `latest_job` | 最近一次落盘的雷达扫描结果 |
| `job_count` | 当前结果目录中的扫描结果数量 |

### GET `/api/radar/results`

读取雷达扫描结果列表。

查询参数：

| 参数 | 说明 |
| --- | --- |
| `task_id` | Web 任务 ID |
| `radar_task_id` / `taskId` | 雷达设备任务 ID |
| `run_id` | 后端生成的单次扫描 ID |
| `waypoint_key` | `/m20pro/active_waypoint` 对应点位 key |
| `status` | `completed`、`failed` 等 |
| `state` | `finished`、`result_unavailable` 等 |
| `mode` / `scan_mode` | `measuring` 或 `modeling` |
| `limit` / `offset` | 分页，默认 `limit=50` |

响应核心字段：

```json
{
  "ok": true,
  "total": 1,
  "count": 1,
  "results": [
    {
      "task_id": "api_radar_test_003",
      "taskId": "B01_U01_F20_R2008_P01_measure_20260710_164336",
      "status": "completed",
      "state": "finished",
      "scan_mode": "measuring",
      "metric_count": 12,
      "result_fetch_status": "success",
      "summary": {"metrics": []},
      "summary_path": "/home/user/m20pro_radar_results/summaries/xxx.json",
      "raw_path": "/home/user/m20pro_radar_results/raw/xxx.json"
    }
  ]
}
```

雷达结果不是仅供前端临时显示的内存数据。104 会把以下内容持久化到 `radar_results_dir`（正式环境默认为 `/home/user/m20pro_radar_results`）：

- `jobs/`：每次任务/点位的完整执行记录，前端结果列表从这里分页读取；
- `raw/`：雷达设备返回的原始 JSON 和任务信息；
- `summaries/`：平整度、极差等结构化指标摘要；
- `downloads/`：仅当雷达 HTTP 接口返回可下载文件 URL 时保存点云工程或压缩包；
- `manual/`：人工登记的点云路径和人工测量回填。

当前系统没有甲方服务器“上传成功确认”接口，也没有自动清理策略，因此这些文件会持续积累。正式对接时应由上传组件读取任务结果，收到甲方服务器持久化 ACK 后再按任务清理本地副本；没有 ACK 时不得自动删除。前端使用分页接口，不会把全部历史结果一次渲染到页面。

### GET `/api/radar/result`

读取单条雷达结果。支持 `run_id`、`radar_task_id`、`taskId`、`waypoint_key` 等参数；没有匹配结果时返回 HTTP 400。

### GET `/api/radar/task`

按 Web 任务 ID 读取雷达任务汇总。

查询参数：

| 参数 | 说明 |
| --- | --- |
| `task_id` | 必填，Web 任务 ID |

返回字段包含 `task`、`results`、`summary`。`summary.result_unavailable_count > 0` 表示雷达已触发但后端未拿到结果。

### GET `/api/radar/task_export`

下载任务级雷达结果，兼容人工交付：

```text
GET /api/radar/task_export?task_id=<task_id>&format=json
GET /api/radar/task_export?task_id=<task_id>&format=csv
```

### POST `/api/radar/artifact`

登记点云建模结果文件路径。

### POST `/api/radar/manual_measurement`

登记人工测量回填。

## 地图接口

### GET `/api/maps`

读取固定地图列表和当前地图身份。

响应核心字段：

```json
{
  "ok": true,
  "maps": [
    {
      "id": "map_example",
      "name": "办公室场地",
      "floor": "F20",
      "yaml_path": "/home/user/m20pro_maps/办公室场地/occ_grid.yaml",
      "source": "106_active_map",
      "navigation": {
        "ready": true,
        "code": "navigation_map_ready",
        "factory_map_path": "/var/opt/robot/data/maps/办公室场地-20260721-160447"
      }
    }
  ],
  "selected_map_id": null,
  "working_map_id": "map_example_f7",
  "effective_map_id": "map_example_f7"
}
```

### POST `/api/maps/select`

选择一个楼层业务地图记录，或回到当前 DDDMR 三维空间地图。v3 不调用 Nav2
`load_map`；选择后通过楼层上下文加载对应 `mapcloud/mapground`，并要求重新确认定位。

### DELETE `/api/maps`

删除 104 上的普通归档地图：

```text
DELETE /api/maps?id=<map_id>&cascade=true
```

- 当前正式清单不预置固定楼层地图；接口删除对象是 104 已归档的普通业务地图；
- 当前生效地图和工作地图不能删除，必须先切换到其他地图；
- 任务执行中不能删除地图；
- `cascade=true` 会同步删除该地图的点位和依赖任务，并清除建图会话里的导入引用；
- 只会物理删除 `map_archive_dir` 内由 104 管理且未被其他地图共用的目录，不会删除 106 原厂地图或工程目录外文件；
- 删除地图不会删除项目的楼层元数据；项目楼层元数据也不能影响其他普通地图的选择和重定位；
- 雷达历史结果是独立的交付证据，不随地图删除。

选择固定地图：

```json
{"map_id": "map_example_f7"}
```

切到当前三维空间地图：

```json
{"map_id": ""}
```

响应核心字段：

```json
{
  "ok": true,
  "selected_map_id": null,
  "working_map_id": "map_example_f7",
  "effective_map_id": "map_example_f7",
  "map_relocalization_required": {
    "map_id": "map_example_f7",
    "message": "当前固定地图已选择，必须重新按开发手册2101定位"
  }
}
```

注意：

- 固定地图切换成功后，通常必须重新重定位。
- v3 选择任何地图都不会调用 Nav2 `load_map`。
- 选择当前三维空间地图不会清除重定位要求。

### POST `/api/maps/edit`（历史兼容，v3 前端不调用）

把当前已生效固定地图上的稀疏栅格修改保存为一个新地图版本。坐标使用地图图片坐标：左上角为 `(0, 0)`；`value` 只能是 `0`（可通行）、`100`（障碍）或 `-1`（未知）。

```json
{
  "map_id": "map_example_f7",
  "name": "F7现场图_修饰",
  "cells": [
    {"x": 120, "y": 85, "value": 0},
    {"x": 121, "y": 85, "value": 100}
  ]
}
```

接口约束：

- 只允许修改当前已经生效的固定地图，实时 `/map` 和任务执行期间拒绝写入；
- 原地图永不覆盖，新地图记录使用 `source=web_map_editor` 并记录 `parent_map_id`；
- 新版本继承原地图的点位，并为单地图任务生成可独立执行的任务副本；
- Web 修饰只改变 104/Nav2 使用的二维占据栅格，不伪造 106 原厂地图路径；切换新版本时不会把 106 错误切回未修饰地图；
- 保存接口不自动切图，调用方需要在操作者确认后再调用 `/api/maps/select`。

响应核心字段：

```json
{
  "ok": true,
  "map": {"id": "map_new", "parent_map_id": "map_old", "source": "web_map_editor"},
  "parent_map_id": "map_old",
  "changed_cells": 42,
  "cloned_annotations": 5,
  "cloned_tasks": 2,
  "message": "地图修饰已保存为新版本；原地图未覆盖"
}
```

### GET `/api/map`（历史兼容，v3 前端不调用）

读取历史占据栅格 `OccupancyGrid` 派生 JSON。v3 主视图不请求该接口。

### GET `/api/map_file?map_id=<id>`（历史兼容，v3 前端不调用）

读取历史固定栅格地图文件。v3 主视图直接使用 `/api/state.navigation_backend.map_3d`
中的 `mapcloud_samples/mapground_samples` 做有界抽样显示。

### GET `/api/multi_floor`

读取普通地图工作区、项目楼层元数据和跨楼层路线摘要。核心字段包括 `current_floor`、`selected_map_id`、`floors[]`、`routes[]`、`latest_mapping_session` 和 `identity_issues`。

`floors[].route_configured=true` 才表示该楼层属于严格跨楼层路线配置；`registry_source=project` 仅表示建图项目登记，不能作为地图选择白名单。没有显式跨楼层路线注册表时，普通地图楼层会进入工作区；存在路线注册表时，跨楼层工作区只暴露路线已注册数据，但这不影响普通地图通过 `/api/maps/select` 选择和重定位。

## 点位接口

### GET `/api/annotations`

读取点位列表。

查询参数：

| 参数 | 说明 |
| --- | --- |
| `map_id` | 可传固定地图 ID，也可传 `live_map` |

推荐：

```text
GET /api/annotations?map_id=live_map
```

响应核心字段：

```json
{
  "ok": true,
  "requested_map_id": "live_map",
  "effective_map_id": "map_example_f7",
  "annotations": [
    {
      "id": "point_xxx",
      "map_id": "map_example_f7",
      "type": "patrol",
      "floor": "F20",
      "label": "客厅P01",
      "area": "",
      "room": "客厅",
      "scan_point": "P01",
      "result_file_prefix": "B03_U01_H2008_F20_客厅_P01",
      "pose": {"x": 1.0, "y": 2.0, "z": 0.0, "yaw": 0.0},
      "dwell_s": 5.0,
      "manual_point_type": "task",
      "radar": {
        "enabled": true,
        "scans": [
          {"mode": "measuring", "label": "实测实量", "result_suffix": "measure"},
          {"mode": "modeling", "label": "点云建模", "result_suffix": "cloud"}
        ]
      }
    }
  ],
  "hidden_annotation_count": 3,
  "total_annotation_count": 8
}
```

昂锐雷达和甲方业务命名建议读取这些字段：

| 字段 | 用途 |
| --- | --- |
| `label` | 操作员给任务点起的名称 |
| `room` | 房间/部位 |
| `scan_point` | 扫描点编号 |
| `result_file_prefix` | 建议的结果文件前缀 |
| `radar` | 雷达模式配置，可包含多模式扫描 |
| `dwell_s` | 当前点位停留时间，雷达扫描耗时应由雷达流程自己判断完成，不要只依赖停留时间 |

### POST `/api/annotations`

保存点位。

推荐请求：

```json
{
  "map_id": "live_map",
  "source": "map_click",
  "type": "patrol",
  "floor": "F20",
  "label": "客厅P01",
  "area": "",
  "room": "客厅",
  "scan_point": "P01",
  "result_file_prefix": "B03_U01_H2008_F20_客厅_P01",
  "pose": {"x": 1.0, "y": 2.0, "z": 0.0, "yaw": 0.0},
  "manual_point_type": "task",
  "dwell_s": 5,
  "vendor_navigation": {
    "Gait": 12,
    "Speed": 1
  },
  "radar": {
    "enabled": true,
    "scans": [
      {"mode": "measuring", "label": "实测实量", "result_suffix": "measure"},
      {"mode": "modeling", "label": "点云建模", "result_suffix": "cloud"}
    ]
  }
}
```

说明：

- `map_id` 推荐传 `effective_map_id`，也允许传 `live_map`。
- 后端会把 `live_map` 解析成当前有效固定地图。
- 如果当前三维资产楼层不能匹配有效业务地图，保存会失败。
- 如果 `map_relocalization_required` 未清除，使用机器人实时位姿保存点位会被阻止。
- `type` 的正式前端取值依次为 `patrol`（任务点）、`transition`、`charge`、`stair_entry`（爬楼梯点）、`stair_exit`、`stair_switch`。
- `manual_point_type` 由 `type` 推导；外部调用可以显式传入，但不能与 `type` 表达相反的业务含义。
- `vendor_navigation` 只接受 `Gait` 和 `Speed` 调整；后端始终固定 `Manner=0`、`ObsMode=0`、`NavMode=1`，并根据点位语义生成 `PointInfo`。
- `stair_entry` 未显式传 `Gait` 时默认 `14`，其他点位默认 `12`。统一跨楼层任务的上下楼方向及步态切换由唯一 `stair_executor` 负责。

### DELETE `/api/annotations?id=<annotation_id>`

删除点位。任务执行中涉及当前任务的点位不能删除。

### POST `/api/annotations/update`

修改已有点位。请求体与新增点位一致，并额外传入 `id`。点位 `id`、`map_id` 和 `created_at` 保持不变；不允许通过修改接口把点位迁移到另一张地图。点位正在当前任务中执行时不允许修改。

```json
{
  "id": "point_xxx",
  "map_id": "map_xxx",
  "type": "patrol",
  "floor": "F20",
  "label": "修改后的点位",
  "pose": {"x": 1.0, "y": 2.0, "z": 0.0, "yaw": 0.5},
  "manual_point_type": "task",
  "dwell_s": 10
}
```

## 任务接口

### GET `/api/tasks`

读取任务列表。

查询参数：

| 参数 | 说明 |
| --- | --- |
| `map_id` | 可传固定地图 ID，也可传 `live_map` |
| `include_all` | `true` 时返回所有任务，否则只返回当前有效地图任务 |

推荐：

```text
GET /api/tasks?map_id=live_map
```

响应中的任务会补充 `waypoints`，其中每个点位包含 `label`、`room`、`scan_point`、`result_file_prefix`、`radar` 等字段。雷达系统应该优先读取 `waypoints`，而不是再自己拼点位名称。

在 `dddmr_3d + field_proxy` DDDMR 模式下，每个任务还会补充
`field_test_task_gate`。示例：

```json
{
  "applies": true,
  "ready": false,
  "code": "field_test_goal_too_far",
  "message": "DDDMR field_proxy 第一版只允许 3.0m 内短目标；当前首点距离 4.20m，请重新标一个近点",
  "runtime_backend": "field_proxy",
  "max_goal_distance_m": 3.0,
  "distance_m": 4.2
}
```

前端必须在 `applies=true && ready=false` 时禁用任务启动按钮；不要等
`/p2p_move_base` action 拒绝后才提示用户。

任务还会返回 `navigation_plan_summary`。单层任务和跨楼层任务使用同一计划
结构：单层只有一个 `floor segment`，跨楼层在连续楼层段之间增加有向
`transition`。`floor_sequence`、`route_plans` 和 `multi_floor` 只是该计划的
兼容投影，不能作为另一套任务顺序来源。每次开始任务时，后端都会用当前
点位顺序和当前有向路线重新生成并刷新该投影；路线调整后可以直接重新执行
原任务，不需要为了旧计划缓存删除并重建任务。

### POST `/api/tasks`

生成任务。

```json
{
  "name": "日常巡检任务",
  "map_id": "live_map",
  "annotation_ids": ["point_a", "point_b"]
}
```

响应：

```json
{
  "ok": true,
  "task": {
    "id": "task_xxx",
    "name": "日常巡检任务",
    "map_id": "map_example_f7",
    "annotation_ids": ["point_a", "point_b"],
    "status": "ready"
  }
}
```

若当前后端处于 `dddmr_3d + field_proxy` DDDMR 模式，创建任务时也会执行
`field_test_task_gate`。不满足单点、3m 距离、当前位姿新鲜或 DDDMR 验收条件时，
后端直接返回 `ok=false`，并携带 `code`、`validation` 和 `field_test_task_gate`。
这样甲方前端或交付脚本直接调用 `/api/tasks` 也不能绕过 field_proxy 限制。

完整任务记录中的 `navigation_plan` 是一个紧凑快照，只保存有序点位 ID、连续
楼层段、地图 ID 和有向连接 ID，不复制点位详情或完整路线配置。例如：

```json
{
  "kind": "unified_navigation_plan",
  "version": 1,
  "annotation_ids": ["point_a", "point_b"],
  "segments": [
    {"index": 0, "floor": "F1", "map_id": "map1", "annotation_ids": ["point_a"]},
    {"index": 1, "floor": "F2", "map_id": "map2", "annotation_ids": ["point_b"]}
  ],
  "transitions": [
    {"route_id": "F1:stairs_to_F2", "source_floor": "F1", "target_floor": "F2"}
  ]
}
```

`navigation_plan` 是点位库和有向路线库的紧凑投影，不是第二份路线数据库。
历史任务第一次启动时会生成该投影；已有任务每次启动前也会从当前点位和路线
重新生成并保存投影。任务执行期间禁止修改点位和跨楼层路线，因此一次运行中的
计划不会被中途替换。

### POST `/api/tasks/start`

开始任务。

```json
{"task_id": "task_xxx"}
```

可选保护字段：

```json
{
  "task_id": "task_xxx",
  "expected_first_annotation_id": "point_a",
  "expected_task_map_id": "map_example_f7"
}
```

任务启动前应确认：

```text
/api/state.localization_status.confirmed == true
/api/state.selected_map_status.ready == true
/api/state.map_relocalization_required == null
/api/preflight 或最近自检没有基础链路错误
```

如果当前是 `dddmr_3d + field_proxy` DDDMR 模式，还必须满足
`field_test_task_gate.ready == true`：DDDMR 验收已通过、任务只有一个点、
当前机器人位姿新鲜、首点距离不超过 `runtime.max_goal_distance_m`。

v3 只运行 `dddmr_3d`。任务启动不检查历史 Nav2 controller/local costmap，必须通过
`field_test_task_gate`、`/api/dddmr/field_test`、三维资产、定位和速度仲裁门禁。
`local_costmap_odom_mismatch` 与 `local_costmap_alignment_unavailable` 仅是后端历史兼容
路径可能返回的旧错误码，v3 前端不得据此展示二维导航状态或提供回退入口。

### POST `/api/tasks/stop`

停止或复位当前任务。

```json
{"reason": "web_manual_stop"}
```

常用 reason：

| reason | 含义 |
| --- | --- |
| `web_manual_stop` | 操作员停止任务 |
| `web_manual_reset` | 操作员复位导航会话，会发送停止/零速度并清理导航显示状态 |

## 人工遥控接管

遥控不直接抢占自主导航速度。DDDMR 适配链发布 `/cmd_vel_nav`，网页发布
`/cmd_vel_teleop`，`m20pro_command_mux` 以 `navigation / teleop / locked` 三态仲裁后
才向 TCP bridge 的 `/cmd_vel` 输出。任何模式切换、指令超时或异常值都先输出零速度。

安全规则：

- 只有 104 以 `move` 模式运行且速度仲裁器就绪时可以接管。
- 接管前后端先停止当前任务；结束接管后仲裁器进入 `locked`，旧任务不会自动恢复。
- 同一时间只允许一个遥控会话；指令必须带会话 ID 和单调递增序号，迟到指令被忽略。
- 浏览器必须在 `teleoperation.command_timeout_s` 内续租。松键、失焦、页面隐藏、断网或后端异常都会零速停车；仲裁器还有独立的第二道超时保护。
- 前端用一个姿态按钮在起立/趴下之间切换。姿态依据 `m20pro_tcp_bridge` 从原厂 2Hz `Type=1002/Command=6` 主动基础状态生成的 `/m20pro_tcp_bridge/motion_state`；`MotionState=0/2/3/4` 时目标为起立，`1/6/8` 时目标为趴下，状态缺失或超过 3 秒时按钮显示“姿态未知”并禁用。起立、趴下和软急停都先发送零速度并锁定速度仲裁器；起立/趴下动作结束后必须重新申请人工接管。原厂动作分别对应 `Type=2/Command=22` 的 `MotionParam=1/4`，软急停为 `MotionParam=2`。
- 原厂手柄不经过本项目的 ROS 仲裁器，不能与网页遥控同时操作；需要切换到手柄时先结束网页接管并确认状态锁定。
- 本接口是运动控制面，在 VPN、身份认证和访问控制完成前不得经内网穿透直接暴露到公网。

### GET `/api/teleop/state`

读取遥控可用性、接管状态、仲裁模式、心跳年龄和限速。不返回当前会话 ID。`GET /api/state` 的 `teleoperation` 字段与此结构一致。

```json
{
  "ok": true,
  "teleoperation": {
    "available": true,
    "active": false,
    "acquiring": false,
    "status": "inactive",
    "mux_mode": "locked",
    "command_timeout_s": 0.35,
    "limits": {
      "forward_mps": 0.18,
      "reverse_mps": 0.12,
      "lateral_mps": 0.30,
      "angular_radps": 0.45
    }
  }
}
```

### POST `/api/teleop/acquire`

显式确认并申请人工接管。

```json
{"confirm": true}
```

成功后返回本操作端专用的 `session_id`。调用方必须立即开始发送指令心跳，不得将该 ID 持久化或转发给其他操作端。

```json
{
  "ok": true,
  "session_id": "teleop_xxx",
  "message": "已终止自主任务并进入人工接管"
}
```

### POST `/api/teleop/command`

三个轴都是 `[-1, 1]` 的归一化值，后端再按统一现场参数换算为实际速度。`sequence` 从 `0` 开始严格递增。

```json
{
  "session_id": "teleop_xxx",
  "sequence": 12,
  "linear_x": 1.0,
  "linear_y": 0.0,
  "angular_z": 0.0
}
```

停止但保持接管时发三轴全 `0`。不允许超范围、非有限数、无会话或无序号指令。

### POST `/api/teleop/release`

```json
{"session_id": "teleop_xxx"}
```

发布多个零速样本、结束会话并把仲裁器切到 `locked`。返回成功不代表恢复自主任务。

### POST `/api/teleop/emergency_stop`

无请求字段。停止当前任务、人工接管和所有网页运动指令，最终保持 `locked`。该接口可用于无法取得当前遥控会话 ID 时的安全停止。

### POST `/api/teleop/motion`

执行人工接管弹层中的运动状态动作。`stand`（起立）和 `lie`（趴下）必须携带当前遥控会话；两者执行前会结束遥控并锁定速度。`soft_stop`（软急停）不要求会话，可在无法取得会话 ID 时直接执行。

```json
{"action": "stand", "session_id": "teleop_xxx"}
```

```json
{"action": "soft_stop"}
```

### POST `/api/charge/one_key`

按当前有效地图的唯一 `manual_point_type=charge` 点位启动一键充电任务。没有充电点、存在多个充电点、当前任务运行中或网页遥控接管中都会拒绝；不会猜测充电桩坐标。

执行链路是固定的：先由当前 `dddmr_3d` 任务链导航到充电点；到点后任务进入
`phase=charging`，104 通过 `/m20pro/charge_command` 请求 TCP 桥下发原厂
`Type=1003/Command=1`，并强制使用 `PointInfo=3`；只有收到
`/m20pro_tcp_bridge/charge_result` 的 `status=accepted` 才将任务标记为完成。原厂拒绝、
TCP 超时或桥未就绪都会将任务标记为失败，不会把“已到点”伪装成“已充电”。

录包时应同时保留以下两个话题，用于核对请求和回执：

```text
/m20pro/charge_command
/m20pro_tcp_bridge/charge_result
```

当前 103 固件不提供可用的独立充电状态查询接口，因此 `accepted` 的含义是“原厂已接受充电导航命令”，不是软件伪造的“正在充电”。如果原厂回执包含 `Status`/`Value`，会原样保存在回执的 `vendor_status`/`vendor_value` 字段；电流方向只能通过 `/BATTERY_DATA` 辅助观察。

```json
{"ok": true, "charge_task_id": "task_xxx", "message": "已按当前地图充电点启动一键充电任务"}
```

### POST `/api/tasks/update`

修改任务名称。

```json
{"task_id": "task_xxx", "name": "新的任务名"}
```

### DELETE `/api/tasks?id=<task_id>`

删除任务。运行中的任务不能直接删除。

## 当前任务点和雷达联动

HTTP 前端读取：

```text
GET /api/state?debug=0
```

关注：

```text
active_task
active_waypoint.parsed
```

`active_waypoint.parsed` 核心结构：

```json
{
  "task_id": "task_xxx",
  "task_name": "日常巡检任务",
  "phase": "navigating",
  "index": 0,
  "remaining_dwell_s": 0,
  "distance_m": 1.2,
  "goal_pose": {"x": 1.0, "y": 2.0, "z": 0.0, "yaw": 0.0},
  "waypoint": {
    "id": "point_xxx",
    "label": "客厅P01",
    "room": "客厅",
    "scan_point": "P01",
    "result_file_prefix": "B03_U01_H2008_F20_客厅_P01",
    "manual_point_type": "task",
    "dwell_s": 5,
    "radar": {"enabled": true}
  }
}
```

跨楼层任务还应同时读取 `floor_switch_transaction`。`SWITCHING_MAP` 表示目标楼层的
三维资产和楼层上下文正在切换，`RELOCALIZING` 表示正在目标共享平台执行 2101，
`COMMITTED` 表示可以继续目标层出口导航，`FAILED` 表示当次任务已停止。连接边处于活动
状态时，入口和出口导航都由 `stair_executor` 独占；楼层上下文提前更新为目标层不会触发
任务主循环并发下发后续任务点。执行器 disabled/busy 或入口/出口导航立即失败时，状态
回执携带本次连接边身份并直接结束当次任务，不等待阶段总超时。

跨楼层接口当前只保留编排合同，尚未完成 v3 纯三维真机验收。前端不得把已保存路线或
历史二维切图实现解释为可用能力，也不得在三维资产切换和目标层重定位未验证前放行跨层任务。

当前不提供单独的切层“解锁”接口。失败后由操作员确认机器狗实际所在楼层，选择对应固定地图并重新执行一次 2101，然后重新启动任务。上一次 `FAILED` 记录不会永久锁住新任务。

ROS 2 功能包也可以订阅：

```text
/m20pro/active_waypoint
```

消息类型是 `std_msgs/String`，内容为同一份 JSON。昂锐雷达如果跑在 ROS 2 包里，推荐订阅这个 topic 获取当前点位名称、房间、扫描点和雷达模式。

## 重定位接口

### POST `/api/localization/initialpose`

发布网页重定位请求，并等待开发手册 2101/1 回执和原厂定位位姿更新。

```json
{
  "x": 1.0,
  "y": 2.0,
  "z": 0.0,
  "yaw": 1.57
}
```

正式前端不显示也不提交重定位楼层。后端从当前选中的固定地图取得楼层，并校验请求与地图身份一致。`floor` 仅为跨楼层内部事务和兼容调用保留；外部前端不得让操作者在重定位弹层中另选楼层。

成功判据：

```text
响应 confirmed == true
响应 localization_status.confirmed == true
随后 /api/state.localization_status.confirmed == true
随后 /api/state.map_relocalization_required == null
```

不要只看 HTTP 200，也不要只看 `initialpose_published`。这两个只能证明请求发出，不代表原厂定位真正成功。

## 自检接口

### GET `/api/preflight`

读取最近一次自检或正在运行的自检。

### POST `/api/preflight/run`

启动自检。

```json
{"mode": "move", "site": "auto", "wait": false}
```

说明：

- `wait=false`：后台执行，前端继续轮询 `/api/preflight`。
- `wait=true`：同步等待结果，容易阻塞前端，不建议高频使用。
- 电量只作为展示，不作为软件阻断条件。

## 录包接口

### GET `/api/recording/status`

返回当前录包进程、名称、开始时间和最新 bag 路径。

### POST `/api/recording/start`

```json
{"duration_s": 300, "prefix": "testfield"}
```

`duration_s` 限制为 10~3600 秒。后端调用正式 `m20pro_record_real.sh`，不使用 `ros2 bag record -a`。

### POST `/api/recording/stop`

向当前录包进程发送 `SIGINT`，等待 rosbag 完成落盘。

### GET `/api/recording/list`

读取 104 `/home/user/bags` 下的已保存录包。只列出直接子目录中的有效 rosbag 目录，按最近修改时间倒序返回；`size_bytes`、`message_count` 和 `duration_s` 用于前端展示。

### POST `/api/recording/rename`

修改录包目录名称，不改动包内 `metadata.yaml` 和数据文件。

```json
{"id": "testfield_20260722_113000", "name": "工地长距离测试"}
```

录包正在写入时不能改名；名称会经过路径安全清洗，不能包含目录分隔符。

### DELETE `/api/recording?id=<id>`

删除一个已保存录包目录。录包正在写入时拒绝删除，删除不可恢复。

### GET `/api/recording/download?id=<id>`

以流式 `tar.gz` 附件下载一个录包目录，避免将大包完整加载到 Web 进程内存。下载后解压得到以录包名称命名的目录，可直接交给 `ros2 bag info` 或 `ros2 bag play`。

## DDDMR 三维资产接口

这组接口负责 DDDMR 的三维资产清单、资产登记和 104 本机建图命令编排。v3 不把二维栅格或 106 地图包当成三维资产。

默认清单路径是 `/home/user/.m20pro_web/dddmr_map_assets.yaml`。前端只传楼层、资产路径和说明，后端负责校验文件、保存清单、读取状态话题，并按模板执行外部命令。

`dddmr_map_asset_server` 会按清单文件修改时间热重载资产；在真实启动里默认约 1 秒内就会看到登记后的资产生效，不需要重启 104。
场地试用时，如果当前地图目录里只有 `full_cloud.pcd`，前端可以先把它填到 `mapcloud/mapground` 做通路验证，正式交付再替换为验收后的 DDDMR 资产。

### GET `/api/dddmr/map_assets`

读取当前 DDDMR 三维资产清单、映射状态和命令模板状态。

返回核心字段：

| 字段 | 说明 |
| --- | --- |
| `manifest_path` | 清单文件路径 |
| `workspace` | 楼层资产工作区摘要 |
| `status` | `/m20pro/dddmr/map/status` 的最新状态 |
| `mapping` | `start/finish/cancel` 命令是否已配置 |

`status.provisional == true` 且 `status.source == "field_test_flat_map"` 时，表示
运行时正在使用临时平面 fallback。前端可以把它作为 DDDMR 短测门禁的一部分显示，
但必须标注“临时平面”，不得把它计入正式三维地图交付资产。

`workspace.floors` 中每个楼层记录至少包含：

`floor`、`label`、`note`、`source`、`mapcloud`、`mapground`、`mapcloud_count`、`mapground_count`、`ready`、`updated_at`

### POST `/api/dddmr/map_assets`

登记或更新一个楼层的三维资产。

```json
{
  "floor": "F20",
  "label": "F20",
  "note": "DDDMR 验收",
  "mapcloud": ["/home/user/m20pro_maps/F20/dddmr/mapcloud.pcd"],
  "mapground": ["/home/user/m20pro_maps/F20/dddmr/mapground.pcd"],
  "source": "web_dashboard"
}
```

要求：

- `floor` 必填；
- `mapcloud` 和 `mapground` 至少各有一个可读文件；
- 路径支持列表、逗号分隔字符串和多行文本；
- 仅登记已验收的 PCD 资产，不在这里做三维建图。

### POST `/api/dddmr/map_assets/delete`

删除一个楼层的三维资产登记。

```json
{"floor": "F20"}
```

### POST `/api/dddmr/mapping/start`

按后端命令模板启动 DDDMR 3D 建图步骤。当前 DDDMR `move` 轨道会默认把
`dddmr_mapping_host` 设为 `localhost`，并把 start/finish/cancel 接到 104 本机
`scripts/104_dddmr_mapping_control.sh`，不再把 DDDMR 建图错误下发到 106。

```json
{"floor": "F20", "mapcloud": ["/..."], "mapground": ["/..."]}
```

`finish` 和 `cancel` 的请求格式相同，只是调用不同的模板。

默认 start 命令使用 v4 的 104 原生 Foxy ARM Lightning mapping launch：
`ros2 launch m20pro_bringup m20pro_lightning_mapping.launch.py`，并固定 104 侧输入边界：

- 默认使用 104/106 之间的密云全字段 relay 话题 `/m20pro/lidar_points_dense_ros + /IMU`，配置为 `lightning_m20pro_raw_mapping.yaml`；它由 106 原生 DrDDS 读取原始雷达后转发到 104，避免 Lightning 直接订阅不稳定的跨主机 `/LIDAR/POINTS`。
- `/dddmr/edge_cloud -> /m20pro/lightning_points` 仍保留为显式 edge fallback；直接使用 `/LIDAR/POINTS` 只在明确验证 raw DDS 可达性时手动覆盖，不作为默认建图输入。

默认 finish 命令调用 `/lightning/save_map` 和 `/lightning/save_path`，并把 Lightning
保存到 `data/<map_id>/global.pcd` 的结果适配成 `map.pcd/ground.pcd/poses.pcd` 后归档到
`/root/lightning_maps`。命令输出中的 `archive_target` 是后续 DDDMR `pose_graph_dir`
或资产验收登记的来源。preview 轨道默认不配置这三条命令，前端会得到
`manual_required=true`，避免只读预览误触发 3D 建图运动。
如果 save service 返回成功但没有非空 `global.pcd`，后端脚本必须返回
`ok=false/code=lightning_global_map_missing`；如果 `global.pcd` 不能适配成前端三件套资产，
必须返回 `ok=false/code=lightning_asset_adaptation_failed`，不得把空 `archive_target`
当成保存成功；现场应查看 `save_log`/`asset_log` 并保留当前 mapping 进程重试或手工排查。

执行 start/finish 前，后端会实时调用状态命令。start 要求状态查询成功、
`package_available=true`、`source_cloud_available=true` 且当前不是 `running`；
finish 要求当前为 `running` 且 `save_service_available=true`。空闲状态不能误执行 finish。
`source_cloud_available=false` 表示激光雷达密集数据链（106 直通 → 104 socket 桥 →
`/m20pro/lidar_points_dense_ros`）未启动或无数据。自 2026-08-19 起这**不再是 start 的
硬拦截条件**：start 命令会无人值守自动拉起密集链（窗口 2h 兜底），建图想什么时候建就
什么时候建；仅当自动拉起也失败时，start 才以 `code=lightning_source_cloud_missing`
（脚本侧退出码 25）加具体 message 失败，前端直接展示该 message。finish/cancel 成功后
会立即停掉密集链，链的生命周期跟随建图会话。
判定依据是 `dddmr_dense_cloud_publisher` 的帧级心跳文件
`/tmp/m20pro_dense_cloud_publisher.heartbeat`（每次成功发布后更新，mtime 5s 内视为有
数据）；心跳文件不存在时才回退到一次性 DDS 订阅探测。心跳判定是瞬时操作，保证现场
高 CPU 负载下状态接口不超时。

### GET `/api/dddmr/mapping/status`

读取建图进程、运行包和保存服务状态。核心字段是 `state`、`package_available`、
`save_service_available`、`source_cloud_available`、`configured` 和 `ok`。空闲时保存
服务可以尚未出现，不影响环境检查通过；开始建图前必须确认运行包存在且
`source_cloud_available=true`（状态脚本会用真实订阅探测源话题是否有发布者和帧，
避免建图进程空转整场却采不到任何点云）。空闲且数据链缺失时脚本输出
`code=lightning_source_cloud_missing`。

模板占位符：

`{floor}`、`{label}`、`{note}`、`{manifest_path}`、`{manifest_dir}`、`{mapcloud}`、`{mapground}`、`{mapping_host}`、`{mapping_user}`

后端在把这些占位符写入 shell 命令前会统一做 `shlex.quote`；前端仍应把 `floor`、
`label` 和路径字段当作普通数据提交，不能自己拼 shell 命令。

如果对应模板为空，后端返回 `manual_required=true`，表示该步骤需要人工执行，不是失败。
若 104 没有 source 独立 Foxy ARM workspace，或其中没有 `lightning`，默认脚本会返回
`lightning_runtime_missing`；若 `m20pro_bringup` mapping launch 不存在则返回
`lightning_mapping_launch_missing`。前端必须把它显示成“Lightning runtime 未安装/未 source”，
不能显示为建图成功。

## 三维建图会话接口

正式前端使用 `/api/mapping/*` 维护项目、楼层步骤和建图会话；start/finish/cancel 在
后端执行同一组 DDDMR 命令模板。`/api/dddmr/mapping/*` 是不维护会话状态的底层接口。

### POST `/api/mapping/check_environment`

检查 start/finish/cancel/status 四个命令模板，并实时查询 DDDMR 运行包状态。状态命令
未配置、查询失败或 `package_available` 不为 true 时返回失败。建图尚未启动时不要求
保存服务已经出现。

### POST `/api/mapping/session`

创建建图会话。

```json
{
  "project_name": "M20Pro 工地巡检",
  "building": "3栋",
  "mode": "multi",
  "floors": ["7", "8", "9"],
  "map_name": "3栋现场图"
}
```

`mode` 取 `single` 或 `multi`。楼层可写数字、`F` 编号或地下层编号，例如 `7`、`F7`、`B1`；接口会统一保存为 `F7`、`B1`。`floors` 在多楼层模式下表示本次项目要建立的全部现场楼层，不表示机器狗当前实时楼层。正式前端不提交 `active_floor`，后端按 `floors` 顺序选择第一层作为初始步骤；API 自动化工具可以显式传入 `active_floor`，但必须属于 `floors`。后续步骤切换使用建图会话的逐层状态，不在创建表单重复选择。

`map_name` 可留空，后端会生成 `<active_floor>_<时间>` 形式的唯一名称。每次新的建图操作都必须创建新会话；正式前端只允许复用当前页面尚未结束的 `created/ready/pending/waiting_manual` 会话，不会从 `latest_mapping_session` 恢复已保存、已拉取或已取消的历史会话。

创建建图会话是登记新项目楼层的唯一入口，历史地图和点位不会反向创建楼层。登记楼层不会创建跨楼层路线，跨层任务仍要求使用前端按现场实测位姿显式配置有向连接边。

### POST `/api/mapping/start`

启动当前会话楼层的 DDDMR 三维建图。

```json
{"session_id": "session_xxx"}
```

启动前置条件：

- `created/ready/pending/waiting_manual` 会话可以启动；
- `mapping` 返回 `code=mapping_session_busy`，防止重复启动；
- `saved/imported/cancelled` 返回 `code=mapping_session_terminal`，调用方必须重新创建会话；
- 进度 UI 只能根据本次接口响应和本次会话状态推进，不能把历史会话终态渲染成新任务进度。

### POST `/api/mapping/finish`

保存并结束当前 DDDMR 三维建图。只有运行状态为 `running` 且保存服务可用时允许执行；
成功响应携带 `archive_target`，会话进入 `saved`。

```json
{"session_id": "session_xxx"}
```

### POST `/api/mapping/select_floor`

多楼层建图完成当前层后，切换会话的下一建图步骤。目标楼层必须属于会话 `floors`；会话处于 `mapping` 时拒绝切换。

```json
{"session_id": "session_xxx", "floor": "F8"}
```

响应返回更新后的 `session` 和当前 `step`。切换步骤不会自动启动建图；调用方仍需依次
调用 `/api/mapping/start` 和 `/api/mapping/finish`。保存目录是后续验收并产出
`mapcloud/mapground` 的来源，不会被当成二维地图自动导入。

### POST `/api/mapping/cancel`

取消建图。

```json
{"session_id": "session_xxx"}
```

### POST `/api/mapping/import_active_map`

历史兼容接口：把 106 地图包拉到 104 并生成旧式地图记录。v3 正式前端不调用该接口，
DDDMR finish 之后也不会自动触发它。

```json
{
  "session_id": "session_xxx",
  "floor": "F20",
  "map_name": "F20_test"
}
```

导入只归档，不自动启用。启用地图仍需调用 `/api/maps/select`。

存在建图会话时，后端按该会话的 `map_name` 查找 106 上最新的同名时间戳目录；不会因为 104 删除过同名地图就把旧会话重新当成新任务。`/api/maps` 删除只负责 104 业务地图库，如需清理 106 原厂包，必须另行确认 `/var/opt/robot/data/maps/active` 不指向目标目录后再精确删除。

## 跨楼层路线接口

跨楼层路线不是由项目楼层或地图名称自动推导的。每条路线必须绑定两张正式地图和四个实测语义点，并按方向保存；`F1 -> F2` 不会隐式生成 `F2 -> F1`。

路线和任务编排接口共用统一导航计划。单层任务是一个 floor segment，跨层任务在相邻 segment 之间引用一条有向路线。运动时只由 `/m20pro/stair_executor/start` 启动单一楼梯执行器；旧 `/m20pro/use_stairs` 入口保持停用，不能与新链并行。

### GET `/api/floor_routes`

返回已保存的有向路线、可用于路线配置的楼梯语义点和地图摘要。只有 `stair_entry`、`stair_switch`、`stair_exit` 且位姿有效的点会进入候选列表。

### POST `/api/floor_routes`

```json
{
  "name": "1层到2层东楼梯",
  "entry_annotation_id": "point_f1_entry",
  "source_platform_annotation_id": "point_f1_switch",
  "target_platform_annotation_id": "point_f2_switch",
  "post_exit_annotation_id": "point_f2_exit"
}
```

保存时后端强制检查两侧点位类型、楼层、地图和坐标一致，同一楼层的所有路线只能引用
同一张正式地图。当前后端仍可能检查历史 104 栅格 yaml 和 106 地图包；这是尚未移除的
兼容门禁，不代表 v3 跨楼层已经可用。v3 正式验收还必须为两层登记并验证各自的
`mapcloud/mapground` 三维资产。路线持久化到 Web `data_dir/floor_routes.json`；任务运行时
Web 将选中的完整有向连接边直接交给唯一 `stair_executor`。`floor_manager` 只接收当前地图
的楼层上下文，不加载路线表，也不把路线楼层作为普通地图白名单。

后端会为每条路线保存一个 `terrain_guard` 只读观测身份块，例如：

```json
{
  "profile_id": "floor_route_xxx:terrain",
  "corridor_version": "corridor-v1",
  "motion_policy": "stop_only",
  "certified_motion": false,
  "source": "106_local_pointcloud",
  "corridor": null
}
```

`corridor` 只有在现场标定完成后才填写 `width_m` 和 `lookahead_m`；缺失时表示未标定。
该块不携带或复制点云几何阈值，当前也不是跨层首轮执行的强制门禁。平地任务不经过该
字段，不改变 DDDMR 点云输入和导航链路。

### POST `/api/floor_routes/delete`

```json
{"id": "floor_route_xxx"}
```

路线被删除前，其地图和四个点位不能删除或修改。任务执行中禁止增删路线。

### 内部切层协议

该协议由单一 `stair_executor` 在到达共享平台并停车后触发。Web 核对当前任务、有向路线、
起始地图和目标地图；v3 的目标协议是切换目标层 `mapcloud/mapground` 与楼层上下文，再在
目标层平台执行 2101 重定位并确认结果。当前代码中的 104 Nav2 `load_map` 与 106
`drmap apply` 并行切图属于历史兼容实现，不是 v3 已验收链路。`terrain_guard` 状态不作为
首轮切层前置条件。事务回执继续携带 `request_id/route_id/plan_id/map_epoch`，仅用于防止
上一次请求的迟到结果推进当前任务。切图或重定位失败时停止楼梯运动和任务，不猜测已到达
目标层。

## YOLO 和视频接口

### YOLO 检测

HTTP 前端从 `/api/state.detections` 读取最近 YOLO 检测结果。该字段来自 ROS 2 topic：

```text
/m20pro_yolov8_inspection/detections
```

检测节点运行状态从 `/api/state.inspection_status` 读取。该字段来自 ROS 2 topic：

```text
/m20pro_yolov8_inspection/status
```

正式 104 进程默认以休眠态常驻，不加载 RKNN、不连接 RTSP。前端启停使用：

```http
POST /api/inspection/toggle
Content-Type: application/json

{"enabled":true}
```

Web 后端通过 `/m20pro_yolov8_inspection/set_enabled` 的 `std_srvs/SetBool` 服务控制节点。
启用时才加载 RKNN/NPU 并启动 RTSP 最新帧线程；关闭时释放 RKNN、摄像头和缓存帧，不重启
`m20pro-real.service` 或 DDDMR 导航链。

轻量检测刷新接口：

| 接口 | 说明 |
| --- | --- |
| `GET /api/inspection/state` | 只返回最近检测 JSON、YOLO 状态和启停服务状态；正式前端约每 200 ms 调用一次，仅在前摄像头和 YOLO 同时开启时调用 |

前端先打开 104 MediaMTX 的 WebRTC/WHEP H.264 视频（信令端口 `8889`），WebRTC/ICE 不可达时回退到 `8888` 的低延迟 HLS，再在视频卡片内启用 YOLO。检测框由浏览器 Canvas 叠加到同一条原始视频上。系统不再发布或提供第二路 ROS Image、JPEG 或 MJPEG 标注视频，避免重复编码和第二个播放器造成卡顿。

检测节点统一发布 JSON。当前支持的推理后端：

| 后端 | 用途 |
| --- | --- |
| `ultralytics` | 仅用于 x86_64 上位机模型基准与导出，不部署到 104 |
| `rknn` | 104 正式后端，使用 RK3588 NPU 按需推理 |
| `onnx` | 笔记本或 CPU 验证中间模型 |
| `dry_run` | 无模型或未安装依赖时发布空检测，接口保持不崩 |

典型检测 payload：

```json
{
  "camera": "front_wide",
  "source_type": "rtsp",
  "backend": "ultralytics",
  "model_path": ".../models/best_rk3588_fp16.rknn",
  "image_width": 1280,
  "image_height": 720,
  "count": 1,
  "detections": [
    {
      "class_id": 0,
      "class_name": "未戴安全帽",
      "confidence": 0.87,
      "bbox_xyxy": [100.0, 80.0, 240.0, 320.0],
      "bbox_xywh": [100.0, 80.0, 140.0, 240.0]
    }
  ]
}
```

接口化消费方式：

| 消费方 | 推荐读取方式 |
| --- | --- |
| 甲方前端 / 调试前端 | `GET /api/state?debug=0`，读取 `detections.parsed` |
| ROS 2 后端包 | 订阅 `/m20pro_yolov8_inspection/detections` 和 `/m20pro_yolov8_inspection/events` |
| 需要绑定房间/点位的检测结果 | 同时订阅 `/m20pro/active_waypoint`，用当前任务点的 `label/room/scan_point/result_file_prefix` 关联结果 |

因此 YOLO 模型、前端页面和任务执行互不写死：换 `.pt`、`.onnx`、`.rknn` 只改检测节点启动参数；前端和任务包继续读同一套 JSON。

典型状态 payload：

```json
{
  "enabled": true,
  "state": "ready",
  "camera": "front_wide",
  "source_type": "rtsp",
  "requested_backend": "auto",
  "backend": "ultralytics",
  "model_path": ".../models/best_rk3588_fp16.rknn",
  "model_loaded": true,
  "ready": true,
  "frame_count": 120,
  "inference_count": 120,
  "last_frame_age_s": 0.2,
  "last_inference_ms": 85.4,
  "last_detection_count": 1,
  "last_error": null
}
```

前端判断：`enabled=false` 表示进程休眠且资源已释放；`enabled=true && ready=true` 才表示模型、RTSP 和新鲜帧均就绪；`last_error` 非空时展示错误；具体识别结果仍以 `detections.parsed.detections` 为准。

启动方式：

```bash
ros2 launch m20pro_inspection m20pro_inspection.launch.py \
  enabled:=true \
  backend:=rknn \
  model_path:=/home/user/m20pro_real_ros2_ws/install/m20pro_inspection/share/m20pro_inspection/models/best_rk3588_fp16.rknn \
  class_names_path:=/home/user/m20pro_real_ros2_ws/install/m20pro_inspection/share/m20pro_inspection/models/labels_zh.txt
```

104 的正式节点只注入 `/home/user/m20pro_rknn_pydeps`，其中只有 RKNNLite；不再注入 Torch `PYTHONPATH`，也不再使用 `LD_PRELOAD=libgomp`。

当前 `best.pt` 的类别顺序为：未戴安全帽、未穿安全背心、跌倒、火灾、现场杂乱、配电箱打开。前端应展示 detection JSON 里的 `class_name`，不要在前端硬编码类别表。

全量 real 服务始终启动轻量控制节点，但默认 `enabled=false`，不会加载模型或占用摄像头/NPU。可由前端随时启停；若要求服务启动后直接推理，在 104 的 `/etc/default/m20pro-real` 中设置：

```text
M20PRO_ENABLE_INSPECTION=true
M20PRO_INSPECTION_BACKEND=rknn
M20PRO_INSPECTION_MODEL_PATH=/home/user/m20pro_real_ros2_ws/install/m20pro_inspection/share/m20pro_inspection/models/best_rk3588_fp16.rknn
M20PRO_INSPECTION_CLASS_NAMES_PATH=/home/user/m20pro_real_ros2_ws/install/m20pro_inspection/share/m20pro_inspection/models/labels_zh.txt
```

### 视频

| 接口 | 说明 |
| --- | --- |
| `http://10.21.31.104:8889/video1/` | 前相机 WebRTC 播放器测试页 |
| `http://10.21.31.104:8889/video2/` | 后相机 WebRTC 播放器测试页 |
| `http://10.21.31.104:8888/video1/` | 前相机 H.264 低延迟 HLS 回退 |
| `http://10.21.31.104:8888/video2/` | 后相机 H.264 低延迟 HLS 回退 |

`/camera/front.*` 与 `/camera/rear.*` 属于已停用的旧通用代理接口，正式原始视频优先走 8889 WebRTC/WHEP，8888 HLS 仅作回退。YOLO 不再提供 `/camera/yolo.*` 标注视频接口。

视频是否可用可检查：

```text
GET http://10.21.31.104:8888/video1/index.m3u8
GET http://10.21.31.104:8888/video2/index.m3u8
OPTIONS http://10.21.31.104:8889/video1/whep
OPTIONS http://10.21.31.104:8889/video2/whep
```

## 项目接口

### GET `/api/projects`

读取项目列表。

### POST `/api/projects`

创建项目。

```json
{"name": "M20Pro 工地巡检", "building": "3栋"}
```

## 推荐前端调用流程

### 页面启动

1. `GET /healthz`
2. `GET /api/state?debug=0`
3. `GET /api/maps`
4. `GET /api/annotations?map_id=live_map`
5. `GET /api/tasks?map_id=live_map`

### 切三维楼层地图

1. `POST /api/maps/select {"map_id":"<fixed_map_id>"}`
2. 刷新 `GET /api/state?debug=0`
3. 如果 `map_relocalization_required != null`，要求操作员重新重定位。

### 回到当前三维空间地图

1. `POST /api/maps/select {"map_id":""}`
2. 刷新 `GET /api/state?debug=0`
3. 继续用 `effective_map_id` 或 `map_id=live_map` 取点位/任务。

### 标点并生成任务

1. 确认 `effective_map_id` 非空。
2. 确认 `selected_map_status.ready == true`。
3. 点击地图得到 `pose`。
4. `POST /api/annotations` 保存点位。
5. `GET /api/annotations?map_id=live_map` 刷新点位。
6. `POST /api/tasks` 生成任务。

### 开始任务

1. `GET /api/state?debug=0`
2. 确认重定位和地图状态：
   - `localization_status.confirmed == true`
   - `map_relocalization_required == null`
   - `selected_map_status.ready == true`
3. `POST /api/tasks/start`
4. 轮询 `/api/state?debug=0` 显示：
   - `pose`
   - `path`
   - `active_task`
   - `active_waypoint.parsed`

## 稳定性边界

前端和外部包可以稳定依赖：

- 本文档列出的 URL、请求字段和核心响应字段；
- `effective_map_id` 作为点位/任务归属；
- `annotations[].label/room/scan_point/result_file_prefix/radar`;
- `tasks[].waypoints[]` 中的点位语义；
- `active_waypoint.parsed.waypoint` 的点位语义；
- `localization_status.confirmed` 作为重定位最终成功判断。

前端可以展示但不要当业务契约依赖：

- `events`;
- `topics`;
- `startup_map_sync` 的内部结构；
- `active_task` 的 timeline/诊断字段；
- 导航后端原始 status 字符串里的未文档字段。

## 维护规则

- 后端新增接口：先更新本文档，再给前端使用。
- 后端改字段含义：必须同步本文档、正式经典前端和合同测试；封存前端不再继续维护。
- 正式经典前端和甲方前端不要复制后端判断逻辑，尤其不要自己根据三维点云文件名推断当前楼层或资产身份。
- 导航、重定位、点位、任务相关行为以 104 API 返回为准，不以页面文字或 rosbag 外的临时脚本为准。
