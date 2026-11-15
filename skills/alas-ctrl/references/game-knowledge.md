# 游戏侧决策知识（L4）

这一层负责 ALAS 不做的判断：**打什么、什么时候打、资源往哪投、队伍怎么配**。
ALAS 只执行被配置的任务，取舍要靠这里。

> 注意：游戏版本会变（新章节、新科研、新活动机制）。本文件只固化**稳定原则**与**决策流程**，
> 涉及具体数值、地图收益、当期活动规则时，必须现场核实，不要凭记忆下结论。

## 决策前先查三件事

1. **ALAS 现状**：`alasctl status` + `alasctl tasks`，确认哪些任务启用、哪些已过期。
2. **资源存量**：石油、物资、钻石、魔方、行动力。ALAS 日志会打印部分（`[OCR_OIL]`、`[OCR_COIN]`），
   也可用 `alasctl log --lines 200` 检索；看不到就截图或问用户。
3. **时间约束**：活动截止（`EventGeneral.TimeLimit`）、每月大世界重置、周常刷新。

## 稳定原则

### 资源分级

| 资源 | 性质 | 决策 |
|---|---|---|
| 石油 | 自然恢复，有上限 | 优先消耗，别让它溢出。`StopCondition.OilLimit` 用来留余量 |
| 物资 | 可刷，但科研与改造消耗大 | 科研连续消耗时要留底；`TaskBalancer.CoinLimit` 是自动切换的保护线 |
| 魔方 | 稀缺，科研专用 | 由 `Research.UseCube` 控制严格程度，改动属 `settings` 授权 |
| 钻石 | 基本不可再生 | 任何消耗一律 `resource` 授权，默认拒绝 |
| 行动力（大世界） | 每月重置 | 月初优先开荒，月末清空 |

### 任务不可协商项

`Restart`、`Commission`、`Research`、`Reward` 无法禁用，它们保证基础运转。不要把「停掉全部任务」当作暂停手段。

### 优先级永远是 ALAS 的调度链

配置只能改 `Enable` 与 `NextRun`，谁先跑由 ALAS 的优先级链决定（见 `task-catalog.md`）。
所以「让某个任务马上跑」的实际效果是「把它标成待执行」，能否抢占取决于当时队列。

### 心情与红脸

长时间刷同一队会红脸掉好感。`<Task>.Emotion.Mode` 设为 `calculate` 时 ALAS 会按上次记录推算，
配合 `Fleet1Control` / `Fleet2Control` 换队或进后宅。跨天连续挂机时优先保心情，其次才是效率。

### 大世界行动力

`OpsiGeneral.OilLimit` 是行动力下限，`BuyActionPointLimit` 决定是否用油买行动力。
月末临近重置时，宁可买满也不要浪费。跨月当天会跑 `OpsiCrossMonth`。

## 活动如何处理

活动上线后，ALAS 的 `Event*` 任务默认是关闭的，需要主动配置。流程：

1. 确认活动类型：限时推图（`Event`）、每日图（`EventA`–`EventD`、`EventSp`）、
   共斗（`Raid`/`RaidDaily`）、怪谈（`Coalition`/`CoalitionSp`）、深谷来信（`Hospital`）、作战档案（`WarArchives`）。
2. 设 `<Task>.Campaign.Event` 为当期活动图集（候选由 ALAS 自动维护，不要手写代号）。
3. 设 `<Task>.Campaign.Name` 为目标关卡。
4. 设 `EventGeneral.PtLimit` / `EventGeneral.TimeLimit` 控制停止条件。
5. 活动与主线并存时，用 `EventGeneral.TaskBalancer.Enable` 让 ALAS 在物资不足时自动回落主线。

**判断要不要打活动**，看三件事：限定获取物（船/装备/图纸）是否已拿到、活动剩余时间、
主线当前目标是否更紧急。这三项需要问用户或看游戏内公告，不要自己拍板。

## 队伍编排

ALAS 的舰队配置只有「用第几队、什么阵型、什么模式」，没有「上哪几艘船」。
换船必须在游戏内做（`Main.GotoFleet` 只做跳转）。可做的事：

- 改 `<Task>.Fleet.Fleet1/2` 决定用哪套预设队。
- 改 `Fleet1Formation`（`line_ahead` / `double_line` / `diamond`）适配敌方阵容。
- 改 `Submarine.Mode` 决定潜艇是否出击、何时呼叫。
- 改 `HpControl.*` 控制残血撤退与紧急维修。

需要真正换船时：这是 `resource` 之外的「游戏内操作」，本 skill 不做，交给用户在游戏里完成，
或者由 ALAS 的 `GemsFarming` / `Research` / `Awaken` 等任务间接推进。

## 常见规划模式

| 场景 | 配置 |
|---|---|
| 日常挂机 | 保持默认：Commission / Research / Tactical / Dorm / Exercise / Daily / Hard 全开 |
| 冲主线进度 | `Main.Campaign.Name` 设目标图，`StopCondition.OilLimit` 留足余量，关掉耗油活动 |
| 活动期 | 开对应 `Event*`，设 `PtLimit`/`TimeLimit`，`TaskBalancer` 保物资 |
| 大世界月末 | `OpsiGeneral.BuyActionPointLimit` 提高，清 `OpsiObscure`/`OpsiAbyssal`/`OpsiStronghold` |
| 科研攒蓝图 | 调 `Research.PresetFilter` 与 `UseCube`，属 `settings` 授权 |
| 想暂停 | 没有「暂停全部」的配置手段；只能 `alasctl stop` 杀进程 |

## 授权触点

做下面这些决定前必须先拿授权：

- 任何消耗钻石、魔方、抽卡券的动作 → `resource`。
- 改打图章节、油量阈值、科研/委托过滤器、舰队配置 → `settings`。
- 启停调度器 → `process`。
- 改任务开关与时间 → `schedule`。

授权按类别记忆，用户说「同类操作可行」后就长期有效，直到用户撤销。
