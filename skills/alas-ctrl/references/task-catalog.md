# ALAS 任务目录

数据来源：`config/alas.json` 顶层条目、`module/config/argument/args.json` 的 `Scheduler.Enable.type`、
`module/config/config_manual.py` 的 `SCHEDULER_PRIORITY`、`module/config/i18n/zh-CN.json` 的中文名。
全部为只读生成，ALAS 升级后重新核对即可。

## 调度规则

- 任务是否被执行，只看两个字段：`Scheduler.Enable` 与 `Scheduler.NextRun`。
- `NextRun` 已过期且 `Enable` 为真的任务进入待执行队列，按下面的优先级链排序，第一个被执行。
- 优先级链没列到的任务**永远不会被调度**。
- `Enable` 为 `lock` / `state` 的任务，写 `false` 也会被 ALAS 强制改回 `true`。

## 优先级链与可禁用性（共 58 个可调度任务）

| 优先级 | 任务 | 中文 | Enable 类型 | 可否禁用 |
|---|---|---|---|---|
| 1 | `Restart` | 重启设置 | state | 否 |
| 2 | `OpsiCrossMonth` | 跨月每日 | checkbox | 是 |
| 3 | `Commission` | 委托 | lock | 否 |
| 4 | `Tactical` | 战术学院 | checkbox | 是 |
| 5 | `Research` | 科研 | lock | 否 |
| 6 | `Exercise` | 演习 | checkbox | 是 |
| 7 | `Dorm` | 后宅 | checkbox | 是 |
| 8 | `Meowfficer` | 指挥喵 | checkbox | 是 |
| 9 | `Guild` | 大舰队 | checkbox | 是 |
| 10 | `Gacha` | 每日抽卡 | checkbox | 是 |
| 11 | `Reward` | 收获 | lock | 否 |
| 12 | `ShopFrequent` | 通用商店 | checkbox | 是 |
| 13 | `EventShop` | 活动商店 | checkbox | 是 |
| 14 | `ShopOnce` | 其他商店 | checkbox | 是 |
| 15 | `Shipyard` | 开发船坞 | checkbox | 是 |
| 16 | `Freebies` | 白嫖奖励 | checkbox | 是 |
| 17 | `PrivateQuarters` | 宿舍计划 | checkbox | 是 |
| 18 | `OpsiExplore` | 每月开荒 | checkbox | 是 |
| 19 | `Minigame` | 小游戏 | checkbox | 是 |
| 20 | `Awaken` | 认知觉醒 | checkbox | 是 |
| 21 | `OpsiAshBeacon` | META作战 | checkbox | 是 |
| 22 | `OpsiDaily` | 大世界每日 | checkbox | 是 |
| 23 | `OpsiShop` | 大世界商店 | checkbox | 是 |
| 24 | `OpsiVoucher` | 兑换商店 | checkbox | 是 |
| 25 | `OpsiAbyssal` | 深渊海域 | checkbox | 是 |
| 26 | `OpsiStronghold` | 塞壬要塞 | checkbox | 是 |
| 27 | `OpsiObscure` | 隐秘海域 | checkbox | 是 |
| 28 | `OpsiArchive` | 档案坐标 | checkbox | 是 |
| 29 | `IslandFreebie` | 日常补给 | checkbox | 是 |
| 30 | `IslandCollect` | 资源采集 | checkbox | 是 |
| 31 | `IslandBusiness` | 店铺经营 | checkbox | 是 |
| 32 | `IslandSeasonTask` | 开发计划 | checkbox | 是 |
| 33 | `IslandOrder` | 岛屿订单 | checkbox | 是 |
| 34 | `IslandTransport` | 货运委托 | checkbox | 是 |
| 35 | `IslandProduction` | 岛屿生产 | checkbox | 是 |
| 36 | `Daily` | 每日任务 | checkbox | 是 |
| 37 | `Hard` | 困难图 | checkbox | 是 |
| 38 | `OpsiAshAssist` | META支援 | checkbox | 是 |
| 39 | `OpsiMonthBoss` | 月度Boss | checkbox | 是 |
| 41 | `EventSp` | 活动每日SP图 | checkbox | 是 |
| 42 | `EventA` | 活动每日A图 | checkbox | 是 |
| 43 | `EventB` | 活动每日B图 | checkbox | 是 |
| 44 | `EventC` | 活动每日C图 | checkbox | 是 |
| 45 | `EventD` | 活动每日D图 | checkbox | 是 |
| 46 | `RaidDaily` | 共斗活动每日 | checkbox | 是 |
| 47 | `CoalitionSp` | 怪谈纪实每日SP | checkbox | 是 |
| 48 | `WarArchives` | 作战档案 | checkbox | 是 |
| 50 | `Event` | 活动图 | checkbox | 是 |
| 51 | `Event2` | 活动图-2 | checkbox | 是 |
| 52 | `Raid` | 共斗活动 | checkbox | 是 |
| 53 | `Hospital` | 深谷来信 | checkbox | 是 |
| 54 | `Coalition` | 怪谈纪实 | checkbox | 是 |
| 55 | `Main` | 主线图 | checkbox | 是 |
| 56 | `Main2` | 主线图-2 | checkbox | 是 |
| 57 | `Main3` | 主线图-3 | checkbox | 是 |
| 58 | `OpsiMeowfficerFarming` | 短猫相接 | checkbox | 是 |
| 59 | `GemsFarming` | 刷紧急委托 | checkbox | 是 |
| 60 | `OpsiHazard1Leveling` | 侵蚀1练级 | checkbox | 是 |

## 不可调度的条目

以下 12 个顶层条目没有 `Scheduler` 组，是全局设置或工具页，属于其他任务的附属配置：

`Alas`、`General`、`EventGeneral`、`OpsiGeneral`、`IslandGeneral`、`Daemon`、`OpsiDaemon`、`EventStory`、`IslandProductionPlanner`、`Benchmark`、`AzurLaneUncensored`、`GameManager`

其中 `Daemon` / `OpsiDaemon` / `EventStory` / `IslandProductionPlanner` / `Benchmark` /
`AzurLaneUncensored` / `GameManager` 属于工具页功能，由 WebUI 单独唤起，不参与调度。

## 用法提示

- 要让某玩法跑起来，改它自己的 `Enable` 与 `NextRun`，不要伪造别的任务。
- 高优先级任务（`Restart`、`OpsiCrossMonth`、`Commission`、`Tactical`、`Research`）会抢占低优先级任务，
  所以「让 Main 立刻跑」不一定立刻开始，得看当时还有哪些更高优先级的任务过期。
- 大世界任务共用一个行动力池，`OpsiGeneral.OilLimit` 与 `OpsiGeneral.BuyActionPointLimit` 决定是否继续。
- 活动图（`Event*`、`Raid*`、`Coalition*`）的 `Campaign.Event` 由 ALAS 根据 `campaign/Readme.md` 自动生成候选，
  新活动上线后直接改这个字段即可，不要在别处硬编码活动代号。
