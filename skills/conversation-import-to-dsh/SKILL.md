---
name: conversation-import-to-dsh
description: >-
  把其他 Agent 应用里的历史对话（WorkBuddy / CodeBuddy 系，以及任何有本地事件流的 agent）
  重建为原生 DSH（DeepSeek Harness）会话：可读、可续聊、出现在 GUI 会话列表里。
  触发场景：想把 WorkBuddy/CodeBuddy/其他 agent 应用的对话记录搬进 DSH；网页分享链接只能导出最近 N 条、
  且首轮就是 assistant、引用着被切掉的用户提问；需要生成或移植 DSH 的 session.v4.jsonl.zstd 会话文件；
  导入后续聊报 `at least one tool must have defer_loading=false`；会话文件已就位但 GUI 列表里看不到。
  不适用于：只是普通聊天；只要把对话导出成 Markdown 档案、不涉及 DSH 会话文件；
  修改 DSH 自身源码或开发 DSH 功能。
---

# 对话导入 DSH

把**别的应用的对话日志**变成**DSH 原生会话**：一个 `session.v4.jsonl.zstd` 文件，
装进 `<DSH_HOME>/sessions` 并登记进 `workspace.json`，之后在 GUI 里能打开、能接着聊。

首个实证案例：一段 116 轮、8 小时 46 分的 WorkBuddy 对话，网页分享链接只保留最近约 100 轮
且首轮被截断；最终从本机日志恢复全量并成功导入。

全程只读源数据；只写 DSH 自己的数据目录。

## 三个必须先理解的机制

1. **分享链接不可信**。云端导出的 `conversation-data.json` 是分享页产物，只有最近约 100 轮，
   截断点落在 user/assistant 轮之间——首轮直接是 assistant 并引用前文。完整历史在本机 app 数据目录的
   jsonl 事件流里。
2. **`request/header` 必须内置 `tools` 基线**。不写，续聊第一句话就被服务端拒绝。
3. **第一个 surface 事件必须是 `system/message`**。不写，会话会在聊过一轮后变成自相矛盾的坏文件。

后两条的机制见「为什么必须带 tools 基线与 system 头」一节。不要靠试错绕过它们。

## 前置

- Python 3.8+；唯一第三方依赖 `zstandard`（`pip install zstandard`），其余标准库。
- Node ≥ 20（脚本只 import DSH 自带包，不需要 npm install）。
- 本机装好 DSH，且**至少有一个真实 DSH v4 会话**——工具基线与 system prompt 默认从它自动提取。
  刚装好 DSH、还没聊过的话，先在 GUI 里正常开一轮对话。
- 校验脚本按此顺序定位 DSH 包：`DSH_PKG_ROOT` → `dsh` 可执行文件所在的 npm 全局目录 → 桌面安装的
  `resources/app.asar.unpacked/dsh`。都找不到就设 `DSH_PKG_ROOT`，别去改脚本猜路径。
- `dsh_build.py` / `dsh_install.py` 支持 `--dsh-home`，可用临时目录做自测，不污染真实 `~/.dsh`。

## 产物一览

| 文件 | 阶段 | 说明 |
| --- | --- | --- |
| `norm.json` | 提取 | 归一化的 `rounds/items`，与 DSH 无关，可反复重生成 |
| `session.jsonl` | 生成 | 明文 Session v4；唯一的「事实源」，压缩和校验都以它为准 |
| `session.v4.jsonl.zstd` | 打包 | 安装产物；文件名必须带 `v4` |
| `<DSH_HOME>/storages/workspace.json.bak-<时间戳>` | 安装 | 每次登记前的备份，回滚用 |

中间产物放**独立目录**（比如 `./import/`），不要写进源 app 的数据目录，也不要写进 `<DSH_HOME>/sessions`。

## 0. 判断来源：这份数据完整吗

```powershell
python scripts/wb_scan.py
```

期望：`FOUND <n> conversation(s) under <root>`，以及一张列表：`conversationId`、消息条数、首末时间、
文件大小、首条用户输入的预览。
若报 `WARN: 未找到本地会话`，用 `--root` 明确指定 app 数据目录；`--json` 可拿结构化结果。

拿到候选后先做三个检查，再决定用哪个来源：

1. **首条是不是用户提问**。首轮就是 assistant、还在引用「上一轮」，说明头部被切了。
2. **时间跨度是否覆盖会话真正开始**。和 app 的 sqlite 元数据、或侧栏快照的 `lastActivityAt` 交叉验证。
3. **轮数 / 用户轮数是否明显偏少**。云端快照约 100 轮封顶，本地应严格更多。

结论只有两种：**换来源**（去本机数据目录拿 jsonl 事件流），或**接受截断并标注**。
不要试图从分享页「补」出头部内容——那是结构性丢失。

## 1. 提取：源 → 归一化 JSON

```powershell
python scripts/wb_extract.py <source> -o norm.json --verify <share.json>
```

`<source>` 可以是本机 `<conversationId>.jsonl`，也可以是云端的 `conversation-data.json`
（按扩展名/内容自动识别，必要时 `--kind local|share` 强制）。

期望输出（关键行）：

```
source: local <path>
rounds=<轮数> user=<n> assistant=<n> system=<n>
items=<总条数> text=<n> reasoning=<n> tool-call=<n> tool-result=<n>
VERIFY zero-loss: source=<n> -> items=<n> OK
out=norm.json (<字节> B)
OK
```

- `--verify` 做零丢失核算（源记录 → 输出条目），带 `<share.json>` 时额外与云端交叉核对轮数/条目数；
  `VERIFY source:` 列每类源记录的条数，`interrupted=` 是被过滤掉的 `Interrupted by user` 占位轮数；
  报 `MISMATCH` 时先修提取，不要往下走。
- 源是分享页时会提示 `云端分享页只保留最近约 99 轮且首轮被截断`。
- 归一化结构是 `rounds[] / items[]`，字段映射与八个已知坑见
  [workbuddy-local-data.md](references/workbuddy-local-data.md)。换应用时先读那一份再改脚本。

## 2. 生成：归一化 JSON → Session v4

```powershell
python scripts/dsh_build.py norm.json -o session.jsonl --cwd "D:\Work\MyProject" --title "导入对话"
```

- `--cwd` **必填**，必须是绝对路径，且要与目标 workspace 的 `path` 一致（否则 GUI 列表里不显示）。
  不确定就打开 `<DSH_HOME>/storages/workspace.json` 看 `tables.workspaces[*].path`，或直接用 GUI 里显示的路径。
- 工具基线 / system prompt 默认自动提取（扫 `<DSH_HOME>/sessions/*/*/session.v4.jsonl.zstd` 按 mtime
  取最新真实会话）。要指定时用 `--tools-file` / `--system-file`。
- `--agent-preset` 默认留空。**不要随手填**：填了目标部署不存在的 preset，会话会「列表可见但打不开」。
- 本 skill 默认只导纯文本对话，工具调用留在归档产物里；生成时 `dropped_items` 会报告丢弃条数。

期望输出：

```
tools=<n> (source: <...>/session.v4.jsonl.zstd)
system_prompt=<n> chars (source: <...>/session.v4.jsonl.zstd)
turns=<n> events=<n> prose_chars=<n>
dropped_items reasoning=<n> tool-call=<n> tool-result=<n>
session_id=session-<uuid> cwd=D:\Work\MyProject   out=session.jsonl (<字节> B)
```

报「未找到可用的工具基线」= 本机没有真实 v4 会话，或 DSH 目录没猜对：先用 `--dsh-home` 指一下，
或在本机跑一轮真实对话。

## 3. 校验：格式、字节、工具、续聊

```powershell
node scripts/dsh_validate.mjs session.jsonl --canonical
node scripts/dsh_verify_tools.mjs session.jsonl
node scripts/dsh_verify_tools.mjs session.jsonl --simulate-resume
```

期望依次出现（都是 exit 0）：`VALID: id=<id> version=v4 events=<n> inherited=0` 与
`CANONICAL: every row byte-identical to DSH encoder output`；`history.tools=<n> history.updates=0`、
`next_turn_tools=<n> next_turn_deferred=0` 与
`PASS: 下一轮至少有 1 个可用工具，defer_loading=true 的数量为 0`；最后 `RESUME VALID: events=<n> turn=<n>`
（模拟 DSH 在文件尾追加一轮事件后，整份文件仍通过校验）。

三条全过再进下一步。失败按现象查 [troubleshooting.md](references/troubleshooting.md)。

## 4. 打包：明文 JSONL → 多帧 zstd

```powershell
python scripts/dsh_pack.py compress session.jsonl session.v4.jsonl.zstd
```

期望：`in <字节> bytes -> out <字节> bytes, frames=<n>, first frame header 28b52ffd0458`（帧数随 `--batch` 与事件数变化）。

`dsh_pack.py info <file.zstd>` 应显示 `checksummed: True  fcs-present: False`。
`fcs-present: True` 说明用了非流式压缩——DSH 还能读，但不再是逐字节复刻的形态。

## 5. 安装：放进 sessions 并登记 workspace

**先关闭 DSH。** GUI 的 workspace 注册表是启动时读进内存、变更时整体回写的，运行中改会被覆盖。

```powershell
python scripts/dsh_install.py --session session.v4.jsonl.zstd --dry-run   # 先看计划
python scripts/dsh_install.py --session session.v4.jsonl.zstd
```

期望输出（缩略，实际每项单独一行）：

```
projectKey: --D-Work-MyProject--
session_id: session-<uuid>   cwd: D:\Work\MyProject
session file: <DSH_HOME>/sessions/--D-Work-MyProject--/session-<uuid>/session.v4.jsonl.zstd (139976 B)
workspace: <uuid> -> sessionIds[0]=session-<uuid>
backup: <DSH_HOME>/storages/workspace.json.bak-<时间戳>
```

- 幂等：文件与登记都在 → `已安装且已在 workspace <uuid> 入账，跳过（幂等）`；文件在、登记丢了
  （DSH 退出时整体回写注册表很常见）→ 不覆盖文件，只补登记，输出 `会话文件已存在，跳过复制、只补登记`。
  所以本脚本可以随时重跑修登记，不会破坏已装好的会话。
- `--session` 也接受明文 `.jsonl`，脚本会先压缩再落位；`--dry-run` 只打印计划。
- 没有 `path` 匹配 `cwd` 的 workspace 时 exit 2：先在 GUI 里为该项目建 workspace，或把 `--cwd`
  指到已有 workspace 的路径。
- 每次改写 `workspace.json` 前自动备份 `.bak-<时间戳>`；回滚就是还原这个备份 + 删除会话目录。

## 6. 验证：真的能开轮

重新打开 DSH，在对应项目的会话列表里找到新会话（标题带「导入」后缀），打开并**发一句话**。
这一步是唯一能同时证伪「tools 基线」与「system 头」两个问题的测试。

## 为什么必须带 tools 基线与 system 头

这两件事都不是「格式洁癖」，而是 deepseek 路由的行为约束。症状都是**文件看起来正常，用起来失败**，
所以必须一次做对。

### tools 基线：否则续聊第一句就被拒

deepseek 路由的工具更新模式是 `toolUpdate: "addition-only"`（`dsh-llm-deepseek` 的模型目录项）。DSH 在折叠工具历史时（`dsh-llm` 的 `projectToolUpdates` /
`toolDeclarations`）只把 `request/header.header.tools` 里的工具当作「基线内、已可用」；
后续 `developer/message` 里出现的 `tool-addition` 才会被标成 `deferLoading: true`（延迟加载）。

于是：**基线为空 → 当前全部工具都被当成「新增」→ 每一个都 `deferLoading: true` 发出**，
服务端拿到「没有任何一个工具是 immediately available」的请求，直接报：

```
tools: at least one tool must have defer_loading=false
```

故障现象：会话能打开、历史能显示，一点发送就失败。修法就是把本部署真实会话的 tools 快照写进
第一个 `request/header.header.tools`（`dsh_build.py` 自动做，`dsh_verify_tools.mjs` 负责证明）。

注意基线必须是**本机当前构建**的工具表：换机器、换插件集，工具名与 schema 都会变。

### system 头：否则聊一轮后文件坏掉

deepseek 只认 `systemPromptUpdate: "in-history"`——system prompt 以历史里的 `system/message` 形式下发。
DSH 的 `SystemPromptProjection.project` 在历史里找不到 system 节点时（`head === undefined`），
返回的是 `surfaceOp: "append"`，也就是**把新的 system 消息追加到历史中间**。

而格式校验规定：`system/message` 出现在 surface 已非空、且 protectedHead 尚未置位的位置时报
`system/message requires a protected first surface head`。protectedHead 只在「surface 还空着时遇到
第一个 `system/message`」才置位。

两条规则叠加的结果：没有头部 system 节点的会话，**聊过一轮之后就会写出一个自相矛盾的文件**，
然后再也读不出来。故障现象可能是「第一版能读、聊完打不开」，也可能是「一开始就打不开」。

修法：生成时把本部署渲染好的 system prompt 快照写成**第一个 surface 事件**。校验器不检查文本内容，
但文本不对会让续聊行为与原生会话不一致，所以还是用真实快照。

## 验证清单

按顺序跑，任何一条不过都不要继续：

1. `node scripts/dsh_validate.mjs session.jsonl --canonical` → `VALID` + `CANONICAL`
2. `node scripts/dsh_verify_tools.mjs session.jsonl` → `PASS`，`defer_loading=true` 计数为 0
3. `node scripts/dsh_verify_tools.mjs session.jsonl --simulate-resume` → `RESUME VALID`
4. 关闭 DSH → `dsh_install.py` → 重新打开 → 会话列表里出现该会话，标题/项目归属正确
5. 打开它，**发一句话**：不报 `defer_loading` 错、不报 protected head 错、模型正常回一轮

第 4、5 步之前的那三条是「不花 token 的回归」，每次改生成逻辑后都重跑。

## 不该做的事

- **不要从分享页补头部**。缺的那段不在云端，补不出来。换来源。
- **不要手改 `workspace.json` 而不备份**，也不要在 DSH 运行时改。
- **不要为了「能跑」删掉 system 头或 tools 基线**。那样只是把故障从「导入时」推迟到「续聊时」。
- **不要动源 app 的数据目录**。全程只读；sqlite 用 `mode=ro`。
- **不要用自造的事件类型**。核心词表外的类型必须带 `ignorable: true`，而那会让本该保留的事件被静默丢弃。

## 一条龙命令

```powershell
python scripts/wb_extract.py <conversationId>.jsonl -o import\norm.json --verify <share.json>
python scripts/dsh_build.py import\norm.json -o import\session.jsonl --cwd "D:\Work\MyProject"
node  scripts/dsh_validate.mjs import\session.jsonl --canonical
node  scripts/dsh_verify_tools.mjs import\session.jsonl --simulate-resume
python scripts/dsh_pack.py compress import\session.jsonl import\session.v4.jsonl.zstd
python scripts/dsh_install.py --session import\session.v4.jsonl.zstd   # 先关闭 DSH
```

## references 什么时候读

| 文件 | 何时读 |
| --- | --- |
| [dsh-session-v4.md](references/dsh-session-v4.md) | 要手写/改造会话文件、改生成脚本的字段选择、报格式或解码错误、需要弄清 header/事件/语义规则/GUI 入账条件时 |
| [workbuddy-local-data.md](references/workbuddy-local-data.md) | 换应用或换数据来源、判断一份数据是否完整、要核对字段映射、踩到时间戳/压缩摘要/工具配对这些坑时 |
| [troubleshooting.md](references/troubleshooting.md) | 任何一步报错或行为不符预期时，先按现象查这里再动代码 |
