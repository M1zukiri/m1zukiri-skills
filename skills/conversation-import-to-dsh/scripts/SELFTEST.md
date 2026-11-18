# SELFTEST — 端到端自测记录

自测环境：隔离的临时 `DSH_HOME`（`%TEMP%\dsh-skill-selftest`）+ 临时 cwd，**全程不写真实 `~/.dsh`**（只读复制一个真实会话当基线样本）。
输入：`wb_extract.py` 从本机 WorkBuddy 真实会话归一化出的 JSON（116 轮 / 1882 条目）。
运行环境：Windows 11、Python 3.11.9 + zstandard 0.25.0、Node v24。

前置：`pip install zstandard`；Node ≥ 20；本机已装 DSH（`~/.dsh/sessions` 下至少有一个真实 v4 会话）。
以下命令在 skill 根目录（`scripts/` 的上一级）执行。

---

## 1) 准备隔离环境 + 基线样本

```powershell
$H = Join-Path $env:TEMP 'dsh-skill-selftest'      # 临时 DSH_HOME
$W = Join-Path $H 'workdir'                        # 临时 cwd
$NORM = '<wb_extract.py 输出的归一化 JSON>'
Remove-Item -Recurse -Force $H -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $W,"$H\sessions\--boot--\session-boot","$H\storages" | Out-Null
# 借一个真实 v4 会话当 tools/system 基线源（只读 ~/.dsh；取最大的，必含 system 头与 request/header.tools）
$real = Get-ChildItem "$HOME\.dsh\sessions\*\*\session.v4.jsonl.zstd" |
        Sort-Object Length -Descending | Select-Object -First 1
Copy-Item $real.FullName "$H\sessions\--boot--\session-boot\session.v4.jsonl.zstd"
# 造一条 path=$W 的 workspace，供 install 入账
@{unit=@{name='workspace';version=2};
  global=@{initialized=$true;workspaceIds=@('ws-1');archivedSessionIds=@();pinnedSessionIds=@()};
  tables=@{workspaces=@{'ws-1'=@{path=$W;title='selftest';sessionIds=@();
    createdAt='2026-01-01T00:00:00.000Z';updatedAt='2026-01-01T00:00:00.000Z'}}}} |
  ConvertTo-Json -Depth 8 | Set-Content "$H\storages\workspace.json" -Encoding utf8
```

## 2) build + pack

```powershell
python scripts/dsh_build.py $NORM -o "$H\session.jsonl" --cwd $W --dsh-home $H
python scripts/dsh_pack.py compress "$H\session.jsonl" "$H\session.v4.jsonl.zstd"
```

```
探测 DSH 基线：<TEMP>\dsh-skill-selftest\sessions
tools=27 (source: <TEMP>\dsh-skill-selftest\sessions\--boot--\session-boot\session.v4.jsonl.zstd)
system_prompt=5949 chars (source: 同上)
turns=55 events=328 prose_chars=133861
dropped_items reasoning=484 tool-call=588 tool-result=588 (只导入文字正文，reasoning/工具调用不进 DSH 历史)
session_id=session-0cc59f81-8930-47f8-81b8-592cd4f7c643 cwd=<TEMP>\dsh-skill-selftest\workdir
out=<TEMP>\dsh-skill-selftest\session.jsonl (814317 B)
in 814317 bytes -> out 136572 bytes, frames=3, first frame header 28b52ffd0458
```

## 3) validate(--canonical) + verify_tools(--simulate-resume)

```powershell
node scripts/dsh_validate.mjs "$H\session.v4.jsonl.zstd" --canonical
node scripts/dsh_verify_tools.mjs "$H\session.v4.jsonl.zstd" --simulate-resume --resume-out "$H\resume.jsonl"
```

```
DSH pkg root: <npm 全局>\@deepseek-ai\dsh\node_modules\@deepseek-ai (dsh executable)
frames=3 readHeader=current stored=v4 target=v4
VALID: id=session-0cc59f81-8930-47f8-81b8-592cd4f7c643 version=v4 events=328 inherited=0
CANONICAL: every row byte-identical to DSH encoder output

history.tools=27 history.updates=0 baseline_deferred=0
next_turn_tools=27 next_turn_deferred=0
PASS: 下一轮至少有 1 个可用工具，defer_loading=true 的数量为 0
resume simulation: +6 events, turn=56, file=<TEMP>\dsh-skill-selftest\resume.jsonl
RESUME VALID: events=334 turn=56
RESUME CANONICAL: 追加后续聊文件仍可通过 DSH 校验
```

## 4) install（文件落位 + workspace 入账）

```powershell
python scripts/dsh_install.py --session "$H\session.jsonl" --dsh-home $H
```

```
projectKey: --C-Users-<用户名>-AppData-Local-Temp-dsh-skill-selftest-workdir--
session file: <TEMP>\dsh-skill-selftest\sessions\--C-Users-<用户名>-…-workdir--\<id>\session.v4.jsonl.zstd (136572 B)
workspace: ws-1 -> sessionIds[0]=session-0cc59f81-…
backup: <TEMP>\dsh-skill-selftest\storages\workspace.json.bak-<时间戳>
```

再跑一次同样的命令，验证幂等：`已安装且已在 workspace ws-1 入账，跳过（幂等）`（exit 0）。

## 5) 校验装好的文件

```powershell
$inst = Get-ChildItem "$H\sessions\--C-Users-*" -Recurse -Filter session.v4.jsonl.zstd | Select-Object -First 1
node scripts/dsh_validate.mjs $inst.FullName --canonical
```

```
frames=3 readHeader=current stored=v4 target=v4
VALID: id=session-0cc59f81-8930-47f8-81b8-592cd4f7c643 version=v4 events=328 inherited=0
CANONICAL: every row byte-identical to DSH encoder output
```

---

## 结论

| 步骤 | 结果 |
| --- | --- |
| dsh_build（自动提取 tools + system prompt） | PASS：tools=27 / system_prompt=5949 chars |
| dsh_pack compress（多帧、header 单独一帧） | PASS：frames=3，首帧 `28b52ffd0458` |
| dsh_validate --canonical | PASS：VALID + CANONICAL（328 事件逐行字节一致） |
| dsh_verify_tools --simulate-resume | PASS：0 个 defer_loading，续聊追加后仍 VALID + CANONICAL |
| dsh_install + 再 validate | PASS：projectKey/文件路径/workspace 入账正确，装好的文件 VALID + CANONICAL |
| install 重跑幂等 | PASS：`已入账，跳过（幂等）`，exit 0 |

脱敏自检：`scripts/` 下全文件 grep 个人绝对路径、本机用户名、样本工程目录名 ⇒ 0 命中。

手工确认项（脚本无法代验）：装进**真实** `~/.dsh` 前先关闭 DSH（运行中会被回写覆盖），重启后在对应 workspace 的会话列表里应能看到该导入会话；如果 `agentPreset` 写了本部署不存在的名字，会「列表可见但打不开」，默认留空即可。
