# {{TITLE}} · 批注工作台

把课件 PDF 变成可批注、可提问的本地阅读器：页面是 300 dpi 原图，批注保存「页码 + 归一化坐标」，
文字层只用于选中和搜索。批注与解答都保存在本机，不上传。

## 启动

双击 `启动工作台.bat`，或在 `{{OUT}}` 下执行：

```bash
python scripts/serve_workbench.py --root . --open
```

默认地址 <http://127.0.0.1:8765/>。停止服务用 `Ctrl+C`，批注与解答不会丢失。

## 课件章节

{{CHAPTERS}}

## 使用

- 点右上角「批注」或按 `Alt+A` 进入批注模式；
- 点一行文字 = 批注这一行；拖选文字 = 批注所选；`Shift + 拖拽` = 框选公式/图形；
- 输入框上方是公式按钮，下方实时预览；`Enter` 保存；
- 标完点「复制提问」把问题交给 AI，解答会在 1–2 秒内自动写回页面；
- 图钉可拖动换行，浮层拖标题栏可挪开；右侧面板支持筛选、追问、标记已解决、导出 Markdown。

## 给 AI 的批注处理（agent 侧）

```bash
python scripts/review_workbench.py --root . --list          # 看未回答的批注
python scripts/review_workbench.py --root . --crops         # 出裁剪图 + 红框整页图
python scripts/review_workbench.py --root . --set <id> <md文件>
```

## 重建与自检

```bash
python scripts/build_workbench.py --root .              # 全量重建页图 + 文字层
python scripts/build_workbench.py --root . --text-only  # 只重建文字层
python scripts/selftest_workbench.py --root . --url http://127.0.0.1:8765
```

依赖 Python 3.10+、Pillow、Poppler（`pdftoppm` / `pdftohtml` / `pdfinfo`）。

## 目录

```
workbench.json   工作台配置（标题 / 章节 / dpi）
web/             阅读器前端（KaTeX、marked 已内置，离线可用）
scripts/         build / serve / review / selftest
data/            manifest、文字层、批注、解答
img/             页图（300 dpi 无损 WebP）
```
