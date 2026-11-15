# 创建时间：2026-11-16 01:08:03
"""ALAS 环境探测层。

刻意不 import ALAS 的任何 Python 模块，只做文件系统与进程探测，
这样 ALAS 升级后本层不受影响。所有路径都由探测得出，不含硬编码的用户目录。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile


class EnvError(RuntimeError):
    """环境探测失败，消息里带修复建议。"""


# ALAS 根目录的判定特征文件
_MARKERS = ("alas.py", os.path.join("config", "alas.json"), "toolkit")


def _looks_like_alas(path):
    return all(os.path.exists(os.path.join(path, m)) for m in _MARKERS)


def find_alas_root(explicit=None):
    """按 显式参数 → 环境变量 → 从 cwd 向上 → 常见安装位置 的顺序定位 ALAS 根目录。"""
    candidates = []
    if explicit:
        candidates.append(explicit)
    env_root = os.environ.get("ALAS_ROOT")
    if env_root:
        candidates.append(env_root)
    here = os.path.abspath(os.getcwd())
    for _ in range(4):
        candidates.append(here)
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    # 常见盘符下的默认安装目录名，不含用户名，仅作兜底
    for drive in ("D:", "C:", "E:"):
        candidates.append(os.path.join(drive + os.sep, "AzurLaneAutoScript"))

    for cand in candidates:
        if cand and os.path.isdir(cand) and _looks_like_alas(cand):
            return os.path.abspath(cand)
    raise EnvError(
        "找不到 ALAS 根目录。请设置环境变量 ALAS_ROOT 指向 AzurLaneAutoScript 目录，"
        "或先 cd 到该目录再执行。已尝试：{0}".format(candidates)
    )


def tasklist_of(pid):
    """返回 PID 的命令行；跨进程查询失败时返回空串（不抛异常）。"""
    if os.name != "nt":
        try:
            with open("/proc/{0}/cmdline".format(pid), "rb") as f:
                return f.read().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            return ""
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Process -Filter 'ProcessId={0}').CommandLine".format(
                    int(pid)
                ),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return proc.stdout.decode("utf-8", "replace").strip()
    except Exception:
        return ""


def process_alive(pid):
    if os.name == "nt":
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", "PID eq {0}".format(int(pid)), "/NH"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            out = proc.stdout.decode("utf-8", "replace")
            return str(int(pid)) in out
        except Exception:
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json_atomic(path, data):
    """同目录临时文件 + os.replace，避免半截 JSON 被 ALAS 读到。"""
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        os.makedirs(directory)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class AlasEnv(object):
    """一次探测，多处复用。"""

    def __init__(self, root=None):
        self.root = find_alas_root(root)
        self.config_dir = os.path.join(self.root, "config")
        self.config_path = os.path.join(self.config_dir, os.environ.get("ALAS_CONFIG", "alas") + ".json")
        self.log_dir = os.path.join(self.root, "log")
        self.error_dir = os.path.join(self.log_dir, "error")
        self.python = self._find_python()
        self.adb = self._find_adb()
        # skill 自身的运行时状态目录
        self.skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.state_dir = os.path.join(self.skill_dir, "state")
        self.backup_dir = os.path.join(self.state_dir, "backup")
        self.perm_path = os.path.join(self.state_dir, "permissions.json")
        self.live_path = os.path.join(self.state_dir, "live.json")
        self.proc_path = os.path.join(self.state_dir, "process.json")

    def _find_python(self):
        cand = os.path.join(self.root, "toolkit", "python.exe")
        if os.path.exists(cand):
            return cand
        cand = os.path.join(self.root, "toolkit", "python")
        if os.path.exists(cand):
            return cand
        return sys.executable

    def _find_adb(self):
        cands = [
            os.path.join(self.root, "toolkit", "Lib", "site-packages", "adbutils", "binaries", "adb.exe"),
            os.path.join(self.root, "toolkit", "Lib", "site-packages", "adbutils", "binaries", "adb"),
            os.path.join(self.root, "bin", "adb", "adb.exe"),
        ]
        for cand in cands:
            if os.path.exists(cand):
                return cand
        return "adb"

    def commit(self):
        """当前 ALAS 版本（git short hash），拿不到返回 None。"""
        git = os.path.join(self.root, "toolkit", "Git", "cmd", "git.exe")
        if not os.path.exists(git):
            git = "git"
        try:
            out = subprocess.run(
                [git, "-C", self.root, "rev-parse", "--short", "HEAD"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            text = out.stdout.decode("utf-8", "replace").strip()
            return text or None
        except Exception:
            return None

    def config_mtime(self):
        try:
            return os.path.getmtime(self.config_path)
        except OSError:
            return 0.0

    def ensure_state(self):
        for d in (self.state_dir, self.backup_dir):
            if not os.path.isdir(d):
                os.makedirs(d)
