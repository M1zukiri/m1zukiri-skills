# Created: 2026-11-18 23:00:30
"""把 DSH 会话装进 $DSH_HOME/sessions 并在 workspace.json 里入账（GUI 列表可见）。

两件事：
  1. 文件落位：<DSH_HOME>/sessions/<projectKey(cwd)>/<encodeSegment(sessionId)>/session.v4.jsonl.zstd
     projectKey 逐 UTF-16 码元编码：/ \\ : 折叠成单个 -，[A-Za-z0-9._-] 原样，其余 ~XXXX 大写，
     去前导 -，截 251，包 --…--。
  2. workspace 入账：把 session id 插到 workspace.json 里 path 匹配 cwd 的 workspace 的 sessionIds 头部。
     GUI 的会话列表是按 workspace → session 组织的，不写入账数组就不会显示。
     改前先备份 workspace.json；已入账则跳过（幂等）。

注意：DSH 运行时会整体回写 workspace.json，务必在 DSH 关闭时执行。

用法:
  python dsh_install.py --session <session.jsonl|session.v4.jsonl.zstd> [--cwd PATH]
        [--dsh-home H] [--dry-run]
  不覆盖已有会话文件；--cwd 省略时取 header.cwd（与 header 不一致则报错）。
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))


def dsh_home(arg=None):
    """DSH_HOME: --dsh-home > 环境变量 > ~/.dsh"""
    if arg:
        return Path(arg)
    env = os.environ.get("DSH_HOME")
    return Path(env) if env else Path.home() / ".dsh"


def _code_units(text):
    """按 JS charCodeAt 语义逐 UTF-16 码元遍历（增补面字符会拆成代理对）。"""
    raw = text.encode("utf-16-le")
    for i in range(0, len(raw), 2):
        yield int.from_bytes(raw[i:i + 2], "little")


def _safe(unit):
    ch = chr(unit)
    return ch != "~" and ch.isascii() and (ch.isalnum() or ch in "._-")


def project_key(cwd):
    """复刻 dsh-session-persistence-jsonl 的 projectKey()。"""
    if not cwd:
        raise ValueError("cwd 不能为空")
    out, separator_run = [], False
    for unit in _code_units(cwd):
        ch = chr(unit)
        if ch in "/\\:":
            if not separator_run:
                out.append("-")
            separator_run = True
        elif _safe(unit):
            out.append(ch)
            separator_run = False
        else:
            out.append("~" + format(unit, "04X"))
            separator_run = False
    readable = "".join(out).lstrip("-") or "root"
    return f"--{readable[:251]}--"


def encode_segment(raw):
    """复刻 encodeSegment()：会话 id -> 单段安全路径。"""
    if not raw:
        raise ValueError("不能编码空段")
    if raw == ".":
        return "~002E"
    if raw == "..":
        return "~002E~002E"
    return "".join(chr(u) if _safe(u) else "~" + format(u, "04X") for u in _code_units(raw))


def read_header(session_path):
    """从 .jsonl 或 .zstd 读 header 行。"""
    if session_path.suffix == ".zstd":
        try:
            import dsh_pack
        except ImportError:
            raise SystemExit("缺少依赖：pip install zstandard")
        plain = dsh_pack.decompress(session_path.read_bytes())
        return json.loads(plain.decode("utf-8").split("\n")[0])
    with open(session_path, encoding="utf-8") as fh:
        return json.loads(fh.readline())


def norm_path(path):
    """工作目录比较用的规范化：Windows 下大小写/分隔符不敏感。"""
    return os.path.normcase(os.path.abspath(str(path)))


def find_workspace(doc, cwd):
    for uid, ws in (doc.get("tables") or {}).get("workspaces", {}).items():
        if norm_path(ws.get("path") or "") == norm_path(cwd):
            return uid, ws
    return None, None


def backup_workspace(ws_path):
    backup = ws_path.with_name(ws_path.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(ws_path, backup)
    return backup


def main():
    ap = argparse.ArgumentParser(description="安装 DSH 会话并在 workspace.json 入账")
    ap.add_argument("--session", required=True, help="会话文件（明文 .jsonl 会先压缩）")
    ap.add_argument("--cwd", help="会话所属工作目录（默认取 header.cwd）")
    ap.add_argument("--dsh-home", help="DSH_HOME（默认 $DSH_HOME 或 ~/.dsh）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不写任何文件")
    args = ap.parse_args()

    session_path = Path(args.session)
    if not session_path.is_file():
        print(f"ERROR: 文件不存在: {session_path}", file=sys.stderr)
        return 2
    header = read_header(session_path)
    sid = header.get("id")
    cwd = args.cwd or header.get("cwd")
    if not sid or not cwd:
        print("ERROR: header 缺 id 或 cwd，且未用 --cwd 指定", file=sys.stderr)
        return 2
    if header.get("cwd") and norm_path(header["cwd"]) != norm_path(cwd):
        print(f"ERROR: --cwd {cwd} 与 header.cwd {header['cwd']} 不一致", file=sys.stderr)
        return 2
    if header.get("version") != 4:
        print(f"ERROR: 只支持 Session v4，文件 header.version={header.get('version')}", file=sys.stderr)
        return 2

    home = dsh_home(args.dsh_home)
    key = project_key(cwd)
    target_dir = home / "sessions" / key / encode_segment(sid)
    target = target_dir / "session.v4.jsonl.zstd"

    print(f"projectKey: {key}")
    print(f"session_id: {sid}")
    print(f"cwd: {cwd}")

    # 先摸 workspace.json：既用于「已入账则幂等」，也用于最后一步入账
    ws_path = home / "storages" / "workspace.json"
    doc = json.loads(ws_path.read_text(encoding="utf-8-sig")) if ws_path.is_file() else None
    uid, ws = find_workspace(doc, cwd) if doc else (None, None)
    ids = ws.setdefault("sessionIds", []) if ws else []

    if target.exists():
        if sid in ids:
            print(f"已安装且已在 workspace {uid} 入账，跳过（幂等）")
            return 0
        # 文件在、登记丢了：DSH 退出时可能把内存里的注册表整体回写，覆盖掉脚本写入的登记。
        # 这种情况不覆盖会话文件，只把 id 补回 sessionIds（所以本脚本可以随时重跑修登记）。
        print(f"会话文件已存在，跳过复制、只补登记: {target}")
    elif args.dry_run:
        print(f"[dry-run] 会写入: {target}")
    else:
        target_dir.mkdir(parents=True, exist_ok=True)
        if session_path.suffix == ".zstd":
            shutil.copyfile(session_path, target)
        else:
            try:
                import dsh_pack
            except ImportError:
                print("缺少依赖：pip install zstandard", file=sys.stderr)
                return 2
            target.write_bytes(dsh_pack.compress(session_path.read_text(encoding="utf-8")))
        print(f"session file: {target} ({target.stat().st_size} B)")

    # ---- 2. workspace.json 入账 ----
    if doc is None:
        print(f"WARN: 没有 {ws_path}（DSH 还没建过项目）。会话文件已装好，"
              f"在 GUI 里为 {cwd} 新建项目后即可看到，或手写一条 workspace 记录。", file=sys.stderr)
        return 2
    if ws is None:
        print(f"WARN: workspace.json 里没有 path 匹配 {cwd} 的 workspace。"
              f"请在 GUI 里先为该目录建项目（或把会话装到已有项目的 cwd）。", file=sys.stderr)
        return 2
    if sid in ids:
        print(f"已在 workspace {uid} 入账，跳过（幂等）")
        return 0
    if args.dry_run:
        print(f"[dry-run] 会把 {sid} 插到 workspace {uid} 的 sessionIds 头部")
        return 0

    backup = backup_workspace(ws_path)
    ids.insert(0, sid)
    ws["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()) + ".000Z"
    tmp = ws_path.with_name(ws_path.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, ws_path)
    print(f"workspace: {uid} -> sessionIds[0]={sid}")
    print(f"backup: {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
