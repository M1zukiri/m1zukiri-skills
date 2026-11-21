# profiles · 知识库

本目录存放跨项目复用的 Agent 知识，**不参与自动加载**。DSH / OMP / Codex 只加载 `AGENTS.md` 与 `CLAUDE.md`，不会读取这里的任何文件。

这里的知识进入上下文的唯一途径是：由 `agents-profile` skill 展开（内联）到项目的 `AGENTS.md` 中，再由项目文件被自动加载。

## 目录

| 路径 | 内容 | 公开 |
| --- | --- | --- |
| `modes/` | 活动模式相关的验证纪律（改代码、写运维、做调研） | 是 |
| `platforms/` | 操作系统相关的硬约束（编码、路径、字体、脚本执行） | 是 |
| `stacks/` | 语言与工具链相关的约定（依赖管理、构建、运行时坑） | 是 |
| `domains/` | 领域相关的验收口径（如与参考实现的数值对齐） | 是 |
| `contexts/` | 工作形态相关约定（常驻 Agent 工作区） | 是 |
| `local/` | 仅对本机有效的信息（目录位置、性能限制、休眠后如何恢复服务） | 否，已在 `.gitignore` |

本目录是**唯一**的 profile 知识库。`m1zukiri-profiles-md` 只保留 `projects/`（项目档案）与
`reference/`（调研资料），不再有 `profiles/`。

`local/` 与项目无关。项目涉及本机环境时由 agent 主动查阅，不参与内联。

`local/projects.txt` 记录本机需要检查内联状态的项目根路径（每行一个），供
`agents-profile check --all` 与 `agents/sync.ps1` 使用。

## 段落锚点

每个 profile 文件用二级标题划分可独立内联的段落，锚点取标题的 kebab-case：

```markdown
<!-- anchor: powershell-bom -->
## PowerShell BOM 约定
```

内联时整段（含二级标题）复制进项目 `AGENTS.md`，用标记包裹：

```markdown
<!-- BEGIN inline: platforms/windows.md#powershell-bom sha=7c3d9f2e -->
...
<!-- END inline: platforms/windows.md#powershell-bom -->
```

`sha` 为该段正文的短哈希，供 `check` 判断是否过期。标记区由工具生成，不要手改。

## 头部声明

每个 profile 文件开头声明它在什么条件下适用、什么条件下排除：

```markdown
---
name: platforms/windows
inline-when:
  any:
    - has-file: "**/*.ps1"
    - has-file: "**/*.bat"
    - project-flag: windows
exclude-when:
  any:
    - project-flag: linux-only
last-verified: 2026-11-20
---
```

`has-file` 由 glob 机械判定，`project-flag` 由项目 `AGENTS.md` 的 `<!-- profile -->` 块声明。两者取或。

**`inline-when` 只是判断依据，不自动触发内联。** 是否内联由人在审阅 `agents-profile audit` 产出的 proposal 时决定。

## 维护规则

- 只写**已经踩过坑**的内容，有具体证据支撑。不要写泛泛的最佳实践。
- 每段保持独立可读：内联到项目后不依赖上下文。
- 修改某段后，需要运行 `agents-profile sync` 让已内联的项目同步更新。
- `last-verified` 超过 6 个月的内容，`check` 会提示复核。
