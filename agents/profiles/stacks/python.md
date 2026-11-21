---
name: stacks/python
inline-when:
  any:
    - has-file: "**/pyproject.toml"
    - has-file: "**/requirements*.txt"
    - has-file: "**/*.py"
    - project-flag: python
exclude-when:
  any:
    - project-flag: no-python
last-verified: 2026-11-21
---

# stacks/python

**适用**：以 Python 为主要实现语言的项目（后端、工具脚本、数据流水线）。
**来源**：`mozunitor`、`handmaid`、`cs2-match-predictor`、`daily-news`、`workspace` 的实际约定。

<!-- anchor: deps -->
## 依赖

- **标准库优先**。加第三方依赖前先问：这件事非得在依赖里做吗。能一个包解决就不要两个。
- 依赖声明要么 `requirements.txt`，要么 `pyproject.toml`，不要两套并存。
- 中文 Windows 上 `requirements.txt` 必须带 **UTF-8 BOM**：旧 pip 按 locale 的 GBK 解码，
  中文注释会让 `pip install -r` 直接崩在 `UnicodeDecodeError`。
- 依赖树小的项目，`requirements.txt` 里只写直接依赖与最低版本，不锁全量传递依赖。

<!-- anchor: editable-install -->
## 可编辑安装与版本

用 `src` 布局 + `pyproject.toml` 的项目，本地安装走可编辑模式：

```bash
pip install -e ".[dev]"
```

- 依赖分 `dependencies` 与 `[project.optional-dependencies].dev`，测试工具只进 dev 组。
- 不要用 `pip install -e .` 省略 extras，否则 pytest 等开发依赖缺失。
- 不要靠 `PYTHONPATH` 拼路径暴露开发入口。
- Python 版本下限写进项目文档（如 `>= 3.11`），不要靠「本机能跑」。

<!-- anchor: code-conventions -->
## 代码约定

- 路径一律 `pathlib.Path`，不要用字符串拼 `\`；读外部数据时用绝对路径。
- 日志用 `logging.getLogger(__name__)`，不要 `print` 打生产路径。
- 命名：函数与变量 `snake_case`、类 `PascalCase`、模块级常量 `UPPER_SNAKE_CASE`。
- 数据结构默认 `@dataclass(frozen=True, slots=True)`；确需可变语义时才用普通 `@dataclass`。
- 外部数据路径暴露为可覆盖的字段（构造参数或 dataclass 字段），测试通过覆盖路径注入，
  不要在模块顶层写死。

<!-- anchor: error-handling -->
## 错误处理

三档分明，不要混用：

1. **解析器遇未知输入** → `warn` 并继续（容忍未知前缀、保留原始行），不要 crash。
2. **运行时数据缺失** → 抛带明确信息的异常，不要返回 `None` 让调用方猜。
3. **空输入** → 返回 `[]` 或空结构，不抛异常。

<!-- anchor: docs -->
## 文档

- 对外 API 的 docstring 用 reStructuredText 风格（`:param:` / `:returns:` / `:raises:`），
  可用英文书写（面向行业惯例）；面向本项目的代码注释仍用中文。这个分工要在项目文档里写明，
  否则会被全局「注释用中文」一刀切。
- 模块内用 `Responsibility` / `Implementation outline` / `Edge cases` 三段说明契约。

<!-- anchor: format-test -->
## 格式化与测试

- 格式化 `black` + `flake8`（或项目既有等价物）；不要两套风格并存。
- 测试用 `pytest`，不要自造测试框架。
- 有 `--test` 或 `--self-check` 类入口的，要能脱离主流程单独跑。

<!-- anchor: directml-dll -->
## DirectML 与原生 DLL

onnxruntime-directml 依赖仓库根目录或同级的 CUDA / cuDNN `*.dll`。换机器或重装环境后先确认 DLL 齐全，再排查推理报错。

CPU 与 GPU 两条推理路径要同时维护：改识别参数或后处理时两边都验证。只测一条路径等于没测。

<!-- anchor: safe-print -->
## 控制台输出的编码兜底

Windows 下 Python 的 `sys.stdout.encoding` 默认是控制台代码页（如 cp936）。中文路径或非 GBK 字符会直接抛 `UnicodeEncodeError`。

统一走一个 `safe_print` 封装，在进程启动时显式设置输出编码，不要在每处 `print` 前单独处理。
