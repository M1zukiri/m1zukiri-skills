# NOTES · m1zukiri-skills

> 路线、进度、当前状态与待决事项。每完成一个可验证节点追加一次。

## 当前状态（2026-11-02）

- 已完成：`AGENTS.md` 改为纯仓库维护规则 + 声明块；`agents/AGENTS.md` 已改为指向
  `m1zukiri-profiles-md/global/AGENTS.md` 的指针（提交 `18ca0db`）。
- 新增 `skills/courseware-annotator/`（2026-10-22）：课件 PDF → 可批注工作台 → 按坐标问答，
  5 个脚本 + 离线前端 + 参考文档；已在临时工作台跑通「建批注 → 裁剪图复核 → 写解答 → 自动刷新」。
- 新增 `skills/meeting-transcript-correction/`（2026-11-02）：会议录音转写校正流程，含用户
  指定的转写修改准则、证据分级、三份产出模板、裁图脚本与一致性自检脚本；已同步到
  `~/.dsh/skills/` 与 `~/.omp/skills/`。
- 进行中：`skills/visual-page-editor/` 有未提交改动（5 个修改 + 1 个新增脚本）——不是本轮
  产生的，保持未暂存。
- 未开始：旧同步集清单的归档处置（待用户授权）。

## 进度记录

### 2026-11-02

- 新增 `skills/meeting-transcript-correction/`：把「会议录音转写 + 现场照片 + 公开资料」的校正
  流程固化成 skill。SKILL.md 保留用户指定的转写修改准则（只改脱节/断裂/明显错误，可保留
  不确定与低价值缺失；修改须满足发音、语法、图片、权威来源、用户指定之一），并补充最小编辑、
  不新增信息、说话人口误不改、幻灯片≠口播、逐条留痕、独立复核等必要条款。
- 结构：`references/rules.md`（判定树、证据等级 E1–E6、错误分类、反例）、
  `references/output-templates.md`（校正版/校正说明/幻灯片原文模板）、
  `scripts/crop_slides.py`（幕布裁剪放大）、`scripts/check_corrections.py`（断链/表格/置信度自检）、
  `evals/evals.json`（3 条触发与边界用例）。
- 验证：两个脚本在本机 ACP 2026 记录上跑通（裁剪 1 张、33 行置信度统计 高 18/中 14/低 1，
  断链 0）；负例能报出断链、表格列数不一致、「高置信度但证据存疑」。
- 同步：仓库 `skills/`、`~/.dsh/skills/`、`~/.omp/skills/` 三份，内容一致；README 自建 skills 表已补。

### 2026-10-22

- 新增 `skills/courseware-annotator/`：把「课件 PDF → 可批注工作台 → agent 按坐标问答」固化为 skill。
  入口 `create_workbench.py` 一键建工作台并构建；`build/serve/review/selftest` 各司其职；
  前端（KaTeX + marked）随 skill 分发，离线可用。
- 验证：用 CH1/CH2 两个 PDF（149 页，150 dpi）在临时目录建工作台 33s；浏览器建批注、
  `review --crops` 出局部图 + 红框整页图、`--set` 写解答后页面 2s 内自动刷新；
  `selftest_workbench.py` 全 PASS；`--text-only` 重建 1s。
- 同步：README 自建 skills 表与 AGENTS 当前清单已更新。

### 2026-10-20

- 完成：`AGENTS.md` 删掉与 global 重复的两节（安全红线、Git 约定），保留并压缩四块本项目
  特有内容（自建 skill 规范、外部清单规范、配置同步、`.gitignore` 先补后加）；补上声明块与
  「开工前必读」表；`agents/AGENTS.md` 的指针地位写进文件（不再重复行为规范）。
- 验证：原 `AGENTS.md` 74 行逐项对照——仓库定位/目录进新文件表格，维护规则进「自建 skill
  规范」「外部 skill 清单规范」，配置进「配置同步」，安全红线压成一行（其余由 global 第八节
  承载），Git 约定删除（由 global 第十一节承载）；`agents/` 与 `skills/` 实况用 `ls` 核对。
- 下一步：用一次实际 skill 变更验证「改完同步 README 表」这条是否会被执行。

## 待决事项

- [ ] 旧仓库 `agent-bootstrap` 与旧同步集（`install.sh`、`install.ps1`、`extensions`）的处置
      —— 阻塞原因：本仓库只有文档，看不到安装脚本现状；按用户裁定本轮只记录不改，需确认
      是否归档或删除（属于删除操作，需单独授权）。
- [ ] `agents/AGENTS.md` 是否在下一个版本的安装脚本切换后删除 —— 目前保留指针是为了不让历史
      链接 404。阻塞原因：不知道安装脚本是否仍指向这个路径。
- [ ] `skills/colorful-palette` 与 `agent-bootstrap/skills/colorful-palette` 已分叉 —— 以哪边为
      准。阻塞原因：本仓库侧是改名后（提交 `22208f3`）的新版，旧仓库未跟进；需用户裁定后
      单向删除或同步。
- [ ] `EXTERNAL_SKILLS.md` 头部的「本机安装统计与更新日期」是否仍在维护 —— 阻塞原因：本轮
      只读取了文件大小与目录，未逐条核对统计是否准确。

## 历史结论

- 2026-10-20：同步仓库归属曾有三种说法（`agent-bootstrap`、本仓库 `agents/`、profiles 仓库
  `global/`）。裁定：**行为规范**以 `m1zukiri-profiles-md/global/AGENTS.md` 为唯一权威；
  **skills 与工具配置**的同步集在本仓库。旧仓库名 `omp-bootstrap` 与旧清单进待决。
- 2026-10-20：本仓库原 `agents/AGENTS.md` 与 `agent-bootstrap/AGENTS.md` 归一仓库名后差异仅
  32 行，前者是更新版；内容并入 global 后降级为指针。
- 2026-10-20：确认本仓库无代码、无构建、无测试，三种活动模式都不成立，故 `modes` 声明为 `-`；
  `platforms: windows` 只因为配置模板面向 Windows 环境。
