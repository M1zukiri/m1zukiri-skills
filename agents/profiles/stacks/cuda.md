---
name: stacks/cuda
inline-when:
  any:
    - has-file: "**/*.cu"
    - has-file: "**/*.cuh"
    - project-flag: cuda
exclude-when:
  any:
    - project-flag: no-cuda
last-verified: 2026-11-21
---

# stacks/cuda

**适用**：CPU 实现已存在、需要加 GPU 路径的 C++ / CUDA 项目。
**来源**：cpp0623、cpp0706、mdzct-xqwaq、cuda-dsp-port 四份文档中复现的条款（内容较窄，
按需声明即可）。

<!-- anchor: gpu-optional -->
## GPU 路径是可选的

- GPU 实现必须由宏或开关控制，未启用时纯 CPU 可编译、可运行。
- 保留 CPU 实现作对照，不因为「有 GPU 版」就删掉 CPU 版。
- CPU 与 GPU 实现**同名同接口**，输入输出 ABI 一致，切换实现不改调用方。

<!-- anchor: numeric-consistency -->
## 数值一致性

- CPU 与 GPU 的数值一致性必须给出**显式阈值**，且按 float32 / float64 分开给。
- 阈值写进文档与验收脚本，不要凭「看起来一样」。

<!-- anchor: timing -->
## 计时

- GPU 计时前后要同步（`cudaDeviceSynchronize`），否则测到的是排队时间。
- 分别报 kernel-only 与 end-to-end 两个数；重复多次取 mean ± std，去极值。

<!-- anchor: vram -->
## 显存

- 显存占用要按架构参数实算（层数 × KV heads × key/value 长度这类），不凭感觉估。
- 精度与显存的取舍要落进文档，写清选了什么、放弃了什么。
