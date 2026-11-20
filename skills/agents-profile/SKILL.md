---
name: agents-profile
description: 把 m1zukiri-skills 仓库 agents/profiles 下的通用知识内联进项目 AGENTS.md，并审计项目规范的时效性。当用户要求「整理 AGENTS.md」「把 profiles 内联进项目」「同步项目规范」「审计某项目的 AGENTS.md」，或项目 AGENTS.md 顶部的 <!-- profile --> 声明块需要展开时触发。不适用于：单纯编辑 AGENTS.md 的正文措辞、只读查询规范内容、修改 profiles 里的知识本身。
---

# agents-profile

管理「profiles 知识库 → 项目 AGENTS.md」的内联。profiles 下的文件**不会被任何 Agent 自动加载**，只有内联进 `AGENTS.md` 后才会进入上下文。

## 位置探测

仓库与项目位置一律探测，不硬编码。执行任何命令前先解析下表；任一项探测失败即中止并报告缺哪一项，**不要用默认值蒙混**。

| 占位符 | 探测方式 |
| --- | --- |
| `${AGENTS_REPO}` | 环境变量 `AGENTS_REPO` → 从 cwd 向上找 `git remote` 含 `m1zukiri-skills` 的目录 → 向上找同时含 `agents/AGENTS.md` 与 `skills/` 的目录 |
| `${PROFILES_DIR}` | `${AGENTS_REPO}/agents/profiles` |
| `${PROJECT_ROOT}` | `git rev-parse --show-toplevel`，失败回退 cwd |
| `${DSH_HOME}` | 环境变量 `DSH_HOME` → `~/.dsh` |

脚本 `scripts/profile_lib.py` 已实现上述探测（`resolve_agents_repo`、`resolve_profiles_dir`、`resolve_project_root`、`resolve_dsh_home`）。直接调用，不要自己重写。

## 命令

```bash
python -B scripts/profile_cli.py list [--profile platforms/windows]
python -B scripts/profile_cli.py add <项目路径> [--dry-run]
python -B scripts/profile_cli.py sync <项目路径> [--dry-run]
python -B scripts/profile_cli.py check <项目路径...> | --all
python -B scripts/profile_cli.py audit <项目路径>
python -B scripts/profile_cli.py apply <proposal.json>
```

`-B` 阻止生成 `__pycache__`（`.pyc` 内嵌绝对路径，公开仓库不带）。

`<项目路径>` 可以是项目根目录，也可以直接给 `AGENTS.md`。

- `add` 按声明块展开：决定「内联哪些」，会追加或更新全部声明中的段落。
- `sync` 只刷新已存在的内联区：决定「内容是否最新」，不会把刻意排除的段落加回来。
- 两者都幂等：同一输入重复执行，第二次 `git diff` 必须为空。
- 单文件内联后上限 24 KB，超限报错且不写入，并列出贡献最大的段落。
- `check --all` 读取 `${PROFILES_DIR}/local/projects.txt`（每行一个项目根路径，本机文件，已 gitignore）。

## 内联标记

```markdown
<!-- BEGIN inline: platforms/windows.md#powershell-bom sha=28bf6009 -->
<!-- anchor: powershell-bom -->
## PowerShell 脚本编码
...
<!-- END inline: platforms/windows.md#powershell-bom -->
```

标记区由工具生成。`sha` 是段落正文的短哈希，用于判断过期。**不要手改标记之间的内容**——改了会被下一次 `sync` 覆盖。

## audit：必须交给 subagent

`audit` 只输出任务说明与当前状态，不执行分析。真正的审计要由 subagent 完成：

1. 主 agent 运行 `audit <项目路径>`，拿到状态摘要与要求
2. 主 agent 启动 subagent，把摘要与要求交给它
3. subagent **只读**，产出 `proposal.json`
4. 人审阅 proposal
5. 主 agent 运行 `apply <proposal.json>`

**subagent 的硬边界（不可放宽）**：

- 允许：读项目文件、读 profiles、glob 探测、核查正文提到的文件与命令是否存在
- 禁止：修改任何文件、修改声明块、删除非标记区内容、执行 `add`/`sync`/`apply`

proposal 格式：

```json
{
  "project": "<项目 AGENTS.md 绝对路径>",
  "add":    [{"source": "platforms/windows.md", "anchor": "powershell-bom", "reason": "..."}],
  "remove": [{"source": "stacks/python.md", "anchor": "safe-print", "reason": "..."}],
  "warnings": ["正文提到的 xxx 已不存在"]
}
```

每条 `add` / `remove` 必须有 `reason`。无理由的条目不输出。

## inline-when 不自动触发

profile 头部的 `inline-when` / `exclude-when` 只是 subagent 的**判断依据**，不是自动执行条件。是否内联由人在审阅 proposal 时决定。不要把 `inline-when` 实现成"满足就自动内联"。

## 何时不要用本 skill

- 只想改项目 `AGENTS.md` 的措辞或补充一段项目专属内容 → 直接编辑，不走内联
- 想修改 profiles 里的知识本身 → 编辑 `agents/profiles/**`，然后 `sync` 各项目
- 项目没有 `<!-- profile -->` 声明块 → `add` 会直接报错，先确认是否真的需要内联

## 验证

任何一次写入后，跑：

```bash
python scripts/profile_cli.py check <项目路径>
```

要求零 issue。`check` 会报告：悬空锚点、标记不成对、内容过期、内联但未声明、声明但 profile 不存在、超预算。
