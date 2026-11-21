---
name: contexts/agent-workspace
inline-when:
  any:
    - project-flag: agent-workspace
last-verified: 2026-11-21
---

# contexts/agent-workspace

**适用**：OpenClaw / Autoclaw 一类常驻 Agent 工作区 —— 没有代码仓库，状态靠文件续命，
产出是对话、记忆与轻量交付物。
**不适用**：有代码与构建产物的工程项目。

**来源**：OpenClaw 工作区模板（会话启动、记忆、心跳、群聊纪律）。这份模板目前来自上游，
不是从多个项目各自沉淀的，条款按「上游约定」对待，改之前确认是否仍适用于当前运行时。

<!-- anchor: session-start -->
## 会话启动

按固定顺序读，不要跳：

1. `SOUL.md` —— 人格与语气。
2. `USER.md` —— 用户偏好与背景。
3. `memory/YYYY-MM-DD.md` —— 今天与昨天。
4. `MEMORY.md` —— **只在主会话读**；群聊等共享上下文不加载（这是安全措施，不是性能优化）。

<!-- anchor: memory-layers -->
## 记忆分层

- 每日原始日志写 `memory/YYYY-MM-DD.md`，不删不改写。
- 长期记忆写 `MEMORY.md`，只放稳定结论与偏好，不放过程。
- 识别到偏好立即写 `USER.md` / `MEMORY.md`，不要等用户说「记住」。
- 记忆是唯一跨会话状态：**重要结论不写进记忆，等于没发生过。**

<!-- anchor: heartbeat-schedule -->
## 心跳与定时

- 心跳按固定轮转检查清单（`HEARTBEAT.md` 可选）；没有新信息时静默，不发「无更新」。
- 心跳与 Cron 分工：周期性巡检用心跳，定时定点用 Cron。不用 `crontab` 做项目级定时
  （那是机器级配置），用项目自己的 cron 入口。
- 深夜静默窗口内不主动联系，除非用户明确要求。
- 心跳状态写 `memory/heartbeat-state.json`，避免重复提醒。

<!-- anchor: proactive-work -->
## 主动工作

无需授权即可做：整理记忆、查项目状态、更新文档、提交自己的改动。
需要授权才能做：对外发送消息、修改用户配置、执行破坏性操作。

<!-- anchor: group-chat -->
## 群聊纪律

- 只在被点名、被直接问到、或确有新信息时发言；否则保持静默（`HEARTBEAT_OK`）。
- 不连发（避免 triple-tap）；需要补充时合并成一条。
- 表情回应用于轻量确认，不替代实质答复。

<!-- anchor: first-run -->
## 首次运行

`BOOTSTRAP.md` 存在时按其自举，完成后删除。自举不是长期流程。
