# Created: 2026-11-18 22:57:53
"""把 WorkBuddy 对话归一化成统一的 JSON（下游 dsh_build.py 的唯一输入格式）。

支持两种来源：
  1. 本地事件流  <WorkBuddy>/projects/<项目目录>/<conversationId>.jsonl  —— 唯一完整来源
  2. 云端分享页  conversation-data.json                                  —— 只保留最近约 100 轮，首轮可能被截断

输出结构（字段顺序固定）：
  source / conversationId / title / assistantName / modelName / rounds[]
  rounds[] = roundId / messageType / createTime / finishTime / items[] / requestId / model / userQuery
  items[]  = type(text|reasoning|tool-call|tool-result) / text / tool

处理规则：
  - tool-call 与 tool-result 按 callId join（本地两者是分离的平级记录，分享页把结果内嵌在 tool.result）
  - arguments 是 JSON 字符串时解析为对象，解析失败原样保留
  - reasoning 正文在 rawContent[0].text（仅个别记录 content 非空，content 优先）
  - 用户正文原样保留在 items[].text，另从 <system-reminder> 包装里抽出纯用户原话到 userQuery
  - "Interrupted by user" 是中断占位符，不算正文（仍保留条目，finishedTime 置空）

用法:
  python wb_extract.py <source> -o <norm.json> [--kind auto|local|share] [--verify [分享页.json]]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

# 控制台/管道统一按 UTF-8 输出，避免中文在 Windows 下乱码
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

USER_QUERY = re.compile(r"<user_query>(.*?)</user_query>", re.S)
SYSTEM_REMINDER = re.compile(r"<system-reminder\b.*?</system-reminder>", re.S)
PLACEHOLDERS = {"Interrupted by user", "interrupted by user"}
SKIP_RECORD_TYPES = {"session-meta", "file-history-snapshot", "ai-title"}
ROUND_KEYS = ["roundId", "messageType", "createTime", "finishTime", "items", "requestId", "model", "userQuery"]
ITEM_KEYS = ["type", "text", "tool"]
TOOL_KEYS = ["name", "callId", "status", "args", "result"]


def parse_args_field(value):
    """arguments 可能是 JSON 字符串、对象或 None；字符串尽量解析。"""
    if value is None or isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def text_of(parts):
    """消息 content 数组里所有 text 拼接（不截断）。"""
    if isinstance(parts, str):
        return parts
    out = [p["text"] for p in parts or [] if isinstance(p, dict) and isinstance(p.get("text"), str)]
    return "".join(out) if out else None


def text_of_output(output):
    """function_call_result.output / 分享页 tool.result -> 纯文本。"""
    if isinstance(output, dict):
        t = output.get("text")
        return t if isinstance(t, str) else json.dumps(output, ensure_ascii=False)
    if isinstance(output, list):
        return json.dumps(output, ensure_ascii=False)
    if isinstance(output, str):
        return output
    return None


def extract_user_query(text):
    """有 <user_query> 取内文；否则剥掉 <system-reminder> 包装；都没有则用原文。"""
    if not text:
        return None
    m = USER_QUERY.search(text)
    if m:
        return m.group(1).strip()
    cleaned = SYSTEM_REMINDER.sub("", text).strip()
    return cleaned or text.strip()


def make_item(kind, text=None, tool=None):
    return {"type": kind, "text": text, "tool": None if tool is None else {k: tool.get(k) for k in TOOL_KEYS}}


def finish(rounds, meta):
    """补 roundId、固定键序、统计。"""
    for rd in rounds:
        src_ids = rd.pop("_src_ids", [])
        if rd.get("roundId") is None:
            rd["roundId"] = src_ids[0] if src_ids else None
    counts = Counter(rd["messageType"] for rd in rounds)
    items = Counter(it["type"] for rd in rounds for it in rd["items"])
    norm = [{"roundId": rd["roundId"], "messageType": rd["messageType"],
             "createTime": rd["createTime"], "finishTime": rd["finishTime"],
             "items": [{k: it[k] for k in ITEM_KEYS} for it in rd["items"]],
             "requestId": rd.get("requestId"), "model": rd.get("model"),
             "userQuery": rd.get("userQuery")} for rd in rounds]
    data = {"source": meta["source"], "conversationId": meta["conversationId"],
            "title": meta["title"], "assistantName": meta["assistantName"],
            "modelName": meta["modelName"], "rounds": norm}
    return data, counts, items


def new_round(message_type, ts, request_id):
    return {"roundId": None, "messageType": message_type, "createTime": ts, "finishTime": None,
            "items": [], "requestId": request_id, "model": None, "userQuery": None, "_src_ids": []}


# ---------------------------------------------------------------- 本地 jsonl
def extract_local(path):
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    title, conversation_id, model_name = None, None, None
    for rec in records:
        if not title and rec.get("type") == "ai-title" and rec.get("aiTitle"):
            title = rec["aiTitle"]
        if not conversation_id and rec.get("sessionId"):
            conversation_id = rec["sessionId"]
        pd = rec.get("providerData") or {}
        if not model_name and pd.get("requestModelName"):
            model_name = pd["requestModelName"]

    # 第一遍：callId -> 结果记录（结果记录与调用记录平级，位置不定）
    result_by_call = {}
    for rec in records:
        if rec.get("type") == "function_call_result" and rec.get("callId"):
            result_by_call.setdefault(rec["callId"], rec)

    rounds, cur_asst = [], None
    stats = Counter()          # 源记录对账
    interrupted = 0

    def ensure_asst(ts, req):
        nonlocal cur_asst
        if cur_asst is None:
            cur_asst = new_round("assistant", ts, req)
            rounds.append(cur_asst)
        return cur_asst

    for rec in records:
        kind = rec.get("type")
        if kind in SKIP_RECORD_TYPES:
            stats["skipped:" + kind] += 1
            continue
        pd = rec.get("providerData") or {}
        req = pd.get("conversationRequestId")
        ts = rec.get("timestamp")

        if kind == "message":
            role = rec.get("role")
            text = text_of(rec.get("content"))
            if role == "user":
                compact = bool(pd.get("isCompactInternal") or pd.get("compactionId")
                               or str(rec.get("id", "")).startswith("cmp_"))
                rd = new_round("system" if compact else "user", ts, req)
                rd["items"].append(make_item("text", text))
                rd["userQuery"] = None if compact else extract_user_query(text)
                rounds.append(rd)
                stats["message:system(compaction)" if compact else "message:user"] += 1
                cur_asst = None
                continue
            rd = ensure_asst(ts, req)
            rd["items"].append(make_item("text", text))
            if rd["model"] is None:
                rd["model"] = pd.get("requestModelName") or pd.get("requestModelId")
            if rec.get("status") == "incomplete" or (text or "").strip() in PLACEHOLDERS:
                interrupted += 1
                rd["finishTime"] = None
            else:
                rd["finishTime"] = ts
            stats["message:assistant"] += 1

        elif kind == "reasoning":
            rd = ensure_asst(ts, req)
            body = text_of(rec.get("content"))
            raw = rec.get("rawContent") or []
            if not body and raw and isinstance(raw[0], dict):
                body = raw[0].get("text")
            if not body:
                body = text_of(raw)
            rd["items"].append(make_item("reasoning", body))
            rd["finishTime"] = ts
            if rd["model"] is None:
                rd["model"] = pd.get("requestModelName") or pd.get("requestModelId")
            stats["reasoning"] += 1

        elif kind == "function_call":
            rd = ensure_asst(ts, req)
            call_id = rec.get("callId")
            result = result_by_call.get(call_id)
            rd["items"].append(make_item("tool-call", None, {
                "name": rec.get("name"), "callId": call_id,
                "status": (result or {}).get("status") or "",
                "args": parse_args_field(rec.get("arguments")), "result": None}))
            rd["finishTime"] = ts
            stats["function_call"] += 1

        elif kind == "function_call_result":
            rd = ensure_asst(ts, req)
            output = rec.get("output")
            rd["items"].append(make_item("tool-result", text_of_output(output), {
                "name": rec.get("name"), "callId": rec.get("callId"),
                "status": rec.get("status") or "", "args": None, "result": output}))
            rd["finishTime"] = ts
            stats["function_call_result"] += 1

        else:
            stats["skipped:" + str(kind)] += 1

    meta = {"source": str(path), "conversationId": conversation_id or path.stem,
            "title": title, "assistantName": "WorkBuddy", "modelName": model_name}
    data, counts, items = finish(rounds, meta)
    return data, stats, counts, items, interrupted


# ------------------------------------------------------------ 云端分享页
def extract_share(path, share):
    messages = share.get("messages") or []
    rounds, stats = [], Counter()
    interrupted = 0
    item_meta = []
    for msg in messages:
        parts = msg.get("content")
        if isinstance(parts, str):
            parts = [{"type": "text", "text": parts}] if parts else []
        parts = parts or []
        msg_type = msg.get("messageType") or msg.get("role") or "user"
        rd = new_round(msg_type, msg.get("createTime"), msg.get("requestId"))
        rd["roundId"] = msg.get("id")
        rd["model"] = (msg.get("extra") or {}).get("modelName")
        rd["finishTime"] = msg.get("finishTime")
        user_text = None
        for part in parts:
            ptype = part.get("type")
            if ptype == "text":
                text = part.get("text")
                rd["items"].append(make_item("text", text))
                if msg_type == "user" and user_text is None:
                    user_text = text
                stats["text"] += 1
                if (text or "").strip() in PLACEHOLDERS:
                    interrupted += 1
                    rd["finishTime"] = None
            elif ptype == "reasoning":
                rd["items"].append(make_item("reasoning", part.get("text")))
                stats["reasoning"] += 1
            elif ptype == "tool-call":
                tool = part.get("tool") or {}
                call_id = tool.get("id")
                rd["items"].append(make_item("tool-call", None, {
                    "name": tool.get("name"), "callId": call_id,
                    "status": tool.get("status") or "",
                    "args": parse_args_field(tool.get("args")), "result": None}))
                stats["tool-call"] += 1
                if tool.get("result") is not None:
                    # 分享页把结果内嵌在 tool-call 里，拆成独立 tool-result 条目以对齐本地形态
                    rd["items"].append(make_item("tool-result", text_of_output(tool.get("result")), {
                        "name": tool.get("name"), "callId": call_id,
                        "status": tool.get("status") or "", "args": None,
                        "result": tool.get("result")}))
                    stats["tool-result(embedded)"] += 1
            else:
                stats["skipped-part:" + str(ptype)] += 1
        if msg_type == "user":
            rd["userQuery"] = extract_user_query(user_text)
        elif msg_type == "system":
            # 分享页的合成时间线轮（模型切换/压缩标记）不承载对话语义
            stats["system-round"] += 1
        rounds.append(rd)
    meta = {"source": str(path), "conversationId": (messages[0].get("conversationId") if messages else None) or path.stem,
            "title": share.get("name"), "assistantName": share.get("assistantName") or "WorkBuddy",
            "modelName": next((m.get("extra", {}).get("modelName") for m in messages
                               if (m.get("extra") or {}).get("modelName")), None)}
    data, counts, items = finish(rounds, meta)
    return data, stats, counts, items, interrupted


# ---------------------------------------------------------------- 入口
def load_source(path, kind):
    """返回 (kind, payload)：local -> None，share -> dict。"""
    if kind == "auto":
        kind = "local"
        with open(path, encoding="utf-8") as fh:
            first = fh.readline()
        try:
            obj = json.loads(first)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and "messages" in obj:
            kind = "share"
        elif Path(path).suffix.lower() == ".json":
            # 可能是缩进排版的分享页
            with open(path, encoding="utf-8") as fh:
                try:
                    obj = json.load(fh)
                except json.JSONDecodeError:
                    obj = None
            if isinstance(obj, dict) and "messages" in obj:
                kind = "share"
    if kind == "share":
        with open(path, encoding="utf-8") as fh:
            return "share", json.load(fh)
    return "local", None


def source_total(stats, kind):
    """源侧「内容承载」条目总数，用于零丢失对账。"""
    if kind == "local":
        return sum(v for k, v in stats.items() if k.startswith(("message:", "reasoning", "function_call")))
    return sum(v for k, v in stats.items() if k in ("text", "reasoning", "tool-call", "tool-result(embedded)"))


def compare_share(target, data, counts):
    """与另一个分享页/归一化文件做轮数、条目数交叉核对。"""
    kind, share = load_source(target, "auto")
    rows = share["messages"] if kind == "share" else share["rounds"]
    other = Counter(x.get("messageType") for x in rows)
    print(f"VERIFY share {target}: rounds={len(rows)} {dict(other)}")
    print(f"VERIFY local-total: rounds={len(data['rounds'])} {dict(counts)}")
    diff = {k: other.get(k, 0) - counts.get(k, 0) for k in set(other) | set(counts)}
    print("VERIFY diff(share - local):", {k: v for k, v in sorted(diff.items()) if v})
    print("VERIFY 分享页轮数少于本地属正常（云端只留最近约 100 轮）；若多于本地则说明本地文件不完整")


def main():
    ap = argparse.ArgumentParser(description="WorkBuddy 对话归一化")
    ap.add_argument("source", help="本地会话 .jsonl 或云端 conversation-data.json")
    ap.add_argument("-o", "--out", required=True, help="输出归一化 JSON")
    ap.add_argument("--kind", choices=["auto", "local", "share"], default="auto")
    ap.add_argument("--verify", nargs="?", const="", metavar="SHARE_JSON",
                    help="打印与源文件的条目数对账；带路径时再与分享页交叉核对")
    args = ap.parse_args()

    kind, share = load_source(args.source, args.kind)
    if kind == "share":
        print("WARN: 云端分享页只保留最近约 100 轮且首轮可能被截断，请核对首轮是否完整；"
              "完整历史在本机 projects/<项目目录>/<conversationId>.jsonl", file=sys.stderr)
        data, stats, counts, items, interrupted = extract_share(args.source, share)
    else:
        data, stats, counts, items, interrupted = extract_local(args.source)
        if not data["rounds"]:
            print(f"ERROR: {args.source} 里没有可用的对话记录（不是 WorkBuddy 事件流？）", file=sys.stderr)
            return 2

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))

    print(f"source: {kind} {args.source}")
    print(f"rounds={len(data['rounds'])} "
          + " ".join(f"{k}={counts[k]}" for k in ("user", "assistant", "system")))
    print(f"items={sum(items.values())} "
          + " ".join(f"{k}={items[k]}" for k in ("text", "reasoning", "tool-call", "tool-result")))
    total_src = source_total(stats, kind)
    total_items = sum(items.values())
    print("VERIFY source: " + " ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    print(f"VERIFY zero-loss: source={total_src} -> items={total_items} "
          + ("OK" if total_src == total_items else "MISMATCH"))
    if interrupted:
        print(f"interrupted={interrupted} (\"Interrupted by user\" 占位符，不进入正文)")
    if data.get("title") is None and data["rounds"]:
        print("note: 源文件无标题记录，title 为空")
    print(f"out={args.out} ({os.path.getsize(args.out)} B)")

    if args.verify:
        compare_share(args.verify, data, counts)

    if total_src != total_items:
        print("MISMATCH: 源条目数与输出条目数不一致，拒绝继续", file=sys.stderr)
        return 4
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
