# AGENTS.md

本文件是 m1zukiri-skills 仓库的维护指引，供 Agent 在本仓库内工作时读取。
Agent 的行为规范（如何思考、如何改代码、如何提交）见 `agents/AGENTS.md`，本仓库为其公开同步源。

## 仓库定位

个人 skill 仓库（公开，GitHub: M1zukiri/m1zukiri-skills），收录三件事：

- **自建 skills**：`skills/`，原创内容，本仓库唯一允许镜像进仓库的 skill 来源
- **外部 skills 清单**：`EXTERNAL_SKILLS.md`，只登记不镜像
- **Agent 环境文档与配置模板**：`agents/`，所有 Agent 环境规范与配置的同步源

仓库无全局构建与测试；改动主体是 Markdown、YAML、JSON 模板，个别 skill 自带辅助脚本（如 `scripts/`），仅限 skill 目录内使用。

## 目录结构

```
m1zukiri-skills/
├── skills/                  # 自建（原创）skills，目录名即 skill 名
│   ├── rhizome/             # 轻量搜索纪律
│   ├── colorful-palette/    # 配色知识库（含 references/ 数据文件）
│   └── gbt7714-citation/    # GB/T 7714 参考文献著录（含 scripts/ 辅助脚本）
├── EXTERNAL_SKILLS.md       # 外部 skills 清单：名称/用途/安装地址/许可证，按来源分组
├── agents/                  # Agent 环境文档与配置模板
│   ├── AGENTS.md            # 全局行为规范（9 节），同步至本机所有 Agent 环境
│   └── config/
│       ├── config.yml              # OMP 代理配置
│       └── settings.template.json  # 模板（仅占位符，不含真实路径）
├── README.md
└── .gitignore               # 防泄漏规则
```

## 维护规则

### 自建 skill（skills/）

- 一个目录一个 skill，目录名即 skill 名，kebab-case 小写英文。
- 必须包含 `SKILL.md`，YAML frontmatter 至少含：
  - `name`：与目录名一致
  - `description`：含触发词，说明何时使用，以及何时**不**应触发（如 rhizome 明确要求只在用户点名时加载）
  - 可选 `compatibility`（rhizome 的示例：“需要 web 搜索能力”）
- 数据、参考文件与辅助脚本放在 skill 目录内的子目录（如 `references/`、`evals/`、`scripts/`），不进仓库根目录。
- 新增或修改 skill 后，同步更新 `README.md` 的「自建 skills」表。

### 外部 skills 清单（EXTERNAL_SKILLS.md）

- 只登记，不镜像：外部 skill 本体及其文件不进本仓库，只记录名称、用途、安装地址、许可证。
- 按来源分组，每组一张表，列为：Skill 名称 / 用途描述 / 安装地址 / 许可证。
- 头部维护本机安装统计与更新日期；增减条目时同步更新。

### Agent 环境文档（agents/）

- `agents/AGENTS.md` 是全局行为规范的同步源。修改后：
  1. 提交并推送
  2. 立即覆盖本机各 Agent 环境副本（`~/.dsh`、`~/.codex`、`~/.omp/agent`）
- `agents/config/` 只允许模板与脱敏配置；`settings.template.json` 必须保留 `shellPath` 占位符，真实 `settings.json` 永不入库。

### 安全红线（公开仓库）

提交前逐文件检查，以下内容一律不得出现：

- 凭据：`auth.json`、`config.toml`、真实 `settings.json`、`*.key`、`*.pem`、`*.token`、`.env`
- 含用户名或环境信息的真实文件系统路径
- 代理凭据、内部网络地址、任何在公开仓库暴露会造成损害的机密

`.gitignore` 已覆盖上述类别；新增敏感文件类型时，先补 `.gitignore` 再 `git add`。

### Git 约定

- 默认分支 `main`。
- Commit 信息用英文，conventional commits 风格（`docs:`、`feat:`、`fix:`、`chore:` 等）。
- 提交信息描述交付结果，不写中间过程。
- 用户明确指示后才推送；不执行 `git push --force` 或其他破坏性操作。
