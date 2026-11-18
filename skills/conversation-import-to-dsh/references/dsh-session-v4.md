# DSH Session v4 会话文件格式参考

导入流程的格式依据。来源是对 DSH 0.2.x 可读 JS 源码的核对 + 真实会话的字节级实测。
`<DSH_HOME>` 指 DSH 数据目录（默认 `~/.dsh`，环境变量 `DSH_HOME` 可覆盖）；行号随构建漂移，
引用实现时只给模块与符号名。

一个会话 = 一个文件 = 一串**独立的 zstd 帧按顺序拼接**：第一帧是 header 行，其余每帧是一批事件行；
事件 append-only，`seq` 从 0 连续。对话、标题、工具调用全在事件里，文件之外没有必需索引。

## 1. 存放位置与命名

```
<DSH_HOME>/sessions/<projectKey(cwd)>/<encodeSegment(sessionId)>/session.v4.jsonl.zstd
```

文件名分代：v0 `session.jsonl`、vN `session.vN.jsonl`，压缩追加 `.zstd`。**新会话必须叫
`session.v4.jsonl.zstd`**，写成 `session.jsonl.zstd` 会被当 v0。一个会话目录只允许一个分代文件，
两代并存会「拒绝歧义」；header 无 `cwd` 时落到 `_no-cwd/`。

### 1.1 项目目录名 `projectKey(cwd)`

逐 UTF-16 码元扫描 `cwd`：`/`、`\`、`:` → 输出 `-`（**连续分隔符只算一个**）；
安全字符 `[A-Za-z0-9._-]`（`~` 除外）原样；其他任何码元（空格、`~`、中文……）→ `~` + 4 位大写
十六进制；最后去掉前导 `-`，为空用 `root`，截断到 251 字符，包成 `--<encoded>--`。

```
D:\Work\MyProject      -> --D-Work-MyProject--
D:\Work\My Project     -> --D-Work-My~0020Project--
```

编码**有损**（分隔符与字面 `-` 不可区分，超长截断），只是人类可读分组；会话身份靠 header 的
`cwd` + `id`，读取时会校验目录名与之相容。

### 1.2 会话目录名 `encodeSegment(sessionId)`

安全字符原样，其余 `~XXXX`；`.` → `~002E`，`..` → `~002E~002E`。常见 id 全是安全字符，所以
**目录名 = id 原文**。应用内新建 id 为 `session-<uuid>`；id 是未校验字符串，自造只需同一 root 下唯一。

## 2. 容器：多帧 zstd

| 项 | 规则 |
| --- | --- |
| 结构 | 若干**完整、可单独解压**的帧拼接；帧 1 = header 行；帧 2..N = 每批事件行 |
| 压缩 | 级别 3、`windowLog=21`（帧头 `0x58`）、写 checksum、**不写 content size**、不写 dict id |
| 其他 | 帧头 `28 b5 2f fd 04 58`；新批次在文件尾**追加新帧**，不重压旧帧；空会话只有 header 帧 |

Python `zstandard` 可与之**逐字节一致**（实测真实会话 228/228 帧重压相同）：

```python
params = zstandard.ZstdCompressionParameters.from_level(
    3, window_log=21, write_checksum=1, write_content_size=0, write_dict_id=0)
obj = zstandard.ZstdCompressor(compression_params=params).compressobj()   # 必须流式
frame = obj.compress(payload) + obj.flush(zstandard.COMPRESSOBJ_FLUSH_FINISH)
```

一次性 `compress()` 会写 content size、帧头变形；不写 content size 的代价是 `zstandard.decompress()` 报 `could not determine content size in frame header`，必须逐帧流式解。## 3. header 行（物理第 1 行）

只允许下列键，**多余键直接判损坏**：

| 字段 | 必需 | 约束 |
| --- | --- | --- |
| `type` / `version` | ✅ | 固定 `"session"` / `4` |
| `id` | ✅ | 与目录名编码后相容 |
| `createdAt` | ✅ | epoch ms，≥ 0 |
| `isSeeded` | ✅ | 普通导入会话为 `false` |
| `delegationDepth` | ✅ | 顶层会话 `0` |
| `cwd` | ❌ | 绝对路径；决定项目目录，须与目标 workspace 一致 |
| `parentSession` / `origin` | ❌ | fork 父 id / 仅 `"subagent"` |
| `agentPreset` | ❌ | 必须是该部署真实存在的 preset；省略 = 用部署默认 |

`agentPreset` 最容易写错：填部署没有的名字 → 会话「列表可见但打不开」；headless 一次性 runner 拒绝任何带 preset 的会话。

## 4. 事件行（物理第 2..N 行）

必需键 `type, seq, time, data`；可选键 `ignorable, surfaceOp, sourceEventSeqs`。

- `seq` 从 0 连续无空洞，行序即 seq 序。
- `surfaceOp` 仅 5 种 surface 事件必需：`system/message`、`user/message`、`developer/message`、
  `assistant/message`、`tool/result`；取值 `"append"` 或 `{"op":"replace","startSeq":n,"endSeq":m}`。
- `sourceEventSeqs` 只允许出现在 surface 事件上，**`assistant/message` 禁止携带**。
- 物理编码须与 DSH 编码器同形：无缩进、`ensure_ascii=False`、无空格，行尾 `\n`
  （Python：`json.dumps(obj, ensure_ascii=False, separators=(",", ":"))`）。
- 未知事件类型必须带 `"ignorable": true`，否则整份会话被判「来自更新版本」而拒绝。

## 5. 导入需要的事件类型（核心词表子集）

- **生命周期**：`turn/start{turn}`、`turn/end{turn,reason}`（`reason.kind` ∈ completed/aborted/
  blocked/error/max-tokens/interrupted/forked）、`step/start{turn,step}`、`step/end{turn,step}`。
- **请求**：`request/header{header{config,adapterDefaults?,tools?},reason}`（`reason` ∈ initial/
  resume/change/series；**v4 禁止 `header.system`**）、`request/context{provider,model,
  contextWindow?,systemPromptUpdate?}`（deepseek 只认 `in-history`）。
- **消息**：`system/message{turn,step,message}`（必须是第 0 个 surface）、`user/message{content,source,
  role,id}`（**data 本身就是消息体**）、`assistant/message{turn,step,message,stream}`（`stream` 必填，
  可为 `[]`）、`developer/message{turn,step,message}`、`tool/result{turn,step,message}`。
- **其余**：`permission/preset{preset}`、`sandbox/mode{mode}`、`approval/policy{policy}`、
  `tool/call{turn,step,callId,name,arguments}`（`arguments` 是模型原始 JSON **字符串**）、
  `session/title{title,messageSeqs,source{kind}}`、`assistant/attempt`、`compaction/*`。

## 6. reader 会拒绝的语义规则

1. `seq` 从 0 连续；`turn/start(n)` 必须在 `turn/end(n)` 前闭合，`turn` 依次 1,2,3…；
   未关闭 step 时不许 `turn/end`。
2. `step/start(turn,step)` 必须等于「当前 turn + 下一个 step」，`step/end` 必须匹配已打开的 step。
3. `system`/`developer`/`assistant/message` 必须在打开的 step 内；`user/message` 只需在打开的 turn 内。
4. **第 0 个 surface 节点若是 `system/message` 会被「保护」**（`protectedHead` 只在 surface 为空时置位）；
   若 surface 已非空而 `protectedHead` 未定义时出现 `system/message`，报
   `system/message requires a protected first surface head`，整份会话读不出来。
5. `assistant/message` 里每个 `tool-call` 块，后面必须有同 `callId` 的 `tool/call` 再接 `tool/result`；
   `tool/result.message` 必须 `role:"tool"`、`toolCallId === callId`、`source.kind === "tool"`。
6. `session/title` 的 `source.kind === "user"` 时 `messageSeqs` 必须为空；完全空会话（只有 header）合法，但不算出 turn。

## 7. 消息对象

`system` / `assistant` / `tool/result` / `developer` 的 `message` 与 `user/message` 的 `data` 同构：
`{role, id, source:{kind}, content:[...]}`。`source.kind` 按 role：`system`→`system-prompt`；
`assistant`→`model`（需 `provider`、`model`）；`tool`→`tool`（需 `callId`）；`user`/`developer`→
生产者自定义。ContentBlock 用 `text`、`reasoning`、`tool-call{id,name,arguments}`；v4 禁止旧的
`tool-result` 包装块。`assistant.message.stream` 存原始流，但 **reader 不强制它与 `content` 一致**：
导入时给 `[]` 或一条单 text 记录即可，`usage` 可省略。

## 8. 让它出现在 GUI 列表里（两层都要过）

1. **存储层**：`list()` 是**目录扫描**，没有索引文件；文件放对位置就能被看见。
2. **GUI 层**：列表按 workspace → 会话组织，记录在 `<DSH_HOME>/storages/workspace.json`：

```jsonc
{"unit":{"name":"workspace","version":2},"global":{"initialized":true,"workspaceIds":["<uuid>"]},
 "tables":{"workspaces":{"<uuid>":{"path":"D:\\Work\\MyProject","title":"<title>",
   "sessionIds":["session-<uuid>"],"createdAt":"ISO","updatedAt":"ISO"}}}}
```

- `sessionIds` 是**显式入账数组**，不是扫描结果，且会与会话 header 的 `cwd` 取交集过滤：
  **`cwd` 与 `path` 不一致的会话不会显示在该 workspace 下**。
- 历史 bootstrap 只跑一次（`initialized === true` 之后新会话**不会自动补账**）；registry 启动时
  读入内存、变更时整体回写，**必须在 DSH 关闭时改**，或退出后重跑登记。
- `storages/session_projcache*` 只是折叠缓存，缺失只影响「秒出」的标题，不影响可见性。

## 9. 最小合法会话骨架

明文 8 行，type 依次为：`header` → `turn/start{turn:1}` → `step/start{turn:1,step:1}` →
`system/message` → `user/message` → `assistant/message` → `step/end{turn:1,step:1}` →
`turn/end{turn:1,reason:{kind:"completed"}}`。

三个消息事件都带 `surfaceOp:"append"`；system 的 `source.kind` 是 `system-prompt`；assistant 的
`source` 需带 `provider`、`model`，`stream` 可为 `[]`。header 最简形态：
`{"type":"session","version":4,"id":"session-<uuid>","createdAt":<ms>,"cwd":"D:\\Work\\MyProject","isSeeded":false,"delegationDepth":0}`

能读、能续聊，但缺 provider/model 快照（应用会用当前默认值补）。导入真实历史务必补
`request/header` + `request/context`，并带 tools 基线与 system header（见 SKILL.md 机制一节）。

## 10. 「写对了」的判据

- `dsh_validate.mjs --canonical` 通过：用 DSH 自带 decoder 解码后再用其 encoder 逐行重编码，
  与文件**逐字节相同**（`CANONICAL: every row byte-identical to DSH encoder output`）。
- `dsh_pack.py info` 显示 `checksummed: True  fcs-present: False`，帧数与字节数吻合。
- 真闭环：DSH 在你写的文件尾**继续追加**新帧后，整份文件仍 `VALID`。

校验脚本按序定位 DSH 包：`DSH_PKG_ROOT` → `dsh` 可执行文件所在的 npm 全局目录（`npm root -g`）
→ 桌面安装的 `resources/app.asar.unpacked/dsh`；都找不到就打印候选路径并非零退出。
第 3 条意味着校验的是**本机正在用的构建**：跨机器复用生成好的会话时，最好在目标机器再校验一次。
