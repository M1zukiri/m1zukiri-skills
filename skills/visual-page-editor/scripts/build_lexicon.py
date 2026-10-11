# 创建时间: 2026-10-12 01:10:12
# 用途：把源码集合压成「字面量 → 候选位置」倒排表，供批注副本在运行时反查。
#
#   生成期只做这一件事，不做任何 DOM 匹配——DOM 匹配全部挪到运行时。这样
#   JS 运行时才生成的元素（弹窗、列表、条件渲染）天然有覆盖，不需要预先
#   遍历页面状态，也不需要为「进入状态」准备素材。
#
#   产出 JSON：
#     files : ["modal.js", ...]                    相对项目根的路径，下标即 id
#     lines : {"modal.js:28": "overlay.class…"}    被引用到的行原文（供 lineText）
#     lex   : {"cls:modal-overlay": [[0,28]], …}   锚点 → 候选 [文件下标, 行号]
#
#   锚点前缀：
#     key:  i18n key（唯一性最高，来自 T('…') / lookup('…') / data-i18n）
#     str:  字符串字面量（运行时按「元素文本是它的子串」匹配）
#     id:   元素 id
#     cls:  class 名
import argparse
import json
import re
import sys
from pathlib import Path

RE_STR = re.compile(r"'([^'\\\n]{3,140})'|\"([^\"\\\n]{3,140})\"|`([^`\\\n$]{3,140})`")
RE_CLASS_ATTR = re.compile(r'class="([^"]{1,240})"')
RE_CLASS_JS = re.compile(r"""classList\.add\(\s*['"]([^'"]+)['"]|className\s*=\s*['"]([^'"]+)['"]""")
RE_ID_ATTR = re.compile(r'id="([^"]{1,90})"')
RE_ID_JS = re.compile(r"""\.id\s*=\s*['"]([^'"]+)['"]""")
RE_KEY = re.compile(
    r"""\bT\(\s*['"]([^'"]+)['"]|\blookup\(\s*['"]([^'"]+)['"]"""
    r"""|data-i18n="([^"]+)"|data-i18n-title="([^"]+)\"""")

EXTS = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py", ".html", ".htm", ".vue", ".svelte"}


def collect_files(paths):
    out = []
    for p in paths:
        if p.is_dir():
            out.extend(f for f in sorted(p.rglob("*"))
                       if f.is_file() and f.suffix.lower() in EXTS)
        elif p.is_file():
            out.append(p)
    seen, uniq = set(), []
    for f in out:
        r = f.resolve()
        if r not in seen:
            seen.add(r)
            uniq.append(f)
    return uniq


def common_root(files):
    if not files:
        return Path(".")
    parts = [f.resolve().parent.parts for f in files]
    n = 0
    for i in range(min(len(p) for p in parts)):
        if len({p[i] for p in parts}) == 1:
            n = i + 1
        else:
            break
    return Path(*parts[0][:n]) if n else Path(".")


def build(files, root):
    names, lex = [], {}

    def mark(fi, ln, key):
        if not key:
            return
        lst = lex.setdefault(key, [])
        if [fi, ln] not in lst:
            lst.append([fi, ln])

    for fi, f in enumerate(files):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            names.append(f.name)
            continue
        try:
            rel = f.resolve().relative_to(root).as_posix()
        except ValueError:
            rel = f.name
        names.append(rel)
        for ln, raw in enumerate(text.splitlines(), 1):
            for m in RE_STR.finditer(raw):
                mark(fi, ln, "str:" + (m.group(1) or m.group(2) or m.group(3)))
            for m in RE_CLASS_ATTR.finditer(raw):
                for c in m.group(1).split():
                    mark(fi, ln, "cls:" + c)
            for m in RE_CLASS_JS.finditer(raw):
                for c in (m.group(1) or m.group(2) or "").split():
                    mark(fi, ln, "cls:" + c)
            for m in RE_ID_ATTR.finditer(raw):
                mark(fi, ln, "id:" + m.group(1))
            for m in RE_ID_JS.finditer(raw):
                mark(fi, ln, "id:" + m.group(1))
            for m in RE_KEY.finditer(raw):
                mark(fi, ln, "key:" + (m.group(1) or m.group(2) or m.group(3) or m.group(4)))

    # 只保留被引用到的行原文：整份源码的行数乘以平均长度会让副本膨胀数倍
    used = set()
    for pairs in lex.values():
        for fi, ln in pairs:
            used.add("%s:%d" % (names[fi], ln))
    lines = {}
    for fi, f in enumerate(files):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ln, raw in enumerate(text.splitlines(), 1):
            key = "%s:%d" % (names[fi], ln)
            if key in used:
                lines[key] = raw.strip()[:200]
    return {"v": 1, "files": names, "lines": lines, "lex": lex}


def summarize(data):
    by_kind = {}
    multi = 0
    for k, v in data["lex"].items():
        kind = k.split(":", 1)[0]
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if len(v) > 1:
            multi += 1
    return by_kind, multi


def main():
    ap = argparse.ArgumentParser(description="生成字面量倒排表")
    ap.add_argument("--source", action="append", default=[],
                    help="源码文件或目录（可重复；目录会递归）")
    ap.add_argument("--root", help="相对路径基准（默认取所有源码的公共父目录）")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    paths = [Path(s) for s in args.source]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        print("  [警告] --source 不存在，已跳过: %s" % ", ".join(missing))
    files = collect_files([p for p in paths if p.exists()])
    if not files:
        print("  [警告] 没有可扫描的源码，倒排表为空")
    root = Path(args.root) if args.root else common_root(files)
    data = build(files, root)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    by_kind, multi = summarize(data)
    size_kb = out.stat().st_size / 1024
    print("  倒排表: %d 个锚点 / %d 个文件 / %.0f KB" % (len(data["lex"]), len(files), size_kb))
    print("    分层: %s" % "  ".join("%s %d" % (k, by_kind[k]) for k in sorted(by_kind)))
    print("    其中多候选锚点 %d 个（运行时必须标 ambiguous，不许取第一个）" % multi)
    print("    行原文 %d 条（供 lineText）" % len(data["lines"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
