# 104 双工作区

104 固定保留两个运行工作区：

| 模式 | 路径 | 运行边界 |
| --- | --- | --- |
| 2D | `/home/user/m20pro_2d_ros2_ws` | `/scan`、本地运动里程计、`slam_toolbox`；不启动 DDDMR、Lightning 或 3D 点云链 |
| 3D | `/home/user/m20pro_real_ros2_ws_v4` | Lightning 仅建图，官方 DDDMR 负责定位、感知、规划、避障和导航执行 |

2D 使用自己的源码包、install、build、log 和运行时 socket，不加载 3D 工作区中的
导航、云桥、描述或 DDDMR/Lightning 包。2D 的专用包为：

```text
m20pro_2d_description
m20pro_2d_navigation
m20pro_2d_cloud_bridge
m20pro_2d_bringup
```

2D 使用标准二维 TF：

```text
map -> odom -> m20pro_base_link
```

2D `/scan` 仍由 106 的 `m20pro_edge_scan` 提供；这是传感器输入边界，不是 2D
工作区对 3D 算法或前端的依赖。

## 首次创建 2D 工作区

以 `user` 身份执行：

```bash
cd /home/user/m20pro_real_ros2_ws_v4
./scripts/104_prepare_2d_workspace.sh
```

脚本会把 `src_2d` 下的四个专用包复制到目标工作区，然后独立构建；不会建立指向
3D `src` 的 symlink。修改 2D 源码后需要重新执行该脚本，3D 的 install 不会被
2D 构建覆盖。

## 切换

切换需要 root：

```bash
su
cd /home/user/m20pro_real_ros2_ws_v4
./scripts/104_switch_workspace.sh status
./scripts/104_switch_workspace.sh 2d
./scripts/104_switch_workspace.sh 3d
```

切换会停止当前 `m20pro-real.service`，写入新的 `/etc/default/m20pro-real`，
再启动目标工作区。2D 模式只启用 `m20pro-2d-motion-source.service` 和 2D
运行链，不启用 DDDMR edge-cloud 或 3D motion socket；3D 模式反向启用官方 DDDMR
输入链。两种模式不会同时运行。

最后一次选择会保存在 `/etc/default/m20pro-real`，机器狗重启后仍进入该模式，
不会自动跳回另一工作区。

## 2D 地图和 RViz

2D 工作区启动后，`slam_toolbox` 发布 `/map`，地图坐标系是 `map`。保存地图：

```bash
mkdir -p /home/user/m20pro_2d_maps
source /opt/robot/scripts/setup_ros2.sh
source /home/user/m20pro_2d_ros2_ws/install/setup.bash
ros2 run nav2_map_server map_saver_cli -f /home/user/m20pro_2d_maps/test_map
```

systemd 默认不开 RViz。需要桌面调试时，在停止 systemd 2D 实例后手工执行：

```bash
source /opt/robot/scripts/setup_ros2.sh
source /home/user/m20pro_2d_ros2_ws/install/setup.bash
ros2 launch m20pro_2d_bringup m20pro_2d_mapping.launch.py rviz:=true
```
