---
name: courseware-annotator
description: >
  把 PDF 课件变成本机可批注的阅读工作台：页面上点选行/公式块/框选区域写下问题，批注实时保存；
  用户把「复制提问」发进对话后，agent 读取批注、按坐标从 300 dpi 页图裁剪复核（文字层丢公式
  信息也不影响定位），再把解答写回，页面自动刷新。用于「课件太长、公式推导看不懂，需要一边读
  一边指着问」的场景，也适合把课程问答沉淀成带页码定位的复习笔记。触发词：课件批注、把课件
  变成可批注页面、实时批注、指着公式提问、课件里标记问题、annotate courseware、
  courseware workbench、PDF 批注工作台。不用于：只想改 HTML 页面的元素（用
  visual-page-editor）；只要课件摘要/笔记而不需要批注交互；没有 PDF/PPT 源文件；或只是
  问一个公式（直接看图回答更快）。
version: 1.0.1
---

# courseware-annotator（课件 → 可批注工作台 → 指着问）

把课件变成「用户能点着标、agent 能按坐标复核」的本地工作台。
核心不是把 PDF 转成文字，而是**始终保留 300 dpi 页图作为真身**：文字层只负责选中、搜索和引用，
批注存「页码 + 归一化坐标」，所以公式即使被读成乱码，位置仍然准确，agent 可以按坐标裁剪复核。

## 何时使用

用：

- 用户有一批课件 PDF（或能先转成 PDF 的 PPTX），想边读边标、边标边问
- 用户说「公式看不懂 / 这页讲得粗略 / 前置知识忘了」，需要指着具体位置提问
- 需要把多轮问答沉淀成带页码定位的复习笔记

不用：

- 页面是 HTML、要改的是源码 → `visual-page-editor`
- 只要摘要、思维导图、整章讲解，不需要批注交互
- 没有源文件、只有截图；或只是问一个公式（直接看截图回答更快）

## 工作流

### 0. 环境检查

需要 Python 3.10+、Pillow、Poppler 的 `pdftoppm` / `pdftohtml` / `pdfinfo`。
缺工具时 `create_workbench.py` 会直接报出缺哪一个。PPTX 先用 LibreOffice 转 PDF
（`soffice --headless --convert-to pdf <pptx>`），本 skill 只吃 PDF。

### 1. 创建工作台

```bash
python scripts/create_workbench.py --out <工作台目录> \
  --pdf <课件1.pdf> [--pdf <课件2.pdf> ...] \
  --title "<课程名>" \
  [--title-for "<课件1.pdf>=<章节标题>"]... \
  [--dpi 300]
```

- 每个 PDF 一章；章节标题默认取 PDF 元数据 `Title`，取不到用文件名，`--title-for` 可覆盖。
- 默认 300 dpi 无损 WebP，一页约 100–150 KB；200 页约 25 MB，构建 1–3 分钟。
- 生成 `workbench.json`、`web/`、`scripts/`、`README.md`、`启动工作台.bat`，并自动构建 `data/`、`img/`。
- 只想先看结构：`--no-build`。

### 2. 启动（后台）

```bash
python <工作台>/scripts/serve_workbench.py --root <工作台> --open
```

- 只监听 `127.0.0.1:8765`；端口占用用 `--port`。
- 作为宿主后台任务启动后，用 `curl -s http://127.0.0.1:8765/api/health` 验证，再让用户打开 URL。
- 页面每 1.5 秒轮询批注与解答，写回后自动刷新。

### 3. 用户批注

- `Alt+A` 或「批注」进入批注模式；点一行 = 批注该行；拖选 = 批注所选；`Shift+拖拽` = 框选公式/图形。
- 浮层可切「这一行 / 公式块 / 整段 / 整页」；输入框上方是 KaTeX 公式按钮，下方实时预览。
- 图钉可拖动换行（重新锚定），浮层拖标题栏可挪开。
- 标完点「复制提问」，把生成的一段话贴进对话。

### 4. agent 处理批注（核心）

用户发来「复制提问」后：

```bash
python <工作台>/scripts/review_workbench.py --root <工作台> --list    # 还有哪些没答
python <工作台>/scripts/review_workbench.py --root <工作台> --crops   # 出裁剪图
```

`--crops` 为每条待回答批注生成两张图（默认在 `<工作台>/_tmp/crops/`）：

- `<id>.png`：按批注坐标裁出的局部图；
- `<id>-context.png`：整页 + 红框，用来确认公式/图形在完整版面中的位置。

**必须看图再答**：文字层会丢分数线、正负号、矩阵括号（例如 `\frac{1}{k}\beta` 可能被读成 `1kβ`）。
读图后把解答写成 Markdown 文件，再：

```bash
python <工作台>/scripts/review_workbench.py --root <工作台> --set <批注id> <解答.md>
```

页面 1–2 秒内自动出现解答；**不要重启服务、不要手改 answers.json**。

解答结构按问题取舍：一句话结论 → 推导/说明 → 前置知识（用户基础薄弱时必给）→ 易错点。
公式用 `$...$` / `$$...$$`，页面用 KaTeX 渲染。

### 5. 收尾与迭代

- 自检：`python <工作台>/scripts/selftest_workbench.py --root <工作台>`
- 只重建文字层：`build_workbench.py --root <工作台> --text-only`（约 2 秒）
- 换分辨率重建：`--dpi 240`（快、小）或 `--dpi 400`（清晰）
- 批量写解答：`review_workbench.py --set-json answers.json`（`{id: md}` 或 `{id: {md}}`）
- 导出笔记：页面「导出笔记」下载 Markdown。

## 关键约定

- **不要直接改 `data/annotations.json`**：服务维护它，人工改会和内存状态打架；改锚点/删除走页面或 API。
- **只写 `data/answers.json`（或经 review 工具）**：服务只读它，页面轮询刷新。
- `data/manifest.json`、`img/`、`data/pages/` 是构建产物，可重建，不要手改。
- 批注坐标是相对页面的 0–1 归一化值，与缩放、dpi 无关。
- 工作台目录可整体移动；`workbench.json` 里的 PDF 路径是相对工作台的。

## 常见坑

- **文字层公式乱序**：正常现象；定位靠坐标 + 页图，不靠 quote。
- **矩阵/多行公式**：单行点击只框到一角；让用户 `Shift+拖拽` 框选，或点浮层里的「公式块」候选。
- **端口占用**：`serve_workbench.py --port 8800`；`启动工作台.bat` 已处理「已在运行则直接开页面」。
- **双击 .bat 后端口无服务**：启动脚本必须是 CRLF 换行（UTF-8 + `chcp 65001` 下 LF 会让 cmd 解析错位）；重新用 `create_workbench.py` 生成，或按 `references/workbench.md` 排查表重写。
- **页面没有新功能**：前端 JS 会缓存，`Ctrl+R` 刷新一次。
- **服务重启后**：批注与解答在磁盘上不会丢，用同一工作台目录重启即可。
- **PPTX**：先转 PDF；若转成「一页一图」没有文字层，仍可批注，只是搜索退化。

## 文件

- `scripts/create_workbench.py` 建工作台并构建（一次性入口）
- `scripts/build_workbench.py` PDF → 页图 + 文字层 + manifest
- `scripts/serve_workbench.py` 本地服务（静态 + `/api/state` + `/api/annotations`）
- `scripts/review_workbench.py` 看批注 / 出裁剪图 / 写解答（agent 侧）
- `scripts/selftest_workbench.py` 端到端自检
- `assets/web/` 阅读器前端（批注层 + KaTeX + marked，离线可用）
- `assets/README.template.md`、`assets/launcher.bat` 工作台模板
- `references/workbench.md` 数据格式、接口、坐标与排查细节
