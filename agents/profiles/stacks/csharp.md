---
name: stacks/csharp
inline-when:
  any:
    - has-file: "**/*.csproj"
    - has-file: "**/*.sln"
    - project-flag: csharp
exclude-when:
  any:
    - project-flag: no-csharp
last-verified: 2026-11-20
---

# stacks/csharp

<!-- anchor: dotnet-build -->
## .NET 构建与 WPF 目标

`net6.0-windows` 的 WPF 项目用 `dotnet build` 产出 DLL 后，由上层工具通过反射或引用调用：

```bash
dotnet build <项目目录>
```

- 构建产物的形态取决于 `OutputType`：`WinExe` 同时产出 `.exe` 与 `.dll`，`Library` 只产 `.dll`。调用方按声明的类型加载，不要假设只有其中一种。
- 需要 `UseWPF=true` 的项目在非 Windows 环境下构建会失败，CI 要指定 Windows runner。
- 反射调用上游内部 API 时，上游一升级就可能断。用版本锁定 + 冒烟测试兜住。

<!-- anchor: license-boundary -->
## 许可证边界

fork 或引用 GPL 系项目时，派生产物同样受 GPL 约束。调用方与 fork 的边界要在动手前划清：只通过反射读 API 与直接复制源码，授权义务不同。

不确定时先确认再写代码，不要留到最后。
