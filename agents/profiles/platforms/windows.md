---
name: platforms/windows
inline-when:
  any:
    - has-file: "**/*.ps1"
    - has-file: "**/*.bat"
    - has-file: "**/*.cmd"
    - project-flag: windows
exclude-when:
  any:
    - project-flag: linux-only
last-verified: 2026-11-20
---

# platforms/windows

Windows 平台上的硬约束。每条都来自实际踩过的坑，不是通用建议。

<!-- anchor: powershell-bom -->
## PowerShell 脚本编码

`powershell.exe`（Windows PowerShell 5.1）执行 `.ps1` 时按系统 ANSI 代码页解码源文件。系统代码页为 936 时，UTF-8 无 BOM 的中文会被拆成乱码字节，引号与括号配对错位，报出与真实问题无关的行号。

- 写 `.ps1` 一律存为 UTF-8 with BOM：
  `[System.IO.File]::WriteAllText($p, $s, (New-Object System.Text.UTF8Encoding($true)))`
- 执行脚本优先 `pwsh`（PowerShell 7 原生按 UTF-8 读源文件），不要默认 `powershell`。
- 解析失败且报错位置与代码内容对不上时，先怀疑源码编码，不要顺着错误行号去改逻辑。

<!-- anchor: console-encoding -->
## 控制台编码

`[Console]::OutputEncoding` 只统一收/发字节编码，**不改变已启动进程对源文件的解码方式**。两者是独立的两层：

- 收/发层：`[Console]::OutputEncoding`、`$OutputEncoding`、`chcp`
- 源文件解码层：由 `powershell.exe` 启动时按 BOM / 系统代码页判定

因此固定输出为 UTF-8 之后，5.1 读无 BOM 脚本仍会失败。不要在控制台编码上找源文件编码问题的解。

<!-- anchor: script-ascii-only -->
## 启动脚本只用 ASCII

被 `.ps1` 启动器、计划任务、服务包装脚本加载的入口脚本，正文全部使用 ASCII，或确保带 BOM。这类脚本一旦因编码解析失败，失败发生在最外层，外部只能看到「服务起不来」，排查成本远高于普通脚本。

注释里也不要写中文，除非确认该文件带 BOM。
