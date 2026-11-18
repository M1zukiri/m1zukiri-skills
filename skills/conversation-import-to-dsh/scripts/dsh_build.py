# Created: 2026-11-18 22:58:51
"""归一化对话 JSON -> DSH Session v4 明文 JSONL。

事件序列（每个用户轮 = 一个 turn）：
  turn/start -> step/start -> [turn1: system/message] -> user/message
              -> [turn1: request/header(带 tools) + request/context + session/title]
              -> [有回复时: assistant/message] -> step/end -> turn/end
seq 从 0 连续；行编码 json.dumps(ensure_ascii=False, separators=(",", ":")), 与 DSH encoder 逐字节一致。

两个必须处理的坑（否则导入的会话一续聊就坏）：
  1. request/header 必须带 tools 基线。deepseek 路由的 toolUpdate 是 addition-only，基线为空时
     下一轮会把所有工具标成 deferLoading 发给服务端，报 tools: at least one tool must have defer_loading=false。
     -> 默认从本机某个真实会话的 request/header.header.tools 复制工具表。
  2. 历史里第一个 surface 必须是 system/message。deepseek 只支持 systemPromptUpdate=in-history，
     历史里没有 system 节点时 DSH 会把新 system 消息 append 到历史中间，格式校验要求
     「非首位 system/message 必须有受保护的头部 system 节点」，文件随即损坏。
     -> 默认从本机真实会话的 system/message 复制 system prompt，写成第一个 surface。

用法:
  python dsh_build.py <norm.json> -o <session.jsonl> --cwd <绝对路径>
        [--title T] [--session-id ID] [--agent-preset NAME] [--provider P] [--model M]
        [--tools-file F] [--system-file F] [--dsh-home H] [--created-at MS]
"""
import argparse
import json
import os
import sys
import uuid
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

PLACEHOLDERS = {"Interrupted by user", "interrupted by user"}
DEFAULT_PROVIDER, DEFAULT_MODEL = "deepseek-official", "deepseek-flash"
CONTEXT_WINDOW = 1048576
MAX_TOKENS = 256000


# ------------------------------------------------------------ DSH 本机数据
def dsh_home(arg=None):
    """DSH_HOME: --dsh-home > 环境变量 > ~/.dsh"""
    if arg:
        return Path(arg)
    env = os.environ.get("DSH_HOME")
    return Path(env) if env else Path.home() / ".dsh"


def decompress_zstd(blob):
    """DSH 的 .zstd 是一串独立帧，无 frame content size，必须用 stream_reader 跨帧读。
    正在被 DSH 追加写入的会话可能带一个不完整的末帧，这里按前缀恢复（够取基线即可）。"""
    import io
    import zstandard
    out = bytearray()
    reader = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(blob), read_across_frames=True)
    try:
        while True:
            chunk = reader.read(1 << 20)
            if not chunk:
                break
            out += chunk
    except zstandard.ZstdError:
        pass
    return bytes(out)


def real_session_texts(home, prefer_cwd=None):
    """按「cwd 匹配优先、mtime 从新到旧」遍历本机真实 v4 会话，逐个产出明文 JSONL 文本。

    优先取与目标 cwd 相同的会话：工具表与 system prompt 都跟 agent preset/插件集走，
    跨项目借用别的会话当基线，工具集可能对不上当前部署。
    """
    root = home / "sessions"
    files = list(root.glob("*/*/session.v4.jsonl.zstd")) + list(root.glob("*/*/session.v4.jsonl"))
    decoded = []
    for path in files:
        try:
            blob = path.read_bytes()
            text = (decompress_zstd(blob) if path.suffix == ".zstd" else blob).decode("utf-8", "replace")
        except Exception as exc:                     # 单个坏文件不影响整体探测
            print(f"[warn] 跳过无法读取的会话 {path}: {exc}", file=sys.stderr)
            continue
        same_cwd = False
        if prefer_cwd:
            try:
                found = json.loads(text.split("\n", 1)[0]).get("cwd") or ""
                same_cwd = os.path.normcase(found) == os.path.normcase(prefer_cwd)
            except (json.JSONDecodeError, ValueError):
                pass
        decoded.append((same_cwd, path.stat().st_mtime, path, text))
    decoded.sort(key=lambda item: (not item[0], -item[1]))
    for _, _, path, text in decoded:
        yield path, text


def scan_baselines(home, prefer_cwd=None):
    """从真实会话里找工具基线（第一个 request/header.header.tools）与 system prompt。"""
    tools = system_prompt = None
    tools_src = system_src = None
    for path, text in real_session_texts(home, prefer_cwd):
        for line in text.split("\n"):
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            data = event.get("data") or {}
            if tools is None and event.get("type") == "request/header":
                found = (data.get("header") or {}).get("tools")
                if found:
                    tools, tools_src = found, path
            elif system_prompt is None and event.get("type") == "system/message":
                content = (data.get("message") or {}).get("content") or []
                body = "".join(b.get("text", "") for b in content if isinstance(b, dict))
                if body.strip():
                    system_prompt, system_src = body, path
        if tools is not None and system_prompt is not None:
            break
    return tools, tools_src, system_prompt, system_src


def load_tools(path):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        if isinstance(obj.get("tools"), list):
            return obj["tools"]
        header = (obj.get("data") or {}).get("header") or obj.get("header") or {}
        if isinstance(header.get("tools"), list):
            return header["tools"]
    raise SystemExit(f"无法从 {path} 解析工具表：需要 tools 数组，或含 header.tools 的对象")


# ------------------------------------------------------------ 组装
def collect_turns(norm):
    """user 轮开新 turn，其后（到下一个 user 轮前的）assistant 正文并入该 turn。"""
    turns, lead, last_user = [], [], None
    for rd in norm.get("rounds") or []:
        kind = rd.get("messageType")
        if kind == "user":
            user = (rd.get("userQuery") or "").strip()
            if not user:
                user = "\n".join(it.get("text") or "" for it in rd.get("items") or [])
                user = user.strip()
            last_user = {"user": user, "assistant": [], "t": int(rd.get("createTime") or 0), "ft": None}
            turns.append(last_user)
        elif kind == "assistant":
            texts = [it.get("text") for it in rd.get("items") or [] if it.get("type") == "text"]
            texts = [t.strip() for t in texts if isinstance(t, str) and t.strip() and t.strip() not in PLACEHOLDERS]
            if not texts:
                continue
            if last_user is None:                     # 罕见：首条就是 assistant，先挂起
                lead.extend(texts)
                continue
            last_user["assistant"].extend(texts)
            ft = rd.get("finishTime")
            if ft:
                last_user["ft"] = int(ft)
    if not turns:
        raise SystemExit("归一化 JSON 里没有 messageType=user 的轮次，无法生成会话")
    if lead:                                          # 挂起的开头 assistant 内容并入首轮，避免丢字
        turns[0]["assistant"] = lead + turns[0]["assistant"]
        print(f"[note] 首条 user 之前有 {len(lead)} 段 assistant 正文，已并入首轮")
    for turn in turns:
        turn["atext"] = "\n\n".join(turn["assistant"]).strip()
    return turns


def build_events(turns, title, tools, system_prompt, provider, model):
    events, seq, clock = [], 0, 0

    def add(kind, time_ms, data, **extra):
        nonlocal seq, clock
        clock = max(clock, int(time_ms))
        row = {"type": kind, "seq": seq, "time": clock, "data": data}
        row.update(extra)
        events.append(row)
        seq += 1

    provider_source = {"kind": "model", "provider": provider, "model": model}
    for index, turn in enumerate(turns):
        number = index + 1
        start = turn["t"] or 0
        end = turn["ft"] or (start + 1000)
        has_assistant = bool(turn["atext"])
        need_step = has_assistant or index == 0

        add("turn/start", start, {"turn": number})
        if need_step:
            add("step/start", start, {"turn": number, "step": 1})
        if index == 0:
            add("system/message", start, {"turn": number, "step": 1, "message": {
                "role": "system", "source": {"kind": "system-prompt"},
                "content": [{"type": "text", "text": system_prompt}],
                "id": str(uuid.uuid4())}}, surfaceOp="append")
        add("user/message", start, {
            "content": [{"type": "text", "text": turn["user"]}],
            "source": {"kind": "user", "rpcId": str(uuid.uuid4()), "clientTimeZone": "Asia/Shanghai"},
            "role": "user", "id": str(uuid.uuid4())}, surfaceOp="append")
        if index == 0:
            add("request/header", start, {"header": {
                "config": {"provider": provider, "model": model,
                           "reasoningEffort": "high", "maxTokens": MAX_TOKENS},
                "adapterDefaults": {"maxTokens": True},
                "tools": tools}, "reason": "initial"})
            add("request/context", start, {"provider": provider, "model": model,
                                           "contextWindow": CONTEXT_WINDOW,
                                           "systemPromptUpdate": "in-history"})
            # messageSeqs 必须为空的前提是 source.kind="user"（不受「引用更早 user/message」约束）
            add("session/title", start + 1, {"title": title, "messageSeqs": [], "source": {"kind": "user"}})
        if has_assistant:
            text = turn["atext"]
            stream = [
                {"type": "chunk", "time": end - 2,
                 "chunk": {"type": "block-start", "index": 0, "blockType": "text"}},
                {"type": "text-chunks", "time0": end - 1, "index": 0, "dt": [0], "texts": [text]},
                {"type": "chunk", "time": end,
                 "chunk": {"type": "block-end", "index": 0, "block": {"type": "text", "text": text}}},
            ]
            add("assistant/message", end, {"turn": number, "step": 1, "stream": stream, "message": {
                "role": "assistant", "source": provider_source,
                "content": [{"type": "text", "text": text}],
                "id": str(uuid.uuid4())}}, surfaceOp="append")
        if need_step:
            add("step/end", end, {"turn": number, "step": 1})
        add("turn/end", end, {"turn": number, "reason": {"kind": "completed"}})
    return events


def build_header(args, turns):
    header = {"type": "session", "version": 4,
              "id": args.session_id or "session-" + str(uuid.uuid4()),
              "createdAt": args.created_at or int(turns[0]["t"] or 0),
              "cwd": args.cwd, "isSeeded": False, "delegationDepth": 0}
    if args.agent_preset:
        header["agentPreset"] = args.agent_preset
    return header


def main():
    ap = argparse.ArgumentParser(description="归一化对话 -> DSH Session v4 明文 JSONL")
    ap.add_argument("input", help="wb_extract.py 输出的归一化 JSON")
    ap.add_argument("-o", "--out", required=True, help="输出明文 JSONL")
    ap.add_argument("--cwd", required=True, help="会话所属工作目录（绝对路径，决定 header.cwd 与安装目录）")
    ap.add_argument("--title", help="会话标题（默认取归一化 title +（WorkBuddy 导入））")
    ap.add_argument("--session-id", help="会话 id（默认 session-<uuid>）")
    ap.add_argument("--agent-preset", default="", help="header.agentPreset；默认留空，走部署默认")
    ap.add_argument("--provider", default=DEFAULT_PROVIDER)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--tools-file", "--tools-snapshot", dest="tools_file",
                    help="工具表 JSON（默认从本机真实会话提取）")
    ap.add_argument("--system-file", "--system-prompt", dest="system_file",
                    help="system prompt 文本文件（默认从本机真实会话提取）")
    ap.add_argument("--dsh-home", help="DSH_HOME（默认 $DSH_HOME 或 ~/.dsh，仅用于自动提取基线）")
    ap.add_argument("--created-at", type=int, help="header.createdAt（epoch ms，默认首轮时间）")
    args = ap.parse_args()

    try:
        import zstandard  # noqa: F401
    except ImportError:
        print("缺少依赖：pip install zstandard", file=sys.stderr)
        return 2

    norm = json.loads(Path(args.input).read_text(encoding="utf-8"))
    turns = collect_turns(norm)

    home = dsh_home(args.dsh_home)
    need_probe = not (args.tools_file and args.system_file)
    tools = tools_src = system_prompt = system_src = None
    if args.tools_file:
        tools, tools_src = load_tools(args.tools_file), args.tools_file
    if args.system_file:
        system_prompt = Path(args.system_file).read_text(encoding="utf-8").rstrip("\n")
        system_src = args.system_file
    if need_probe:
        print(f"探测 DSH 基线：{home / 'sessions'}")
        probe_tools, probe_tools_src, probe_system, probe_system_src = scan_baselines(home, args.cwd)
        if tools is None:
            tools, tools_src = probe_tools, probe_tools_src
        if system_prompt is None:
            system_prompt, system_src = probe_system, probe_system_src
    if not tools:
        print("ERROR: 未找到可用的工具基线。请用 --tools-file 指定工具表，"
              "或先在本机真实跑一次 DSH 会话（~/.dsh/sessions 下要有 v4 会话）。", file=sys.stderr)
        return 3
    if not system_prompt:
        print("ERROR: 未找到可用的 system prompt。请用 --system-file 指定，"
              "或先在本机真实跑一次 DSH 会话。", file=sys.stderr)
        return 3

    title = args.title or ((norm.get("title") or "WorkBuddy 对话").strip() + "（WorkBuddy 导入）")
    header = build_header(args, turns)
    events = build_events(turns, title, tools, system_prompt, args.provider, args.model)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(header, ensure_ascii=False, separators=(",", ":")) + "\n")
        for event in events:
            fh.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")

    # 透明化：文字导入不重建工具调用，丢弃的条目要报出来
    dropped = {"reasoning": 0, "tool-call": 0, "tool-result": 0}
    for rd in norm.get("rounds") or []:
        for it in rd.get("items") or []:
            if it.get("type") in dropped:
                dropped[it["type"]] += 1
    total_chars = sum(len(t["user"]) + len(t["atext"]) for t in turns)
    print(f"tools={len(tools)} (source: {tools_src})")
    print(f"system_prompt={len(system_prompt)} chars (source: {system_src})")
    print(f"turns={len(turns)} events={len(events)} prose_chars={total_chars}")
    print("dropped_items " + " ".join(f"{k}={v}" for k, v in dropped.items())
          + " (只导入文字正文，reasoning/工具调用不进 DSH 历史)")
    print(f"title={title}")
    print(f"session_id={header['id']} cwd={header['cwd']}")
    print(f"out={out} ({out.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
