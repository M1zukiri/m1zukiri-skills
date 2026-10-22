# 批注工作台：数据格式、接口与排查

本文件是实现细节，供 agent 在排查或二次开发时查。日常使用只需看 `SKILL.md`。

## 目录结构

```
<工作台>/
├─ workbench.json          配置：项目名、副标题、dpi、章节列表
├─ web/                    前端（index.html / app.js / app.css / vendor/）
├─ scripts/                build / serve / review / selftest
├─ data/
│  ├─ manifest.json        构建产物：章节清单（页面读它渲染章节标签）
│  ├─ pages/<章>.json      构建产物：每页文字行/段落/标题（归一化坐标）
│  ├─ build_report.json    构建统计
│  ├─ annotations.json     批注（服务写）
│  └─ answers.json         解答（review 工具写，服务只读）
├─ img/<章>/001.webp       页图（300 dpi 无损 WebP）
├─ _tmp/crops/             review 工具生成的裁剪图
├─ README.md
└─ 启动工作台.bat
```

`web/`、`scripts/` 由 `create_workbench.py` 从 skill 复制；`data/pages`、`img` 可随时重建。

## workbench.json

```json
{
  "schema": 1,
  "title": "线性代数",
  "subtitle": "课件批注工作台",
  "dpi": 300,
  "chapters": [
    { "id": "CH1", "pdf": "../CH1.pdf", "title": "线性空间与线性变换" }
  ]
}
```

- `pdf` 相对工作台目录（也支持绝对路径）。
- `id` 用于文件名与 API，建议 ASCII；重名时 create 脚本会自动加后缀。

## data/manifest.json

```json
{
  "generated": "2026-10-22T18:30:00+08:00",
  "dpi": 300,
  "project": { "title": "线性代数", "subtitle": "课件批注工作台" },
  "chapters": [
    {
      "id": "CH1", "title": "线性空间与线性变换", "pdf": "../CH1.pdf",
      "pages": 70, "data": "data/pages/CH1.json", "img": "img/CH1"
    }
  ]
}
```

前端从 `/data/manifest.json` 读 `project`（顶栏标题）与 `chapters`（章节标签）；`data` / `img` 是相对工作台根的路径。

## data/pages/<章>.json

```json
{
  "chapter": "CH1",
  "title": "线性空间与线性变换",
  "pdf": "../CH1.pdf",
  "pageW": 680, "pageH": 382,
  "pages": [
    {
      "n": 20,
      "title": "线性空间的性质",
      "lines": [
        { "x": 0.066, "y": 0.353, "w": 0.247, "h": 0.042, "f": 0.0235, "b": 1, "t": "1. V 中的零元素惟一；" }
      ],
      "blocks": [ { "x": 0.066, "y": 0.30, "w": 0.53, "h": 0.20 } ],
      "text": "……"
    }
  ]
}
```

- 坐标全部归一化到 0–1：`x/w` ÷ `pageW`，`y/h` ÷ `pageH`；`f` 是字号 ÷ `pageW`，前端用 `calc(var(--pw) * f)` 还原。
- `b` 是段落索引；`blocks` 是段落矩形（用于「整段」候选）。
- `text` 是整页文字拼接，用于搜索。
- 文字层由 `pdftohtml -xml` 提取后按基线聚成行；水印（opacity < 0.5）与页脚被过滤。
- **公式会乱序**：这是 PDF 文字对象顺序决定的，不影响页图与坐标。

## annotations.json

```json
{
  "rev": 41,
  "items": [
    {
      "id": "a-mvj6by2l-x1mbo",
      "ch": "CH1", "page": 20, "kind": "line",
      "rects": [{ "x": 0.344, "y": 0.801, "w": 0.062, "h": 0.060 }],
      "quote": "= 1kβ.",
      "tag": "不懂",
      "q": "这里的 $0\\alpha=\\mathbf{0}$ 用哪条性质？",
      "created": "2026-10-22T14:42:00+08:00",
      "updated": "2026-10-22T14:42:00+08:00",
      "resolved": false,
      "parent": "（可选，追问时指向父批注 id）"
    }
  ]
}
```

- 服务在收到 `save` 时会做字段清洗：`rects` 裁到 0–1、`q` ≤ 4000 字、`quote` ≤ 3000 字。
- `kind`：`line`（行/公式块）、`selection`（拖选）、`region`（框选）、`page`（整页）、`follow`（追问）。
- **不要手工编辑**：内存状态与文件由服务维护。

## answers.json

```json
{
  "rev": 9,
  "updated": "2026-10-22T18:40:00+08:00",
  "answers": {
    "a-mvj6by2l-x1mbo": {
      "md": "**结论**：……\n\n$$J_2(0)=\\begin{pmatrix}0&1\\\\0&0\\end{pmatrix}$$",
      "at": "2026-10-22T18:40:00+08:00"
    }
  }
}
```

- key 是批注 id；`md` 走 marked + KaTeX 渲染（`$...$` / `$$...$$`）。
- 服务按文件 mtime 自动重载，页面 1.5s 轮询刷新，**写完不用重启**。

## HTTP 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 阅读器（`web/index.html`） |
| GET | `/api/state` | `{annotationsRev, annotations, answers, answersRev, serverTime, workbench:{root}}` |
| GET | `/api/health` | `{ok:true, time}` |
| POST | `/api/annotations` | `{action:"save", item}` / `{action:"delete", id}` / `{action:"resolve", id, resolved}` |
| GET | `/data/...`、`/img/...`、`/web/...` | 静态资源 |

服务只监听 `127.0.0.1`，不鉴权、无 CORS；批注写入用「临时文件 + `os.replace`」保证原子性。

## 前端行为要点

- 页图 `<img loading=lazy>` + 透明文字层（逐行绝对定位）；文字层只用于点选/拖选/搜索，视觉上不可见。
- 批注层叠在页面上：图钉按「页内创建顺序」编号；颜色 = 待回答（橙）/ 已回答（绿）/ 已解决（灰）。
- 点行 → 浮层候选「这一行 / 整段 / 整页」；识别到相邻数学行时插入「公式块」候选（把矩阵、分数的上下几行合成一块）。
- 浮层标题栏可拖动；图钉可拖动重锚（拖到另一行）或平移框选区域。
- 输入框上方 20 个 KaTeX 公式按钮（点击在光标处插入 `$...$`，矩阵/求和/积分用 `$$...$$`）；下方实时预览。
- 渲染顺序：先把 `$...$` 抽成占位符 → marked 解析 → 还原 → KaTeX auto-render；这样 `\\`、`&` 不会被 Markdown 吞掉。
- 快捷键：`Alt+A` 批注模式、`/` 搜索、`←` `→` 翻页、`Esc` 逐层关闭。

## 构建与重建

```bash
python scripts/build_workbench.py --root <工作台>                # 全量
python scripts/build_workbench.py --root <工作台> --only CH1     # 单章
python scripts/build_workbench.py --root <工作台> --text-only    # 只重建文字层（约 2 秒）
python scripts/build_workbench.py --root <工作台> --dpi 240      # 换分辨率
```

页图流程：`pdftoppm -r <dpi> -png` → Pillow 转无损 WebP（多进程）。文字层流程：
`pdftohtml -xml -i` → 按基线聚类成行 → 按行距聚成段 → 归一化坐标。`pdftohtml` 的
fontspec 是全文唯一的（只出现在首次使用页），解析时必须全局合并，否则会丢整页文字。

## 排查

| 现象 | 原因 / 处理 |
| --- | --- |
| 页面白屏、控制台 404 | 先 `build_workbench.py --root ...`；确认 `data/manifest.json` 存在 |
| 批注保存失败 400 | 看服务日志；多为 `rects` 为空或 id 不合法 |
| 解答写回不显示 | 确认写的是 `<工作台>/data/answers.json`、key 与批注 id 一致；等 2 秒 |
| 公式显示成红字/原文 | 该条答案的 `$...$` 不配对，或命令 KaTeX 不支持；`throwOnError:false` 会显示原文 |
| 端口被占 | `serve_workbench.py --port 8800` |
| 页面样式/脚本没更新 | 前端走 `no-cache`，但仍需 `Ctrl+R` 刷新已打开的旧标签 |
| 页图模糊 | `--dpi 400` 重建；清晰度与体积权衡 |
| 文字层公式乱 | 预期行为；以 `--crops` 生成的页图为准 |

## 已知限制

- 单机单用户、无鉴权；批注与解答是明文 JSON，只适合本机使用。
- 只支持 PDF；PPTX 需先转 PDF。
- 页图按固定 dpi 生成，放大超过约 150% 会看出像素。
- 「公式块」是启发式（相邻数学行 + 水平重叠），不保证覆盖所有多行公式；框选永远最稳。
- 追问是独立批注（带 `parent`），没有嵌套回复树。
