# 故障处置手册

## 先定位

```bash
python scripts/alasctl.py status          # 状态机 + 最近错误 + 错误快照目录
python scripts/alasctl.py errors --limit 3
python scripts/alasctl.py log --lines 100
```

错误现场在 `log/error/<毫秒时间戳>/`，每个目录含 1 张截图与一份 `log.txt`。
`log.txt` 只截取「最近一次任务横幅之后」的片段，不是全天日志。
截图已对玩家名/UID 打码，不要指望从中读出账号信息。

## 按日志特征分类

| 日志特征 | 含义 | 处置 |
|---|---|---|
| `GameStuckError: Wait too long` | 某个按钮/界面等不到，识别超时 | 先等 ALAS 自带 Restart；连续 3 次则看快照定位卡在哪一页 |
| `GameStuckError: Battle preparation not entering combat` | 战斗准备点不进去 | 常见于编队异常或网络抖动；等一次自愈，反复出现则检查舰队配置 |
| `GameTooManyClickError: Too many click for a button: LOGIN_GAME_UPDATE` | 游戏更新后的登录界面，ALAS 找不到预期按钮 | 需要人工更新游戏客户端；更新完 `start` 即可 |
| `GameTooManyClickError: ... BATTLE_PREPARATION` | 反复点战斗准备无响应 | 检查是否处于特殊活动机制；等自愈后观察 |
| `GameTooManyClickError: ... MAP_SWIPE_*` | 地图滑动异常 | 多为偶发；反复出现则换图或检查 `UseAutoSearch` |
| `An error has occurred in Azur Lane game client` | 游戏客户端自身报错 | ALAS 无法处理，需人工重启游戏/模拟器 |
| `Game page unknown` + `Starting from current page is not supported` | 启动时游戏停在 ALAS 不认识的界面，ALAS 会直接退出 | 见 `operations.md` 的 OP-001：截图确认卡在哪个弹窗，关掉再启动 |
| `Fleet composition error` | 舰队编成不符合要求 | 改 `<Task>.Fleet` 配置，或换一张不限制编成的图 |
| `OpsiCrossMonth` / 月度重置提示 | 大世界跨月，行动力与海域重置 | 正常流程，确认 `OpsiExplore` 在月初会跑 |
| `CRITICAL ... Request human takeover` | ALAS 放弃自动化 | 一律停止自动重启，读 `state/alert.json` 后人工判断 |
| `Task \`X\` failed 3 or more times` | 同一任务连续失败 3 次 | 同上，进程随后会 `exit(1)` |

## 处置顺序（从轻到重）

1. **等**：ALAS 自身对 `GameStuckError` / `GameTooManyClickError` 有重试与 Restart 机制。
   `status` 显示 `STUCK` 时先观察，不要立刻杀。
2. **调配置**：若是某个任务反复失败，把它 `task <Name> off` 或调整其参数（换图、改编队、放宽条件），
   让已过期的高优先级任务不再卡住队列。
3. **重启调度器**：`alasctl stop --force` 后 `alasctl start`。ALAS 启动会重新 Restart 游戏并回主界面。
4. **重启模拟器**：`adb` 层面不作为，需要用户手动重启雷电模拟器后再 `start`。
5. **人工**：`NEEDS_HUMAN` 一律交回用户。

## 什么情况必须问用户

- 状态为 `NEEDS_HUMAN` 且原因是不认识的错误。
- 需要重启模拟器（会打断用户其他操作）。
- 需要更新游戏客户端（`LOGIN_GAME_UPDATE`）。
- 需要消耗资源才能继续（钻石买行动力、抽卡、退役换石油）。
- 反复重启 3 次仍失败。

## 看门狗会自动做什么

`alaswatch.py` 每轮读取状态后：

- `DOWN` → 自动 `start`；10 分钟内最多 3 次，超限改为告警。
- `STUCK` → 先等 10 分钟自愈，超时才强制重启。
- `NEEDS_HUMAN` → 写 `state/alert.json`，**不再自动重启**，避免无限循环。
- `WAITING` / `RUNNING` / `CONFLICT` → 不动作。

看门狗的行为受 `process` 授权约束：未授权时它只能观察和告警。

## 排查用的只读命令

```bash
# 当前设备与前台应用（不干扰 ALAS）
adb -s <serial> devices
adb -s <serial> shell dumpsys window windows | findstr mCurrentFocus

# 是否有 ALAS 在控制游戏（MaaTouch 通道）
adb -s <serial> shell ps -A | findstr maatouch
```

禁止 `adb kill-server`、`adb connect/disconnect`、`adb shell input`——会打断 ALAS 的控制通道。
