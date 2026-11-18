# Created: 2026-11-18 22:57:24
"""扫描本机 WorkBuddy（腾讯 CodeBuddy 系）的本地数据目录，列出可导入的候选会话。

云端分享页只保留最近约 100 轮，完整历史在本机：
    <WorkBuddy 数据目录>/projects/<项目目录>/<conversationId>.jsonl

用法:
    python wb_scan.py [--root DIR] [--json]

--root 省略时依次尝试 $WORKBUDDY_HOME、~/.workbuddy、%APPDATA%/WorkBuddy、%APPDATA%/CodeBuddy。
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# 控制台/管道统一按 UTF-8 输出，避免中文在 Windows 下乱码
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

USER_QUERY = re.compile(r"<user_query>(.*?)</user_query>", re.S)


def candidate_roots():
    """按优先级列出可能的 WorkBuddy 数据目录。"""
    roots = []
    if os.environ.get("WORKBUDDY_HOME"):
        roots.append(Path(os.environ["WORKBUDDY_HOME"]))
    home = Path.home() / ".workbuddy"
    if home not in roots:
        roots.append(home)
    appdata = os.environ.get("APPDATA")
    if appdata:
        for name in ("WorkBuddy", "workbuddy", "CodeBuddy"):
            p = Path(appdata) / name
            if p not in roots:
                roots.append(p)
    return roots


def projects_dir(root):
    """返回 root 下的 projects 目录（兼容两者任一存在）。"""
    for p in (root / "projects", root):
        if p.is_dir() and any(p.glob("*/*.jsonl")):
            return p
    return None


def fmt_time(ms):
    if not ms:
        return "-"
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def brief(text, width=60):
    """压平空白并截断，用于列表预览。"""
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:width]


def scan_file(path, project):
    """流式读取一个会话 jsonl，统计消息数、时间跨度、标题与首条正文。"""
    try:
        size = path.stat().st_size
    except OSError:
        return None
    messages, records = 0, 0
    title, headline = None, None
    first_ms, last_ms = None, None
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                records += 1
                ts = rec.get("timestamp")
                if isinstance(ts, int):
                    first_ms = ts if first_ms is None else min(first_ms, ts)
                    last_ms = ts if last_ms is None else max(last_ms, ts)
                kind = rec.get("type")
                if kind == "ai-title" and rec.get("aiTitle") and not title:
                    title = rec["aiTitle"]
                if kind != "message":
                    continue
                messages += 1
                if headline is None and rec.get("role") == "user":
                    parts = rec.get("content") or []
                    raw = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
                    m = USER_QUERY.search(raw)
                    headline = brief(m.group(1) if m else raw)
    except OSError as exc:
        print(f"[warn] 无法读取 {path}: {exc}", file=sys.stderr)
        return None
    return {
        "conversationId": path.stem,
        "projectDir": project,
        "messages": messages,
        "records": records,
        "firstTime": fmt_time(first_ms),
        "lastTime": fmt_time(last_ms),
        "bytes": size,
        "title": title or "",
        "headline": headline or "",
        "path": str(path),
    }


def main():
    ap = argparse.ArgumentParser(description="扫描本机 WorkBuddy 会话文件")
    ap.add_argument("--root", help="WorkBuddy 数据目录（默认自动探测）")
    ap.add_argument("--json", action="store_true", help="输出 JSON 数组")
    args = ap.parse_args()

    roots = [Path(args.root)] if args.root else candidate_roots()
    found_root, proj = None, None
    for root in roots:
        proj = projects_dir(root)
        if proj:
            found_root = root
            break
    if not proj:
        print("WARN: 未找到本地会话（尝试过: %s）" % ", ".join(str(r) for r in roots), file=sys.stderr)
        return 1

    items = []
    for project in sorted(p for p in proj.iterdir() if p.is_dir()):
        for path in sorted(project.glob("*.jsonl")):
            info = scan_file(path, project.name)
            if info:
                items.append(info)
    items.sort(key=lambda x: x["lastTime"], reverse=True)

    if args.json:
        # --json 时 stdout 只放纯 JSON，状态行走 stderr
        print(json.dumps(items, ensure_ascii=False, indent=1))
        print(f"FOUND {len(items)} conversation(s) under {found_root}", file=sys.stderr)
    else:
        print(f"{'conversationId':<38} {'msgs':>5}  {'first':<19} {'last':<19} {'KB':>7}  headline")
        for it in items:
            print(f"{it['conversationId']:<38} {it['messages']:>5}  {it['firstTime']:<19} {it['lastTime']:<19} "
                  f"{it['bytes'] / 1024:>7.1f}  {it['headline']}")
        print()
        print(f"FOUND {len(items)} conversation(s) under {found_root}")
    return 0 if items else 1


if __name__ == "__main__":
    sys.exit(main())
