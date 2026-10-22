# 创建时间: 2026-10-22 18:00:00
"""从 PDF 课件创建一个本地批注工作台（courseware-annotator skill 的入口）。

用法：
    python scripts/create_workbench.py --out <工作台目录> \
        --pdf <课件1.pdf> [--pdf <课件2.pdf> ...] \
        [--title "课程名"] [--subtitle "课件批注工作台"] \
        [--title-for <pdf>=<章节标题>]... \
        [--dpi 300] [--no-build]

产物（都在 <工作台目录> 内）：
    workbench.json        工作台配置：标题、章节、dpi
    web/                  阅读器前端（KaTeX / marked 已内置，离线可用）
    scripts/              build / serve / review / selftest 四个脚本
    README.md             本工作台的使用说明
    启动工作台.bat        Windows 双击启动
    data/ img/            构建产物（由 build_workbench.py 生成）

依赖：Python 3.10+、Pillow、Poppler（pdftoppm / pdftohtml / pdfinfo）。
章节标题默认取 PDF 元数据 Title，取不到用文件名；可用 --title-for 覆盖。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ASSETS = SKILL / "assets"
SCRIPTS = SKILL / "scripts"
RUNTIME_SCRIPTS = [
    "build_workbench.py",
    "serve_workbench.py",
    "review_workbench.py",
    "selftest_workbench.py",
]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def check_environment() -> None:
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        raise SystemExit("缺少 Pillow：pip install pillow")
    missing = [tool for tool in ("pdftoppm", "pdftohtml", "pdfinfo") if not shutil.which(tool)]
    if missing:
        raise SystemExit(
            "缺少 Poppler 工具：" + "、".join(missing) +
            "\n  Windows 可安装 Poppler 后把 bin 加入 PATH（或使用 TeX Live 自带的同名工具）。"
        )


def pdf_title(pdf: Path) -> str:
    try:
        out = subprocess.run(
            ["pdfinfo", str(pdf)], capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        ).stdout
        m = re.search(r"^Title:\s+(.+)$", out, re.M)
        if m:
            title = m.group(1).strip()
            if title and title.lower() not in ("untitled", "无标题", "unknown"):
                return title
    except Exception:  # noqa: BLE001 —— 取标题失败不应阻塞创建
        pass
    return pdf.stem


def chapter_id(pdf: Path, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", pdf.stem).strip("-_") or "chapter"
    base = base[:24]
    candidate = base
    index = 2
    while candidate.lower() in used:
        candidate = f"{base}-{index}"
        index += 1
    used.add(candidate.lower())
    return candidate


def parse_title_for(values: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in values or []:
        if "=" not in item:
            raise SystemExit(f"--title-for 需要 <pdf>=<标题> 格式：{item}")
        path, title = item.split("=", 1)
        mapping[os.path.normcase(os.path.abspath(path.expanduser()))] = title.strip()
    return mapping


def main() -> None:
    ap = argparse.ArgumentParser(description="从 PDF 课件创建批注工作台")
    ap.add_argument("--out", required=True, help="工作台目录（需要不存在或为空）")
    ap.add_argument("--pdf", action="append", required=True, help="课件 PDF，可重复（每个 PDF 一章）")
    ap.add_argument("--title", default="", help="项目名（默认取第一个 PDF 上层的目录名/文件名）")
    ap.add_argument("--subtitle", default="课件批注工作台", help="顶栏副标题")
    ap.add_argument("--title-for", action="append", default=[],
                    help="覆盖章节标题，格式 <pdf路径>=<标题>，可重复")
    ap.add_argument("--dpi", type=int, default=300, help="页图分辨率（默认 300）")
    ap.add_argument("--no-build", action="store_true", help="只创建工作台结构，暂不构建页图")
    args = ap.parse_args()

    check_environment()

    pdfs = [Path(p).expanduser() for p in args.pdf]
    for pdf in pdfs:
        if not pdf.is_file():
            raise SystemExit(f"找不到 PDF：{pdf}")
    out = Path(args.out).expanduser().resolve()
    if (out / "workbench.json").exists():
        raise SystemExit(f"目录里已有工作台配置，换一个 --out：{out / 'workbench.json'}")
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"输出目录不是空的：{out}")

    title_for = parse_title_for(args.title_for)
    (out / "scripts").mkdir(parents=True, exist_ok=True)
    (out / "data" / "pages").mkdir(parents=True, exist_ok=True)
    (out / "img").mkdir(parents=True, exist_ok=True)

    if (out / "web").exists():
        shutil.rmtree(out / "web")
    shutil.copytree(ASSETS / "web", out / "web")
    for name in RUNTIME_SCRIPTS:
        shutil.copy2(SCRIPTS / name, out / "scripts" / name)

    chapters = []
    used: set[str] = set()
    for pdf in pdfs:
        key = os.path.normcase(os.path.abspath(pdf))
        title = title_for.get(key) or pdf_title(pdf)
        chapters.append({
            "id": chapter_id(pdf, used),
            "pdf": os.path.relpath(pdf, out).replace("\\", "/"),
            "title": title,
        })
    project_title = args.title.strip() or (
        pdfs[0].parent.name if len(pdfs) > 1 else pdfs[0].stem)

    config = {
        "schema": 1,
        "title": project_title,
        "subtitle": args.subtitle or "课件批注工作台",
        "dpi": args.dpi,
        "chapters": chapters,
    }
    (out / "workbench.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    chapter_list = "\n".join(
        f"- `{c['id']}` · {c['title']}（`{c['pdf']}`）" for c in chapters)
    readme = (ASSETS / "README.template.md").read_text(encoding="utf-8")
    readme = (readme.replace("{{TITLE}}", project_title)
              .replace("{{CHAPTERS}}", chapter_list)
              .replace("{{OUT}}", str(out)))
    (out / "README.md").write_text(readme, encoding="utf-8")
    shutil.copy2(ASSETS / "launcher.bat", out / "启动工作台.bat")

    print(f"工作台已创建：{out}")
    print(f"  项目：{project_title}（{len(chapters)} 章，{args.dpi} dpi）")
    for chapter in chapters:
        print(f"  - {chapter['id']}  {chapter['title']}  ← {chapter['pdf']}")

    if args.no_build:
        print("\n已跳过构建。下一步：")
        print(f"  python \"{out / 'scripts' / 'build_workbench.py'}\" --root \"{out}\"")
        return

    print("\n开始构建页图与文字层……")
    subprocess.run(
        [sys.executable, str(out / "scripts" / "build_workbench.py"), "--root", str(out)],
        check=True,
    )
    print("\n下一步：")
    print(f"  python \"{out / 'scripts' / 'serve_workbench.py'}\" --root \"{out}\" --open")
    print("  或双击 启动工作台.bat；然后用浏览器打开 http://127.0.0.1:8765/")


if __name__ == "__main__":
    main()
