# PUA Extension for pi — 官方轻量版

这个目录是 `tanweai/pua` 的 pi coding agent 适配层。它不依赖网络，不注册危险工具，不管理权限；只做三件事：

1. 在 pi 会话启动前注入简短 PUA diligence context；
2. 通过 tool result 维护共享失败计数 `~/.pua/.failure_count`；
3. 提供 `/pua-on`、`/pua-off`、`/pua-status`、`/pua-reset`。

## 推荐：pi.dev package

本仓库现在提供 pi.dev package 源码：`pi/package/`。

本地安装：

```bash
pi install ./pi/package
```

发布到 npm 后安装：

```bash
pi install npm:@tanweai/pi-pua
```

## 手动安装 extension-only

```bash
mkdir -p ~/.pi/agent/extensions/pua
cp -R ./pi/pua/. ~/.pi/agent/extensions/pua/
```

Windows PowerShell：

```powershell
$target = Join-Path $env:USERPROFILE ".pi\agent\extensions\pua"
New-Item -ItemType Directory -Path $target -Force | Out-Null
Copy-Item -Path .\pi\pua\* -Destination $target -Recurse -Force
```

重启 pi 后使用：

| 命令 | 作用 |
|---|---|
| `/pua-on` | `always_on=true`，当前和后续会话启用 |
| `/pua-off` | `always_on=false` 且 `feedback_frequency=0` |
| `/pua-status` | 查看开关、离线模式、失败计数和配置路径 |
| `/pua-reset` | 清零失败计数 |

## 共享状态

```text
~/.pua/config.json
~/.pua/.failure_count
```

pi 版和 Claude Code / Codex 版共享这两个文件，因此 `/pua-off`、离线模式和失败计数语义一致。

## 边界

- 不自带搜索、MCP、PowerShell、subagent 或权限系统。
- 不替代 pi 的 sandbox / approval / network policy。
- `offline=true` 只表示 PUA 自身不触发联网反馈；真正网络隔离应由运行环境控制。
