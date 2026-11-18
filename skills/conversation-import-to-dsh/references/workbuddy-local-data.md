# WorkBuddy / CodeBuddy 本地对话数据参考

首个实证案例来自 WorkBuddy（腾讯 CodeBuddy 系）。本文件说明它的本地数据长什么样、怎么变成可导入的
归一化 JSON、以及哪些地方会骗人。`<WORKBUDDY_HOME>` 默认 `~/.workbuddy`。

## 1. 权威来源只有一处

```
<WORKBUDDY_HOME>/projects/<workspace-slug>/<conversationId>.jsonl
```

一个会话一个 jsonl，**逐条事件流**，是唯一包含完整对话正文的地方。
`workspace-slug` 由 cwd 变形而来（盘符小写、分隔符换成 `-`，如 `d-Work-MyProject`），
但不同版本规则会变，**不要自己推算目录名**，直接扫描全部 `*.jsonl` 再按内容判定归属。

同一 `projects/` 下还可能有：

| 路径 | 内容 | 能否当来源 |
| --- | --- | --- |
| `<conversationId>/tool-results/` | `function_call_result` 的渲染副本 | ❌ 冗余子集 |
| `<conversationId>.file-rollback.ndjson` | 文件回滚索引 | ❌ 无对话正文 |
| `workbuddy.db`（sqlite，21 表） | `sessions`/`session_usage`/`spaces`/`local_skills` 等**元数据** | ❌ 无消息体表 |
| `sessions/*.json` | PID、心跳、cwd、endpoint | ❌ 无消息 |
| `space-history/spaces/*.json` | 空间创建时的 `primaryFolderPath` | 仅用于确认 cwd 归属 |
| `storage/user-*/.../conversation-list.json`、`sidebar-list-snapshot.json` | 侧栏缓存 | 仅标题/时间，可交叉验证 |
| `audit-log/*.jsonl` | 工具审计 | 不含对话正文 |

**sqlite 不是答案**：它只提供 `model`、`cwd`、`created_at`/`updated_at`、`status` 这类会话级元数据，
消息正文一律在 jsonl 事件流里。这也是最容易走偏的一步——别在数据库里找消息表。

## 2. jsonl 是事件流，不是消息列表

每行一条记录，主要类型：

| 记录 type | 含义 | 进入对话体 |
| --- | --- | --- |
| `message`(role=user) | 用户轮；压缩摘要也用它 | ✅ |
| `message`(role=assistant) | 助手正文；被中断时是占位文本 | ✅ |
| `reasoning` | 助手思考 | ✅（单独 item） |
| `function_call` | 工具调用，只有 `arguments` | ✅ |
| `function_call_result` | 工具返回，靠 `callId` 关联 | ✅ |
| `file-history-snapshot` | 文件快照（上百条，混在中间） | ❌ 跳过 |
| `session-meta` | 心跳元数据 | ❌ 跳过 |
| `ai-title` | 会话标题（1 条） | 取标题用 |

`parentId` 串成单链，**文件顺序即时间顺序**，顺序遍历即可；`timestamp` 是毫秒 epoch。
`file-history-snapshot` 的 `parentId` 不参与主链，漏跳过会打乱轮次边界。

## 3. 归一化结构与字段映射

`wb_extract.py` 输出的结构（`rounds` + `items`）：

```jsonc
{"source":"<path>","conversationId":"<id>","title":"<title>","assistantName":"<name>","modelName":"<model>",
 "rounds":[{"roundId":"<id>","messageType":"user|assistant|system","createTime":<ms>,"finishTime":<ms|null>,
            "requestId":"<id>","model":"<model>","userQuery":"<user text>",
            "items":[{"type":"text|reasoning|tool-call|tool-result","text":"<text>",
                      "tool":{"name":"<n>","callId":"<id>","status":"<s>","args":{},"result":{}}}]}]}
```

| 归一化字段 | 来源 | 变换 |
| --- | --- | --- |
| `messageType` | `message.role`；压缩消息 → `system` | — |
| `createTime` | 轮内第一条记录的 `timestamp` | — |
| `finishTime` | 轮内末条记录 `timestamp`；user/system 轮与 `incomplete` 的 assistant 轮为 `null` | — |
| `requestId` | `providerData.conversationRequestId` | 分组用这个，不要用 `messageId` |
| `userQuery` | `content[0].text` 中 `<user_query>...</user_query>` 之间 | 正则抽取纯用户原话 |
| `items[].text`(text) | `message.content[]` 中多段 `text`/`input_text`/`output_text` | 拼接为一条，不截断 |
| `items[].text`(reasoning) | `reasoning.rawContent[0].text`（`content` 为空时） | — |
| `tool-call` | `function_call`：`name`、`callId`、`arguments`（JSON 字符串 → 对象） | 结果在另一条记录 |
| `tool-result` | `function_call_result`：`output.text`（list 时转 JSON 字符串）、`callId` | — |

## 4. 先判断「这份数据完整吗」

拿到任何一份来源（本机 jsonl 或云端 `conversation-data.json`）先做三个检查：

1. **首条是否用户提问**。若首轮就是 assistant 并引用「上一轮」「前面提到的」，说明头部被切掉了。
   真正的用户提问应在 `messageType === "user"` 且 `userQuery` 非空的记录里。
2. **时间跨度是否覆盖会话真正开始**。与本机 sqlite 的 `sessions.created_at` 或侧栏 `lastActivityAt` 交叉验证；
   云端快照的首条时间明显晚于它，就是被截断。
3. **轮数 / 用户轮数是否少于预期**。云端只保留最近约 100 个「扁平轮」，本地应严格更多。

```powershell
# source: local jsonl or cloud conversation-data.json (auto-detected)
python scripts/wb_extract.py <source> -o norm.json --verify <share.json>
# expect: rounds=116 user=55 assistant=57 system=4
#         VERIFY zero-loss: source=1882 -> items=1882 OK
```

对账里出现的「云端有、本地无」只剩合成时间线事件（`timeline:model-switch:*`、
`timeline:context-compaction:*`，`content` 为空）时，可以认定本地完整。

## 5. 八个已知坑

1. **分享链接不可信**。`conversation-data.json` 的 `messages` 只有最近 ~100 轮，截断点落在**轮与轮之间**：
   首轮直接是 assistant，被丢掉的是它前面那条 user 提问以及更早的整段历史。
   分享页还会给压缩后的会话**重新分配轮 id**（部分 user 轮 id 在本地不存在，但 `requestId`/`createTime` 对得上），
   并额外合成 3 条 `timeline:*` 事件。**顺序、时间线、轮 id 一律以本地 `timestamp` 为准。**
2. **tool-call 与 tool-result 分离存储**。`function_call` 只存 `arguments`，结果在平级记录
   `function_call_result` 里，用 `callId` join。`providerData.messageId` 是 **step 级** id
   （一个 step 可挂多个并行调用），`stepSeq` 在同一 request 内会复用——分组只能用 `conversationRequestId`。
3. **`arguments` 是 JSON 字符串**，不是对象，需 `json.loads`；`providerData.argumentsDisplayText`
   是给人看的可读版，未必是合法 JSON，不要用。
4. **`reasoning` 正文在 `rawContent[0].text`**，`content` 通常是 `[]`。
   而且 `function_call.providerData.reasoning` 里**重复存了一份同样的思考文本**，照搬会双倍计数。
5. **上下文压缩会插入「伪 user 消息」**。每次压缩产生两条：一条 3–5 万字的
   `<conversation_history_summary>` 摘要、一条固定的「请基于摘要继续」续跑提示。
   它们的 `role` 是 `user`，但**不是用户说的话**。只按 `role` 过滤，就会把几万字摘要当成用户输入——
   这是最容易踩的坑。按 `providerData.compactionId` / `isSummary` 识别，归为 `system` 轮。
6. **被中断的轮是占位文本**。assistant 轮 `status="incomplete"`、正文恰为 `Interrupted by user`、
   带 `providerData.error`、`finishTime` 应为 `null`。这是系统占位符，不是模型输出，导入前过滤掉。
7. **用户消息正文被 `<system-reminder>` 包裹**。真实调用形如
   `<system-reminder data-role="user-context">...</system-reminder><user_query>真正的提问</user_query>`，
   整条可能 500–7000 字而真正提问只有几十字。归档可原样保留全文，**导入会话必须改用 `userQuery`**。
8. **非对话记录混在流里**。`file-history-snapshot`（接近两百条）、`session-meta`（几十条）必须跳过，
   否则轮次边界会错位、条目数会虚高。

## 6. 只读纪律

- jsonl 用只读方式打开；sqlite 用 `file:<path>?mode=ro` 的 URI 只读连接，不做 checkpoint、vacuum 或任何写操作。
- WorkBuddy 进程在跑时 jsonl 会继续增长（`mtime` 变化）。**先确认会话已结束再提取**，
  并用 `mtime` + 最后一条记录时间判断数据是否还在写。
- 提取产物写到独立目录，不要写进 `<WORKBUDDY_HOME>`。

## 7. 换一个 CodeBuddy 系应用

若目标应用不是 WorkBuddy，先做一次结构探查（记录类型分布、字段名、时间戳单位），
对照第 2 节的记录类型表判断是否同构：

- **同构**：直接复用 `wb_extract.py`，只改扫描根目录。
- **不同构**：保留「事件流 → rounds/items」的分层，改映射层即可；`dsh_build.py` 只看归一化 JSON，
  不需要跟着改。
