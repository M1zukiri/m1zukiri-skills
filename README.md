# m1zukiri-skills

个人 skill 仓库：收录自研（自建）skills，整理外部来源 skills 清单，并归档 Agents 环境文档。

## 目录结构

```
m1zukiri-skills/
├── skills/                  # 自建（自研原创）skills，目录名即 skill 名
│   ├── rhizome/             # 轻量搜索纪律
│   └── colorful-palette/    # 《配色设计速查手册》配色知识库（7 色系 / 1583 方案）
├── EXTERNAL_SKILLS.md       # 外部下载 skills 清单：名称 / 用途 / 安装地址（按来源分组）
├── agents/                  # 其他 Agents 的环境文档与配置模板
│   ├── AGENTS.md            # 全局行为规范（9 节，多 Agent 统一）
│   └── config/
│       ├── config.yml               # OMP 代理配置（主题/TUI/压缩等）
│       └── settings.template.json   # 模板（shellPath 占位，需手动填写）
└── .gitignore              # 防泄漏规则（settings.json / auth.json / *.key 等）
```

## 自建 skills

| skill | 说明 |
|---|---|
| [rhizome](skills/rhizome/) | 轻量搜索纪律：不凭记忆作答、溯源一手、转载去重、区分口径、知不知为不知 |
| [colorful-palette](skills/colorful-palette/) | 基于《配色设计速查手册》（红糖美学著）的配色知识库：7 大色系、162 类意象配色、52 类大自然配色、20 种流行风格，共 1583 个配色方案（CMYK + RGB 取自书中印刷色号，HEX 为派生值） |

## 外部 skills

外部下载 skills 清单（名称、用途、安装地址，按来源分组）见 [EXTERNAL_SKILLS.md](EXTERNAL_SKILLS.md)：

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
- 独立来源 19 个（drawio-skill、mirofish、de-slop、pua、grill-me、taste-skill 等）
