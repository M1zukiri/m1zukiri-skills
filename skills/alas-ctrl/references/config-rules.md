# 配置规则

## 结构

`config/alas.json` 是三层 JSON：**任务 → 组 → 参数**。

```jsonc
"Main": {
  "Scheduler": { "Enable": true, "NextRun": "2026-11-14 23:42:00", "Command": "Main", ... },
  "Campaign":  { "Name": "11-4", "Event": "campaign_main", "Mode": "normal", ... },
  "Fleet":     { "Fleet1": 1, "Fleet1Formation": "double_line", ... },
  "Storage":   { "Storage": {} }
}
```

- 配置路径的写法与 `cfg get/set` 一致：`Task.Group.Arg`，例如 `Main.Campaign.Name`。
- 架构上就是 70 个顶层条目，其中 58 个带 `Scheduler`（可调度），见 `task-catalog.md`。
- 每个任务的可用字段由 `module/config/argument/args.json` 定义，`alasctl` 用它判断字段是否可写。

## 生效时机

改完文件**不需要重启 ALAS**：

- ALAS 空闲等待下一个任务点时，每 5 秒检查一次文件 mtime，变化即重载。
- 任务执行中，每个战斗结算点会重读配置并重算队列；若下一个任务变了，当前任务会被中断。
- ALAS 自己写配置前会先重读磁盘，所以外部修改通常不会被吞掉。窗口是毫秒级，不要并发狂写。

## 四个会「写了也不生效」的坑

工具通过只读 `args.json` 的 `type` / `display` 自动拦截，无需记忆：

| 坑 | 判据 | 表现 |
|---|---|---|
| 隐藏字段 | `display=hide` 且 `type` 不是 `stored` | `cfg set` 拒绝，ALAS 读取时重置为默认值 |
| 锁定字段 | `type=lock` / `type=state` | `task off` 拒绝，ALAS 强制回到默认值 |
| 时间钳制 | `NextRun` 超过该任务上限 | `task at/in` 自动降级为立即执行并提示 |
| 自定义键 | 不在 `args.json` 里 | `cfg set` 拒绝，ALAS 写盘时会丢弃 |

`NextRun` 上限：

| 任务 | 上限 |
|---|---|
| `Commission`、`Reward` | 12 小时 |
| `Research` | 24 小时 |
| `OpsiArchive` | 7 天 |
| `OpsiExplore`、`OpsiCrossMonth`、`OpsiVoucher`、`OpsiMonthBoss`、`OpsiShop` | 31 天 |
| 其余任务 | 24 小时 |

## 常用设置项

字段语义与可选值来源：`module/config/argument/argument.yaml`；运行期实际候选值：`args.json`。

### 主线 / 活动打图

| 路径 | 说明 |
|---|---|
| `<Task>.Campaign.Name` | 打哪张图，自由文本。`11-4`、`D3`、`SP`、`T1` 等，解析见 `module/handler/fast_forward.py` |
| `<Task>.Campaign.Event` | 图集。主线写死 `campaign_main`；活动由 `campaign/Readme.md` 自动生成候选 |
| `<Task>.Campaign.Mode` | `normal` / `hard` |
| `<Task>.Campaign.Use2xBook` | 是否用双倍书 |
| `<Task>.Campaign.AmbushEvade` | 是否规避伏击 |
| `<Task>.StopCondition.OilLimit` | 油量低于此值停手 |
| `<Task>.StopCondition.RunCount` | 跑几轮，0 为不限 |
| `<Task>.StopCondition.MapAchievement` | `non_stop` / `100_percent_clear` / `map_3_stars` / `threat_safe` / `threat_safe_without_3_stars` |
| `<Task>.StopCondition.GetNewShip` | 捞到新船就停 |

### 舰队

| 路径 | 说明 |
|---|---|
| `<Task>.Fleet.Fleet1` / `Fleet2` | 用第几队 |
| `<Task>.Fleet.Fleet1Formation` | `line_ahead` / `double_line` / `diamond` |
| `<Task>.Fleet.Fleet1Mode` | `combat_auto` / `combat_manual` / `standby` |
| `<Task>.Fleet.FleetOrder` | 出击顺序，如 `fleet1_standby_fleet2_all` |
| `<Task>.Submarine.Mode` | `do_not_use` / `hunt_only` / `boss_only` / `hunt_and_boss` / `every_combat` |
| `<Task>.Emotion.Mode` | 心情计算模式，`calculate` 会按上次记录推算，避免红脸 |

### 每日运营

| 路径 | 说明 |
|---|---|
| `Commission.PresetFilter` | `cube` / `cube_24h` / `chip` / `chip_24h` / `oil` / `custom` |
| `Commission.CustomFilter` | 文本过滤器，`>` 分隔优先级，`-` 后缀为时长约束 |
| `Research.PresetFilter` | 科研项目预设，如 `series_9_blueprint_ta152` |
| `Research.UseCube` / `UseCoin` / `UsePart` | `always_use` / `only_05_hour` / `only_no_project` / `do_not_use` |
| `Dorm.Collect` / `Dorm.Feed` | 后宅收取与喂食 |
| `Exercise.OpponentChooseMode` | `max_exp` / `easiest` / `leftmost` / `easiest_else_exp` |
| `Hard.HardStage` | 困难图章节，如 `12-4` |
| `Gacha.UseTicket` / `UseDrill` | 每日抽卡是否用券/钻（用钻需 `resource` 授权） |
| `Reward.CollectOil` / `CollectCoin` / `CollectMission` / `CollectWeeklyMission` | 收获项 |

### 大世界

| 路径 | 说明 |
|---|---|
| `OpsiGeneral.OilLimit` | 大世界行动力下限 |
| `OpsiGeneral.BuyActionPointLimit` | 是否用油买行动力，0–5 |
| `OpsiGeneral.RepairThreshold` | 维修阈值 |
| `OpsiGeneral.AkashiShopFilter` | 明石商店过滤，如 `ActionPoint > PurpleCoins` |
| `OpsiFleet.Fleet` / `OpsiFleet.Submarine` | 大世界用队 |
| `OpsiExplore.SpecialRadar` / `ForceRun` / `LastZone` | 每月开荒的特殊雷达、强制执行、上次海域 |
| `OpsiShop.PresetFilter` | `max_benefit` / `max_benefit_meta` / `no_meta` / `all` / `custom` |
| `OpsiMonthBoss.Mode` | `normal` / `normal_hard` |
| `OpsiHazard1Leveling.TargetZone` | 侵蚀 1 练级目标海域（启用它会连带启用 `OpsiMeowfficerFarming`） |

### 活动

| 路径 | 说明 |
|---|---|
| `EventGeneral.PtLimit` | 活动点数上限，到点停止 |
| `EventGeneral.TimeLimit` | 活动截止时间，到点任务自杀 |
| `EventGeneral.TaskBalancer.Enable` | 是否在活动与主线之间自动平衡 |
| `EventGeneral.TaskBalancer.CoinLimit` | 物资低于此值时切回 `TaskCall` 指定的任务 |
| `EventA`–`EventD`.`EventDaily.StageFilter` | 活动每日图的关卡优先级过滤器 |

### 待机行为

| 路径 | 说明 |
|---|---|
| `Alas.Optimization.WhenTaskQueueEmpty` | 无任务可跑时干什么：`stay_there` / `goto_main` / `close_game` |
| `Alas.Optimization.TaskHoardingDuration` | 允许提前多少分钟执行待跑任务，0 为严格按时间 |
| `Alas.Optimization.ScreenshotInterval` | 截图间隔，ldopengl 下会被压到 0.2 |
| `Alas.Error.HandleError` | 任务失败后是否继续调度 |

## 修改配置的正确顺序

1. `alasctl cfg get <path>` 确认当前值与路径存在。
2. `alasctl cfg set <path> <value>`（会自动备份到 `state/backup/`，并预判 ALAS 是否强制覆盖）。
3. 需要 ALAS 立刻感知时，不要重启进程，等它下一个检查点即可。
4. 想回滚，从 `state/backup/` 取最近一份；或用 `cfg set` 写回旧值。

## 多实例

`config/<name>.json` 对应一个实例名。目前只有 `alas`。多开会争用同一个模拟器，
不要在没有第二台模拟器的情况下启用多实例。
