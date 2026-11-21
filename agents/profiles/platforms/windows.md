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
last-verified: 2026-11-21
---

# platforms/windows

Windows 平台上的硬约束。每条都来自实际踩过的坑，不是通用建议。

**来源**：Mozunitor 的 BOM / GBK / 会话 / 退出码条款，keysight-pam4 的控制台编码，
scout-python 组的 Windows 项，cpp 组的编译环境。

<!-- anchor: powershell-bom -->
## PowerShell 脚本编码

`powershell.exe`（Windows PowerShell 5.1）执行 `.ps1` 时按系统 ANSI 代码页解码源文件。系统代码页为 936 时，UTF-8 无 BOM 的中文会被拆成乱码字节，引号与括号配对错位，报出与真实问题无关的行号。

| 文件类型 | 要求 | 原因 |
| --- | --- | --- |
| `.ps1` | **UTF-8 BOM** | 5.1 读无 BOM 脚本按 ANSI 解析，含中文时静默少做一件事 |
| `.vbs` | **GBK / ANSI** | WSH 按 ANSI 读，存 UTF-8 会路径失效 |
| `requirements.txt` | **UTF-8 BOM** | 旧 pip 按 locale 解码，中文注释会崩 |
| 其他文本 | UTF-8 无 BOM | 默认 |

- 写 `.ps1` 一律存为 UTF-8 with BOM：
  `[System.IO.File]::WriteAllText($p, $s, (New-Object System.Text.UTF8Encoding($true)))`
- 编辑器保存会抹掉 BOM。改完 `.ps1` 跑一次 BOM 检查（`--fix` 补上），并在验收脚本里断言它。
- 解析失败且报错位置与代码内容对不上时，先怀疑源码编码，不要顺着错误行号去改逻辑。

<!-- anchor: console-encoding -->
## 控制台编码

`[Console]::OutputEncoding` 只统一收/发字节编码，**不改变已启动进程对源文件的解码方式**。两者是独立的两层：

- 收/发层：`[Console]::OutputEncoding`、`$OutputEncoding`、`chcp`
- 源文件解码层：由 `powershell.exe` 启动时按 BOM / 系统代码页判定

因此固定输出为 UTF-8 之后，5.1 读无 BOM 脚本仍会失败。不要在控制台编码上找源文件编码问题的解。

中文 Windows 控制台是 GBK：输出里不要放 GBK 装不下的符号（`✗`、部分全角符号），`stdout` / `stderr` 用 `errors=replace`。这类地方「本机跑得好好的」不算证据。

<!-- anchor: script-ascii-only -->
## 启动脚本只用 ASCII

被 `.ps1` 启动器、计划任务、服务包装脚本加载的入口脚本，正文全部使用 ASCII，或确保带 BOM。这类脚本一旦因编码解析失败，失败发生在最外层，外部只能看到「服务起不来」，排查成本远高于普通脚本。

注释里也不要写中文，除非确认该文件带 BOM。

<!-- anchor: cli-encoding -->
## 命令行与编码传递

- PowerShell 的 `-Command "& script"` 会吞脚本退出码（`exit 3` 回来变 `1`）。写成
  `[Console]::OutputEncoding=…; & $env:SCRIPT_PATH; exit $LASTEXITCODE`，或用 `-File`。
  同时满足三件事：输出强制 UTF-8、退出码正确传播、命令串是常量。
- `PowerShell` 变量名不区分大小写，`[switch]` 参数整份脚本带类型约束：开关参数不要与局部变量
  撞名，否则赋值不生效、变量保持 `$true`，脚本静默少做一件事。
- 经 SSH 回来的 PowerShell 输出是 UTF-16LE：远端命令前加
  `[Console]::OutputEncoding=[Text.Encoding]::UTF8;`，本机侧按实际编码解码（不要固定 utf-8）。
  两处缺一都会让中文变 `U+FFFD`。
- 不要用 `Get-Content` 直接判读 UTF-8 日志：控制台编码会把中文显示成乱码，误导排查。

<!-- anchor: path-process -->
## 路径与进程

- 项目路径含非 ASCII 字符会让 Android AGP 在配置阶段直接失败；`android.overridePathCheck=true`
  只绕过配置阶段，aapt2 / NDK 层面的路径问题仍可能出现。
- WMI 起进程须传 `ProcessStartupInformation` 且 `ShowWindow = 0`，且它只压制**第一个**窗口；
  `pywebview` 这类 WinForms 窗口会显式 `SW_SHOW` 盖过 STARTUPINFO，压不掉。
- 无控制台进程（`pythonw`、WMI 拉起）没有可靠 stdout：必须重定向到日志文件，否则诊断信息消失。
- Session 0 没有交互桌面（窗口站 `Service-0x0-3e7$`）：只跑后端、跳过窗口与托盘；远端要托盘
  只能经计划任务 `/sc onlogon /it`。
- `CommandLine` 只对调用方**自己会话**里的进程可读；跨会话读不到是权限语义，不是采集坏了。
- `ctypes` 调 Win32 必须显式声明 `argtypes` / `restype`，否则 HANDLE 被按 `c_int` 截断后
  静默返回 0。

<!-- anchor: dir-permissions -->
## 目录与权限

- 网络共享优先用 UNC 映射（`\\host\share`）而不是管理共享（`host\D$`）：后者权限更严，
  且部分工具链对 `$` 解析方式不同。
- 计划任务、Windows 服务、进程三种探测方式各有可读边界；跨会话判断「常驻任务在不在跑」优先
  用计划任务状态（`Running` 即 up），拿不到 mem/cpu 是可接受的代价。
