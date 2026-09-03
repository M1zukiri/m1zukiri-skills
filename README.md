# m1zukiri-skills

个人 skill 仓库：收录自研（自建）skills，并整理外部来源 skills 清单。

## 目录结构

```
m1zukiri-skills/
├── skills/                  # 自建（自研原创）skills，目录名即 skill 名
│   └── rhizome/             # 轻量搜索纪律（原名 search-strategy）
├── EXTERNAL_SKILLS.md       # 外部下载 skills 清单：名称 / 用途 / 安装地址（按来源分组）
└── agents/                  # 其他 Agents 的环境文档（agent-bootstrap 同步集）
    ├── AGENTS.md            # 全局行为规范（9 节，多 Agent 统一）
    ├── INSTALL.md           # 跨 Agent 安装流程（兼容性矩阵 + 冲突/敏感检查）
    ├── agent-bootstrap-README.md  # agent-bootstrap 仓库说明
    ├── config/
    │   ├── config.yml               # OMP 代理配置（主题/TUI/压缩等）
    │   └── settings.template.json   # 模板（shellPath 占位，需手动填写）
    └── (本 README.md)
```

## 自建 skills

| skill | 说明 |
|---|---|
| [rhizome](skills/rhizome/) | 轻量搜索纪律：不凭记忆作答、溯源一手、转载去重、区分口径、知不知为不知。含 evals 评测数据（原名 search-strategy） |

## 外部 skills

本机已安装的 143 个 skills 中，142 个为外部下载，其名称、用途、安装地址（来源仓库）统一整理在 [EXTERNAL_SKILLS.md](EXTERNAL_SKILLS.md)，按来源分组：

- Anthropic 官方 (anthropics/skills)
- promptadvisers/claude-code-polished-documents-skills（Anthropic 文档系历史打包版）
- Gonglitian/agent-skills（56 个，含多个有更早上游的收集品）
- Imbad0202/academic-research-skills（academic-paper 系列，CC BY-NC 4.0）
- Yuan1z0825/nature-skills（nature-* 系列）
- luwill/research-skills、aeopress/writing-skills.TW、fleurytian/awesome-claude-skills
- markli1hoshipu/embody-ai-research-skills（Embody AI 系列）
- tuoxie2046/claude-code-research-skills（autofigure / gpt-image / nano-banana 等原创）
- YANZHANLIN/literature-review-skill（中文文献综述套件）
- KKKKhazix/khazix-skills、mdwoicke/obsidian-skills
- 独立来源 18 个（drawio-skill、mirofish、de-slop、pua、grill-me 等）

## 记录

- 2026-09-06：仓库初始化。外部清单经逐 skill 元数据与上游仓库核对生成（142 条）；rhizome 为唯一自建 skill（含 evals）；agents/ 收录 agent-bootstrap 同步集文档（无凭证）。
