# 创建时间: 2026-10-22 16:20:00
"""批注工作台（agent 侧）工具：看批注、出裁剪图、写解答。

由 create_workbench.py 放在 <工作台>/scripts/review_workbench.py。

用法：
    python scripts/review_workbench.py --root <工作台> --list              # 待回答批注
    python scripts/review_workbench.py --root <工作台> --list --all        # 全部批注与状态
    python scripts/review_workbench.py --root <工作台> --crops             # 裁剪图 + 带红框整页图
    python scripts/review_workbench.py --root <工作台> --set <id> <md文件> # 写入/覆盖一条解答
    python scripts/review_workbench.py --root <工作台> --set-json <json>   # 批量写解答

说明：
    批注由页面写入 data/annotations.json；解答由本脚本写入 data/answers.json。
    服务端只读 answers.json，页面每 1.5s 轮询，因此写完解答后无需重启即可在页面上看到。
    裁剪图默认输出到 <工作台>/_tmp/crops/，包含：
      <id>.png           按批注坐标裁出的局部图
      <id>-context.png   整页 + 红框，用于核对公式/图形在版面中的位置
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

STUDY = Path(__file__).resolve().parent.parent
DATA = STUDY / "data"
ANN_PATH = DATA / "annotations.json"
ANS_PATH = DATA / "answers.json"


def find_root(start: Path) -> Path:
    """从 start 向上查找含 workbench.json 的工作台目录。"""
    cur = start.resolve()
    for _ in range(8):
        if (cur / "workbench.json").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise SystemExit(f"找不到 workbench.json（从 {start} 向上查找）；请用 --root 指定工作台目录。")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path: Path, doc: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def manifest() -> dict:
    doc = load(DATA / "manifest.json", {"chapters": []})
    return {c["id"]: c for c in doc.get("chapters", [])}


def collect(all_items: bool) -> list[dict]:
    ann = load(ANN_PATH, {"items": []})
    ans = load(ANS_PATH, {"answers": {}})
    items = ann.get("items", [])
    out = []
    for item in items:
        answered = item["id"] in ans.get("answers", {})
        if all_items or not (item.get("resolved") or answered):
            out.append({**item, "_answered": answered})
    return out


def describe(item: dict) -> str:
    status = "已解决" if item.get("resolved") else ("已回答" if item["_answered"] else "待回答")
    quote = (item.get("quote") or "").replace("\n", " ")[:60]
    question = (item.get("q") or "").replace("\n", " ")[:100]
    return (f"[{item['id']}] {item['ch']} p{item['page']} · {status} · 标签 {item.get('tag') or '-'}\n"
            f"    引用：{quote}\n"
            f"    问题：{question}")


def make_crops(items: list[dict], out_dir: Path) -> list[dict]:
    chapters = manifest()
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for item in items:
        meta = chapters.get(item["ch"])
        if not meta:
            continue
        img_path = STUDY / meta["img"] / f"{int(item['page']):03d}.webp"
        if not img_path.exists():
            results.append({"id": item["id"], "error": f"缺页图 {img_path}"})
            continue
        with Image.open(img_path) as img:
            page = img.convert("RGB")
            w, h = page.size
            rects = item.get("rects") or [{"x": 0.0, "y": 0.0, "w": 0.12, "h": 0.05}]
            x0 = min(r["x"] for r in rects)
            y0 = min(r["y"] for r in rects)
            x1 = max(r["x"] + r["w"] for r in rects)
            y1 = max(r["y"] + r["h"] for r in rects)
            margin = 0.045
            box = (
                max(0, int((x0 - margin) * w)),
                max(0, int((y0 - margin) * h)),
                min(w, int((x1 + margin) * w)),
                min(h, int((y1 + margin) * h)),
            )
            if box[2] - box[0] < 40:
                box = (box[0], box[1], min(w, box[0] + 40), box[3])
            dst = out_dir / f"{item['id']}.png"
            page.crop(box).save(dst)

            # 整页 + 红框：公式/图形在完整版面中的位置，用于复核上下文
            context = page.copy()
            draw = ImageDraw.Draw(context)
            stroke = max(3, int(h / 220))
            for r in rects:
                draw.rectangle(
                    [int(r["x"] * w), int(r["y"] * h),
                     int((r["x"] + r["w"]) * w), int((r["y"] + r["h"]) * h)],
                    outline=(220, 30, 30), width=stroke,
                )
            ctx_dst = out_dir / f"{item['id']}-context.png"
            context.save(ctx_dst)
        results.append({
            "id": item["id"], "ch": item["ch"], "page": item["page"],
            "tag": item.get("tag"), "quote": (item.get("quote") or "")[:80],
            "q": item.get("q"), "crop": str(dst),
            "context": str(ctx_dst), "full_page": str(img_path),
        })
    return results


def set_answer(answers: dict, ann_id: str, md: str) -> dict:
    answers.setdefault("answers", {})[ann_id] = {"md": md, "at": now_iso()}
    answers["rev"] = int(answers.get("rev", 0)) + 1
    answers["updated"] = now_iso()
    return answers


def main() -> None:
    ap = argparse.ArgumentParser(description="批注工作台：看批注 / 出裁剪图 / 写解答")
    ap.add_argument("--root", default=".", help="工作台目录（含 workbench.json），默认向上查找")
    ap.add_argument("--list", action="store_true", help="列出批注（默认只列未回答）")
    ap.add_argument("--all", action="store_true", help="配合 --list：列出全部批注")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出列表")
    ap.add_argument("--crops", action="store_true", help="为待回答批注生成裁剪图与带红框的整页图")
    ap.add_argument("--out", default=None, help="裁剪图输出目录（默认 <工作台>/_tmp/crops）")
    ap.add_argument("--set", nargs=2, metavar=("ID", "MD_FILE"), help="写入一条解答")
    ap.add_argument("--set-json", metavar="JSON_FILE", help="批量写入解答")
    args = ap.parse_args()

    global STUDY, DATA, ANN_PATH, ANS_PATH
    root = find_root(Path(args.root))
    STUDY = root
    DATA = root / "data"
    ANN_PATH = DATA / "annotations.json"
    ANS_PATH = DATA / "answers.json"
    if not (DATA / "manifest.json").exists():
        raise SystemExit(f"缺少 {DATA / 'manifest.json'}；先运行 scripts/build_workbench.py --root {root}")

    if args.set:
        ann_id, md_path = args.set
        md = Path(md_path).read_text(encoding="utf-8")
        answers = load(ANS_PATH, {"rev": 0, "answers": {}})
        save(ANS_PATH, set_answer(answers, ann_id, md))
        remaining = collect(False)
        print(f"已写入解答：{ann_id}（{len(md)} 字符），剩余待回答 {len(remaining)} 条")
        for item in remaining:
            print(describe(item))
        return

    if args.set_json:
        batch = json.loads(Path(args.set_json).read_text(encoding="utf-8"))
        answers = load(ANS_PATH, {"rev": 0, "answers": {}})
        for ann_id, value in batch.items():
            md = value.get("md") if isinstance(value, dict) else str(value)
            answers = set_answer(answers, ann_id, md)
        save(ANS_PATH, answers)
        remaining = collect(False)
        print(f"已写入 {len(batch)} 条解答，剩余待回答 {len(remaining)} 条")
        return

    items = collect(args.all)
    if args.crops:
        out_dir = Path(args.out) if args.out else (STUDY / "_tmp" / "crops")
        results = make_crops(items, out_dir)
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=1))
        return
    if not items:
        print("没有待回答的批注。")
        return
    print(f"共 {len(items)} 条：")
    for item in items:
        print(describe(item))
        print()


if __name__ == "__main__":
    main()
