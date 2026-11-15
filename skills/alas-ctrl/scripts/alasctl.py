# 创建时间：2026-11-16 01:09:45
"""alas-ctrl 唯一控制入口。

设计原则（与用户对齐）：
  1. ALAS 能做的事一律通过「配置 ALAS 任务」实现，本工具不自行操作游戏。
  2. 只依赖 5 个稳定接口：config/alas.json 格式、log/*_alas.txt 行格式、
     `toolkit/python.exe alas.py` 入口、adb 只读命令、进程命令行。
  3. 任何写操作先过 _auth 授权闸门，再备份、再原子写、再回读校验。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _auth
import _logparse
from _env import EnvError, AlasEnv, read_json, process_alive, write_json_atomic

# ALAS 启动入口：alas.py 的 __main__ 就是 AzurLaneAutoScript().loop()（alas.py:625-627），
# 直接跑它可让文件日志自然落到 log/<date>_alas.txt（loop 内 logger.set_file_logger(config_name)）。
ENTRY = "alas.py"

# 各任务 NextRun 的上限，超出会被 AzurLaneConfig.override() 钳成「现在」。
# 来源：module/config/config.py:285-317
NEXTRUN_LIMITS = {
    "Commission": 12 * 3600,
    "Reward": 12 * 3600,
    "Research": 24 * 3600,
    "OpsiExplore": 31 * 86400,
    "OpsiCrossMonth": 31 * 86400,
    "OpsiVoucher": 31 * 86400,
    "OpsiMonthBoss": 31 * 86400,
    "OpsiShop": 31 * 86400,
    "OpsiArchive": 7 * 86400,
}
NEXTRUN_DEFAULT_LIMIT = 24 * 3600


# ---------------------------------------------------------------- 输出


def emit(data, as_json=False, human=None):
    if as_json:
        sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write((human if human is not None else json.dumps(data, ensure_ascii=False, indent=2)) + "\n")


def fail(message, code=2):
    sys.stderr.write("ERROR: {0}\n".format(message))
    sys.exit(code)


# ---------------------------------------------------------------- 进程


def _ps_list():
    """列出 python/alas 进程的 (pid, 命令行)。仅 Windows 与 POSIX 各一条路径。"""
    if os.name == "nt":
        try:
            out = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Process | "
                    "Where-Object { $_.Name -like '*python*' -or $_.Name -like '*alas*' } | "
                    "ForEach-Object { \"$($_.ProcessId)\t$($_.CommandLine)\" }",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=25,
            )
            text = out.stdout.decode("utf-8", "replace")
        except Exception:
            return []
    else:
        try:
            out = subprocess.run(
                "ps -eo pid=,args=", shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            text = out.stdout.decode("utf-8", "replace")
        except Exception:
            return []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1) if "\t" in line else line.split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0].strip())
        except ValueError:
            continue
        rows.append((pid, parts[1]))
    return rows


def _is_our_scheduler(cmdline):
    """判定命令行是否为 ALAS 调度器进程。"""
    if not cmdline:
        return False
    if "alas.py" not in cmdline:
        return False
    # 排除本工具与 ALAS 的 webui（gui.py）
    if "alasctl" in cmdline or "alaswatch" in cmdline:
        return False
    return True


def find_scheduler_processes(env):
    found = []
    for pid, cmdline in _ps_list():
        if _is_our_scheduler(cmdline):
            found.append({"pid": pid, "cmdline": cmdline})
    return found


def _record_process(env, pid, started_at):
    env.ensure_state()
    write_json_atomic(env.proc_path, {"pid": pid, "started_at": started_at, "entry": ENTRY})


def _read_recorded_pid(env):
    data = read_json(env.proc_path, default=None)
    if not data:
        return None
    pid = data.get("pid")
    if pid and process_alive(pid):
        return pid
    return None


def detect_maatouch(env):
    """检测游戏是否正被 MaaTouch 通道控制。

    任何 ALAS 实例（含 WebUI 拉起的）在跑任务时都会起这个持久通道，
    而 Windows 上 WebUI 的任务进程命令行看不出 alas.py，只能靠这个反推。
    返回 True / False / None（无法判断）。
    """
    data = read_json(env.config_path, default={}) or {}
    serial = ((data.get("Alas") or {}).get("Emulator") or {}).get("Serial")
    if not serial:
        return None
    try:
        out = subprocess.run(
            [env.adb, "-s", str(serial), "shell", "ps", "-A"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        if out.returncode != 0:
            return None
        return "maatouch" in out.stdout.decode("utf-8", "replace").lower()
    except Exception:
        return None


def detect_conflict(env, sched_procs):
    """判断是否存在非本工具管理的 ALAS 实例在跑（例如 WebUI 里点了启动）。"""
    recorded = _read_recorded_pid(env)
    foreign = [p for p in sched_procs if p["pid"] != recorded]
    if foreign:
        return foreign
    if recorded is not None:
        return []
    if detect_maatouch(env):
        return [{"pid": None, "cmdline": "检测到 MaaTouch 控制通道（疑似 WebUI 启动的实例）"}]
    return []


# ---------------------------------------------------------------- 配置


def load_config(env):
    data = read_json(env.config_path, default=None)
    if data is None:
        fail("读不到配置文件：{0}".format(env.config_path))
    return data


def backup_config(env, note):
    env.ensure_state()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target = os.path.join(env.backup_dir, "{0}_{1}.json".format(stamp, note))
    src = read_json(env.config_path, default=None)
    if src is not None:
        write_json_atomic(target, src)
    # 只保留最近 50 份备份
    try:
        backups = sorted(os.listdir(env.backup_dir))
        for old in backups[:-50]:
            os.unlink(os.path.join(env.backup_dir, old))
    except OSError:
        pass
    return target


def get_path(data, dotted):
    node = data
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return None, False
        node = node[key]
    return node, True


def set_path(data, dotted, value):
    keys = dotted.split(".")
    node = data
    for key in keys[:-1]:
        if key not in node or not isinstance(node[key], dict):
            node[key] = {}
        node = node[key]
    node[keys[-1]] = value


def coerce(value, current):
    """按现有值的类型做最小转换，避免把数字写成字符串。"""
    if isinstance(current, bool):
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on", "是", "开")
        return bool(value)
    if isinstance(current, int) and not isinstance(current, bool):
        return int(value)
    if isinstance(current, float):
        return float(value)
    if isinstance(current, str):
        return value
    if current is None:
        return value
    return value


def is_scheduler_path(dotted):
    return dotted.endswith(".Scheduler.Enable") or dotted.endswith(".Scheduler.NextRun")


def task_names(data):
    return [
        name
        for name, node in data.items()
        if isinstance(node, dict) and isinstance(node.get("Scheduler"), dict)
    ]


def priority_order(env):
    """从 ALAS 源码读取 SCHEDULER_PRIORITY；读不到则退回空表（不阻塞主流程）。"""
    path = os.path.join(env.root, "module", "config", "config_manual.py")
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    m = re.search(r"SCHEDULER_PRIORITY\s*=\s*\"\"\"(.*?)\"\"\"", text, re.S)
    if not m:
        return []
    order = []
    for chunk in m.group(1).split(">"):
        name = chunk.strip()
        if name and re.match(r"^[A-Za-z0-9_]+$", name):
            order.append(name)
    return order


def parse_duration(text):
    m = re.match(r"^(\d+)\s*([smhd])$", text.strip().lower())
    if not m:
        raise ValueError("无法解析时长：{0}（示例 30m / 2h / 90s）".format(text))
    n = int(m.group(1))
    unit = m.group(2)
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


_SCHEMA_CACHE = {}


def load_args_schema(env):
    """读 module/config/argument/args.json：ALAS 自己的设置项定义表。

    只读 JSON，不 import 任何 ALAS 模块。拿不到时返回 None，调用方按「未知」处理。
    """
    key = env.root
    if key in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[key]
    path = os.path.join(env.root, "module", "config", "argument", "args.json")
    data = read_json(path, default=None)
    _SCHEMA_CACHE[key] = data
    return data


def normalization_hint(env, dotted):
    """预判 ALAS 读配置时会不会把这一项改回默认值。

    module/config/config_updater.py:684-688 的规则：type 为 lock/state，
    或 display 为 hide 且 type 不是 stored 时，值会被 args.json 的默认值覆盖。
    """
    schema = load_args_schema(env)
    if not schema:
        return None
    node = schema
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    if not isinstance(node, dict):
        return None
    typ = node.get("type")
    display = node.get("display")
    default = node.get("value")
    if typ in ("lock", "state"):
        return "该项 type={0}，ALAS 每次读取配置都会强制改回默认值 {1}，写入不会生效".format(
            typ, json.dumps(default, ensure_ascii=False)
        )
    if display == "hide" and typ != "stored":
        return "该项 display=hide，ALAS 每次读取配置都会重置为默认值 {0}，写入不会生效".format(
            json.dumps(default, ensure_ascii=False)
        )
    return None


def nextrun_limit(task):
    return NEXTRUN_LIMITS.get(task, NEXTRUN_DEFAULT_LIMIT)


# ---------------------------------------------------------------- 命令：doctor


def cmd_doctor(env, args):
    info = {"alas_root": env.root, "config": env.config_path, "log_dir": env.log_dir}
    info["alas_commit"] = env.commit()
    info["python"] = env.python
    info["python_exists"] = os.path.exists(env.python)
    info["adb"] = env.adb
    info["adb_exists"] = os.path.exists(env.adb) if env.adb != "adb" else True
    info["entry"] = os.path.join(env.root, ENTRY)
    info["entry_exists"] = os.path.exists(info["entry"])
    info["config_exists"] = os.path.exists(env.config_path)

    # adb 只读探测
    try:
        out = subprocess.run(
            [env.adb, "devices", "-l"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20
        )
        info["adb_devices"] = out.stdout.decode("utf-8", "replace").strip().splitlines()[1:]
    except Exception as exc:  # noqa: BLE001
        info["adb_devices"] = ["adb 调用失败: {0}".format(exc)]

    data = read_json(env.config_path, default={}) or {}
    info["serial_configured"] = (((data.get("Alas") or {}).get("Emulator") or {}).get("Serial"))
    info["package"] = (((data.get("Alas") or {}).get("Emulator") or {}).get("PackageName"))
    procs = find_scheduler_processes(env)
    info["scheduler_processes"] = procs
    info["recorded_pid"] = _read_recorded_pid(env)
    info["conflict"] = detect_conflict(env, procs)

    problems = []
    if not info["config_exists"]:
        problems.append("配置文件不存在")
    if not info["entry_exists"]:
        problems.append("alas.py 不存在，ALAS 版本可能已变")
    if not info["python_exists"]:
        problems.append("toolkit python 不存在")
    if not info["adb_devices"] or not any("device" in d for d in info["adb_devices"]):
        problems.append("ADB 未发现 device 状态的设备")
    info["problems"] = problems
    info["ok"] = not problems

    if args.json:
        emit(info, as_json=True)
        return 0
    lines = [
        "ALAS 根目录 : {0}".format(info["alas_root"]),
        "ALAS 版本   : {0}".format(info["alas_commit"]),
        "解释器      : {0} ({1})".format(info["python"], "存在" if info["python_exists"] else "缺失"),
        "ADB         : {0}".format(info["adb"]),
        "设备        : {0}".format("; ".join(info["adb_devices"]) or "无"),
        "配置序列号  : {0}".format(info["serial_configured"]),
        "游戏包名    : {0}".format(info["package"]),
        "调度进程    : {0}".format(
            ", ".join(str(p["pid"]) for p in procs) if procs else "无"
        ),
        "本工具 PID  : {0}".format(info["recorded_pid"]),
        "结论        : {0}".format("正常" if info["ok"] else "有问题 -> " + "; ".join(problems)),
    ]
    if info["conflict"]:
        lines.append("冲突        : 存在非本工具管理的 ALAS 实例，勿再启动")
    emit(info, as_json=False, human="\n".join(lines))
    return 0


# ---------------------------------------------------------------- 命令：status


def collect_status(env):
    procs = find_scheduler_processes(env)
    recorded = _read_recorded_pid(env)
    conflict = detect_conflict(env, procs)
    path = _logparse.find_today_log(env)
    fallback = None
    if path is None:
        path, fallback = _logparse.latest_log(env)
    analysis = _logparse.analyze(path)
    data = read_json(env.config_path, default={}) or {}

    # 进程会话语义：有本工具记录的 PID 或命令行可识别的调度进程才算「在跑」。
    # 无进程时无论日志写了什么都不可能是运行中，直接判 DOWN。
    running = bool(procs) or recorded is not None
    if conflict:
        state = _logparse.STATE_CONFLICT
    elif not running:
        state = _logparse.STATE_DOWN
    else:
        state = analysis["state"]

    tasks = []
    now = datetime.datetime.now()
    for name in task_names(data):
        sched = data[name]["Scheduler"]
        nr = sched.get("NextRun")
        try:
            nr_dt = datetime.datetime.strptime(str(nr), "%Y-%m-%d %H:%M:%S")
            delta = int((nr_dt - now).total_seconds())
        except (ValueError, TypeError):
            nr_dt = None
            delta = None
        tasks.append(
            {
                "task": name,
                "enable": bool(sched.get("Enable")),
                "next_run": nr,
                "delta_sec": delta,
                "pending": delta is not None and delta <= 0,
            }
        )
    order = priority_order(env)
    rank = {n: i for i, n in enumerate(order)}
    pending = [t for t in tasks if t["enable"] and t["pending"]]
    pending.sort(key=lambda t: (rank.get(t["task"], 9999), str(t["next_run"])))

    today = now.strftime("%Y-%m-%d")
    return {
        "state": state,
        "processes": procs,
        "recorded_pid": recorded,
        "conflict": conflict,
        "log_path": analysis["log_path"],
        "log_date": (fallback or today) if path else None,
        "log_is_stale": bool(path) and (fallback or today) != today,
        "current_task": analysis["task"],
        "last_event": analysis["last_event"],
        "last_ts": analysis["last_ts"].strftime("%Y-%m-%d %H:%M:%S") if analysis["last_ts"] else None,
        "silence_sec": analysis["silence_sec"],
        "ui_page": analysis["ui_page"],
        "waiting_until": analysis["waiting_until"],
        "last_error": analysis["last_error"],
        "error_dir": analysis["error_dir"],
        "human_reason": analysis["human_reason"],
        "pending_tasks": [t["task"] for t in pending],
        "pending_count": len(pending),
        "enabled_count": len([t for t in tasks if t["enable"]]),
    }


def cmd_status(env, args):
    status = collect_status(env)
    if args.json:
        emit(status, as_json=True)
        return 0
    lines = [
        "状态      : {0}".format(status["state"]),
        "当前任务  : {0}".format(status["current_task"] or "-"),
        "最后事件  : {0} ({1})".format(status["last_event"], status["last_ts"]),
        "静默时长  : {0}".format(
            "{0}s".format(status["silence_sec"]) if status["silence_sec"] is not None else "-"
        ),
        "界面      : {0}".format(status["ui_page"] or "-"),
        "待执行    : {0} 个 -> {1}".format(
            status["pending_count"], ", ".join(status["pending_tasks"][:8]) or "-"
        ),
        "日志      : {0}{1}".format(
            status["log_path"] or "今日无调度日志",
            "（旧日志，非今日）" if status["log_is_stale"] else "",
        ),
    ]
    if status["waiting_until"]:
        lines.append("等待至    : {0}".format(status["waiting_until"]))
    if status["last_error"]:
        lines.append("最近错误  : {0}".format(status["last_error"]))
    if status["error_dir"]:
        lines.append("错误快照  : {0}".format(status["error_dir"]))
    if status["human_reason"]:
        lines.append("需人工    : {0}".format(status["human_reason"]))
    if status["conflict"]:
        lines.append("冲突      : 非本工具实例在运行 -> {0}".format(status["conflict"]))
    if status["state"] in (_logparse.STATE_DOWN, _logparse.STATE_CONFLICT):
        lines.append("说明      : 调度器当前未运行，任务信息为最后一次运行留下的状态")
    emit(status, as_json=False, human="\n".join(lines))
    return 0


# ---------------------------------------------------------------- 命令：tasks


def cmd_tasks(env, args):
    data = load_config(env)
    order = priority_order(env)
    rank = {name: i for i, name in enumerate(order)}
    now = datetime.datetime.now()
    rows = []
    for name in task_names(data):
        sched = data[name]["Scheduler"]
        nr = sched.get("NextRun")
        try:
            delta = int(
                (datetime.datetime.strptime(str(nr), "%Y-%m-%d %H:%M:%S") - now).total_seconds()
            )
        except (ValueError, TypeError):
            delta = None
        rows.append(
            {
                "task": name,
                "enable": bool(sched.get("Enable")),
                "next_run": nr,
                "delta_sec": delta,
                "priority": rank.get(name, 9999),
            }
        )
    rows.sort(key=lambda r: (r["priority"], r["task"]))
    if args.json:
        emit(rows, as_json=True)
        return 0
    out = ["{0:<24}{1:<8}{2:<22}{3}".format("任务", "启用", "下次执行", "相对")] 
    out.append("-" * 72)
    for r in rows:
        rel = "-"
        if r["delta_sec"] is not None:
            s = r["delta_sec"]
            rel = "已过期" if s <= 0 else "in {0}".format(
                "{0}d{1}h".format(s // 86400, (s % 86400) // 3600) if s >= 86400
                else "{0}h{1}m".format(s // 3600, (s % 3600) // 60) if s >= 3600
                else "{0}m".format(s // 60)
            )
        out.append(
            "{0:<24}{1:<8}{2:<22}{3}".format(
                r["task"], "是" if r["enable"] else "否", str(r["next_run"]), rel
            )
        )
    emit(rows, as_json=False, human="\n".join(out))
    return 0


# ---------------------------------------------------------------- 命令：log / errors


def cmd_log(env, args):
    path = _logparse.find_today_log(env)
    if path is None:
        path, _ = _logparse.latest_log(env)
    if path is None:
        fail("找不到任何 _alas.txt 日志")
    lines = _logparse.tail_text(path, args.lines)
    if args.json:
        emit({"path": path, "lines": lines}, as_json=True)
        return 0
    emit(None, as_json=False, human="# {0}\n{1}".format(path, "\n".join(lines)))
    return 0


def cmd_errors(env, args):
    rows = _logparse.recent_errors(env, args.limit)
    if args.json:
        emit(rows, as_json=True)
        return 0
    if not rows:
        emit(rows, as_json=False, human="没有错误快照")
        return 0
    out = ["{0:<22}{1}".format("时间", "快照目录")]
    out.append("-" * 60)
    for r in rows:
        out.append("{0:<22}{1}".format(r["time"], os.path.join(env.error_dir, r["name"])))
    emit(rows, as_json=False, human="\n".join(out))
    return 0


# ---------------------------------------------------------------- 命令：cfg


def cmd_cfg(env, args):
    if args.cfg_action is None:
        fail("用法：cfg get <path> | cfg set <path> <value>")
    if args.cfg_action == "get":
        data = load_config(env)
        value, ok = get_path(data, args.path)
        if not ok:
            fail("配置路径不存在：{0}".format(args.path))
        emit({"path": args.path, "value": value}, as_json=args.json,
             human="{0} = {1}".format(args.path, json.dumps(value, ensure_ascii=False)))
        return 0

    # set
    allowed, payload = _auth.gate(env, "settings", "设置 {0} = {1}".format(args.path, args.value))
    if not allowed:
        emit(payload, as_json=True)
        return 3
    data = load_config(env)
    current, ok = get_path(data, args.path)
    if not ok:
        fail("配置路径不存在：{0}（拒绝创建新键，ALAS 会在下次写盘时丢弃自定义键）".format(args.path))
    hint = normalization_hint(env, args.path)
    if hint:
        payload = {
            "path": args.path,
            "old": current,
            "refused": True,
            "reason": hint,
            "hint": "改用同一任务下 type=checkbox/input/select 的可写项",
        }
        emit(payload, as_json=True)
        return 4
    new_value = coerce(args.value, current)
    backup = backup_config(env, "cfg")
    set_path(data, args.path, new_value)
    write_json_atomic(env.config_path, data)

    # 回读校验：ALAS 对 hide/lock/state 项会强制覆盖
    verify = read_json(env.config_path, default={}) or {}
    got, _ = get_path(verify, args.path)
    forced = json.dumps(got, ensure_ascii=False) != json.dumps(new_value, ensure_ascii=False)
    result = {
        "path": args.path,
        "old": current,
        "new": new_value,
        "verify": got,
        "forced_by_alas": forced,
        "backup": backup,
    }
    if forced:
        result["warning"] = (
            "写入值未被保留：该项可能被 ALAS 标记为 hide/lock/state，"
            "下次读取时会被重置。请改对应的可写项。"
        )
    if args.json:
        emit(result, as_json=True)
    else:
        text = "{0}: {1} -> {2}".format(
            args.path, json.dumps(current, ensure_ascii=False), json.dumps(new_value, ensure_ascii=False)
        )
        if forced:
            text += "\n警告：{0}".format(result["warning"])
        emit(result, as_json=False, human=text)
    return 0 if not forced else 4


# ---------------------------------------------------------------- 命令：task 调度


def cmd_task(env, args):
    data = load_config(env)
    name = args.name
    if name not in task_names(data):
        fail("任务不存在或不可调度：{0}（可用任务见 tasks 子命令）".format(name))
    sched = data[name]["Scheduler"]

    action = args.action
    if action == "off":
        hint = normalization_hint(env, "{0}.Scheduler.Enable".format(name))
        if hint:
            payload = {
                "task": name,
                "forced_by_alas": True,
                "refused": True,
                "message": "该任务无法禁用：" + hint,
            }
            emit(payload, as_json=True)
            return 4
        allowed, payload = _auth.gate(env, "schedule", "禁用任务 {0}".format(name))
        if not allowed:
            emit(payload, as_json=True)
            return 3
        backup_config(env, "task_off")
        sched["Enable"] = False
        write_json_atomic(env.config_path, data)
        verify = (read_json(env.config_path, default={}) or {}).get(name, {}).get("Scheduler", {})
        forced = bool(verify.get("Enable"))
        if forced:
            emit(
                {"task": name, "forced_by_alas": True,
                 "message": "该任务的 Enable 为 lock/state 类型，ALAS 会强制保持启用（Restart/Commission/Research/Reward）"},
                as_json=args.json,
                human="任务 {0} 无法禁用：ALAS 强制启用（lock/state）".format(name),
            )
            return 4
        emit({"task": name, "enable": False}, as_json=args.json, human="已禁用任务 {0}".format(name))
        return 0

    # on / now / at / in —— 都需要写 NextRun
    allowed, payload = _auth.gate(env, "schedule", "调整任务 {0} 的执行时间".format(name))
    if not allowed:
        emit(payload, as_json=True)
        return 3

    now = datetime.datetime.now()
    if action == "on":
        if not sched.get("Enable"):
            sched["Enable"] = True
        target = None
    elif action == "now":
        target = now.replace(microsecond=0)
    elif action == "in":
        try:
            target = now + datetime.timedelta(seconds=parse_duration(args.value))
        except ValueError as exc:
            fail(str(exc))
    elif action == "at":
        try:
            target = datetime.datetime.strptime(args.value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                target = datetime.datetime.strptime(
                    now.strftime("%Y-%m-%d ") + args.value, "%Y-%m-%d %H:%M"
                )
            except ValueError:
                fail("时间格式应为 'YYYY-MM-DD HH:MM:SS' 或 'HH:MM'")
    else:
        fail("未知动作")

    warning = None
    if target is not None:
        limit = nextrun_limit(name)
        if (target - now).total_seconds() > limit:
            target = now.replace(microsecond=0)
            warning = (
                "目标时间超出 {0} 的上限 {1} 小时，ALAS 会把它钳成「现在」，已按立即执行写入"
            ).format(name, limit // 3600)
        sched["NextRun"] = target.strftime("%Y-%m-%d %H:%M:%S")

    backup_config(env, "task_{0}".format(action))
    write_json_atomic(env.config_path, data)
    result = {
        "task": name,
        "enable": bool(sched.get("Enable")),
        "next_run": sched.get("NextRun"),
        "warning": warning,
    }
    if args.json:
        emit(result, as_json=True)
    else:
        text = "{0}: enable={1} next_run={2}".format(name, result["enable"], result["next_run"])
        if warning:
            text += "\n提示：" + warning
        emit(result, as_json=False, human=text)
    return 0


# ---------------------------------------------------------------- 命令：start / stop


def cmd_start(env, args):
    allowed, payload = _auth.gate(env, "process", "启动 ALAS 调度进程")
    if not allowed:
        emit(payload, as_json=True)
        return 3

    procs = find_scheduler_processes(env)
    recorded = _read_recorded_pid(env)
    own = [p for p in procs if p["pid"] == recorded]
    if own:
        emit({"already_running": True, "pid": own[0]["pid"]}, as_json=args.json,
             human="ALAS 已在运行（PID {0}）".format(own[0]["pid"]))
        return 0
    conflict = detect_conflict(env, procs)
    if conflict:
        emit({"conflict": conflict}, as_json=args.json,
             human="检测到非本工具管理的 ALAS 实例，拒绝再启动：{0}".format(conflict))
        return 5

    if not os.path.exists(env.python):
        fail("找不到 ALAS 的 python：{0}".format(env.python))
    if not os.path.exists(os.path.join(env.root, ENTRY)):
        fail("找不到 {0}，ALAS 版本可能已变".format(ENTRY))

    env.ensure_state()
    log_path = os.path.join(env.state_dir, "scheduler.out.log")
    out = open(log_path, "ab")
    creationflags = 0
    if os.name == "nt":
        creationflags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [env.python, ENTRY],
        cwd=env.root,
        stdout=out,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    started = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _record_process(env, proc.pid, started)
    # 给 ALAS 一点启动时间，随后做一次健康检查
    time.sleep(6)
    alive = process_alive(proc.pid)
    result = {"pid": proc.pid, "started_at": started, "alive": alive, "stdout_log": log_path}
    if not alive:
        tail = ""
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                tail = "".join(f.readlines()[-20:])
        except OSError:
            pass
        result["tail"] = tail
    emit(result, as_json=args.json,
         human="已启动 ALAS（PID {0}），存活={1}\n输出日志：{2}".format(proc.pid, alive, log_path))
    return 0 if alive else 6


def cmd_stop(env, args):
    allowed, payload = _auth.gate(env, "process", "停止 ALAS 调度进程")
    if not allowed:
        emit(payload, as_json=True)
        return 3

    procs = find_scheduler_processes(env)
    recorded = _read_recorded_pid(env)
    targets = [p for p in procs if p["pid"] == recorded] or procs
    if not targets:
        emit({"stopped": False, "reason": "no scheduler process"}, as_json=args.json,
             human="没有正在运行的 ALAS 调度进程")
        return 0

    waited = 0
    at_safe_point = args.force
    if not args.force:
        # 等一个任务间缝隙：最近 15 秒内出现过 `End task` 即认为不在战斗中
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            path = _logparse.find_today_log(env)
            if path:
                since = _logparse.seconds_since_last_end(path)
                if since is not None and since <= 15:
                    at_safe_point = True
                    break
            time.sleep(2)
            waited += 2

    stopped = []
    for target in targets:
        pid = target["pid"]
        if pid is None:
            continue
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            else:
                os.kill(int(pid), 15)
            stopped.append(pid)
        except Exception:
            pass
    try:
        os.unlink(env.proc_path)
    except OSError:
        pass
    result = {
        "stopped": stopped,
        "waited_sec": waited,
        "force": bool(args.force),
        "at_safe_point": at_safe_point,
    }
    if not at_safe_point and stopped:
        result["warning"] = (
            "未等到任务间隙就停止，若正在战斗可能丢失当前进度；"
            "ALAS 下次启动会自动 Restart 游戏恢复"
        )
    if args.json:
        emit(result, as_json=True)
    else:
        text = "已停止 ALAS 进程 {0}（等待安全点 {1}s，安全点={2}）".format(
            stopped, waited, at_safe_point
        )
        if result.get("warning"):
            text += "\n提示：" + result["warning"]
        emit(result, as_json=False, human=text)
    return 0


# ---------------------------------------------------------------- 命令：perm


def cmd_perm(env, args):
    env.ensure_state()
    if args.perm_action is None:
        fail("用法：perm list|check|grant|revoke|reset")
    if args.perm_action == "list":
        rows = _auth.list_all(env)
        if args.json:
            emit(rows, as_json=True)
            return 0
        out = ["{0:<12}{1:<10}{2:<8}{3}".format("类别", "当前", "一次性", "说明")] 
        out.append("-" * 76)
        for r in rows:
            out.append(
                "{0:<12}{1:<10}{2:<8}{3}".format(
                    r["category"], r["decision"], r["once"], r["description"]
                )
            )
        emit(rows, as_json=False, human="\n".join(out))
        return 0
    if args.perm_action == "check":
        decision = _auth.check(env, args.category, consume_once=args.consume)
        emit({"category": args.category, "decision": decision}, as_json=args.json,
             human="{0}: {1}".format(args.category, decision))
        return 0
    if args.perm_action == "grant":
        scope = "once" if args.once else "deny" if args.deny else "always"
        decision = _auth.grant(env, args.category, scope, note=args.note or "")
        emit({"category": args.category, "scope": scope, "decision": decision}, as_json=args.json,
             human="已记录授权：{0} = {1}（scope={2}）".format(args.category, decision, scope))
        return 0
    if args.perm_action == "revoke":
        decision = _auth.revoke(env, args.category)
        emit({"category": args.category, "decision": decision}, as_json=args.json,
             human="已撤销授权：{0} -> {1}".format(args.category, decision))
        return 0
    if args.perm_action == "reset":
        _auth.reset(env)
        emit({"reset": True}, as_json=args.json, human="授权状态已重置为默认")
        return 0
    fail("未知 perm 动作")


# ---------------------------------------------------------------- 命令：watch（单轮，子进程隔离以避免循环导入）


def cmd_watch(env, args):
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alaswatch.py")
    cmd = [sys.executable, script, "--once", "--root", env.root]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.json:
        cmd.append("--json")
    return subprocess.run(cmd).returncode


# ---------------------------------------------------------------- 入口


def build_parser():
    p = argparse.ArgumentParser(
        prog="alasctl", description="ALAS 控制与监控 CLI（不修改 ALAS 源码）"
    )
    p.add_argument("--root", help="ALAS 根目录，默认自动探测或读 ALAS_ROOT")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("doctor", help="环境体检")

    s = sub.add_parser("status", help="运行状态")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("tasks", help="任务清单与调度")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("log", help="最近日志")
    s.add_argument("--lines", type=int, default=60)
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("errors", help="错误快照")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("cfg", help="读写配置项")
    cfg_sub = s.add_subparsers(dest="cfg_action")
    g = cfg_sub.add_parser("get")
    g.add_argument("path")
    g.add_argument("--json", action="store_true")
    st = cfg_sub.add_parser("set")
    st.add_argument("path")
    st.add_argument("value")
    st.add_argument("--json", action="store_true")

    s = sub.add_parser("task", help="任务调度（on/off/now/at/in）")
    s.add_argument("name")
    s.add_argument("action", choices=["on", "off", "now", "at", "in"])
    s.add_argument("value", nargs="?", default=None, help="at 需要时间，in 需要时长")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("start", help="启动 ALAS 调度进程")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("stop", help="停止 ALAS 调度进程")
    s.add_argument("--force", action="store_true", help="不等安全点直接杀")
    s.add_argument("--timeout", type=int, default=120, help="等待安全点的秒数")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("perm", help="授权管理")
    perm_sub = s.add_subparsers(dest="perm_action")
    pl = perm_sub.add_parser("list")
    pl.add_argument("--json", action="store_true")
    pc = perm_sub.add_parser("check")
    pc.add_argument("category")
    pc.add_argument("--consume", action="store_true")
    pc.add_argument("--json", action="store_true")
    pg = perm_sub.add_parser("grant")
    pg.add_argument("category")
    grp = pg.add_mutually_exclusive_group()
    grp.add_argument("--once", action="store_true")
    grp.add_argument("--always", action="store_true")
    grp.add_argument("--deny", action="store_true")
    pg.add_argument("--note", default="")
    pg.add_argument("--json", action="store_true")
    pr = perm_sub.add_parser("revoke")
    pr.add_argument("category")
    pr.add_argument("--json", action="store_true")
    preset = perm_sub.add_parser("reset")
    preset.add_argument("--json", action="store_true")

    s = sub.add_parser("watch", help="看门狗（单轮检查；常驻请直接运行 alaswatch.py）")
    s.add_argument("--once", action="store_true", default=True)
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    try:
        env = AlasEnv(root=args.root)
    except EnvError as exc:
        fail(str(exc), code=1)

    handlers = {
        "doctor": cmd_doctor,
        "status": cmd_status,
        "tasks": cmd_tasks,
        "log": cmd_log,
        "errors": cmd_errors,
        "cfg": cmd_cfg,
        "task": cmd_task,
        "start": cmd_start,
        "stop": cmd_stop,
        "perm": cmd_perm,
        "watch": cmd_watch,
    }
    try:
        return handlers[args.command](env, args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        fail("{0}: {1}".format(type(exc).__name__, exc), code=1)


if __name__ == "__main__":
    sys.exit(main())
