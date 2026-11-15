# 创建时间：2026-11-16 01:08:20
"""ALAS 运行日志解析与状态判定。

只读 log/<date>_alas.txt。必须锁定 `_alas.txt` 后缀：`_gui.txt` 是 WebUI 主进程、
`_-c.txt` 是 WebUI 的 multiprocessing 子进程，后者会打印 `Pending tasks` 造成误判。

日志行格式：`%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s`（module/logger.py:139-140），
控制台宽度 119 会硬折行，因此解析必须先按行首时间戳重新拼接。
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.(\d{3}) \| ([A-Z]+)\s*\| (.*)$")
LEVEL_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.(\d{3}) \| ([A-Z]+)\s*\| (.*)$")

# 关键事件
RE_START = re.compile(r"^Scheduler: Start task `([^`]+)`")
RE_END = re.compile(r"^Scheduler: End task `([^`]+)`")
RE_WAIT = re.compile(r"^Wait until (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) for task `([^`]+)`")
RE_PENDING = re.compile(r"^Pending tasks: \[(.*)\]")
RE_UI = re.compile(r"^\[UI\] (page_[a-z_]+)")
RE_SAVE_ERR = re.compile(r"Saving error: (\./log/error/\d+)")
RE_HUMAN = re.compile(r"Request human takeover|failed 3 or more times")
RE_STUCK = re.compile(r"GameStuckError: (.*)")
RE_MANYCLICK = re.compile(r"GameTooManyClickError: (.*)")

STATE_DOWN = "DOWN"
STATE_RUNNING = "RUNNING"
STATE_WAITING = "WAITING"
STATE_STUCK = "STUCK"
STATE_NEEDS_HUMAN = "NEEDS_HUMAN"
STATE_CONFLICT = "CONFLICT"

# 任务执行时日志间隔 p90≈1.1s、p99≈20s；等待期可合法静默 5-11 分钟。
STUCK_SILENCE_SECONDS = 60
WAIT_SILENCE_SECONDS = 1200


def _parse_line(line):
    """返回 (datetime, level, message)；非日志行返回 None。"""
    m = LINE_RE.match(line)
    if not m:
        return None
    base = m.group(1)
    ms = m.group(2)
    try:
        ts = datetime.strptime(base, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    ts = ts.replace(microsecond=int(ms) * 1000)
    return ts, m.group(3), m.group(4).rstrip()


def _read_tail(path, max_bytes=4 * 1024 * 1024):
    """从文件尾部读至多 max_bytes，按行返回。大日志不整读。"""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
            f.readline()  # 丢弃可能被截断的首行
        raw = f.read()
    text = raw.decode("utf-8", "replace")
    return text.splitlines()


def fold_continuations(lines):
    """把折行日志拼回逻辑行：只有以时间戳开头的行才是新逻辑行。"""
    out = []
    for line in lines:
        if LINE_RE.match(line):
            out.append(line.rstrip())
        elif out:
            out[-1] = out[-1] + line.rstrip()
    return out


def find_today_log(env, day=None):
    """定位当天调度器日志。不存在说明当天调度器没启动过。"""
    day = day or datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(env.log_dir, "{0}_alas.txt".format(day))
    return path if os.path.exists(path) else None


def latest_log(env):
    """最近一份 _alas.txt（跨天兜底），返回 (路径, 日期字符串)。"""
    try:
        names = [n for n in os.listdir(env.log_dir) if n.endswith("_alas.txt")]
    except OSError:
        return None, None
    if not names:
        return None, None
    names.sort(reverse=True)
    return os.path.join(env.log_dir, names[0]), names[0][:10]


def analyze(path, now=None):
    """解析日志尾部并给出状态判定。

    返回 dict：state / task / last_event / last_ts / silence_sec / pending /
              last_error / error_dir / ui_page / waiting_until / human_reason
    """
    now = now or datetime.now()
    result = {
        "state": STATE_DOWN,
        "task": None,
        "last_event": None,
        "last_ts": None,
        "silence_sec": None,
        "pending": [],
        "last_error": None,
        "error_dir": None,
        "ui_page": None,
        "waiting_until": None,
        "human_reason": None,
        "log_path": path,
    }
    if not path or not os.path.exists(path):
        return result

    lines = fold_continuations(_read_tail(path))

    open_task = None
    last_ts = None
    last_event = None
    waiting_until = None
    human_reason = None
    last_error = None
    last_error_ts = None
    error_dir = None
    ui_page = None
    pending = []

    for line in lines:
        parsed = _parse_line(line)
        if not parsed:
            continue
        ts, level, msg = parsed
        last_ts = ts

        m = RE_START.match(msg)
        if m:
            open_task = m.group(1)
            last_event = "start:" + open_task
            waiting_until = None
            continue
        m = RE_END.match(msg)
        if m:
            open_task = None
            last_event = "end:" + m.group(1)
            continue
        m = RE_WAIT.match(msg)
        if m:
            waiting_until = m.group(1)
            last_event = "wait:" + m.group(2)
            continue
        m = RE_PENDING.match(msg)
        if m:
            items = [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
            pending = items
            continue
        m = RE_UI.match(msg)
        if m:
            ui_page = m.group(1)
            last_event = "ui:" + ui_page
            continue
        m = RE_SAVE_ERR.search(msg)
        if m:
            error_dir = m.group(1)
            last_event = "error_saved"
            continue
        if RE_HUMAN.search(msg):
            human_reason = msg
            last_event = "human"
            continue
        if level in ("ERROR", "CRITICAL"):
            last_error = msg
            last_error_ts = ts
            last_event = "error"

    result["task"] = open_task
    result["last_ts"] = last_ts
    result["last_event"] = last_event
    result["pending"] = pending
    result["last_error"] = last_error
    result["last_error_ts"] = last_error_ts.strftime("%Y-%m-%d %H:%M:%S") if last_error_ts else None
    result["error_dir"] = error_dir
    result["ui_page"] = ui_page
    result["waiting_until"] = waiting_until
    result["human_reason"] = human_reason

    if last_ts is not None:
        result["silence_sec"] = max(0, int((now - last_ts).total_seconds()))

    # --- 状态判定，优先级：需人工 > 卡死 > 运行 > 等待 > 空闲 ---
    if human_reason:
        result["state"] = STATE_NEEDS_HUMAN
    elif open_task is not None:
        silence = result["silence_sec"]
        frozen = silence is not None and silence > STUCK_SILENCE_SECONDS
        # 卡死类错误只在「新鲜」时算数：ALAS 自己会在数秒内重启任务，
        # 若之后已恢复出新日志，就不该继续报 STUCK。
        fresh_error = (
            last_error is not None
            and last_error_ts is not None
            and (now - last_error_ts).total_seconds() <= STUCK_SILENCE_SECONDS
            and last_error.startswith(
                ("GameStuckError", "GameTooManyClickError", "GameBugError", "GamePageUnknownError")
            )
        )
        result["state"] = STATE_STUCK if (frozen or fresh_error) else STATE_RUNNING
    elif waiting_until is not None:
        result["state"] = STATE_WAITING
    elif last_ts is not None:
        # 有日志但既无任务也不在等待：视为空闲，交由此后进程存活检查进一步降级
        result["state"] = STATE_WAITING
    else:
        result["state"] = STATE_DOWN

    return result


def recent_errors(env, limit=10):
    """列出最近的错误快照目录（按毫秒时间戳倒序）。"""
    try:
        names = [n for n in os.listdir(env.error_dir) if n.isdigit()]
    except OSError:
        return []
    names.sort(key=lambda x: int(x), reverse=True)
    out = []
    for name in names[:limit]:
        ts = datetime.fromtimestamp(int(name) / 1000.0)
        entry = {"name": name, "time": ts.strftime("%Y-%m-%d %H:%M:%S"), "files": []}
        try:
            entry["files"] = sorted(os.listdir(os.path.join(env.error_dir, name)))
        except OSError:
            pass
        out.append(entry)
    return out


def tail_text(path, lines=60):
    """取日志最后若干逻辑行，供人读。"""
    if not path or not os.path.exists(path):
        return []
    folded = fold_continuations(_read_tail(path))
    return folded[-lines:]


def recent_activity(path, seconds=120, now=None):
    """统计最近 N 秒的日志行数，作为「是否真在动」的量化指标。"""
    now = now or datetime.now()
    if not path or not os.path.exists(path):
        return 0
    cutoff = now - timedelta(seconds=seconds)
    count = 0
    for line in fold_continuations(_read_tail(path)):
        parsed = _parse_line(line)
        if parsed and parsed[0] >= cutoff:
            count += 1
    return count


def seconds_since_last_end(path, now=None):
    """距最近一次 `Scheduler: End task` 的秒数；从未出现返回 None。

    停止调度器时用它找安全点：任务刚结束（或正处于任务间切换的缝隙）再杀，
    避免打断战斗。比「最后一条事件恰好是 end」可靠，因为轮询很难踩中那个瞬间。
    """
    now = now or datetime.now()
    if not path or not os.path.exists(path):
        return None
    last_end = None
    for line in fold_continuations(_read_tail(path)):
        parsed = _parse_line(line)
        if not parsed:
            continue
        if RE_END.match(parsed[2]):
            last_end = parsed[0]
    if last_end is None:
        return None
    return max(0, int((now - last_end).total_seconds()))
