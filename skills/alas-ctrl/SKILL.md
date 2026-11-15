---
name: alas-ctrl
description: >-
  控制与监控本机的碧蓝航线自动化脚本 ALAS（AzurLaneAutoScript）：查询运行状态、启停调度器、
  调整任务开关与执行时间、修改运营设置、诊断卡死与人工接管、跑看门狗自愈。
  用户提到「碧蓝航线」「碧蓝」「ALAS」「AzurLane」「alas」「打理/肝/挂机碧蓝」「活动该不该打」
  「队伍怎么编」时触发。
  不适用于：其他游戏；修改 ALAS 自身源码或开发 ALAS 功能；需要真实游戏内点击的场景
  （本 skill 一律通过配置 ALAS 任务来驱动游戏，不自行点屏幕）。
---

# ALAS 控制与监控（alas-ctrl）

## 定位

**本 skill 是 ALAS 之上的决策与监控层，不是 ALAS 的替代品。**

ALAS 已经具备完整的游戏操作能力（刷图、大世界、委托、科研、活动、装备管理等 58 个任务）。
本 skill 只负责三件事：

1. **看**：读日志判状态、诊断故障。
2. **调**：把「要做什么」翻译成对 `config/alas.json` 的配置修改，交给 ALAS 执行。
3. **补**：做 ALAS 自己不做的决策——活动取舍、队伍编排、资源规划、周/月节奏。

**铁律**：任何能由 ALAS 完成的事，都通过配置 ALAS 任务实现，禁止用 adb 模拟点击二次实现。
需要某个玩法跑起来时，先问「哪个 ALAS 任务负责它」，再去改那个任务的配置。

## 前置检查

```bash
python scripts/alasctl.py doctor
```

必须全部正常才能继续：ALAS 根目录、`toolkit/python.exe`、`alas.py`、ADB 设备、配置序列号。
若 `doctor` 报「冲突」，说明有非本工具管理的 ALAS 实例在跑，先处理冲突，不要抢。

环境变量 `ALAS_ROOT` 可指定 ALAS 目录；不设则自动探测（cwd 向上、常见盘符）。

## 命令速查

| 命令 | 用途 |
|---|---|
| `doctor` | 环境体检（根目录/解释器/ADB/设备/进程/冲突） |
| `status [--json]` | 运行状态：状态机、当前任务、静默时长、界面、待执行队列 |
| `tasks [--json]` | 58 个可调度任务的启用状态、下次执行时间、调度优先级 |
| `log --lines N` | 最近日志（自动定位今日 `_alas.txt`） |
| `errors --limit N` | 最近的错误快照目录（含截图与现场日志） |
| `cfg get <Task.Group.Arg>` | 读设置项 |
| `cfg set <Task.Group.Arg> <value>` | 改设置项（会预判 ALAS 是否强制覆盖） |
| `task <Name> on\|off\|now\|at <时间>\|in <时长>` | 调整任务调度 |
| `start` | 启动 ALAS 调度进程（独立于 WebUI） |
| `stop [--force] [--timeout N]` | 停止（默认等任务间隙再杀） |
| `perm list\|check\|grant\|revoke\|reset` | 授权管理 |
| `watch --once [--dry-run]` | 看门狗单轮检查 |

常驻看门狗：`python scripts/alaswatch.py --interval 20`。

## 授权制度

按「手机应用权限」模型。执行前用 `perm check <类别>` 判断：

- `allow` / `allow_once` → 直接执行。
- `deny` → 拒绝，向用户说明。
- `ask` → **必须先向用户请求授权**，措辞：「需要授权：<类别>（<说明>），动作：<具体动作>。请回复：本次可行 / 同类操作可行 / 拒绝。」
  用户答复后用 `perm grant <类别> --once|--always|--deny` 记录，再继续。

| 类别 | 覆盖范围 | 默认 |
|---|---|---|
| `read` | 读状态/日志/配置 | 允许 |
| `process` | 启停 ALAS 进程 | 询问 |
| `schedule` | 改任务开关与执行时间 | 询问 |
| `settings` | 改运营设置（章节、油量、舰队等） | 询问 |
| `resource` | 消耗游戏资源（钻石/魔方/抽卡/退役/分解） | 拒绝 |

## 状态机

`status` 与看门狗共用一套判定，全部来自 `log/<date>_alas.txt`：

| 状态 | 判据 | 处置 |
|---|---|---|
| `RUNNING` | 有未闭合的 `Start task`，且 60s 内有新行 | 正常，别动 |
| `WAITING` | 最后是 `Wait until`（空闲可静默 5–11 分钟） | 正常，别动 |
| `STUCK` | 有任务在跑但 60s 无新行，或刚出 `GameStuckError`/`GameTooManyClickError` | 先等 ALAS 自愈（它自带 Restart），超 10 分钟再重启 |
| `NEEDS_HUMAN` | 出现 `Request human takeover` 或 `failed 3 or more times` | 停止自动重启，读 `state/alert.json`，人工判断 |
| `DOWN` | 无调度进程 | 可 `start` |
| `CONFLICT` | 有非本工具管理的 ALAS 实例（靠 MaaTouch 通道或外来进程识别） | 不介入 |

**日志文件必须锁定 `_alas.txt`**：`_gui.txt` 是 WebUI 主进程、`_-c.txt` 是 WebUI 子进程，
后者会打印 `Pending tasks`，拿来判状态会误报。

## 配置修改的四个坑（工具已内置拦截）

1. **`SuccessInterval` / `FailureInterval` / `ServerUpdate` / `Command` 写不进去**：`display=hide`，ALAS 读取时重置为默认值。`cfg set` 会直接拒绝。
2. **`Restart` / `Commission` / `Research` / `Reward` 的 `Enable` 关不掉**：类型为 `state`/`lock`，ALAS 每次读取都强制改回 `true`。`task off` 会直接拒绝。
3. **`NextRun` 超过上限会被钳成「现在」**：一般任务 24h、`Commission`/`Reward` 12h、`Research` 24h、`OpsiArchive` 7d、其余 Opsi 任务 31d。`task at/in` 超限时自动降级为立即执行并提示。
4. **自定义键会被丢弃**：ALAS 用 `args.json` 重建配置，不在 schema 里的键下次写盘时消失。`cfg set` 拒绝创建新键。

这些判断都通过只读 `module/config/argument/args.json` 的 `type`/`display` 字段得出，不依赖硬编码清单。
若 `args.json` 结构变化，`normalization_hint` 会返回 `None`（降级为不拦截），此时以 ALAS 实际行为为准。

## 典型工作流

### 看一眼现在在干什么

```bash
python scripts/alasctl.py status
python scripts/alasctl.py log --lines 40
```

### 让某个任务马上跑

```bash
python scripts/alasctl.py task Main now      # 立即（需 schedule 授权）
python scripts/alasctl.py task Main in 30m   # 30 分钟后
python scripts/alasctl.py task Main at "22:00"
```

注意是「插队标记」不是「抢占」：只有优先级高于当前任务时才会在下一个检查点抢占，
否则等当前任务自然结束。优先级链见 `references/task-catalog.md`。

### 出错了

```bash
python scripts/alasctl.py status      # 看状态与最近错误
python scripts/alasctl.py errors --limit 3
python scripts/alasctl.py log --lines 80
```

按 `references/failure-playbook.md` 的对照表处置。

### 启动 / 停止

```bash
python scripts/alasctl.py start
python scripts/alasctl.py stop          # 等任务间隙
python scripts/alasctl.py stop --force  # 立刻杀
```

与 WebUI 共存：WebUI 可以开着当看板，但**不要在 WebUI 里点启动**，
否则两个实例会抢同一个 ADB 设备。`start` 会自动检测并拒绝。

## 硬性禁止

- `adb kill-server` / `connect` / `disconnect`：会打断 ALAS 的 MaaTouch 持久连接。
- `adb shell input tap/swipe/keyevent`：与 MaaTouch 抢注入，导致页签错乱和 `GameStuckError`。
- 修改 ALAS 源码：升级会 `reset --hard` 覆盖，且违背本 skill 的稳健性目标。
- 用 `_gui.txt` / `_-c.txt` 判断任务状态。
- 仅凭日志 mtime 判停摆（空闲等待可静默 11 分钟）。

## 参考资料

| 文件 | 什么时候读 |
|---|---|
| `references/task-catalog.md` | 要知道 58 个任务的职责、优先级、锁定约束 |
| `references/config-rules.md` | 要改设置项，需要字段语义与取值来源 |
| `references/failure-playbook.md` | 状态是 `STUCK` / `NEEDS_HUMAN`，要对照处置 |
| `references/game-knowledge.md` | 要做活动取舍、队伍编排、资源规划等 L4 决策 |
