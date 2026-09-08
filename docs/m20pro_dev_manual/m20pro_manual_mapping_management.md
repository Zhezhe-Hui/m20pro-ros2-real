# 山猫M20开发指南（离线保存）

> 来源页面：建图与地图管理.html

- 
- 建图与地图管理

本文档介绍山猫 M20 机器人的完整建图流程与地图管理方法。本文功能仅 山猫 M20 Pro 支持，山猫 M20 标准版不支持相关指令。目录1. 建图概述2. drmap 命令速查3. 地图目录结构4. 地图管理5. 地图切换流程6. 第三方地图导入﻿﻿
# 1. 建图概述
建图模块运行在 NOS 上，通过 LiDAR + IMU 采集环境点云数据，生成三维点云地图和二维栅格地图。建图结果是后续定位和导航的基础。具体的建图操作步骤请参考：建图操作指南﻿﻿﻿
# 2. drmap 命令速查
| 命令 | 说明 |
|---|---|
| ﻿sudo drmap mapping﻿ | 开始建图（自动命名） |
| ﻿sudo drmap mapping -n ﻿ | 开始建图并指定地图名称 |
| ﻿sudo drmap mapping -s﻿ | 开始建图（RViz 实时可视化模式） |
| ﻿sudo drmap mapping -b﻿ | 开始建图（后台模式） |
| ﻿sudo drmap stop_mapping﻿ | 停止建图并保存地图 |
| ﻿drmap pack﻿ | 打包当前活动地图为 .zip 文件 |
| ﻿drmap unpack ﻿ | 导入地图包到系统 |
| ﻿sudo drmap apply ﻿ | 切换指定地图为活动地图 |打包后的地图包默认输出到 /home/user/Downloads/map-XXX.zip。﻿﻿
# 3. 地图目录结构
地图存放路径为 /var/opt/robot/data/maps/active（软链接），指向实际地图文件夹：复制代码91234567▶/var/opt/robot/data/maps/active → /var/opt/robot/data/maps/MAP_NAME├── full_cloud.pcd # 完整点云地图├── occ_grid.pgm # ID 为 0 的栅格地图├── occ_grid.yaml # ID 为 0 的栅格地图配置├── occ_grid_1.pgm # ID 为 1 的栅格地图├── ...└── occ_grid_id_map.toml # 栅格地图 ID 映射
### 栅格地图配置（occ_grid.yaml）
复制代码9123456▶image: /var/opt/robot/data/maps/active/occ_grid.pgmresolution: 0.1 # 像素物理长度 Res (m)origin: [-8.6, -11.2, 0.0] # 左下角坐标 [X0, Y0] (m)negate: 0occupied_thresh: 0.65free_thresh: 0.196
### 像素坐标与地图坐标换算
复制代码912▶xp = (PosX - X0) / Resyp = H - (PosY - Y0) / Res其中 xp、yp 为像素坐标，PosX、PosY 为地图坐标，H 为 pgm 图片高度（像素），其余参数参考 occ_grid.yaml 中的注释。在pgm图片的目录下执行：复制代码91▶file image.pgm输出image.pgm: Netpbm PGM image, 640 x 480，其中第二个数字就是高度H。﻿﻿
# 4. 地图管理
机器狗内部会保留已建过的所有地图，均存放在 /var/opt/robot/data/maps 目录下。每份地图为文件夹形式，命名规则为 自定义名称-日期时间。注意事项：●地图文件夹名称为重要信息，不建议随意更改，也请勿删除 active 软链接。●﻿occ_grid.yaml 第一行记录了 pgm 文件路径，如果地图文件夹名有修改，该路径也要相应更新。●受存储大小限制，建议通过 df -h 命令留意 /var/opt/robot/data 目录的磁盘空间，必要时手动删除无用的地图。﻿﻿
# 5. 地图切换流程
复制代码991234567891011▶# 1. 进入地图目录cd /var/opt/robot/data/maps
# 2. 切换活动地图sudo drmap apply MAP_NAME
# 3. 重启定位程序使新地图生效sudo systemctl restart localization.service
# 4.（可选）查看预加载进度sudo journalctl -fu localization若地图面积过大，定位服务需要时间预处理。持续打印表示加载中，不再打印且有 finish 字样表示预处理完成。﻿﻿
# 6. 第三方地图导入
以绝影 X30 地图导入 M20 为例：1. 导出 X30 地图在 X30 上进入 106 主机终端，执行：复制代码91▶sudo dr_map pack当前生效的地图会被压缩为 zip，默认保存至 /home/ysc/Downloads。2. 导入 M20将地图文件转移至 M20 的 106 主机 /home/user 下，执行：复制代码91▶sudo drmap unpack MAP_FILE_NAME.zip3. 文件重命名复制代码9123456789▶cd /var/opt/robot/data/maps/active
# 重命名地图文件sudo mv jueying.pcd full_cloud.pcdsudo mv jueying.pgm occ_grid.pgmsudo mv jueying.yaml occ_grid.yaml
# 如有 loc_map 文件夹则重命名为 blockssudo mv loc_map blocks # 没有此文件夹则跳过4. 修改配置文件使用文本编辑器修改 occ_grid.yaml 第一行路径为：复制代码91▶image: /var/opt/robot/data/maps/active/occ_grid.pgm﻿相关文档：软件使用指南﻿大纲建图与地图管理1. 建图概述2. drmap 命令速查3. 地图目录结构栅格地图配置（occ_grid.yaml）像素坐标与地图坐标换算4. 地图管理5. 地图切换流程6. 第三方地图导入