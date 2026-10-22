# 创建时间: 2026-10-22 14:42:00
"""把课件 PDF 构建成可批注工作台的静态数据：页图 + 文字层 + 目录。

由 create_workbench.py 复制到 <工作台>/scripts/ 后运行，读取 <工作台>/workbench.json。

用法：
    python scripts/build_workbench.py --root <工作台目录>
    python scripts/build_workbench.py --root <工作台目录> --only CH1
    python scripts/build_workbench.py --root <工作台目录> --text-only   # 只重建文字层

产物（都在工作台目录内）：
    img/<章>/001.webp ...        页图（默认 300 dpi 无损 WebP）
    data/pages/<章>.json         每页文字行/段落/标题（坐标归一化）
    data/manifest.json           章节清单（供页面与 review 工具读取）
    data/build_report.json       构建耗时与统计
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 以下路径与配置在 main() 里按 --root 与 workbench.json 覆盖
STUDY = Path(__file__).resolve().parent
ROOT = STUDY
DATA = STUDY / "data"
PAGES_DIR = DATA / "pages"
IMG_DIR = STUDY / "img"
CHAPTERS: list[dict] = []
PROJECT = {"title": "课件批注工作台", "subtitle": ""}


def find_root(start: Path) -> Path:
    """从 start 向上查找含 workbench.json 的工作台目录。"""
    cur = start.resolve()
    for _ in range(8):
        if (cur / "workbench.json").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise SystemExit(f"找不到 workbench.json（从 {start} 向上查找）；请先运行 create_workbench.py 创建工作台。")


def load_config(root: Path) -> dict:
    try:
        return json.loads((root / "workbench.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"缺少 {root / 'workbench.json'}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"workbench.json 不是合法 JSON: {exc}")

# 文字层阈值（pdftohtml 坐标单位，页面约 680×382）
WATERMARK_OPACITY = 0.5   # 不透明度低于此值视为水印
FOOTER_FS = 11            # 页脚字号上限（页码等）
TITLE_FS = 20             # 标题字号下限
LINE_JOIN_GAP = 0.35      # 同一行内片段间距超过 0.35 倍行高时补空格
LINE_SPLIT_GAP = 1.5      # 同一基线上两片段水平间距超过 1.5 倍行高时断成两行
BLOCK_GAP = 0.6           # 行间垂直间距超过 0.6 倍行高时断成新段落


def sh(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def pdf_page_count(pdf: Path) -> int:
    out = sh(["pdfinfo", str(pdf)]).stdout
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    if not m:
        raise RuntimeError(f"无法读取页数: {pdf}")
    return int(m.group(1))


def _convert_one(args: tuple[str, str]) -> int:
    src, dst = args
    with Image.open(src) as im:
        im.convert("RGB").save(dst, "WEBP", lossless=True, method=4)
    return os.path.getsize(dst)


def render_pages(pdf: Path, ch_id: str, count: int, dpi: int) -> int:
    """把 PDF 渲染成无损 WebP 页图，返回总字节数。"""
    out_dir = IMG_DIR / ch_id
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with __import__("tempfile").TemporaryDirectory(prefix="engmath_img_") as td:
        prefix = str(Path(td) / "p")
        sh(["pdftoppm", "-r", str(dpi), "-png", str(pdf), prefix])
        files = sorted(Path(td).glob("p-*.png"),
                       key=lambda p: int(re.search(r"-(\d+)\.png$", p.name).group(1)))
        if len(files) != count:
            raise RuntimeError(f"页图数量不符: {len(files)} != {count}")
        jobs = [(str(f), str(out_dir / f"{i:03d}.webp")) for i, f in enumerate(files, 1)]
        workers = min(8, os.cpu_count() or 4)
        total = 0
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for i, size in enumerate(pool.map(_convert_one, jobs), 1):
                total += size
                if i % 25 == 0 or i == count:
                    print(f"  [{ch_id}] 页图 {i}/{count}  {time.time() - t0:.1f}s")
    return total


def parse_text_xml(pdf: Path, count: int) -> list[dict]:
    """pdftohtml -xml 提取带坐标的文字片段，按页返回。"""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="engmath_txt_") as td:
        xml_path = Path(td) / "text.xml"
        sh(["pdftohtml", "-xml", "-i", "-f", "1", "-l", str(count),
            str(pdf), str(xml_path)])
        root = ET.parse(xml_path).getroot()
    # pdftohtml 的 fontspec 是全文唯一的，只出现在首次使用的那一页，
    # 因此必须按全文合并字体表，否则没有 fontspec 的页会丢掉全部文字。
    global_fonts = {}
    for fs in root.findall(".//fontspec"):
        global_fonts[fs.get("id")] = {
            "size": float(fs.get("size") or 0),
            "opacity": float(fs.get("opacity") or 1.0),
        }
    pages = []
    for page in root.findall("page"):
        fonts = dict(global_fonts)
        for fs in page.findall("fontspec"):
            fonts[fs.get("id")] = {
                "size": float(fs.get("size") or 0),
                "opacity": float(fs.get("opacity") or 1.0),
            }
        items = []
        for t in page.findall("text"):
            f = fonts.get(t.get("font"))
            if f is None or f["opacity"] < WATERMARK_OPACITY:
                continue
            x0, y0 = float(t.get("left")), float(t.get("top"))
            w, h = float(t.get("width")), float(t.get("height"))
            text = "".join(t.itertext())
            if not text.strip() or w <= 0 or h <= 0:
                continue
            items.append({"x0": x0, "y0": y0, "x1": x0 + w, "y1": y0 + h,
                          "t": text, "fs": f["size"]})
        pages.append({"pw": float(page.get("width")),
                      "ph": float(page.get("height")),
                      "items": items})
    return pages


def cluster_lines(items: list[dict]) -> list[dict]:
    """把文字碎片按基线聚类成行；同一基线上相距很远的片段断成两行。"""
    items = sorted(items, key=lambda it: (it["y0"], it["x0"]))
    lines: list[dict] = []
    for it in items:
        h = max(it["y1"] - it["y0"], 1.0)
        best = None
        for ln in reversed(lines):
            if ln["y0"] > it["y1"]:
                continue
            ov = min(ln["y1"], it["y1"]) - max(ln["y0"], it["y0"])
            if ov <= 0.45 * min(ln["hmax"], h):
                continue
            gap = max(ln["x0"] - it["x1"], it["x0"] - ln["x1"], 0.0)
            if gap > max(LINE_SPLIT_GAP * max(h, ln["hmax"]), 14.0):
                continue
            best = ln
            break
        if best is None:
            lines.append({"y0": it["y0"], "y1": it["y1"], "x0": it["x0"],
                          "x1": it["x1"], "hmax": h, "items": [it]})
        else:
            best["y0"] = min(best["y0"], it["y0"])
            best["y1"] = max(best["y1"], it["y1"])
            best["x0"] = min(best["x0"], it["x0"])
            best["x1"] = max(best["x1"], it["x1"])
            best["hmax"] = max(best["hmax"], h)
            best["items"].append(it)

    lines.sort(key=lambda ln: (ln["y0"], ln["x0"]))
    out = []
    for ln in lines:
        its = sorted(ln["items"], key=lambda it: it["x0"])
        parts, prev_end = [], None
        for it in its:
            if prev_end is not None and it["x0"] - prev_end > LINE_JOIN_GAP * ln["hmax"]:
                parts.append(" ")
            parts.append(it["t"])
            prev_end = it["x1"]
        text = "".join(parts).strip()
        if not text:
            continue
        out.append({"x0": ln["x0"], "y0": ln["y0"], "x1": ln["x1"], "y1": ln["y1"],
                    "hmax": ln["hmax"], "t": text,
                    "fs": max(it["fs"] for it in its)})
    return out


def drop_footer(lines: list[dict], ph: float) -> list[dict]:
    return [ln for ln in lines
            if not (ln["y0"] > 0.88 * ph and ln["fs"] <= FOOTER_FS)]


def build_blocks(lines: list[dict]) -> list[dict]:
    """把相邻行聚成段落（用于「整段」批注候选）。"""
    blocks: list[dict] = []
    for i, ln in enumerate(lines):
        if blocks:
            prev_lines = [lines[j] for j in blocks[-1]["lines"]]
            prev = prev_lines[-1]
            gap = ln["y0"] - prev["y1"]
            same_block = gap <= BLOCK_GAP * max(prev["hmax"], ln["hmax"], 1.0)
        else:
            same_block = False
        if same_block:
            blocks[-1]["lines"].append(i)
            b = blocks[-1]
            b["x0"] = min(b["x0"], ln["x0"]); b["y0"] = min(b["y0"], ln["y0"])
            b["x1"] = max(b["x1"], ln["x1"]); b["y1"] = max(b["y1"], ln["y1"])
        else:
            blocks.append({"lines": [i], "x0": ln["x0"], "y0": ln["y0"],
                           "x1": ln["x1"], "y1": ln["y1"]})
    for k, b in enumerate(blocks):
        for i in b["lines"]:
            lines[i]["b"] = k
    return blocks


def pick_title(lines: list[dict]) -> str:
    cands = [ln for ln in lines if ln["fs"] >= TITLE_FS]
    if not cands:
        return ""
    best = max(cands, key=lambda ln: (ln["fs"], -ln["y0"]))
    return best["t"].strip()


def norm(value: float, base: float) -> float:
    return round(value / base, 5) if base else 0.0


def build_chapter(meta: dict, dpi: int, text_only: bool) -> dict:
    pdf = ROOT / meta["pdf"]
    t0 = time.time()
    count = pdf_page_count(pdf)
    print(f"[{meta['id']}] {pdf.name} 共 {count} 页", flush=True)

    total_bytes = None
    if not text_only:
        total_bytes = render_pages(pdf, meta["id"], count, dpi)
        print(f"  页图完成，共 {total_bytes / 1024 / 1024:.1f} MB  {time.time() - t0:.1f}s", flush=True)

    text_pages = parse_text_xml(pdf, count)
    if len(text_pages) != count:
        raise RuntimeError(f"文字层页数不符: {len(text_pages)} != {count}")
    print(f"  文字层解析完成  {time.time() - t0:.1f}s", flush=True)

    pages = []
    title_count = 0
    for idx, pg in enumerate(text_pages):
        pw, ph = pg["pw"], pg["ph"]
        lines = drop_footer(cluster_lines(pg["items"]), ph)
        blocks = build_blocks(lines)
        title = pick_title(lines)
        if title:
            title_count += 1
        page = {
            "n": idx + 1,
            "title": title,
            "lines": [{
                "x": norm(ln["x0"], pw), "y": norm(ln["y0"], ph),
                "w": norm(ln["x1"] - ln["x0"], pw), "h": norm(ln["y1"] - ln["y0"], ph),
                "f": norm(ln["fs"], pw), "b": ln.get("b", 0), "t": ln["t"],
            } for ln in lines],
            "blocks": [{
                "x": norm(b["x0"], pw), "y": norm(b["y0"], ph),
                "w": norm(b["x1"] - b["x0"], pw), "h": norm(b["y1"] - b["y0"], ph),
            } for b in blocks],
            "text": "\n".join(ln["t"] for ln in lines),
        }
        pages.append(page)

    doc = {
        "chapter": meta["id"],
        "title": meta["title"],
        "pdf": meta["pdf"],
        "pageW": round(text_pages[0]["pw"], 2) if text_pages else 680,
        "pageH": round(text_pages[0]["ph"], 2) if text_pages else 382,
        "pages": pages,
    }
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    out = PAGES_DIR / f"{meta['id']}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    line_total = sum(len(p["lines"]) for p in pages)
    print(f"  写出 {out.name}：{line_total} 行 / {title_count} 页有标题 / "
          f"{out.stat().st_size / 1024:.0f} KB  {time.time() - t0:.1f}s", flush=True)
    return {"pages": count, "lines": line_total, "titled": title_count,
            "jsonBytes": out.stat().st_size, "imgBytes": total_bytes or 0,
            "seconds": round(time.time() - t0, 1)}


def main() -> None:
    ap = argparse.ArgumentParser(description="构建课件批注工作台：页图 + 文字层 + 目录")
    ap.add_argument("--root", default=".", help="工作台目录（含 workbench.json），默认从当前目录向上查找")
    ap.add_argument("--only", help="只构建指定章节 id，如 CH1")
    ap.add_argument("--dpi", type=int, default=0, help="页图分辨率；默认取 workbench.json 的 dpi（300）")
    ap.add_argument("--text-only", action="store_true", help="跳过页图渲染，只重建文字层与目录")
    args = ap.parse_args()

    global STUDY, ROOT, DATA, PAGES_DIR, IMG_DIR, CHAPTERS, PROJECT
    root = find_root(Path(args.root))
    cfg = load_config(root)
    STUDY = ROOT = root
    DATA = root / "data"
    PAGES_DIR = DATA / "pages"
    IMG_DIR = root / "img"
    CHAPTERS = [{
        "id": str(c["id"]),
        "pdf": str(c["pdf"]),
        "title": str(c.get("title") or c["id"]),
    } for c in cfg.get("chapters", [])]
    if not CHAPTERS:
        raise SystemExit("workbench.json 里没有 chapters")
    PROJECT = {
        "title": cfg.get("title") or "课件批注工作台",
        "subtitle": cfg.get("subtitle") or "",
    }
    dpi = args.dpi or int(cfg.get("dpi") or 300)
    print(f"工作台: {root}")
    print(f"项目: {PROJECT['title']} · {len(CHAPTERS)} 章 · {dpi} dpi")

    targets = [c for c in CHAPTERS if not args.only or c["id"] == args.only]
    if not targets:
        raise SystemExit(f"未知章节：{args.only}")

    started = datetime.now()
    report = {"generated": started.isoformat(timespec="seconds"), "dpi": dpi,
              "chapters": {}}
    for meta in targets:
        report["chapters"][meta["id"]] = build_chapter(meta, dpi, args.text_only)

    manifest_path = DATA / "manifest.json"
    old = {}
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            old = {}
    chapters = {c["id"]: c for c in old.get("chapters", [])} if old else {}
    for meta in CHAPTERS:
        st = report["chapters"].get(meta["id"])
        prev = chapters.get(meta["id"], {})
        chapters[meta["id"]] = {
            "id": meta["id"], "title": meta["title"], "pdf": meta["pdf"],
            "pages": (st or {}).get("pages") or prev.get("pages") or 0,
            "data": f"data/pages/{meta['id']}.json",
            "img": f"img/{meta['id']}",
        }
    manifest = {
        "generated": report["generated"],
        "dpi": dpi,
        "project": PROJECT,
        "chapters": [chapters[c["id"]] for c in CHAPTERS],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    (DATA / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    total_pages = sum(v["pages"] for v in report["chapters"].values())
    print(f"完成：本次构建 {total_pages} 页，耗时 {(datetime.now() - started).total_seconds():.0f}s")


if __name__ == "__main__":
    main()
