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
last-verified: 2026-11-21
---

# stacks/csharp

**适用**：C# / .NET 项目，尤其是 WPF 桌面应用与带第三方 fork 的工具链。
**来源**：galextractor（WPF / MVVM / 流处理）、handmaid（WPF + Unity 混合）。

<!-- anchor: project-config -->
## 项目配置

- 目标框架写死并统一（如 `net6.0-windows`）；同一解决方案里不要出现两套目标框架。
- 开启 Nullable 与 ImplicitUsings，按需显式处理可空性。
- 零第三方 NuGet 是默认选项：加包前先问能不能用 BCL 解决。
- 不依赖 `.editorconfig` 也算接受，但要有一份说明风格来源的文档。

<!-- anchor: dotnet-build -->
## .NET 构建与产物形态

```bash
dotnet build <项目目录>
```

- 构建产物的形态取决于 `OutputType`：`WinExe` 同时产出 `.exe` 与 `.dll`，`Library` 只产 `.dll`。调用方按声明的类型加载，不要假设只有其中一种。
- `net6.0-windows` 的 WPF 项目需要 `UseWPF=true`，在非 Windows 环境下构建会失败，CI 要指定 Windows runner。
- 反射调用上游内部 API 时，上游一升级就可能断。用版本锁定 + 冒烟测试兜住。

<!-- anchor: wpf-mvvm -->
## WPF 与 MVVM

- `ViewModelBase` + `RelayCommand` 作为最小 MVVM 骨架，不引入重型框架。
- 属性变更走 `INotifyPropertyChanged`，命令可用性由 `CanExecute` 表达，不在 XAML 里写条件。
- 长任务不阻塞 UI 线程：`Task.Run` 包装同步 I/O，UI 更新回 `Dispatcher`。
- 不要用 UI 状态推断内部状态（见全局基线的「准确性与推理效率」）。

<!-- anchor: streams-files -->
## 流与文件

- 读二进制流时记录并恢复流位置（`Position` 保存/还原），不要假设调用方会重开流。
- 资源用 `using` / `await using`；大文件走流式处理，不整份 `ReadAllBytes`。

<!-- anchor: encoding -->
## 编码与文件组织

- 源码文件 UTF-8（可带 BOM，MSVC 与 dotnet 都能处理）。
- 命名与文件组织遵循项目既有约定；新增文件按项目已有的目录语义放置。

<!-- anchor: license-boundary -->
## 许可证边界

fork 或引用 GPL 系项目时，派生产物同样受 GPL 约束。调用方与 fork 的边界要在动手前划清：只通过反射读 API 与直接复制源码，授权义务不同。

不确定时先确认再写代码，不要留到最后。
