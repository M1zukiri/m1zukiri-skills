# 排障手册

按「现象」查。每条给出：**判据 → 根因 → 修法 → 复验**。
命令都在 skill 根目录执行，脚本路径为 `scripts/...`，`<D>` 指 `<DSH_HOME>`（默认 `~/.dsh`）。

## 分诊表

| 现象 | 先看哪里 | 章节 |
| --- | --- | --- |
| 续聊一句话就报 `tools: at least one tool must have defer_loading=false` | `dsh_verify_tools.mjs` | A |
| 会话打不开 / 打开就报 `system/message requires a protected first surface head` | 文件里第 0 个 surface 事件 | B |
| GUI 列表里根本没有这个会话 | `dsh_install.py` 输出 + `workspace.json` | C |
| 列表里有，点开报错或续聊失败 | header 的 `agentPreset` | D |
| 文件解码就失败 | `dsh_validate.mjs` 的报错 | E |
| 能打开，但轮次/顺序/内容不对 | 归一化 JSON 的 `rounds` | F |
| 轮数明显偏少、首轮是 assistant | 提取阶段 | G |
| 工具调用缺失、错位、重复 | `callId` 配对 | H |

## A. 续聊报 `at least one tool must have defer_loading=false`

**判据**：会话能打开、能显示历史，但发第一句话时服务端拒绝，错误原文含
`tools: at least one tool must have defer_loading=false`。

**根因**：第一个 `request/header` 里没有 `tools` 基线。deepseek 路由的 `toolUpdate` 模式是
`addition-only`（`dsh-llm-deepseek` 的模型目录项），折叠工具历史时只认 request header 里的工具表；
基线为空 → DSH 把当前全部工具当成「新增」，逐个 `deferLoading: true` 发出 → 服务端拒绝。

**修法**：把**本部署一份真实会话**的 tools 快照写进第一个 `request/header.header.tools`，重新生成会话。

```powershell
node scripts/dsh_verify_tools.mjs <session.jsonl>
# expect: history.tools=37 history.updates=0 baseline_deferred=0
#         next_turn_tools=37 next_turn_deferred=0
#         PASS: at least one usable tool, defer_loading=true count = 0
```

默认直接读该会话 `request/header.header.tools`，只有要验证「基线换成另一份工具表会怎样」时才加
`--tools-file`。

快照必须是**本机当前真实会话**里的工具表（不是抄别人的、也不是硬编码），
否则工具名/参数 schema 与部署不一致，模型会调不到工具。

## B. 打不开 / `protected first surface head`

**判据**：文件写好后 DSH 读不出来；或第一版能读，聊了一轮之后再也读不出来。

**根因**：deepseek 路由只支持 `systemPromptUpdate: "in-history"`，system prompt 以历史里的
`system/message` 形式下发。如果文件里**没有头部 system 节点**，DSH 下一轮
`SystemPromptProjection.project` 在 `head === undefined` 时走 `surfaceOp: "append"` 分支，
把新的 system 消息追加到历史中间；而格式校验规定「surface 非空且未置位 protectedHead 时出现
`system/message`」即报错 → 文件自相矛盾。

**修法**：生成会话时，第 0 个 surface 事件必须是 `system/message`，
内容用**本部署真实会话里渲染好的 system prompt 快照**。校验器不会检查这段文本「对不对」，
但文本不对会让续聊行为与原生会话不一致。

**复验**：`dsh_validate.mjs --canonical` 通过后，确认明文第 1 条带 `surfaceOp` 的事件
（或解压后第一条 surface）是 `system/message`。

## C. GUI 列表里看不到

按顺序排除：

1. **文件在不在预期路径**。
   `<D>/sessions/<projectKey(cwd)>/<id>/session.v4.jsonl.zstd`。
   目录名算错是高频错误：`projectKey` 有损（分隔符折叠、空格转 `~0020`、去前导 `-`、包 `--<encoded>--`）。
   直接看 `dsh_install.py` 打印的目标路径，或对比 `sessions/` 下已有目录的形态。
2. **分代文件名对不对**。必须是 `session.v4.jsonl.zstd`；写成 `session.jsonl.zstd` 会被当 v0。
3. **workspace 有没有入账**。`<D>/storages/workspace.json` 的
   `tables.workspaces[<uid>].sessionIds` 里必须有这个 id。没有 ⇒ 用 `dsh_install.py` 登记。
4. **cwd 与 workspace 的 path 是否一致**。GUI 取 `sessionIds` 与该会话 header `cwd` 的**交集**，
   两者差一个反斜杠或大小写都不会显示。会话 header 的 `cwd` 必须是已注册 workspace 的 canonical path。
5. **是不是在 DSH 运行时改的**。registry 启动时把 `workspace.json` 读进内存、变更时整体回写，
   运行中手改会被覆盖。正确姿势：**关闭 DSH → 跑 `dsh_install.py` → 再启动**。
   若 DSH 退出时又回写了注册表，重启后再跑一次登记（脚本幂等，已登记会跳过）。
6. **bootstrap 不会帮你补账**。`global.initialized === true` 表示一次性历史 bootstrap 已完成，
   之后新塞进来的会话不会自动出现在列表里——这正是需要显式登记的原因。

## D. 列表可见但打不开 / 续聊失败

**判据**：会话出现在列表，点开报 preset 相关错误，或无法开轮。

**根因**：header 的 `agentPreset` 写了本部署没有的 preset 名。
headless 一次性 runner 更是**拒绝任何带 preset 的会话**（报「runs under agent preset …,
which the one-shot runner does not compose」）。

**修法**：删掉 `agentPreset`（走部署默认），或改成目标部署真实存在的名字。
调试期优先删掉——报错信息本身也证明「DSH 已经读到并解析了你的 header」。

## E. 文件解码失败

| 报错/现象 | 根因 | 修法 |
| --- | --- | --- |
| `could not determine content size in frame header` | 用一次性 `decompress()` 解流式帧 | 逐帧流式解；`dsh_pack.py decompress` 已处理 |
| 读到一半失败 / 尾部不完整 | 最后一帧被截断（崩溃或复制中断） | 截断到该帧起点；`dsh_pack.py info` 看帧数与末帧是否完整 |
| 判「来自更新版本」 | 事件类型不在该构建词表且没有 `ignorable: true` | 只用核心事件类型，或补 `ignorable` |
| 「拒绝歧义」 | 同一 session 目录里有两个分代文件 | 删掉多余的那个（先确认哪个是目标） |
| `bad zstd magic` | 文件不是 zstd，或明文 JSONL 直接改了扩展名 | 明文 → `dsh_pack.py compress` |
| header 校验失败 | 多了未知键、`version` 不是 4、`isSeeded` 缺失 | header 只允许文档列出的键 |

## F. 能打开但内容不对

| 现象 | 根因 | 修法 |
| --- | --- | --- |
| 几万字摘要变成用户发言 | 压缩消息 `role` 是 `user`，被当成真实提问 | 按 `compactionId`/`isSummary` 归为 system 过滤掉 |
| 出现 `Interrupted by user` 这种正文 | 中断占位文本被当模型输出 | 过滤 `status="incomplete"` 的占位轮 |
| 用户提问里全是 `<system-reminder>` 元信息 | 没抽 `<user_query>` | 导入用 `userQuery`，不要用整条 `text` |
| 顺序错乱 / 轮次边界漂移 | 遍历时没跳过 `file-history-snapshot`、`session-meta` | 只按 `timestamp` 排序的主链遍历 |
| 工具调用数量对不上 | 把 `providerData.reasoning` 或 `messageId` 当轮次单位 | 轮用 `conversationRequestId`，调用用 `callId` |
| 时间线对不上分享页 | 分享页时间戳在压缩后被重排 | 一律以本地 `timestamp` 为准 |

## G. 轮数偏少、首轮是 assistant

不是网络问题，是**源数据本身被截断**。判据与提取方法见 `references/workbuddy-local-data.md` 第 4 节：
换个来源（本机 app 数据目录里的 jsonl 事件流），不要试图从分享页「补」出头部内容。

## H. 工具调用缺失或错位

1. **配对**：`function_call` 与 `function_call_result` 是两条平级记录，靠 `callId` join；
   缺一半说明提取时按 role 过滤掉了其中一类。
2. **成链**：多条 `function_call` 通过 `parentId` 成链，表示同一步内的并行/顺序调用，**不是嵌套**。
3. **step 级 id 不能当调用 id**：`providerData.messageId` 一个 step 可能对应多个并行调用。
4. **导入 DSH 时**：本 skill 默认只导纯文本对话，工具调用记录留在归档产物里；
   若确实要导工具调用，`assistant/message` 里每个 `tool-call` 块都必须有同 `callId` 的
   `tool/call` + `tool/result` 紧随，且 `step/end` 前必须全部闭合。

## I. 安装与回滚

- `dsh_install.py` 是**幂等**的：文件与登记都在 → 跳过（exit 0）；文件在但未登记 → `REFUSE`（exit 3）；
  没有 path 匹配 `cwd` 的 workspace → exit 2。`--dry-run` 只打印计划，但缺 workspace 时同样 exit 2。
- 每次改写 `workspace.json` 前会写 `.bak-<时间戳>` 备份；撤销登记用备份还原。
- 彻底移除一个导入会话：删 `<D>/sessions/<projectKey>/<id>/` 整个目录，
  并从 `workspace.json` 对应 workspace 的 `sessionIds` 里移除该 id。
- 源数据目录全程只读，不产生回滚需求。

## 诊断命令速查

```powershell
python scripts/wb_scan.py                              # list local conversation candidates
python scripts/wb_extract.py <source> -o norm.json --verify <share.json>   # extract + reconcile
python scripts/dsh_pack.py info <file.zstd>            # frames / checksum / content-size flag
node  scripts/dsh_validate.mjs <file> --canonical      # format + byte-identical check
node  scripts/dsh_verify_tools.mjs <file>              # will next turn defer all tools?
node  scripts/dsh_verify_tools.mjs <file> --simulate-resume   # valid after one appended turn
python scripts/dsh_install.py --session <file> --dry-run      # print the install plan only
python scripts/dsh_install.py --session <file>                # install + register in workspace
```

`--dsh-home` 用于自测：`dsh_build.py` 与 `dsh_install.py` 都支持，可以指到一个临时目录，
不写真实 `~/.dsh`。校验脚本（`dsh_validate.mjs` / `dsh_verify_tools.mjs`）按 DSH 包定位规则
自行找到本机构建，不需要这个参数。
