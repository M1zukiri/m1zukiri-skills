# 创建时间: 2026-10-11 22:59:09
# 用途：为生成型页面建立「元素 → 源码位置」索引。
#   1) 为每个元素派生稳定标识 eid（内容哈希，不依赖易漂移的 id 后缀）
#   2) 按多策略反查生成它的源码位置（id 字面量 / 动态 id 前缀 / 唯一文本 / class）
#   3) 标注源头类别：literal(模板字面量) / logic(生成器函数) / registry(注册表)
# 输出 JSON，供副本生成器烧入 data-eid 与 data-src。
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

try:
    import lxml.html
except ImportError:
    print("需要 lxml：请用项目自带的 .venv 运行")
    sys.exit(2)

WS = re.compile(r"\s+")
SKIP_TAGS = {"script", "style", "meta", "link", "title", "head", "noscript", "template"}
# 通用类名：出现位置太多，用于定位会把元素带到无关分支（实测 muted 曾把
# <span class="stag-line muted"> 引到空态兜底分支）。
GENERIC_CLASSES = {
    "muted", "note", "hint", "num", "val", "card", "row", "item", "text",
    "name", "value", "title", "label", "body", "head", "main", "wrap",
    "grid", "flex", "left", "right", "center", "small", "large",
}


def norm(s) -> str:
    return WS.sub(" ", str(s or "")).strip()


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def elem_path(el) -> str:
    """CSS 路径：到最近的带 id 祖先为止。"""
    parts = []
    cur = el
    guard = 0
    while cur is not None and guard < 64:
        tag = getattr(cur, "tag", None)
        if not isinstance(tag, str):
            break
        cur_id = cur.get("id")
        if cur_id:
            parts.insert(0, "#" + cur_id)
            break
        parent = cur.getparent()
        if parent is not None:
            same = [c for c in parent if getattr(c, "tag", None) == tag]
            if len(same) > 1:
                tag += ":nth-of-type(%d)" % (same.index(cur) + 1)
        parts.insert(0, tag)
        cur = parent
        guard += 1
    return " > ".join(parts)


def direct_text(el) -> str:
    """仅元素自身的直接文本（不含后代），用于区分容器与文本节点。"""
    out = []
    if el.text:
        out.append(el.text)
    for ch in el:
        if ch.tail:
            out.append(ch.tail)
    return norm(" ".join(out))


def section_of(el) -> str:
    """向上找最近的标题作为所属章节。"""
    cur = el
    guard = 0
    while cur is not None and guard < 128:
        prev = cur.getprevious()
        while prev is not None:
            tag = getattr(prev, "tag", None)
            if isinstance(tag, str) and re.fullmatch(r"h[1-4]", tag):
                return norm(prev.text_content())
            prev = prev.getprevious()
        cur = cur.getparent()
        guard += 1
    return ""


def make_eid(tag: str, elem_id, cls: str, text: str, path: str) -> str:
    """
    内容派生的稳定标识。
    刻意不用元素 id：generate_page.py 的 _uid() 会按碰撞顺序生成 -2/-3 后缀，
    页面内容一变后缀就漂移，无法作为跨会话主键。
    """
    key = "|".join([tag, elem_id or "", cls or "", text[:100], path])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def classify_line(line: str) -> str:
    s = line.strip()
    # 注释与文档字符串不是可定位的产出点，必须先剔除，
    # 否则 class/文本匹配会误命中它们，且错误会沿继承链放大。
    if s.startswith("#") or s.startswith('"""') or s.startswith("'''"):
        return "comment"
    if s.startswith("def ") or s.startswith("class "):
        return "logic"
    if re.match(r'^["\']?[A-Za-z_][A-Za-z_0-9]*["\']?\s*:', s) and "(" not in s[:12]:
        return "registry"
    return "literal"


def is_meaningful(text: str) -> bool:
    """中文两个字即可承载语义，英文需要四个字符，避免短串误匹配。"""
    cn = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return len(text) >= 4 or cn >= 2


def load_sources(paths):
    srcs = []
    for p in paths:
        pp = Path(p)
        if not pp.is_file():
            continue
        text = pp.read_text(encoding="utf-8", errors="replace")
        srcs.append({
            "file": pp.name,
            "path": str(pp),
            "sha256": sha256_of(pp),
            "lines": list(enumerate(text.splitlines(), start=1)),
        })
    return srcs


def locate(el, srcs, limit=4):
    """多策略反查。返回按置信度排序的候选位置。"""
    tag = el.tag
    el_id = el.get("id")
    cls = norm(el.get("class"))
    text = norm(el.text_content())
    direct = direct_text(el)
    out = []

    def add(src, ln, line, kind, conf, why):
        if kind == "comment":
            return
        out.append({
            "file": src["file"], "line": ln, "line_text": line.strip()[:200],
            "kind": kind, "confidence": conf, "why": why,
        })

    # 策略 1：id 属性字面量
    if el_id:
        pat_d = 'id="%s"' % el_id
        pat_s = "id='%s'" % el_id
        for s in srcs:
            for ln, line in s["lines"]:
                if pat_d in line or pat_s in line:
                    add(s, ln, line, "literal", "high", "id 字面量命中")

    # 策略 1b：动态 id 前缀（如 f'id="stage-{pid}"'）
    if el_id and not out:
        prefix = el_id.split("-")[0]
        if len(prefix) >= 3:
            for s in srcs:
                for ln, line in s["lines"]:
                    if ('id="%s-' % prefix) in line or ("id=\\'%s-" % prefix) in line:
                        add(s, ln, line, "logic", "medium", "动态 id 前缀 %s- 命中" % prefix)

    # 策略 2：文本字面量（优先直接文本，更贴近源码字面量）
    probe = direct if is_meaningful(direct) else (
        text if is_meaningful(text) and len(text) <= 120 else "")
    if probe and not out:
        hits = []
        for s in srcs:
            for ln, line in s["lines"]:
                if probe in line:
                    hits.append((s, ln, line))
        if len(hits) == 1:
            s, ln, line = hits[0]
            add(s, ln, line, classify_line(line), "high", "文本唯一命中")
        elif 1 < len(hits) <= 3:
            for s, ln, line in hits:
                add(s, ln, line, classify_line(line), "medium", "文本命中（%d 处之一）" % len(hits))

    # 策略 2b：容器元素改用「首个有意义的后代叶子」文本再试。
    # 容器的 text_content() 会把跨节点文本粘连（<th>字段</th><th>值</th> -> "字段值"），
    # 与源码里分开的字面量对不上；取单个叶子则能命中。
    if not out and len(el):
        for leaf in el.iterdescendants():
            lt = direct_text(leaf)
            if is_meaningful(lt):
                hits3 = []
                for s in srcs:
                    for ln, line in s["lines"]:
                        if lt in line:
                            hits3.append((s, ln, line))
                if len(hits3) == 1:
                    s, ln, line = hits3[0]
                    add(s, ln, line, classify_line(line), "medium",
                        "容器内首个叶子文本命中：%s" % lt[:20])
                break

    # 策略 3：class 名（子串匹配——源码里常写作 class="a b c"，全等匹配会漏）
    # 两个约束，都是为了避开误命中：
    #   a) 类名至少 4 字符，短名（name/table/cfg）在注释与文档串里极易命中；
    #   b) 跳过通用类名（muted/note/num…）——它们在多处出现，会把元素带到无关分支；
    #   c) 按具体度依次尝试（第一个类名最具体），命中即止，不做 any() 并集匹配。
    if not out and cls:
        names = [n for n in cls.split()
                 if len(n) >= 4 and n.lower() not in GENERIC_CLASSES]
        for name in names[:2]:
            hit = False
            for s in srcs:
                for ln, line in s["lines"]:
                    if name in line and "<" in line:
                        add(s, ln, line, classify_line(line), "low",
                            "class 名命中 .%s" % name)
                        hit = True
                        break
                if hit:
                    break
            if out:
                break

    # 说明：曾尝试用「祖先 class 名 → 源码」做区域级定位，实测准确率仅约 4 成
    # （常命中文档说明、空态兜底分支等无关行），只换来 0.7% 覆盖提升，
    # 权衡后撤除——宁可标为无来源，也不给出会误导 agent 的位置。

    # 去重 + 截断
    seen = set()
    dedup = []
    for c in out:
        k = (c["file"], c["line"])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(c)
    order = {"high": 0, "medium": 1, "inherited": 2, "low": 4, "unknown": 5}
    dedup.sort(key=lambda c: order.get(c["confidence"], 9))
    return dedup[:limit]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("html", help="待索引的 HTML 文件")
    ap.add_argument("--source", action="append", default=[],
                    help="参与反查的源码文件（可重复）")
    ap.add_argument("-o", "--out", help="输出 JSON（默认 <html>.index.json）")
    args = ap.parse_args()

    t0 = time.time()
    hp = Path(args.html)
    if not hp.is_file():
        print("HTML 不存在: %s" % hp)
        return 2

    doc = lxml.html.parse(str(hp)).getroot()
    srcs = load_sources(args.source)
    if args.source and not srcs:
        print("警告：给出的源码文件都不存在，反查将为空")

    elements = []
    pairs = []          # (lxml 元素, 索引条目)，供第二遍继承使用
    for el in doc.iter():
        tag = getattr(el, "tag", None)
        if not isinstance(tag, str) or tag.lower() in SKIP_TAGS:
            continue

        el_id = el.get("id")
        cls = norm(el.get("class"))
        text = norm(el.text_content())
        direct = direct_text(el)
        path = elem_path(el)

        eid = make_eid(tag, el_id, cls, direct or text, path)
        src = locate(el, srcs)

        entry = {
            "eid": eid,
            "path": path,
            "tag": tag,
            "id": el_id,
            "cls": cls,
            "text": text[:200],
            "direct": direct[:200],
            "section": section_of(el),
            # annotatable：无文本、无 id、无 class 的纯结构容器不建议作为批注目标
            "annotatable": bool(el_id or cls or direct),
            "src": src,
        }
        elements.append(entry)
        pairs.append((el, entry))

    # 第二遍：祖先继承。
    # 表格单元格、动态模板片段自身没有源码字面量，但它们由生成父容器的同一个函数产出，
    # 继承祖先位置能给出「该改哪个函数」这一层信息。
    # 只允许继承 high/medium：low(class) 与 unknown(data) 的祖先位置不可信，
    # 一旦被继承就会把错误放大到整棵子树。
    by_el = {id(el): entry for el, entry in pairs}
    for el, entry in pairs:
        if entry["src"]:
            continue
        cur = el.getparent()
        guard = 0
        while cur is not None and guard < 64:
            anc = by_el.get(id(cur))
            if anc and anc["src"] and anc["src"][0]["confidence"] in ("high", "medium", "region"):
                s = dict(anc["src"][0])
                s["confidence"] = "inherited"
                s["why"] = "继承自祖先 <%s%s>（同一函数产出；祖先为 %s 置信）" % (
                    anc["tag"], ("#" + anc["id"]) if anc["id"] else "",
                    anc["src"][0]["confidence"])
                entry["src"] = [s]
                entry["inherited_from"] = anc["eid"]
                break
            cur = cur.getparent()
            guard += 1

        # 单元格的值一律来自数据层：无论是否继承了表格模板的位置，都要把这点告诉 agent，
        # 否则它会去改模板（改了不生效）。
        if tag in ("td", "th"):
            entry["src"].append({
                "file": None, "line": None, "line_text": None,
                "kind": "data", "confidence": "unknown",
                "why": "单元格值来自数据源（results JSON / configs），改数值需回到数据层",
            })

    def conf(e):
        return e["src"][0]["confidence"] if e["src"] else None

    located = [e for e in elements if e["src"]]
    high = [e for e in located if conf(e) == "high"]
    medium = [e for e in located if conf(e) == "medium"]
    inherited = [e for e in located if conf(e) == "inherited"]
    region = [e for e in located if conf(e) == "region"]
    datadriven = [e for e in located if conf(e) == "unknown"]
    dt = time.time() - t0

    result = {
        "schema": "page-element-index/v1",
        "html": {
            "path": str(hp),
            "name": hp.name,
            "sha256": sha256_of(hp),
            "bytes": hp.stat().st_size,
        },
        "sources": [{"file": s["file"], "sha256": s["sha256"]} for s in srcs],
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stats": {
            "elements": len(elements),
            "annotatable": sum(1 for e in elements if e["annotatable"]),
            "located": len(located),
            "high": len(high),
            "medium": len(medium),
            "inherited": len(inherited),
            "region": len(region),
            "data_driven": len(datadriven),
            "elapsed_sec": round(dt, 2),
        },
        "elements": elements,
    }

    out = Path(args.out) if args.out else hp.with_suffix(".index.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    st = result["stats"]
    print("索引完成: %s" % out)
    print("  元素 %d（可批注 %d）" % (st["elements"], st["annotatable"]))
    print("  高置信 %d | 中置信 %d | 祖先继承 %d | 区域定位 %d | 数据驱动 %d" % (
        st["high"], st["medium"], st["inherited"], st["region"], st["data_driven"]))
    print("  有来源 %d / %d，耗时 %.2fs" % (st["located"], st["elements"], dt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
