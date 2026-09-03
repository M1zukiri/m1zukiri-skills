# INSTALL.md — 跨 Agent 安装流程

本文件定义「检查兼容性 → 安装 → 检查安装结果」的通用安装流程，供任何 Agent 在新终端、新环境自助执行。本流程不依赖平台安装脚本。

## 0. 流程总览

1. 环境识别：确定操作系统与 Agent 类型
2. 兼容性检查：路径映射、技能适用性、冲突与敏感文件检查
3. 安装：规则文件 + 适用技能（含必要适配）
4. 检查安装结果：文件完整性、frontmatter、哈希一致
5. 报告与回滚

## 1. 环境识别

### 1.1 操作系统

用系统标准命令识别：Windows（`Get-Command` / PowerShell）、macOS / Linux（`command -v`）。

### 1.2 Agent 类型（按顺序探测）

| 探测条件 | 判定 |
|---|---|
| `$CODEX_HOME` 或 `~/.codex` 存在 | Codex |
| `~/.omp` 存在或 `omp` 命令可用 | OMP |
| `~/.claude` 存在或 `claude` 命令可用 | Claude Code |
| `~/.openclaw` 存在 | OpenClaw |
| `~/.config/opencode` 存在 | OpenCode |
| 均不匹配 | 询问用户，不得假设 |

### 1.3 目标路径映射

常用路径：

| Agent | 全局规则文件 | 用户技能目录 |
|---|---|---|
| Codex | `~/.codex/AGENTS.md`（或 `$CODEX_HOME/AGENTS.md`） | `~/.codex/skills/` |
| OMP | `~/.omp/agent/AGENTS.md` | `~/.omp/skills/` |
| Claude Code | `~/.claude/CLAUDE.md` | `~/.claude/skills/` |
| OpenClaw | 项目根 markdown（CLAUDE.md / AGENTS.md） | `~/.openclaw/skills/` |
| OpenCode | `~/.config/opencode/` | `~/.config/opencode/skills/`（同时扫描 `~/.claude/skills/`、`~/.codex/skills/`） |

### 1.4 仓库定位

优先使用当前工作目录中的 m1zukiri-skills 仓库；否则克隆 `https://github.com/M1zukiri/m1zukiri-skills` 到临时目录，安装完成后可删除。官方文档 skills（docx / pdf / pptx / xlsx 等）亦可直接从其上游（anthropics/skills）获取。

## 2. 兼容性检查

### 2.1 技能适用性矩阵

| 技能 | Codex | OMP | Claude Code / OpenClaw / OpenCode | 适配要求 |
|---|---|---|---|---|
| neat-freak | ✅ | ✅ | ✅ | 无（自带跨平台路径表） |
| frontend-design | ✅ | ✅ | ✅ | 无 |
| storage-analyzer | ✅ | ✅ | ✅ | 无 |
| grill-me | ✅ | ✅ | ✅ | 无 Ask 工具的环境改为文字提问 |
| pua | ⚠️ | ✅ | ⚠️ | 移除 SessionStart / PreCompact hook、`/pua:*` 命令、`~/.pua` 持久化依赖后可用 |
| docx / pdf / pptx / xlsx / skill-creator | ❌ 与内置技能重复 | ✅ | ✅ | Codex 跳过，其余可装 |

### 2.2 冲突检查

- 目标技能目录已存在同名技能：比较内容哈希。相同则跳过；不同则备份为 `<name>.bak-<时间戳>`，再询问用户覆盖或跳过；无法交互时跳过并报告。
- 全局规则文件已存在：先备份为 `<文件名>.bak-<时间戳>`，再覆盖（备份可回滚）。
- 检查目标环境是否已有同功能的 Agent 内置技能：有则跳过仓库版本（如 Codex 的 docx / pdf / pptx / xlsx / skill-creator）。

### 2.3 敏感文件检查

复制前检查源仓库，安装后检查目标，两者都不得包含：API key、token、密码、私钥、真实 `settings.json`、代理凭证。发现即中止并报告。

## 3. 安装

1. 规则文件：将仓库 `AGENTS.md` 复制到目标全局规则路径（已存在则先备份）。
2. 技能：按 2.1 矩阵，将适用技能目录整体复制到目标技能目录，保留 `scripts/`、`assets/`、`references/`、`LICENSE.txt` 等子内容。
3. 适配：按矩阵要求修改目标副本（源仓库文件不动）：
   - grill-me：把「Ask 工具」改为当前环境的提问方式（文字提问 / 原生提问工具）。
   - pua：删除 hook、命令、持久化文件依赖，保留行为指导与方法论 references。
4. OMP 专属（仅当目标为 OMP）：按 `config/config.yml` 与 `config/settings.template.json` 配置。

## 4. 检查安装结果

1. 规则文件：存在；与仓库源文件 SHA-256 一致；抽查 9 个章节标题完整。
2. 技能：每个已装技能的 `SKILL.md` 存在；frontmatter 含 `name` 与 `description`；必要子目录与源一致；逐个文件哈希一致；目标目录无敏感文件。
3. 输出报告：已安装清单、跳过清单（附原因）、备份路径、未决事项（如需用户确认的覆盖）。

## 5. 回滚

- 备份文件即回滚点：将 `.bak-<时间戳>` 恢复为正式文件名。
- 仓库源为权威版本：重新执行本流程即可重装。
- 删除技能时遵循项目规则：列出清单并向用户确认。
