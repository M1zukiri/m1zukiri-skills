---
name: platforms/android-proot
inline-when:
  any:
    - project-flag: android-proot
exclude-when:
  any:
    - project-flag: linux-only
last-verified: 2026-11-21
---

# platforms/android-proot

**适用**：在 Android 手机上的 proot 容器里运行（dsh-go 内置 Ubuntu 环境），没有桌面、
没有可用的系统 root、内存与电量都受限的会话。
**来源**：dsh-go 内置运行时的实测输出（`free`、`df`、`uname`、`getprop`、诊断快照）。

<!-- anchor: runtime-shape -->
## 运行形态

- 这是 Ubuntu 24.04（aarch64）跑在 Android 15 的 proot 里，不是虚拟机也不是真实 root：
  shell 里 `id` 显示 `uid=0`，但 `/proc/self/status` 的真实 Uid 是 App 自己的应用 uid；
  `su`、`/data/adb`、`/system/bin` 列表都不可用。Magisk 装着也不代表本进程能用 root。
- 因此**能改系统设置（无障碍、VPN、应用权限）的只有用户**：自己做不到的事不要反复试，
  停下写清要用户点哪里。
- 会话默认 cwd 是 `/root/workspace`（空目录，无版本控制）；`$HOME` 是 `/root`。
- 后台不可靠：切走 App、系统清内存都可能结束引擎进程。长任务拆成可续跑的小步，
  关键中间结果落到文件，不指望一个进程活到会话结束。

<!-- anchor: sandbox-permissions -->
## 沙箱与权限

- 没有 bubblewrap，也没有 Landlock（`/sys/kernel/security/landlock` 不存在）：
  `workspace-write` 必然被拒。执行命令一律直接申请 `danger-full-access` 并写一句理由，
  不要先试沙箱模式再重试。
- 文件写入范围默认只有会话工作区；要动 `/root/.dsh`、`/sdcard`、`/etc` 这类路径，
  必须在同一次调用里带 `sandbox_permissions`，否则直接失败。

<!-- anchor: device-budget -->
## 设备预算

| 项 | 实测量级 | 做法 |
| --- | --- | --- |
| CPU | 8 核，大小核混合 | 并行编译按 2～4 进程，不要 `-j8` |
| 内存 | 总 3.7 GB，常驻已占 2.9 GB，可用常 <800 MB | 不装重型依赖；Node 已限 `--max-old-space-size=896`，大文件处理走流式 |
| 存储 | `/` 与 `/sdcard` 同一块 22 GB 分区，余 14 GB | 不克隆大仓库、不缓存模型权重；临时文件用完即删 |
| 网络 | 家用 Wi-Fi + 国内 DNS | 见下节 |

<!-- anchor: network -->
## 网络

- `api.github.com`、`raw.githubusercontent.com` 直连可用；`github.com` 直连会被卡在 TLS 阶段
  （超时，不是 404）。需要 `github.com`（网页登录、`git clone`、OAuth 设备码轮询）时，
  先确认用户开着代理（本机装的是 Clash Meta），否则直接说明并请用户开，不要换 IP 硬试。
- 设备上的常见替代：HTTP 客户端用 `python3` 的 `urllib`（镜像里没有 curl / wget / ssh / jq / gh），
  装包走 `apt-get update && apt-get install -y <包>`，npm / pnpm 默认 npmmirror。
- 代理切换后 `/etc/hosts` 里的固定 IP 会破坏按域名分流，用完要撤掉。

<!-- anchor: screen-output -->
## 屏幕与输出

- 显示 720×1280，系统字号被放大过：一行装不下多少字。回复控制在短句 + 短列表，
  代码块宽度按 60 列以内排；宽表格改成纵向列表。
- 需要长输出时给文件路径，不要整段贴屏；产出文件放 `/sdcard/Download/DSH-Go/`。

<!-- anchor: phone-control -->
## 手机操控

- `mcp__phone__screen` / `tap` / `type` / `scroll` 依赖无障碍服务；它没开时整组工具失效，
  只剩 `apps` / `open` / `intent` / `clipboard` / `notify`。读屏失败先看诊断里的
  「无障碍开关」，没开就请用户在 设置 → 手机操控 打开，不要盲点坐标。
- 元素编号只在本次返回的屏幕内有效，每个动作都会返回新屏幕；`tap_xy` 只在元素找不到时用。
- 验证码类的分格输入框（`user-code-0…8`）要逐格输入单个字符，整串输入会被清空。
- 系统设置、支付、银行类界面不碰；`handoff` 交还用户，被拒绝就换路子或问，不绕过。

<!-- anchor: dsh-go-ui -->
## 界面能力（dsh-go）

- 对话界面是 Flutter 原生界面，不是 Harness Web Client。没点名载体时默认改 dsh-go 原生界面：
  外观与布局用 `dsh-go-ui`（`$DSH_HOME/dsh-go/ui.json`），加胶囊 / 菜单项 / 状态条 / 面板 / 工具卡
  用 `dsh-go-plugin`（`$DSH_HOME/dsh-go/plugins/`，装法 `dsh plugin --profile web add`）；
  只有用户明确要做 Cordis 插件或改网页版 / 桌面端时才用官方 cordis 技能，两套目录不要混。
- 可视化视图靠 `dsh-ui` 围栏代码块渲染：先一两句结论再放视图，一条回复最多两个视图，
  围栏里只放一个 JSON 对象（≤4 KB）。比较与趋势用 chart，关键数字用 metric，方案对比用 compare，
  步骤用 steps，需要用户点选用 options / confirm。含 options 的视图放最后并结束该轮。
  不要用视图收集密码、密钥、验证码。
- 用户报障（卡顿、发热、连不上、闪退、插件不生效、操控失败）先读
  `$DSH_HOME/dsh-app/diagnostics.md`，再按 `dsh-go-support` 技能走；报告已脱敏，但仍不要把其中的
  路径与设备信息原样贴出去。

<!-- anchor: local-deploy -->
## 本机部署

- 本机副本由 `agents/sync.ps1` 分发到 `~/.dsh/AGENTS.md` 与 `~/.omp/agent/AGENTS.md`，分发后校验逐字节一致；
  Android 特有的差异**只写在本 profile**，不要塞回全局基线。
- 项目 `AGENTS.md` 的声明块 `platforms: android-proot` 决定它被 `add` 或 `audit` 选中。
