# 创建时间：2026-11-16 01:22:10
"""alas-ctrl 自测：不依赖真实 ALAS 运行，用构造日志验证状态机与配置规则。

用法：python scripts/selftest.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _logparse as lp

FAILED = []


def _make(lines):
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    f.write("\n".join(lines))
    f.close()
    return f.name


def _ts(now, offset=0):
    return (now - timedelta(seconds=offset)).strftime("%Y-%m-%d %H:%M:%S")


def check(name, got, expect):
    ok = got == expect
    print("{0} {1:<22} expect={2!r:<14} got={3!r}".format("PASS" if ok else "FAIL", name, expect, got))
    if not ok:
        FAILED.append(name)


def test_state_machine():
    now = datetime.now()
    cases = [
        (
            "运行中",
            [
                "{0}.000 | INFO | Scheduler: Start task `Main`".format(_ts(now, 30)),
                "{0}.000 | INFO | [UI] page_main".format(_ts(now, 2)),
            ],
            "RUNNING",
        ),
        (
            "无新行卡死",
            [
                "{0}.000 | INFO | Scheduler: Start task `Main`".format(_ts(now, 200)),
                "{0}.000 | INFO | [UI] page_battle".format(_ts(now, 190)),
            ],
            "STUCK",
        ),
        (
            "错误新鲜",
            [
                "{0}.000 | INFO | Scheduler: Start task `Event`".format(_ts(now, 20)),
                "{0}.000 | ERROR | GameTooManyClickError: Too many click for a button:".format(_ts(now, 3)),
                "POPUP_CONFIRM_AUTO_SEARCH_COMBAT_EXECUTE",
                "{0}.000 | WARNING | Saving error: ./log/error/1794604553214".format(_ts(now, 2)),
            ],
            "STUCK",
        ),
        (
            "错误已恢复",
            [
                "{0}.000 | INFO | Scheduler: Start task `Main`".format(_ts(now, 300)),
                "{0}.000 | ERROR | GameStuckError: Wait too long".format(_ts(now, 280)),
                "{0}.000 | INFO | Scheduler: End task `Main`".format(_ts(now, 270)),
                "{0}.000 | INFO | Scheduler: Start task `Commission`".format(_ts(now, 269)),
                "{0}.000 | INFO | [UI] page_commission".format(_ts(now, 2)),
            ],
            "RUNNING",
        ),
        (
            "等待中",
            [
                "{0}.000 | INFO | Scheduler: End task `Main`".format(_ts(now, 100)),
                "{0}.000 | INFO | Wait until 2026-11-16 04:00:00 for task `Main`".format(_ts(now, 99)),
                "{0}.000 | INFO | Page arrive: page_main".format(_ts(now, 98)),
            ],
            "WAITING",
        ),
        (
            "需人工",
            [
                "{0}.000 | INFO | Scheduler: Start task `Restart`".format(_ts(now, 50)),
                "{0}.000 | CRITICAL | Task `Restart` failed 3 or more times.".format(_ts(now, 40)),
                "{0}.000 | CRITICAL | Request human takeover".format(_ts(now, 40)),
            ],
            "NEEDS_HUMAN",
        ),
        ("空日志", [], "DOWN"),
    ]
    for name, lines, expect in cases:
        path = _make(lines)
        try:
            result = lp.analyze(path)
            check(name, result["state"], expect)
            if name == "错误新鲜":
                check(
                    "折行还原",
                    "POPUP_CONFIRM_AUTO_SEARCH_COMBAT_EXECUTE" in (result["last_error"] or ""),
                    True,
                )
        finally:
            os.unlink(path)


def test_safe_point():
    now = datetime.now()
    path = _make(
        [
            "{0}.000 | INFO | Scheduler: End task `Main`".format(_ts(now, 8)),
            "{0}.000 | INFO | Scheduler: Start task `Commission`".format(_ts(now, 7)),
        ]
    )
    try:
        since = lp.seconds_since_last_end(path)
        check("安全点秒数", since is not None and 7 <= since <= 12, True)
    finally:
        os.unlink(path)


def test_parse_duration():
    import alasctl

    check("时长 30m", alasctl.parse_duration("30m"), 1800)
    check("时长 2h", alasctl.parse_duration("2h"), 7200)
    check("时长 90s", alasctl.parse_duration("90s"), 90)
    try:
        alasctl.parse_duration("abc")
        check("非法时长应报错", False, True)
    except ValueError:
        check("非法时长应报错", True, True)


def test_nextrun_limit():
    import alasctl

    check("Main 上限", alasctl.nextrun_limit("Main"), 24 * 3600)
    check("Commission 上限", alasctl.nextrun_limit("Commission"), 12 * 3600)
    check("OpsiArchive 上限", alasctl.nextrun_limit("OpsiArchive"), 7 * 86400)
    check("OpsiExplore 上限", alasctl.nextrun_limit("OpsiExplore"), 31 * 86400)


def test_auth_defaults():
    import _auth

    check("默认 read", _auth.DEFAULTS["read"], "allow")
    check("默认 process", _auth.DEFAULTS["process"], "ask")
    check("默认 resource", _auth.DEFAULTS["resource"], "deny")


def main():
    test_state_machine()
    test_safe_point()
    test_parse_duration()
    test_nextrun_limit()
    test_auth_defaults()
    print()
    if FAILED:
        print("FAILED: {0}".format(", ".join(FAILED)))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
