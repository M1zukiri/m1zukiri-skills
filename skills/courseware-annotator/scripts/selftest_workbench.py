# 创建时间: 2026-10-22 18:00:00
"""工作台端到端自检：结构、服务、批注读写、解答文件。

需要先启动服务（scripts/serve_workbench.py），然后：

    python scripts/selftest_workbench.py --root <工作台> [--url http://127.0.0.1:8765]

检查项：
    1. 工作台结构（workbench.json / data/manifest.json / web / scripts）
    2. 服务健康、首页与静态资源可访问
    3. 建一条临时批注 → 服务端可见 → 删除
    4. answers.json 可解析

返回码 0 = 全部通过；1 = 有失败项。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def find_root(start: Path) -> Path:
    cur = start.resolve()
    for _ in range(8):
        if (cur / "workbench.json").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise SystemExit(f"找不到 workbench.json（从 {start} 向上查找）；请用 --root 指定工作台目录。")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def http_json(url: str, data: dict | None = None):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def http_status(url: str) -> int:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def main() -> None:
    ap = argparse.ArgumentParser(description="批注工作台端到端自检")
    ap.add_argument("--root", default=".", help="工作台目录（含 workbench.json）")
    ap.add_argument("--url", default="http://127.0.0.1:8765", help="服务地址")
    args = ap.parse_args()

    root = find_root(Path(args.root))
    base = args.url.rstrip("/")
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    # 1. 工作台结构
    for rel in ("workbench.json", "data/manifest.json", "web/app.js", "web/index.html",
                "scripts/build_workbench.py", "scripts/serve_workbench.py",
                "scripts/review_workbench.py"):
        check(f"文件存在 {rel}", (root / rel).exists())
    launcher = root / "启动工作台.bat"
    if launcher.exists():
        raw = launcher.read_bytes()
        lone_lf = raw.count(b"\n") - raw.count(b"\r\n")
        check("启动脚本为 CRLF", lone_lf == 0, f"{lone_lf} 个 LF 换行" if lone_lf else "")
    manifest = {}
    try:
        manifest = json.loads((root / "data/manifest.json").read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        check("manifest 可解析", False, str(exc))
    chapters = manifest.get("chapters") or []
    check("manifest 有章节", bool(chapters))
    if failures:
        print("\n结构不完整，先构建工作台：python scripts/build_workbench.py --root", root)
        sys.exit(1)

    # 2. 服务
    try:
        health = http_json(f"{base}/api/health")
        check("服务健康 /api/health", bool(health.get("ok")), str(health))
    except Exception as exc:  # noqa: BLE001
        check("服务健康 /api/health", False,
              f"{exc}；先启动 scripts/serve_workbench.py --root {root}")
        sys.exit(1)
    check("首页可访问", http_status(f"{base}/") == 200)
    check("清单可访问", http_status(f"{base}/data/manifest.json") == 200)
    first = chapters[0]
    first_page = f"{base}/img/{first['id']}/001.webp"
    check("页图可访问", http_status(first_page) == 200, first_page)
    state = http_json(f"{base}/api/state")
    check("状态接口返回批注列表", isinstance(state.get("annotations"), list))
    check("状态接口返回工作台路径",
          bool((state.get("workbench") or {}).get("root")),
          str((state.get("workbench") or {}).get("root")))

    # 3. 临时批注读写
    test_id = "selftest-" + datetime.now().strftime("%H%M%S")
    try:
        http_json(f"{base}/api/annotations", {
            "action": "save",
            "item": {
                "id": test_id, "ch": first["id"], "page": 1, "kind": "line",
                "rects": [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.04}],
                "quote": "自检临时批注", "tag": "不懂",
                "q": "这是一条自检批注，保存后会被删除。",
                "created": now_iso(), "resolved": False,
            },
        })
        after_save = http_json(f"{base}/api/state")
        check("批注可写入", any(a.get("id") == test_id for a in after_save.get("annotations", [])))
    finally:
        try:
            http_json(f"{base}/api/annotations", {"action": "delete", "id": test_id})
        except Exception:  # noqa: BLE001
            pass
    after_delete = http_json(f"{base}/api/state")
    check("批注可删除", not any(a.get("id") == test_id for a in after_delete.get("annotations", [])))

    # 4. 解答文件
    answers_path = root / "data" / "answers.json"
    try:
        answers = json.loads(answers_path.read_text(encoding="utf-8"))
        check("answers.json 可解析", isinstance(answers.get("answers"), dict))
    except Exception as exc:  # noqa: BLE001
        check("answers.json 可解析", False, str(exc))

    print()
    if failures:
        print(f"自检失败 {len(failures)} 项：{', '.join(failures)}")
        sys.exit(1)
    print("自检通过：工作台结构、服务、批注读写、解答文件均正常。")


if __name__ == "__main__":
    main()
