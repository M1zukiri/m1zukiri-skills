# m1zukiri-skills

个人 skill 仓库：收录自研（自建）skills，整理外部来源 skills 清单，并归档 Agents 环境文档。

## 目录结构

```
m1zukiri-skills/
├── skills/                  # 自建（自研原创）skills，目录名即 skill 名
│   ├── rhizome/             # 轻量搜索纪律
│   ├── colorful-palette/    # 《配色设计速查手册》配色知识库（7 色系 / 1583 方案）
│   ├── gbt7714-citation/    # GB/T 7714—2025 参考文献著录（中英文，全文献类型）
│   ├── visual-page-editor/  # 页面元素批注 → 源码坐标回指
│   ├── alas-ctrl/           # 碧蓝航线 ALAS 脚本的控制与监控层
│   └── agents-profile/      # profiles 知识库 → 项目 AGENTS.md 的内联与审计
├── EXTERNAL_SKILLS.md       # 外部下载 skills 清单：名称 / 用途 / 安装地址（按来源分组）
├── agents/                  # Agent 行为规范与知识库
│   ├── AGENTS.md            # 全局行为规范正文（分发源，由 sync.ps1 同步到各 Agent 环境）
│   ├── profiles/            # 跨项目知识库（platforms / stacks），不参与自动加载
│   ├── check-public.ps1     # 公开前敏感信息扫描
│   ├── sync.ps1             # 分发全局规范 + 项目内联检查
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
| [gbt7714-citation](skills/gbt7714-citation/) | 按 GB/T 7714—2025《信息与文献 参考文献著录规则》生成、格式化、核对中英文参考文献条目，覆盖期刊/图书/学位论文/会议/标准/专利/报告/网页等全部文献类型，并可将 2015 版旧格式升级为 2025 版 |
| [visual-page-editor](skills/visual-page-editor/) | 让用户在任意 HTML 页面上点选元素、添加批注与修改意见，并把每条批注对应回源码位置（文件 + 行号），供 agent 直接改源码；自动识别页面产生方式（生成器注入 `data-src` / 离线反查），对含 canvas 的页面移植像素以保证批注时图形非空白。配套三个脚本：`make_annotator.py`（生成批注副本）、`index_elements.py`（离线反查坐标）、`build_lexicon.py`（字面量词典） |
| [courseware-annotator](skills/courseware-annotator/) | 把课件 PDF 变成本机可批注的阅读工作台：页面上点选行/公式块/框选区域写问题，批注存「页码 + 归一化坐标」；用户把「复制提问」发进对话后，agent 按坐标从 300 dpi 页图裁剪复核（文字层丢公式信息也不影响定位），再把解答写回、页面自动刷新。配套 5 个脚本（创建 / 构建 / 服务 / 阅卷 / 自检）与离线前端（KaTeX + marked） |
| [meeting-transcript-correction](skills/meeting-transcript-correction/) | 会议录音转写校正：用现场 PPT/白板照片、上下文与学校/机构/论文/标准等公开来源，找出可确认的听写错误、缺失与矛盾，产出「校正版 + 校正说明 + 幻灯片原文」。默认学术资产模式（经权威来源确认后可直接改正原文错误，保留原词与依据），也可切到逐字保真模式；内含证据分级、产出模板、裁图脚本与一致性自检脚本 |
| [alas-ctrl](skills/alas-ctrl/) | 碧蓝航线自动化脚本 ALAS 的控制与监控层：查状态、启停调度器、调任务开关与时间、改运营设置、诊断卡死与人工接管、跑看门狗自愈。不改 ALAS 源码，只依赖配置与日志；一切能由 ALAS 完成的玩法都通过改任务配置驱动，不自行点屏幕。含授权分级（读/进程/调度/设置/资源）与状态机（RUNNING/WAITING/STUCK/NEEDS_HUMAN/DOWN/CONFLICT） |
| [conversation-import-to-dsh](skills/conversation-import-to-dsh/) | 把其他 Agent 应用的历史对话（WorkBuddy / CodeBuddy 系，及任何有本地事件流的 agent）重建为原生 DSH 会话：可读、可续聊、出现在 GUI 列表。含判断来源完整性（网页分享链接只留最近约 100 轮且首轮被截断，完整历史只在本机事件流）、生成 Session v4 文件、校验、安装入账的 7 个脚本；专治导入后 `at least one tool must have defer_loading=false` 与 `system/message requires a protected first surface head` 两个坑 |
| [agents-profile](skills/agents-profile/) | 把 `agents/profiles/` 下的跨项目知识内联进项目 `AGENTS.md`。profiles 不会被任何 Agent 自动加载，只有内联后才进入上下文；内联区带来源与内容哈希，可幂等重跑、可检测过期。审计环节强制交给 subagent 只读执行，产出 proposal 由人审阅后再机械写入 |

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
