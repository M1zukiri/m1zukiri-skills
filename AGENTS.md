# AGENTS.md · m1zukiri-skills

<!-- profile
repo: M1zukiri/m1zukiri-profiles-md
modes: -
stacks: -
platforms: windows
domains: -
contexts: -
-->

个人 skill 与 Agent 环境配置的公开仓库：自建 skills、外部 skills 登记清单、Agent 配置模板。
仓库无全局构建与测试，改动主体是 Markdown / YAML / JSON 模板。

**行为规范不在本仓库**：唯一权威是 `m1zukiri-profiles-md/global/AGENTS.md`（本仓库
`agents/AGENTS.md` 已改为指向它的指针）。本文件只记仓库维护规则。

## 开工前必读

| profile | 什么时候必须读 |
| --- | --- |
| `platforms/windows` | 改 `agents/config/` 模板、含路径或编码要求的配置前 |

`modes` / `stacks` / `domains` / `contexts` 均为 `-`：没有代码、没有构建，三种活动模式都不成立。

## 仓库定位与目录

| 路径 | 作用 | 规则 |
| --- | --- | --- |
| `skills/` | 自建（原创）skills，目录名即 skill 名 | 唯一允许镜像进仓库的 skill 来源 |
| `EXTERNAL_SKILLS.md` | 外部 skills 清单 | 只登记不镜像 |
| `agents/AGENTS.md` | 全局行为规范指针 | 不要往这里写行为规范 |
| `agents/config/config.yml` | OMP 代理配置模板 | 不含凭据 |
| `agents/config/settings.template.json` | 配置模板 | 仅占位符，不含真实路径 |
| `README.md` | 使用说明与自建 skills 表 | 增删 skill 时同步 |

当前自建 skills：`rhizome`（搜索纪律）、`colorful-palette`（含 `references/` 数据）、
`gbt7714-citation`（含 `scripts/`）、`visual-page-editor`（含 `assets/`、`references/`、`scripts/`）、
`courseware-annotator`（含 `assets/`、`references/`、`scripts/`）。

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
| `agents/AGENTS.md` | 指针文件，不必读 |
