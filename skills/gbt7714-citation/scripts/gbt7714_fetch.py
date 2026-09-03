#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 创建时间: 2026-09-01 21:30:00
# gbt7714_fetch.py — 从 DOI / arXiv ID / URL 抓取元数据，输出 GB/T 7714—2025 参考文献条目
# 纯标准库实现（urllib + json），无第三方依赖；网络不可用时降级输出已知元数据字段。

"""
用法示例：
    python gbt7714_fetch.py --doi 10.1038/nature13308
    python gbt7714_fetch.py --arxiv 2301.12345
    python gbt7714_fetch.py --url https://arxiv.org/abs/2301.12345 --type pp
    python gbt7714_fetch.py --doi 10.1111/1747-7917.13496 --type j      # 强制覆盖类型判定

输出：JSON，包含元数据字段与按 GB/T 7714—2025 排版的引用条目（默认期刊 J / 预印本 PP / 图书 M，
按元数据自动判定，可用 --type 覆盖）。所有字段在正式使用前须人工核对。
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime

USER_AGENT = "gbt7714-fetch/1.0 (reference formatter; mailto:user@example.com)"


def http_get_json(url, timeout=30):
    """抓取 JSON 接口，返回解析后的数据；失败返回 None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except Exception:
        return None


def http_get_text(url, timeout=30):
    """抓取纯文本接口；失败返回 None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


# ---------- 元数据抓取 ----------

def fetch_crossref(doi):
    """通过 CrossRef API 按 DOI 取元数据（期刊论文、图书、会议论文等）。"""
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    data = http_get_json(url)
    if not data:
        return None
    m = data.get("message", {})
    title = (m.get("title") or [""])[0]
    container = (m.get("container-title") or [""])[0]
    authors = []
    for a in m.get("author", []):
        given = a.get("given", "")
        family = a.get("family", "")
        name = a.get("name", "")  # 机构/团体作者
        if name:
            authors.append({"family": name, "given": ""})
        else:
            authors.append({"family": family, "given": given})
    year = None
    full_date = ""
    for key in ("published-print", "published-online", "issued"):
        dp = m.get(key, {}).get("date-parts")
        if dp and dp[0]:
            try:
                y, mo, d = (dp[0] + [None, None])[:3]
                year = str(y) if y else None
                if y and mo and d:
                    full_date = "%04d-%02d-%02d" % (y, mo, d)
            except (IndexError, TypeError):
                year = None
            if year:
                break
    volume = m.get("volume", "")
    issue = m.get("issue", "")
    pages = m.get("page", "")
    article_no = m.get("article-number", "")
    kind = m.get("type", "")
    return {
        "source": "crossref",
        "type": kind,
        "title": title,
        "container": container,
        "publisher": m.get("publisher", ""),
        "authors": authors,
        "year": year or "",
        "published_date": full_date,
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "article_number": article_no,
        "doi": doi,
        "url": m.get("URL", ""),
    }


def fetch_arxiv(arxiv_id):
    """通过 arXiv API 按 ID 取元数据（预印本）。"""
    url = "http://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(arxiv_id)
    text = http_get_text(url)
    if not text:
        return None
    # 取 <entry> 内的标题（feed 根的 <title> 是查询描述）
    entry_block = re.search(r"<entry>([\s\S]*?)</entry>", text)
    block = entry_block.group(1) if entry_block else text
    title = re.search(r"<title>\s*(.+?)\s*</title>", block, re.S)
    authors_raw = re.findall(r"<name>\s*(.+?)\s*</name>", block, re.S)
    authors = []
    for n in authors_raw:
        parts = n.split()
        if len(parts) >= 2:
            authors.append({"family": parts[-1], "given": " ".join(parts[:-1])})
        else:
            authors.append({"family": n, "given": ""})
    published = re.search(r"<published>\s*(\d{4})-(\d{2})-(\d{2})", block)
    return {
        "source": "arxiv",
        "type": "preprint",
        "title": title.group(1).strip() if title else "",
        "container": "arXiv",
        "publisher": "arXiv",
        "authors": authors,
        "year": published.group(1) if published else "",
        "published_date": "-".join(published.groups()) if published else "",
        "volume": "",
        "issue": "",
        "pages": "",
        "article_number": "",
        # 预印本引用其自身 DOI（arXiv 官方 DOI），而非正式发表版的 DOI
        "doi": "10.48550/arXiv." + re.sub(r"v\d+$", "", arxiv_id),
        "url": "https://arxiv.org/abs/" + arxiv_id,
    }


def fetch_openalex_search(query):
    """通过 OpenAlex 按标题搜索（作为 arXiv/DOI 之外的兜底）。"""
    url = "https://api.openalex.org/works?search=" + urllib.parse.quote(query) + "&per-page=1"
    data = http_get_json(url)
    if not data or not data.get("results"):
        return None
    w = data["results"][0]
    authors = []
    for a in w.get("authorships", []):
        name = a.get("author", {}).get("display_name", "")
        if not name:
            continue
        parts = name.rstrip().split(" ")
        if len(parts) >= 2:
            authors.append({"family": parts[-1], "given": " ".join(parts[:-1])})
        else:
            authors.append({"family": name, "given": ""})
    year = w.get("publication_year") or ""
    loc = w.get("primary_location") or {}
    source = loc.get("source") or {}
    return {
        "source": "openalex",
        "type": w.get("type", ""),
        "title": w.get("title", ""),
        "container": source.get("display_name", ""),
        "publisher": source.get("host_organization_name", ""),
        "authors": authors,
        "year": str(year),
        "volume": w.get("biblio", {}).get("volume", ""),
        "issue": w.get("biblio", {}).get("issue", ""),
        "pages": w.get("biblio", {}).get("first_page", "") or "",
        "article_number": "",
        "doi": w.get("doi", ""),
        "url": w.get("id", ""),
    }


# ---------- 姓名规范化（西文） ----------

def format_author_name(family, given=""):
    """西文姓名 -> '姓 名首字母'（姓首字母大写其余小写，名缩写为字母、不加点）。"""
    family = family.strip()
    given = given.strip()
    if not family:
        return ""
    # 仅当姓氏全大写时规范为"首字母大写、其余小写"（2025 版规则：EINSTEIN A -> Einstein A）；
    # 已是常规大小写（如 "van der Veen"）则原样保留，避免破坏前缀/连字符惯例
    if family.isupper():
        parts = re.split(r"(\s+|-|')", family)
        fam_normalized = "".join(p.capitalize() if p and not p.isspace() and p != "-" and p != "'" else p
                                 for p in parts)
    else:
        fam_normalized = family
    if not given:
        return fam_normalized
    initials = [p[0].upper() for p in re.findall(r"[A-Za-zÀ-ÿ]+", given) if p[0].isalpha()]
    return fam_normalized + " " + " ".join(initials) if initials else fam_normalized


def format_authors(authors, lang="en"):
    """作者列表 -> 'A, B, C, et al' / '甲, 乙, 丙, 等'（>3 取前 3）。"""
    names = []
    for a in authors:
        if a.get("family") or a.get("given") or a.get("name"):
            if a.get("name") and not a.get("family"):
                names.append(a["name"])
            else:
                names.append(format_author_name(a.get("family", ""), a.get("given", "")))
    if not names:
        return ""
    if len(names) <= 3:
        return ", ".join(names)
    tail = "等" if lang == "zh" else "et al"
    return ", ".join(names[:3]) + ", " + tail


# ---------- 条目排版（GB/T 7714—2025，半角标点） ----------

def normalize_issue(issue):
    """合并期号规范：'1-2' -> '1/2'（2025 版：合并期号/卷号用 '/' 分隔）。"""
    issue = issue.strip()
    if re.fullmatch(r"\d+-\d+", issue):
        return issue.replace("-", "/")
    return issue


def build_entry(meta, doc_type="auto", lang="en"):
    """按类型排版为 GB/T 7714—2025 条目。返回引用字符串。"""
    authors = format_authors(meta.get("authors", []), lang)
    title = meta.get("title", "").strip()
    container = meta.get("container", "").strip()
    year = meta.get("year", "") or ""
    volume = str(meta.get("volume", "") or "").strip()
    issue = normalize_issue(str(meta.get("issue", "") or "").strip())
    pages = meta.get("pages", "").strip()
    doi = meta.get("doi", "").strip()
    url = meta.get("url", "").strip()
    src_type = (meta.get("type") or "").lower()
    pub_date = meta.get("published_date", "")

    # 类型判定（可被 --type 覆盖）
    if doc_type == "auto":
        if "preprint" in src_type or "arxiv" in src_type:
            doc_type = "pp"
        elif "book" in src_type or "monograph" in src_type:
            doc_type = "m"
        elif "proceedings" in src_type or "conference" in src_type or "paper-conference" in src_type:
            doc_type = "c"
        elif "dissertation" in src_type or "thesis" in src_type:
            doc_type = "d"
        elif "report" in src_type:
            doc_type = "r"
        else:
            doc_type = "j"

    link = url
    # URL 已含 DOI 时不重复标注（GB/T 7714—2025 规则）
    if doi and "doi.org/" not in link and "doi:" not in link.lower():
        link = (link + " " if link else "") + "DOI: " + doi

    head = authors + ". " if authors else ""

    if doc_type == "j":
        # 期刊论文
        vol_issue = ""
        if volume and issue:
            vol_issue = ", " + str(year) + ", " + volume + "(" + issue + ")"
        elif volume and not issue:
            vol_issue = ", " + str(year) + ", " + volume
        elif issue and not volume:
            # 无卷号：年份(期号)，中间无逗号
            vol_issue = ", " + str(year) + "(" + issue + ")"
        else:
            vol_issue = ", " + str(year)
        page_part = ": " + pages if pages else ""
        entry = head + title + "[J]. " + container + vol_issue + page_part + "."
        if link:
            entry += " " + link + "."
        return entry

    if doc_type == "m":
        entry = head + title + "[M]."
        pub = meta.get("publisher", "").strip()
        if pub:
            entry += " " + pub + "."
        if year:
            entry += " " + year
        if pages:
            entry += ": " + pages
        entry += "."
        if link:
            entry += " " + link + "."
        return entry

    if doc_type == "pp":
        # 预印本：题名[PP/OL]. 平台(创建或修改日期)[引用日期]. 路径. 永久标识符.
        plate = container or "arXiv"
        date_part = "(" + pub_date + ")" if pub_date else ""
        cited = "[" + datetime.now().strftime("%Y-%m-%d") + "]"
        entry = head + title + "[PP/OL]. " + plate + date_part + cited + "."
        if link:
            entry += " " + link + "."
        return entry

    if doc_type == "c":
        entry = head + title + "[C]."
        if container:
            entry += " " + container + ", " + year + ": " + (pages or "") + "."
        if link:
            entry += " " + link + "."
        return entry

    if doc_type == "d":
        entry = head + title + "[D]."
        pub = meta.get("publisher", "").strip()
        if pub:
            entry += " " + pub + ","
        if year:
            entry += " " + year
        if pages:
            entry += ": " + pages
        entry += "."
        if link:
            entry += " " + link + "."
        return entry

    if doc_type == "r":
        entry = head + title + "[R/OL]. "
        if pub_date:
            entry += pub_date + ": "
        if pages:
            entry += pages + ". "
        if link:
            entry += link + "."
        return entry

    # 兜底：未知类型按通用电子资源格式
    entry = head + title + "[Z/OL]."
    if link:
        entry += " " + link + "."
    return entry


# ---------- 主流程 ----------

def main():
    # Windows 控制台默认 GBK，强制 UTF-8 输出避免 UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description="抓取元数据并生成 GB/T 7714—2025 参考文献条目")
    parser.add_argument("--doi", help="DOI，如 10.1038/nature13308")
    parser.add_argument("--arxiv", help="arXiv ID，如 2301.12345")
    parser.add_argument("--url", help="文献 URL（arXiv / doi.org / 出版页面）")
    parser.add_argument("--type", default="auto",
                        help="强制文献类型: j / m / c / d / r / pp / eb / ds / s / p / n / a / cm（默认 auto）")
    parser.add_argument("--lang", default="en", help="条目语言 zh / en（默认 en）")
    args = parser.parse_args()

    meta = None
    note = []

    if args.doi:
        meta = fetch_crossref(args.doi)
        if not meta:
            note.append("CrossRef 查询失败（网络或 DOI 无效）")
    elif args.arxiv:
        meta = fetch_arxiv(args.arxiv)
        if not meta:
            note.append("arXiv 查询失败（网络或 ID 无效）")
    elif args.url:
        url = args.url
        m = re.search(r"arxiv\.org/abs/([0-9.]+[vV]?\d*)", url)
        if m:
            meta = fetch_arxiv(m.group(1))
        elif re.search(r"doi\.org/([^\s]+)", url):
            doi = re.search(r"doi\.org/([^\s]+)", url).group(1)
            meta = fetch_crossref(doi)
        else:
            # 尝试用页面标题搜索 OpenAlex
            text = http_get_text(url)
            t = re.search(r"<title>\s*(.+?)\s*</title>", text, re.S)
            if t:
                meta = fetch_openalex_search(t.group(1).split("|")[0].strip())
            if not meta:
                note.append("URL 无法解析为 DOI/arXiv，且 OpenAlex 搜索无结果")
    else:
        parser.print_help()
        sys.exit(1)

    if not meta:
        print(json.dumps({"error": "未能获取元数据", "notes": note}, ensure_ascii=False, indent=2))
        sys.exit(1)

    entry = build_entry(meta, doc_type=args.type, lang=args.lang)
    print(json.dumps({"meta": meta, "entry": entry, "notes": note},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
