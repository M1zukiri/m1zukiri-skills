---
name: stacks/cpp
inline-when:
  any:
    - has-file: "**/*.cpp"
    - has-file: "**/*.h"
    - project-flag: cpp
exclude-when:
  any:
    - project-flag: no-cpp
last-verified: 2026-11-21
---

# stacks/cpp

**适用**：C++ 实现的项目，尤其是手写构建脚本、MSVC 工具链、与参考实现对照的工程。
**来源**：cpp0623 / cpp0706 / cuda-dsp-port / dbi-dsp / mdzct-xqwaq 五个项目的逐字复现条款。

> 注意：这四个 DSP 项目是同一条代码血统的快照与分叉，不是四个独立工程。条款的「复用证据」
> 说明它被几份文档需要，不代表独立收敛。判真通用时以血统外的项目为准。

<!-- anchor: layering-interface -->
## 分层与接口

- 三层架构 L0 → L1 → L2 **单向**，禁止跳层。L1 是模块层，L2 是底层函数。
- L2 纯函数：无状态、无 I/O、不读全局配置。
- L3 子函数只在母函数内可见，不外露。
- L1 返回**命名 struct**，禁止 `std::tuple`：字段名是契约的一部分。
- 除 `main.cpp` 外全部 `.hpp` + `#pragma once`。
- L2 命名空间 `dbi::<子模块>::`；不要用全局命名空间放实现。

<!-- anchor: naming-format -->
## 命名与格式

- 类型 `CamelCase`、变量与函数 `snake_case`、常量 `SCREAMING_SNAKE_CASE`。
- **例外**：L1 函数名沿用参考实现（MATLAB）原名，不强行统一大小写 —— 可追溯性优先于风格一致。
- 4 空格缩进、K&R 花括号、行宽 ≤ 120、单行必加 `{}`。
- `include` 顺序：标准库 → 第三方 → L2 → L1。
- 头文件全局禁止 `using namespace`。

<!-- anchor: comments-header -->
## 注释与文件头

文件头三要素：文件名、**参考实现对照**（文件 + 行号 / 函数名）、创建时间（精确到秒）。

- 参考实现是 1-based、C++ 是 0-based：**每处索引转换都要注释原文行号**。
- 注释写意图与约束，不复述代码。

<!-- anchor: build -->
## 构建

- 手写 `.bat` 直接调 `cl.exe`，**不用** CMake / MSBuild / vcpkg，除非项目已确立别的方案。
- 脚本先 `call vcvarsall.bat x64`，再编译。
- 编译标志：`/O2 /EHsc /std:c++17 /utf-8 /D_USE_MATH_DEFINES`。`/utf-8` 是中文注释与字符串
  能正确编译的必要条件。
- 第三方依赖 vendored 到 `third_party/`，不引入包管理器。
- 构建命令、产物路径、运行入口写进文档。

<!-- anchor: numeric-parallel -->
## 数值与并行

- Eigen：向量化、`Ref` / `segment` 避免深拷贝、FFT 核预计算，不在热循环里分配。
- OpenMP 用于通道级并行；DLL 或会被外部线程调用的代码禁用内层并行。
- 随机源独立播种，种子写进结果文件。
- 计时：分级调试计时；中间数据导出到固定路径（如 `output/L{N}/{module}/{var}.csv`）；
  环境变量与 CLI 两种入口等价。

<!-- anchor: tests-exceptions -->
## 测试与异常

- 单元测试用 doctest。
- 逐阶段 golden vectors：每个 stage 一个固定目录，与参考实现逐步对齐，不只比最终指标。
- 异常策略：L1 / L2 抛 `std::runtime_error`；入口捕获并转错误码；禁止 `exit` / `abort`。
- DLL 的 C ABI：buffer 格式、错误码规则写进头文件注释，列间距与步长约定不可隐式。
