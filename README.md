# m1zukiri-skills

个人 skill 仓库：收录自研（自建）skills 并提供常用外部 skills 的镜像，附外部来源清单与 Agents 环境文档。

## 目录结构

```
m1zukiri-skills/
├── skills/                  # skills 目录，目录名即 skill 名
│   ├── rhizome/             # 【自建】轻量搜索纪律（原名 search-strategy，含 evals）
│   ├── colorful-palette/    # 【自建】《配色设计速查手册》配色知识库（7 色系 / 1583 方案）
│   ├── docx/ pdf/ pptx/ xlsx/ frontend-design/ skill-creator/
│   └── grill-me/ neat-freak/ storage-analyzer/ pua/   # 【外部镜像】源自 agent-bootstrap，上游见下方清单
├── EXTERNAL_SKILLS.md       # 外部下载 skills 清单：名称 / 用途 / 安装地址（按来源分组）
├── agents/                  # 其他 Agents 的环境文档与适配层
│   ├── AGENTS.md            # 全局行为规范（9 节，多 Agent 统一）
│   ├── INSTALL.md           # 跨 Agent 安装流程（兼容性矩阵 + 冲突/敏感检查）
│   ├── agent-bootstrap-README.md  # 原 agent-bootstrap 仓库说明（历史存档）
│   ├── config/
│   │   ├── config.yml               # OMP 代理配置（主题/TUI/压缩等）
│   │   └── settings.template.json   # 模板（shellPath 占位，需手动填写）
│   └── extensions/pua/     # 【外部镜像】tanweai/pua 的 pi 适配层
└── .gitignore              # 防泄漏规则（settings.json / auth.json / *.key 等）
```

## 自建 skills

| skill | 说明 |
|---|---|
| [rhizome](skills/rhizome/) | 轻量搜索纪律：不凭记忆作答、溯源一手、转载去重、区分口径、知不知为不知。含 evals 评测数据（原名 search-strategy） |
| [colorful-palette](skills/colorful-palette/) | 基于《配色设计速查手册》（红糖美学著）的配色知识库：7 大色系、162 类意象配色、52 类大自然配色、20 种流行风格，共 1583 个配色方案（CMYK + RGB 取自书中印刷色号，HEX 为派生值） |

## 外部 skills 镜像

`skills/` 下 docx、pdf、pptx、xlsx、frontend-design、skill-creator、grill-me、neat-freak、storage-analyzer、pua 为**外部 skill 的镜像副本**（迁移自 agent-bootstrap，与本机已装版本逐文件一致），供离线/快速安装；权威来源与安装地址见 [EXTERNAL_SKILLS.md](EXTERNAL_SKILLS.md)：

- Anthropic 官方：docx / pdf / pptx / xlsx / frontend-design / skill-creator
- RobMitt/grill-me-skill：grill-me
- KKKKhazix/khazix-skills：neat-freak / storage-analyzer
- tanweai/pua：pua（skill + `agents/extensions/pua` pi 适配层）

本机已安装的全部 143 个 skills 中，142 个为外部下载，完整清单（按来源分组：anthropics/skills、promptadvisers、Gonglitian/agent-skills、Imbad0202、Yuan1z0825、luwill、aeopress、fleurytian、Embody AI、tuoxie2046、YANZHANLIN、khazix、mdwoicke 及 18 个独立来源）见 [EXTERNAL_SKILLS.md](EXTERNAL_SKILLS.md)。

## 记录

- 2026-09-06：仓库初始化。外部清单经逐 skill 元数据与上游仓库核对生成（142 条）；rhizome 为唯一自建 skill（含 evals）；agents/ 收录 agent-bootstrap 同步集文档（无凭证）。
- 2026-09-06：接收 agent-bootstrap 的 skills 迁移（11 个 skill + pua 扩展镜像 + .gitignore），install 脚本（install.ps1 / install.sh）不迁移。
