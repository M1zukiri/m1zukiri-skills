# AGENTS.md（指针，已停止维护）

> **本文件自 2026-10-20 起不再维护。** 全局行为规范的唯一权威是
> [`m1zukiri-profiles-md/global/AGENTS.md`](https://github.com/M1zukiri/m1zukiri-profiles-md/blob/main/global/AGENTS.md)。
>
> 本机三处副本（`~/.dsh`、`~/.codex`、`~/.omp/agent`）与它逐字节一致；项目级约束由该仓库的
> `profiles/` 按项目声明块提供。

两个仓库的分工：

| 仓库 | 负责 |
| --- | --- |
| `m1zukiri-skills` | 自建 skills（`skills/`）、外部 skills 清单（`EXTERNAL_SKILLS.md`）、Agent **配置模板**（`agents/config/`） |
| `m1zukiri-profiles-md` | 全局行为规范（`global/AGENTS.md`）、可组合的原子 profile（`profiles/`）、各项目的约束与进度（`projects/`） |

改行为规范请到 profiles 仓库；**不要在本文件上继续追加条款**。
