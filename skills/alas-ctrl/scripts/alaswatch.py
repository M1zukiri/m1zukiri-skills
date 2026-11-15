# 创建时间：2026-11-16 01:10:30
"""ALAS 看门狗。

只做两件事：读日志判状态、管进程。绝不点击屏幕、绝不写游戏数据。
所有「让游戏动起来」的意图都转成对 ALAS 任务的配置，由 ALAS 执行。
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import alasctl as cli
from _env import read_json, write_json_atomic

RESTART_WINDOW_SEC = 600
RESTART_MAX_IN_WINDOW = 3
STUCK_GRACE_SEC = 600  # 卡住后先等 ALAS 自愈（它自带 Restart），超时才强杀
HUMAN_ALERT_FILE = "alert.json"


def _state_path(env):
    return os.path.join(env.state_dir, "watch.json")


def _load(env):
    data = read_json(_state_path(env), default=None) or {}
    data.setdefault("restarts", [])
    data.setdefault("stuck_since", None)
    data.setdefault("last_state", None)
    data.setdefault("last_tick", None)
    return data


def _save(env, data):
    env.ensure_state()
    write_json_atomic(_state_path(env), data)


def _now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _recent_restarts(data, now_ts):
    kept = [ts for ts in data.get("restarts", []) if now_ts - ts <= RESTART_WINDOW_SEC]
    data["restarts"] = kept
    return kept


def _restart(env, dry_run):
    """复用 alasctl 的 start 逻辑（含授权闸门与冲突检测）。"""
    if dry_run:
        return {"action": "restart", "dry_run": True}
    procs = cli.find_scheduler_processes(env)
    recorded = cli._read_recorded_pid(env)
    for proc in procs:
        if recorded and proc["pid"] != recorded:
            return {"action": "refuse", "reason": "存在非本工具管理的实例", "pid": proc["pid"]}
    # 先杀掉可能残留的本工具进程
    try:
        cli.cmd_stop(env, _StopArgs())
    except SystemExit:
        pass
    try:
        code = cli.cmd_start(env, _StartArgs())
    except SystemExit as exc:
        return {"action": "restart", "exit": int(exc.code or 0)}
    return {"action": "restart", "exit": code}


class _StopArgs(object):
    force = True
    timeout = 0
    json = True


class _StartArgs(object):
    json = True


def tick(env, dry_run=False):
    """执行一轮检查，返回本轮决策。"""
    now_ts = time.time()
    data = _load(env)
    status = cli.collect_status(env)
    state = status["state"]

    decision = {"at": _now_str(), "state": state, "action": "none", "reason": ""}

    if state == cli._logparse.STATE_CONFLICT:
        decision["reason"] = "存在非本工具管理的 ALAS 实例，看门狗不介入"

    elif state == cli._logparse.STATE_NEEDS_HUMAN:
        decision["action"] = "alert"
        decision["reason"] = "ALAS 请求人工接管"
        env.ensure_state()
        write_json_atomic(
            os.path.join(env.state_dir, HUMAN_ALERT_FILE),
            {
                "at": _now_str(),
                "state": state,
                "reason": status.get("human_reason") or status.get("last_error"),
                "current_task": status.get("current_task"),
                "log": status.get("log_path"),
                "error_dir": status.get("error_dir"),
            },
        )
        # 需要人工时不自动重启，避免无限循环
        data["stuck_since"] = None

    elif state == cli._logparse.STATE_STUCK:
        since = data.get("stuck_since")
        if not since:
            data["stuck_since"] = now_ts
            decision["reason"] = "判定卡住，进入宽限期等待 ALAS 自愈"
        else:
            elapsed = now_ts - float(since)
            if elapsed >= STUCK_GRACE_SEC:
                recent = _recent_restarts(data, now_ts)
                if len(recent) >= RESTART_MAX_IN_WINDOW:
                    decision["action"] = "alert"
                    decision["reason"] = "卡住且重启次数超限，停止自动重启"
                else:
                    decision["action"] = "restart"
                    decision["reason"] = "卡住超过 {0} 秒".format(int(elapsed))
                    if not dry_run:
                        data["restarts"].append(now_ts)
                        _restart(env, dry_run)
                        data["stuck_since"] = None
            else:
                decision["reason"] = "卡住，宽限 {0}s / {1}s".format(
                    int(elapsed), STUCK_GRACE_SEC
                )

    elif state == cli._logparse.STATE_DOWN:
        # 进程不存在或今天从未启动
        procs = cli.find_scheduler_processes(env)
        recorded = cli._read_recorded_pid(env)
        if not procs and not recorded:
            recent = _recent_restarts(data, now_ts)
            if len(recent) >= RESTART_MAX_IN_WINDOW:
                decision["action"] = "alert"
                decision["reason"] = "进程不在且重启次数超限（{0}/{1} 次/10min）".format(
                    len(recent), RESTART_MAX_IN_WINDOW
                )
            else:
                decision["action"] = "restart"
                decision["reason"] = "进程不在，自动拉起"
                if not dry_run:
                    data["restarts"].append(now_ts)
                    _restart(env, dry_run)
        else:
            decision["reason"] = "进程在但今日无调度日志，继续观察"

    elif state == cli._logparse.STATE_WAITING:
        decision["reason"] = "空闲等待下一个任务时间点（合法静默）"
        data["stuck_since"] = None

    else:  # RUNNING
        decision["reason"] = "任务执行中"
        data["stuck_since"] = None

    data["last_state"] = state
    data["last_tick"] = _now_str()
    if not dry_run:
        _save(env, data)
        write_json_atomic(
            env.live_path,
            {
                "at": _now_str(),
                "status": status,
                "decision": decision,
            },
        )
    decision["status"] = status
    return decision


def loop(env, interval=20, dry_run=False):
    sys.stdout.write("alaswatch 启动，间隔 {0}s，dry_run={1}\n".format(interval, dry_run))
    sys.stdout.flush()
    try:
        while True:
            decision = tick(env, dry_run=dry_run)
            sys.stdout.write(
                "[{0}] {1:<12} {2:<8} {3}\n".format(
                    decision["at"], decision["state"], decision["action"], decision["reason"]
                )
            )
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        sys.stdout.write("alaswatch 退出\n")
        return 0


def main(argv=None):
    import argparse

    from _env import AlasEnv

    parser = argparse.ArgumentParser(prog="alaswatch", description="ALAS 看门狗")
    parser.add_argument("--root", help="ALAS 根目录")
    parser.add_argument("--once", action="store_true", help="只检查一轮")
    parser.add_argument("--interval", type=int, default=20, help="轮询间隔秒数")
    parser.add_argument("--dry-run", action="store_true", help="只报告不执行动作")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    env = AlasEnv(root=args.root)
    if args.once:
        result = tick(env, dry_run=args.dry_run)
        if args.json:
            sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        else:
            sys.stdout.write(
                "[{0}] {1} -> {2}: {3}\n".format(
                    result["at"], result["state"], result["action"], result["reason"]
                )
            )
        return 0
    return loop(env, interval=args.interval, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
