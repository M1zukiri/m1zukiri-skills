# 创建时间: 2026-10-22 14:50:00
"""课件批注工作台的本地服务（由 create_workbench.py 复制到 <工作台>/scripts/）。

启动：
    python scripts/serve_workbench.py --root <工作台目录>
    python scripts/serve_workbench.py --root <工作台目录> --port 8800 --open

接口：
    GET  /api/state          批注与解答快照 + 工作台路径（前端每 1.5s 轮询）
    POST /api/annotations    {action: "save"|"delete"|"resolve", ...}
    GET  /api/health

静态文件：
    <工作台>/web/   →  /web/...（入口 /）
    <工作台>/img/   →  /img/...
    <工作台>/data/  →  /data/...

数据文件（服务只写 annotations.json；answers.json 由 review_workbench.py 写入，服务只读）：
    <工作台>/data/annotations.json
    <工作台>/data/answers.json
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

STUDY = Path(__file__).resolve().parent
WEB = STUDY / "web"
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


def load_manifest(root: Path) -> dict:
    path = root / "data" / "manifest.json"
    if not path.exists():
        raise SystemExit(f"缺少 {path}；先运行 scripts/build_workbench.py --root {root}")
    return json.loads(path.read_text(encoding="utf-8"))

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("application/json", ".json")

_lock = threading.RLock()
_ann: dict | None = None
_answers_cache: dict = {"mtime": 0.0, "doc": {"rev": 0, "answers": {}}}

MAX_Q = 4000
MAX_QUOTE = 3000
MAX_RECTS = 40


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: dict) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def annotations() -> dict:
    global _ann
    if _ann is None:
        _ann = read_json(ANN_PATH, {"rev": 0, "items": []})
        _ann.setdefault("rev", 0)
        _ann.setdefault("items", [])
    return _ann


def answers() -> dict:
    try:
        mtime = ANS_PATH.stat().st_mtime
    except FileNotFoundError:
        return {"rev": 0, "answers": {}}
    if mtime != _answers_cache["mtime"]:
        doc = read_json(ANS_PATH, {"rev": 0, "answers": {}})
        doc.setdefault("rev", 0)
        doc.setdefault("answers", {})
        _answers_cache.update(mtime=mtime, doc=doc)
    return _answers_cache["doc"]


def clean_item(item: dict) -> dict:
    if not isinstance(item, dict):
        raise ValueError("item 必须是对象")
    aid = item.get("id")
    if not isinstance(aid, str) or not (1 <= len(aid) <= 80):
        raise ValueError("id 不合法")
    ch = item.get("ch")
    if not isinstance(ch, str) or len(ch) > 20:
        raise ValueError("ch 不合法")
    page = item.get("page")
    if not isinstance(page, int) or page < 1:
        raise ValueError("page 不合法")
    rects = item.get("rects")
    if not isinstance(rects, list) or not rects:
        raise ValueError("rects 不合法")
    out_rects = []
    for r in rects[:MAX_RECTS]:
        if not isinstance(r, dict):
            raise ValueError("rect 不合法")
        try:
            x, y = float(r["x"]), float(r["y"])
            w, h = float(r["w"]), float(r["h"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("rect 字段不合法")
        x, y = max(0.0, min(1.0, x)), max(0.0, min(1.0, y))
        w, h = max(0.0, min(1.0, w)), max(0.0, min(1.0, h))
        if x + w > 1.0:
            w = 1.0 - x
        if y + h > 1.0:
            h = 1.0 - y
        out_rects.append({"x": round(x, 5), "y": round(y, 5),
                          "w": round(w, 5), "h": round(h, 5)})
    clean = {
        "id": aid,
        "ch": ch,
        "page": page,
        "kind": str(item.get("kind") or "line")[:20],
        "rects": out_rects,
        "quote": str(item.get("quote") or "")[:MAX_QUOTE],
        "tag": str(item.get("tag") or "不懂")[:20],
        "q": str(item.get("q") or "")[:MAX_Q],
        "created": str(item.get("created") or now_iso())[:40],
        "updated": now_iso(),
        "resolved": bool(item.get("resolved", False)),
    }
    parent = item.get("parent")
    if isinstance(parent, str) and parent:
        clean["parent"] = parent[:80]
    return clean


class Handler(BaseHTTPRequestHandler):
    server_version = "EngMathStudy/1.0"

    def log_message(self, fmt: str, *args) -> None:  # 静默静态请求，只保留错误
        if self.command != "GET" or self.path.startswith("/api/"):
            sys.stdout.write(f"[{time.strftime('%H:%M:%S')}] {self.command} {self.path}\n")
            sys.stdout.flush()

    # ---------- 基础输出 ----------
    def send_json(self, obj: dict, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path) -> None:
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",
                                                 "application/json"):
            ctype += "; charset=utf-8"
        try:
            data = path.read_bytes()
        except OSError:
            self.send_json({"error": "not found"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        rel = str(path.relative_to(STUDY)).replace("\\", "/")
        if rel.startswith(("img/", "web/vendor/")):
            self.send_header("Cache-Control", "public, max-age=86400")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def read_body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 2_000_000:
            raise ValueError("请求体为空或过大")
        return json.loads(self.rfile.read(n).decode("utf-8"))

    # ---------- GET ----------
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/state":
            with _lock:
                ann = annotations()
                ans = answers()
                payload = {
                    "annotationsRev": ann.get("rev", 0),
                    "annotations": ann.get("items", []),
                    "answers": ans.get("answers", {}),
                    "answersRev": ans.get("rev", 0),
                    "serverTime": now_iso(),
                    "workbench": {"root": str(STUDY)},
                }
            return self.send_json(payload)
        if path == "/api/health":
            return self.send_json({"ok": True, "time": now_iso()})
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if path in ("/", "/index.html"):
            return self.send_file(WEB / "index.html")
        rel = unquote(path).lstrip("/")
        target = (STUDY / rel).resolve()
        try:
            target.relative_to(STUDY.resolve())
        except ValueError:
            return self.send_json({"error": "forbidden"}, 403)
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            return self.send_json({"error": "not found", "path": rel}, 404)
        return self.send_file(target)

    # ---------- POST ----------
    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/annotations":
            return self.send_json({"error": "not found"}, 404)
        try:
            body = self.read_body()
            action = body.get("action")
            with _lock:
                ann = annotations()
                items = ann["items"]
                if action == "save":
                    clean = clean_item(body.get("item") or {})
                    existing = next((i for i in items if i.get("id") == clean["id"]), None)
                    if existing is not None:
                        clean["created"] = existing.get("created", clean["created"])
                        items[items.index(existing)] = clean
                    else:
                        items.append(clean)
                    ann["rev"] = int(ann.get("rev", 0)) + 1
                    write_json(ANN_PATH, ann)
                    return self.send_json({"ok": True, "rev": ann["rev"], "item": clean})
                if action == "delete":
                    aid = body.get("id")
                    before = len(items)
                    items[:] = [i for i in items if i.get("id") != aid]
                    if len(items) == before:
                        return self.send_json({"ok": True, "rev": ann["rev"], "deleted": 0})
                    ann["rev"] = int(ann.get("rev", 0)) + 1
                    write_json(ANN_PATH, ann)
                    return self.send_json({"ok": True, "rev": ann["rev"], "deleted": 1})
                if action == "resolve":
                    aid = body.get("id")
                    resolved = bool(body.get("resolved", True))
                    found = False
                    for item in items:
                        if item.get("id") == aid:
                            item["resolved"] = resolved
                            item["updated"] = now_iso()
                            found = True
                    if found:
                        ann["rev"] = int(ann.get("rev", 0)) + 1
                        write_json(ANN_PATH, ann)
                    return self.send_json({"ok": True, "rev": ann["rev"], "found": found})
                raise ValueError("未知 action")
        except (ValueError, json.JSONDecodeError) as exc:
            return self.send_json({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001 —— 服务不应因单个请求崩溃
            sys.stderr.write(f"POST {path} 失败: {exc}\n")
            return self.send_json({"error": "internal error"}, 500)


def main() -> None:
    ap = argparse.ArgumentParser(description="启动课件批注工作台的本地服务")
    ap.add_argument("--root", default=".", help="工作台目录（含 workbench.json），默认从当前目录向上查找")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true", help="启动后打开浏览器")
    args = ap.parse_args()

    global STUDY, WEB, DATA, ANN_PATH, ANS_PATH
    root = find_root(Path(args.root))
    manifest = load_manifest(root)
    STUDY = root
    WEB = root / "web"
    DATA = root / "data"
    ANN_PATH = DATA / "annotations.json"
    ANS_PATH = DATA / "answers.json"

    DATA.mkdir(parents=True, exist_ok=True)
    if not ANN_PATH.exists():
        write_json(ANN_PATH, {"rev": 0, "items": []})
    if not ANS_PATH.exists():
        write_json(ANS_PATH, {"rev": 0, "answers": {}})

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    project = manifest.get("project") or {}
    title = project.get("title") or "课件批注工作台"
    print(f"{title} · 批注工作台已启动: {url}")
    print(f"  工作台目录: {root}")
    print(f"  批注数据: {ANN_PATH}")
    print(f"  解答数据: {ANS_PATH}")
    print("  Ctrl+C 停止")
    sys.stdout.flush()
    if args.open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
