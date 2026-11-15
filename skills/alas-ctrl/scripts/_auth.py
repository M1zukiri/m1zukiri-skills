# 创建时间：2026-11-16 01:09:10
"""操作授权（手机应用权限模型）。

每个操作类别有独立状态：未询问 / 本次允许(once) / 同类永久允许(always) / 拒绝(deny)。
未询问时调用方必须向用户发起授权请求，拿到答复后用 grant() 记录，再继续。

类别划分（按影响面）：
  read      读状态、日志、配置              —— 默认允许
  process   启停 ALAS 进程                  —— 默认询问
  schedule  改任务开关与执行时间            —— 默认询问
  settings  改 ALAS 运营设置                —— 默认询问
  resource  任何消耗游戏资源的动作          —— 默认拒绝
"""
from __future__ import annotations

import datetime

from _env import read_json, write_json_atomic

ALLOW = "allow"
DENY = "deny"
ASK = "ask"

CATEGORIES = {
    "read": "读取状态/日志/配置",
    "process": "启动或停止 ALAS 进程",
    "schedule": "修改任务开关与执行时间",
    "settings": "修改 ALAS 运营设置（打图章节、油量、舰队等）",
    "resource": "消耗游戏资源（钻石/魔方/抽卡/退役/分解）",
}

DEFAULTS = {
    "read": ALLOW,
    "process": ASK,
    "schedule": ASK,
    "settings": ASK,
    "resource": DENY,
}

_SCHEMA_VERSION = 1


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load(env):
    data = read_json(env.perm_path, default=None)
    if not data or not isinstance(data, dict):
        data = {}
    data.setdefault("version", _SCHEMA_VERSION)
    cats = data.setdefault("categories", {})
    for name, default in DEFAULTS.items():
        entry = cats.get(name)
        if not isinstance(entry, dict):
            cats[name] = {"decision": default, "decided_at": None, "note": ""}
        else:
            entry.setdefault("decision", default)
            entry.setdefault("decided_at", None)
            entry.setdefault("note", "")
    data.setdefault("once", {})
    data.setdefault("audit", [])
    return data


def save(env, data):
    # 审计只保留最近 200 条
    data["audit"] = data.get("audit", [])[-200:]
    write_json_atomic(env.perm_path, data)


def _audit(data, action, category, detail=""):
    data.setdefault("audit", []).append(
        {"at": _now(), "action": action, "category": category, "detail": detail}
    )


def list_all(env):
    data = load(env)
    rows = []
    for name, desc in CATEGORIES.items():
        entry = data["categories"][name]
        rows.append(
            {
                "category": name,
                "description": desc,
                "decision": entry["decision"],
                "once": data.get("once", {}).get(name, 0),
                "decided_at": entry.get("decided_at"),
                "note": entry.get("note", ""),
            }
        )
    return rows


def check(env, category, consume_once=False):
    """返回 allow / allow_once / deny / ask。consume_once=True 时扣减一次性授权。"""
    if category not in CATEGORIES:
        return ASK
    data = load(env)
    once = data.get("once", {}).get(category, 0)
    if once > 0:
        if consume_once:
            data["once"][category] = once - 1
            _audit(data, "consume_once", category)
            save(env, data)
        return "allow_once"
    decision = data["categories"][category]["decision"]
    if decision in (ALLOW, DENY):
        return decision
    return ASK


def grant(env, category, scope, note=""):
    """scope: once / always / deny。返回更新后的状态。"""
    if category not in CATEGORIES:
        raise ValueError("未知授权类别: {0}".format(category))
    data = load(env)
    if scope == "once":
        data["once"][category] = data.get("once", {}).get(category, 0) + 1
        _audit(data, "grant_once", category, note)
    elif scope == "always":
        data["categories"][category].update(
            {"decision": ALLOW, "decided_at": _now(), "note": note}
        )
        _audit(data, "grant_always", category, note)
    elif scope == "deny":
        data["categories"][category].update(
            {"decision": DENY, "decided_at": _now(), "note": note}
        )
        _audit(data, "deny", category, note)
    else:
        raise ValueError("未知授权范围: {0}".format(scope))
    save(env, data)
    return check(env, category)


def revoke(env, category):
    data = load(env)
    if category in data["categories"]:
        data["categories"][category].update(
            {"decision": DEFAULTS.get(category, ASK), "decided_at": _now(), "note": ""}
        )
        data["once"][category] = 0
        _audit(data, "revoke", category)
        save(env, data)
    return check(env, category)


def reset(env):
    data = {"version": _SCHEMA_VERSION, "categories": {}, "once": {}, "audit": []}
    _audit(data, "reset", "-")
    save(env, data)
    return load(env)


def gate(env, category, action_desc):
    """供命令层调用的统一闸门：返回 (allowed, payload)。

    payload 在需要用户介入时给出可直接展示的询问文案。
    """
    result = check(env, category)
    if result in ("allow", "allow_once"):
        return True, {"decision": result}
    if result == "deny":
        return False, {
            "decision": "deny",
            "message": "操作类别 `{0}` 已被拒绝，未执行：{1}".format(category, action_desc),
        }
    desc = CATEGORIES.get(category, "")
    return False, {
        "decision": "ask",
        "category": category,
        "description": desc,
        "action": action_desc,
        "message": (
            "需要授权：类别 `{0}`（{1}），动作：{2}。"
            "请回复「本次可行 / 同类操作可行 / 拒绝」，"
            "或以 `perm grant {0} --once|--always|--deny` 记录决定。"
        ).format(category, desc, action_desc),
    }
