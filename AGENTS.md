# AGENTS.md · m1zukiri-skills

<!-- profile
modes: -
stacks: -
platforms: windows
domains: -
contexts: -
-->

个人 skill 与 Agent 环境配置的公开仓库：自建 skills、外部 skills 登记清单、Agent 配置模板。
仓库无全局构建与测试，改动主体是 Markdown / YAML / JSON 模板。

**行为规范正文在 `agents/AGENTS.md`**：那是分发到本机各 Agent 环境（`~/.dsh`、`~/.omp/agent`）
的全局规范源，由 `agents/sync.ps1` 负责同步。**本文件（仓库根 `AGENTS.md`）只记仓库维护规则**，
在仓库内工作时以本文件为准；`agents/AGENTS.md` 不是本目录的维护规则，不要往里写仓库约定。

## 开工前必读

本仓库有 `.ps1` 脚本（`agents/check-public.ps1`、`agents/sync.ps1`），已内联 `platforms/windows`
的相关段落，见文末。改配置模板或脚本前，另需读 `agents/profiles/platforms/windows.md` 全文。

`modes` / `stacks` / `domains` / `contexts` 均为 `-`：没有代码、没有构建，三种活动模式都不成立。

## 仓库定位与目录

| 路径 | 作用 | 规则 |
| --- | --- | --- |
| `skills/` | 自建（原创）skills，目录名即 skill 名 | 唯一允许镜像进仓库的 skill 来源 |
| `EXTERNAL_SKILLS.md` | 外部 skills 清单 | 只登记不镜像 |
| `agents/AGENTS.md` | 全局行为规范正文（分发源） | 改行为规范改这里，再跑 `agents/sync.ps1` |
| `agents/profiles/` | 跨项目知识库，不参与自动加载 | 只写踩过坑且有证据的内容 |
| `agents/check-public.ps1` | 公开前敏感信息扫描 | 提交前执行，命中即失败 |
| `agents/sync.ps1` | 分发全局规范到各 Agent 环境 | 分发后校验逐字节一致 |
| `agents/config/config.yml` | OMP 代理配置模板 | 不含凭据 |
| `agents/config/settings.template.json` | 配置模板 | 仅占位符，不含真实路径 |
| `README.md` | 使用说明与自建 skills 表 | 增删 skill 时同步 |

当前自建 skills：`rhizome`（搜索纪律）、`colorful-palette`（含 `references/` 数据）、
`gbt7714-citation`（含 `scripts/`）、`visual-page-editor`（含 `assets/`、`references/`、`scripts/`）、
`courseware-annotator`（含 `assets/`、`references/`、`scripts/`）、`meeting-transcript-correction`
（含 `references/`、`scripts/`、`evals/`）、`alas-ctrl`（含 `references/`、`scripts/`、`evals/`，
运行时状态写 `state/`，已 gitignore）、`conversation-import-to-dsh`（含 `references/`、`scripts/`）。

## 自建 skill 规范

- 一目录一 skill，目录名即 skill 名，kebab-case 小写英文。
- 必须含 `SKILL.md`，frontmatter 至少两个字段：
  - `name`：与目录名一致。
  - `description`：含触发词，并说明**何时不应触发**（如 rhizome 要求只在用户点名时加载）。
  - 可选 `compatibility`（示例：「需要 web 搜索能力」）。
- 数据、参考文件与辅助脚本放在 skill 目录内的子目录（`references/`、`evals/`、`scripts/`、
  `assets/`），不进仓库根目录。
- 新增或修改 skill 后同步更新 `README.md` 的「自建 skills」表。

## 外部 skill 清单规范

- **只登记，不镜像**：外部 skill 本体及其文件不进本仓库，只记名称、用途、安装地址、许可证。
- 按来源分组，每组一张表；头部维护本机安装统计与更新日期，增减条目时同步更新。

## 配置同步

- **行为规范**：以 `m1zukiri-profiles-md/global/AGENTS.md` 为唯一权威。更新后提交推送，
  同时覆盖本机三处副本（`~/.dsh`、`~/.codex`、`~/.omp/agent`），三处必须逐字节一致。
- **自建 skills 与工具配置模板**：同步集在本仓库 `skills/` 与 `agents/config/`。
- `agents/config/` 只允许模板与脱敏配置；`settings.template.json` 必须保留 `shellPath`
  占位符，真实 `settings.json` 永不入库。
- 新增敏感文件类型时，**先补 `.gitignore` 再 `git add`**（`git add` 前检查 `.gitignore` 是
  global 的要求，先补后加是本仓库的执行顺序）。

## 项目特有的坑

- **同步集曾有三处互相矛盾的说法**（2026-10-20）：旧仓库 `agent-bootstrap` 声明同步集含
  `install.sh` / `install.ps1` / `extensions`，本仓库声明 `agents/`，profiles 仓库声明
  `global/`。裁定后：行为规范看 profiles 仓库，skills 与工具配置看本仓库。旧仓库的处置记在
  `NOTES.md` 待决，不要在本文件里写死。
- **`settings.template.json` 是模板不是配置**：往里写真实路径或 key，会被同步到所有 Agent
  环境，且下一次复制会把真实值带回来。
- **`agents/config/` 与 `agent-bootstrap/config/` 有同名同哈希副本**：迁移已开始、旧副本未删；
  改配置模板只改本仓库这一份，旧副本会误导人。

## 其他文档

| 文档 | 读取时机 |
| --- | --- |
| `NOTES.md` | 待决事项与同步集历史结论 |
| `agents/AGENTS.md` | 全局行为规范正文；仓库内工作时以根 `AGENTS.md` 为准 |

<!-- BEGIN inline: platforms/windows.md#powershell-bom sha=28bf6009 -->
## PowerShell 脚本编码

`powershell.exe`（Windows PowerShell 5.1）执行 `.ps1` 时按系统 ANSI 代码页解码源文件。系统代码页为 936 时，UTF-8 无 BOM 的中文会被拆成乱码字节，引号与括号配对错位，报出与真实问题无关的行号。

- 写 `.ps1` 一律存为 UTF-8 with BOM：
  `[System.IO.File]::WriteAllText($p, $s, (New-Object System.Text.UTF8Encoding($true)))`
- 执行脚本优先 `pwsh`（PowerShell 7 原生按 UTF-8 读源文件），不要默认 `powershell`。
- 解析失败且报错位置与代码内容对不上时，先怀疑源码编码，不要顺着错误行号去改逻辑。
<!-- END inline: platforms/windows.md#powershell-bom -->

<!-- BEGIN inline: platforms/windows.md#console-encoding sha=dd77fa18 -->
## 控制台编码

`[Console]::OutputEncoding` 只统一收/发字节编码，**不改变已启动进程对源文件的解码方式**。两者是独立的两层：

- 收/发层：`[Console]::OutputEncoding`、`$OutputEncoding`、`chcp`
- 源文件解码层：由 `powershell.exe` 启动时按 BOM / 系统代码页判定

因此固定输出为 UTF-8 之后，5.1 读无 BOM 脚本仍会失败。不要在控制台编码上找源文件编码问题的解。
<!-- END inline: platforms/windows.md#console-encoding -->

<!-- BEGIN inline: platforms/windows.md#script-ascii-only sha=f7dd4cd7 -->
## 启动脚本只用 ASCII

被 `.ps1` 启动器、计划任务、服务包装脚本加载的入口脚本，正文全部使用 ASCII，或确保带 BOM。这类脚本一旦因编码解析失败，失败发生在最外层，外部只能看到「服务起不来」，排查成本远高于普通脚本。

注释里也不要写中文，除非确认该文件带 BOM。
<!-- END inline: platforms/windows.md#script-ascii-only -->
