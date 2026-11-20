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
last-verified: 2026-11-20
---

# stacks/python

<!-- anchor: editable-install -->
## 可编辑安装与依赖

用 `src` 布局 + `pyproject.toml` 的项目，本地安装走可编辑模式：

```bash
pip install -e ".[dev]"
```

- 依赖分 `dependencies` 与 `[project.optional-dependencies].dev`，测试工具只进 dev 组。
- 装完先跑一次测试确认基线，再改代码。
- 不要用 `pip install -e .` 省略 extras，否则 pytest 等开发依赖缺失。

<!-- anchor: directml-dll -->
## DirectML 与原生 DLL

onnxruntime-directml 依赖仓库根目录或同级的 CUDA / cuDNN `*.dll`。换机器或重装环境后先确认 DLL 齐全，再排查推理报错。

CPU 与 GPU 两条推理路径要同时维护：改识别参数或后处理时两边都验证。只测一条路径等于没测。

<!-- anchor: safe-print -->
## 控制台输出的编码兜底

Windows 下 Python 的 `sys.stdout.encoding` 默认是控制台代码页（如 cp936）。中文路径或非 GBK 字符会直接抛 `UnicodeEncodeError`。

统一走一个 `safe_print` 封装，在进程启动时显式设置输出编码，不要在每处 `print` 前单独处理。
