# NOTES · m1zukiri-skills

> 路线、进度、当前状态与待决事项。每完成一个可验证节点追加一次。

## 当前状态（2026-11-16）

- 已完成：`AGENTS.md` 改为纯仓库维护规则 + 声明块；`agents/AGENTS.md` 已改为指向
  `m1zukiri-profiles-md/global/AGENTS.md` 的指针（提交 `18ca0db`）。
- 新增 `skills/courseware-annotator/`（2026-10-22）：课件 PDF → 可批注工作台 → 按坐标问答，
  5 个脚本 + 离线前端 + 参考文档；已在临时工作台跑通「建批注 → 裁剪图复核 → 写解答 → 自动刷新」。
- 新增 `skills/meeting-transcript-correction/`（2026-11-02）：会议录音转写校正流程，含用户
  指定的转写修改准则、证据分级、三份产出模板、裁图脚本与一致性自检脚本；已同步到
  `~/.dsh/skills/` 与 `~/.omp/skills/`。
- 新增 `skills/alas-ctrl/`（2026-11-16）：碧蓝航线 ALAS 的控制与监控层，`alasctl.py` 十一类子命令
  + `alaswatch.py` 看门狗 + 四份 references；`selftest.py` 20 项全通过，真实启停已在
  `emulator-5554` 上跑通。
- 未开始：`alas-ctrl` 的 L2/L4 决策自动化（当前只提供配置能力与知识文档，不含自动编排）；
  `alas-ctrl` 同步到 `~/.dsh/skills/`（待本轮收尾）。
- 未开始：旧同步集清单的归档处置（待用户授权）。

## 进度记录

### 2026-11-16

- 新增 `skills/alas-ctrl/`：把「用 ALAS 自动处理碧蓝航线全部事务」固化为 skill。
  定位是 ALAS 之上的控制与监控层，不替代 ALAS、不改其源码。
  - `scripts/alasctl.py`：`doctor` / `status` / `tasks` / `log` / `errors` / `cfg get|set` /
    `task on|off|now|at|in` / `start` / `stop` / `perm` / `watch`。
  - `scripts/alaswatch.py`：看门狗，按状态机自愈（DOWN 自动拉起、STUCK 宽限 10 分钟、
    NEEDS_HUMAN 停止重启并写告警）。
  - `scripts/_logparse.py`：把折行日志还原成逻辑行后判定 6 种状态。
  - `scripts/_auth.py`：手机应用式授权（read / process / schedule / settings / resource）。
  - `scripts/selftest.py`：20 项自测，覆盖状态机 7 种场景、折行还原、安全点、时长解析、
    NextRun 上限、授权默认值。
- 关键事实（只读核对得出，写入 references 供后续复用）：
  - WebUI 是 PyWebIO，只有 `GET /` 与 WebSocket `/`，**没有 REST**，因此不逆向它。
  - 调度完全由 `config/alas.json` 的 `Scheduler.Enable` / `NextRun` 驱动；改文件后被
    mtime 轮询热重载（空闲 5s、任务中在战斗结算点）。
  - 日志必须锁定 `_alas.txt`：`_gui.txt` 是 WebUI 主进程、`_-c.txt` 是 WebUI 子进程，
    后者会打印 `Pending tasks` 造成误判。
  - `args.json` 的 `type` / `display` 可预判哪些字段写了会被 ALAS 强制覆盖，
    比「写完回读文件」可靠——回读文件看不到 ALAS 侧的规范化。
- 验证：`selftest.py` 全通过；在真实环境跑通 `start` → 日志出现 `Start task` → `stop` 找安全点；
  改配置测试后 `config/alas.json` 按 SHA256 校验字节还原。

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
- 准则 v1.1（2026-11-02，经用户确认）：把「发音接近」扩展为发音/字母序列/词边界/术语接近；
  「语法唯一确定」限定为功能词与结构词；数据条款改为「与图片或公开资料明显不符」，常识只触发
  存疑；v1.0 原文存档在 `references/rules.md` 附录。
- 准则 v1.2（2026-11-02，经用户确认）：增加「学术资产 / 逐字保真」双模式，默认资产模式；
  「幻灯片不替代口播」只在保真模式成立，资产模式允许经权威来源确认后直接改正原文的数据、
  术语、专名与事实表述，但须保留原词、来源并声明「整理版，非逐字稿」。

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

## 待观察：agents/profile 机制的止损条件

2026-11-20 引入 `agents/profiles/` + `agents-profile` skill。该设计有可证伪的退出条件：

- 试点（`E:\Sync\handmaid`）完成后 2 周内，若新增内联 > 3 处且 `check` 报告过 ≥ 1 次真实过期
  → 机制在运转，继续推广。
- 若一次都没跑过 → 说明它只是又一层「声明了但没人用」的抽象，应退回纯单体：
  保留全局 `AGENTS.md` 与各项目文件，删除 `profiles/` 与 skill。

此条仅为提示，不触发任何自动动作。到期由人判断。

### 2026-11-20 agents/profile 机制落地

- `agents/AGENTS.md` 从 879 B 指针恢复为 12983 B 全局规范正文；`agents/sync.ps1` 分发到
  `~/.dsh`、`~/.omp/agent` 并校验逐字节一致；`agents/check-public.ps1` 守公开区敏感信息。
- 新增 `agents/profiles/`：`modes/engineering.md`、`platforms/windows.md`、`stacks/python.md`、
  `stacks/csharp.md`，共 4 文件 11 个锚点。`local/` 放本机手册与项目清单，已 gitignore。
- 新增 skill `skills/agents-profile/`：`list` / `add` / `sync` / `check` / `audit` / `apply`
  六个子命令；`add`/`apply` 幂等；单文件内联上限 24 KB；`audit` 强制由 subagent 只读执行，
  产出 proposal 经人审阅后再机械写入。
- 试点 `E:\Sync\handmaid`：subagent 审计后建议只内联 2 段（`windows#powershell-bom`、
  `csharp#dotnet-build`），`stacks/python` 三段整份不内联（与正文重复、全仓零命中、无对应实现）。
  应用后 9925 B → 11319 B，`check` 通过。
- 审计同时发现知识库本身的错误：`stacks/csharp.md#dotnet-build` 原写「构建产物是 .dll，
  不是可执行文件」，与实际 `OutputType=WinExe`（同时产出 exe 与 dll）冲突，已修正。
  这正是该机制要防的失效类型。
- 试点产出 7 条项目侧 warning（根目录 SPEC 副本缺失、viewer/src 不存在、命令块路径错位、
  被 gitignore 的脚本仍写在文档里、悬空 global/AGENTS.md、版本号漂移），留给项目侧处理。