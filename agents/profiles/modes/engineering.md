---
name: modes/engineering
inline-when:
  any:
    - project-flag: engineering
exclude-when:
  any:
    - project-flag: docs-only
last-verified: 2026-11-20
---

# modes/engineering

改代码时的验证纪律。全局 `AGENTS.md` §1–§5 是行为准则，本文件只补「如何证明这次改动有效」，不重复那些准则。

<!-- anchor: baseline-first -->
## 先取基线再改

改之前先让现有验证跑通一次，记录结果。没跑过基线就动手，出问题时分不清是改坏了还是本来就有问题。

基线包括：构建是否通过、测试是否全绿、关键命令是否产出预期输出。三者取该项目实际有的。

<!-- anchor: same-check-after -->
## 用同一条验证证明改动

改完必须跑**与基线完全相同**的那条验证。换一条更宽松的检查、或只做肉眼确认，都不算验证通过。

改动声称解决的问题，要能被一条可执行的检查复现出来：改前失败、改后通过。做不到就先别改。

<!-- anchor: diff-selfcheck -->
## diff 自查

提交前逐行看一遍 diff，每行问「这行对应哪个需求」。答不上来的行删掉。

特别检查：有没有顺手改的相邻格式、有没有被改动的死代码、有没有调试残留。
