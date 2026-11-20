# 创建时间: 2026-11-20 13:30:02
# 用途: agents-profile 的核心库——解析 profile 文件与项目 AGENTS.md，
#       渲染内联块、计算段落哈希、探测仓库与 DSH home 位置。
# 说明: 本文件随公开仓库分发，不得硬编码任何本机路径；位置一律通过探测解析。

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# ---------- 常量 ----------

FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.S)
ANCHOR_RE = re.compile(r"^<!--\s*anchor:\s*([a-z0-9-]+)\s*-->\s*$", re.M)
DECL_RE = re.compile(r"<!--\s*profile\s*\n(.*?)-->", re.S)
INLINE_BEGIN_RE = re.compile(
    r"<!--\s*BEGIN inline:\s*(\S+)#([a-z0-9-]+)\s+sha=([0-9a-f]{8})\s*-->"
)
INLINE_END_RE = re.compile(
    r"<!--\s*END inline:\s*(\S+)#([a-z0-9-]+)\s*-->"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)

INLINE_BUDGET = 24 * 1024  # 单个项目 AGENTS.md 内联后的字节上限


# ---------- 位置探测 ----------

def _run_git(args: list[str], cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode != 0:
            return None
        return out.stdout.strip()
    except Exception:
        return None


def resolve_agents_repo(start: Path | None = None) -> Path:
    """定位 m1zukiri-skills 仓库根。

    顺序：环境变量 AGENTS_REPO → git remote 匹配 → 向上查找含 agents/AGENTS.md 的目录。
    全部失败则抛错，不使用默认值。
    """
    env = os.environ.get("AGENTS_REPO")
    if env:
        p = Path(env).expanduser()
        if (p / "agents" / "AGENTS.md").is_file():
            return p
        raise RuntimeError(f"AGENTS_REPO 指向的目录不含 agents/AGENTS.md: {p}")

    here = (start or Path.cwd()).resolve()
    for d in [here, *here.parents]:
        remote = _run_git(["remote", "get-url", "origin"], d)
        if remote and "m1zukiri-skills" in remote:
            if (d / "agents" / "AGENTS.md").is_file():
                return d
        if (d / "agents" / "AGENTS.md").is_file() and (d / "skills").is_dir():
            return d
    raise RuntimeError(
        "无法定位 m1zukiri-skills 仓库。请设置 AGENTS_REPO 环境变量，或在仓库内运行。"
    )


def resolve_profiles_dir(repo: Path | None = None) -> Path:
    repo = repo or resolve_agents_repo()
    d = repo / "agents" / "profiles"
    if not d.is_dir():
        raise RuntimeError(f"profiles 目录不存在: {d}")
    return d


def resolve_dsh_home() -> Path:
    env = os.environ.get("DSH_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".dsh"


def resolve_project_root(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    top = _run_git(["rev-parse", "--show-toplevel"], here)
    if top:
        return Path(top)
    return here


# ---------- 数据结构 ----------

@dataclass
class Section:
    """profile 文件中的一个可内联段落。"""
    anchor: str
    title: str
    level: int
    body: str          # 含标题行的完整段落正文
    sha: str           # body 前 8 位 sha256


@dataclass
class Profile:
    """一个 profile 文件。"""
    name: str
    path: Path
    rel: str                               # 相对 profiles 根，如 platforms/windows.md
    inline_when: list[str] = field(default_factory=list)
    exclude_when: list[str] = field(default_factory=list)
    last_verified: str = ""
    sections: list[Section] = field(default_factory=list)

    def section(self, anchor: str) -> Section | None:
        for s in self.sections:
            if s.anchor == anchor:
                return s
        return None


@dataclass
class Inline:
    """项目文件中的一段内联区。"""
    source: str        # profiles 相对路径，如 platforms/windows.md
    anchor: str
    sha: str           # 文件中记录的 sha
    start: int         # BEGIN 注释起始偏移
    end: int           # END 注释结束偏移（含）
    body: str


# ---------- 解析 ----------

def sha8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw = m.group(1)
    meta: dict[str, object] = {}
    key = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if re.match(r"^\s+\S", line) or line.lstrip().startswith("- "):
            # 列表项
            item = line.strip()
            if item.startswith("- "):
                item = item[2:].strip()
                if key:
                    meta.setdefault(key, [])
                    if isinstance(meta[key], list):
                        meta[key].append(item)
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            key = k.strip()
            v = v.strip()
            meta[key] = v if v else []
    return meta, text[m.end():]


def _flatten_when(value) -> list[str]:
    """把 inline-when 结构压平成条件字符串列表。"""
    out: list[str] = []
    if isinstance(value, list):
        out.extend(str(v) for v in value)
    return out


def parse_profile(path: Path, rel: str) -> Profile:
    text = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    prof = Profile(
        name=str(meta.get("name", "")),
        path=path,
        rel=rel,
        inline_when=_flatten_when(meta.get("inline-when")),
        exclude_when=_flatten_when(meta.get("exclude-when")),
        last_verified=str(meta.get("last-verified", "")),
    )
    prof.sections = parse_sections(body)
    return prof


def parse_sections(body: str) -> list[Section]:
    """按 anchor 注释切段：锚点后的下一个标题起，到下一个锚点前止。"""
    marks = list(ANCHOR_RE.finditer(body))
    sections: list[Section] = []
    for i, m in enumerate(marks):
        anchor = m.group(1)
        seg_end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        seg = body[m.end():seg_end]
        # 找该段第一个标题
        hm = HEADING_RE.search(seg)
        if not hm:
            continue
        level = len(hm.group(1))
        title = hm.group(2).strip()
        # 正文从标题行开始，到下一个同级或更高级标题前
        start = hm.start()
        rest = seg[hm.end():]
        cut = len(rest)
        for nxt in HEADING_RE.finditer(rest):
            if len(nxt.group(1)) <= level:
                cut = nxt.start()
                break
        section_body = (hm.group(0) + rest[:cut]).strip()
        sections.append(
            Section(
                anchor=anchor,
                title=title,
                level=level,
                body=section_body,
                sha=sha8(section_body),
            )
        )
    return sections


def load_profiles(profiles_dir: Path) -> dict[str, Profile]:
    """加载 profiles 下所有非 local 的 md 文件（README 除外）。"""
    result: dict[str, Profile] = {}
    for path in sorted(profiles_dir.rglob("*.md")):
        rel = path.relative_to(profiles_dir).as_posix()
        if rel.startswith("local/"):
            continue
        if path.name == "README.md":
            continue
        result[rel] = parse_profile(path, rel)
    return result


def parse_declaration(text: str) -> list[str]:
    """解析项目 AGENTS.md 的 <!-- profile --> 块，返回 profile 相对路径列表。"""
    m = DECL_RE.search(text)
    if not m:
        return []
    names: list[str] = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if k == "repo" or not v or v == "-":
            continue
        for item in v.split(","):
            item = item.strip()
            if not item or item == "-":
                continue
            names.append(f"{k}/{item}.md")
    return names


def parse_inlines(text: str) -> list[Inline]:
    """提取文件中所有完整的内联区（BEGIN 与 END 配对）。"""
    begins = list(INLINE_BEGIN_RE.finditer(text))
    result: list[Inline] = []
    for b in begins:
        source, anchor, sha = b.group(1), b.group(2), b.group(3)
        end_m = INLINE_END_RE.search(text, b.end())
        if not end_m:
            continue
        if end_m.group(1) != source or end_m.group(2) != anchor:
            continue
        result.append(
            Inline(
                source=source,
                anchor=anchor,
                sha=sha,
                start=b.start(),
                end=end_m.end(),
                body=text[b.end():end_m.start()].strip("\n"),
            )
        )
    return result


# ---------- 渲染 ----------

def render_inline(inline_source: str, section: Section) -> str:
    return (
        f"<!-- BEGIN inline: {inline_source}#{section.anchor} sha={section.sha} -->\n"
        f"{section.body}\n"
        f"<!-- END inline: {inline_source}#{section.anchor} -->"
    )


# ---------- 校验 ----------

@dataclass
class Issue:
    kind: str        # dangling / unpaired / stale / missing / budget / undeclared / declared-missing
    detail: str
    path: str = ""


def check_project(path: Path, profiles: dict[str, Profile], budget: int = INLINE_BUDGET) -> list[Issue]:
    issues: list[Issue] = []
    if not path.is_file():
        return [Issue("missing", f"项目文件不存在: {path}", str(path))]

    text = path.read_text(encoding="utf-8")
    declared = parse_declaration(text)
    inlines = parse_inlines(text)

    # 1) 声明了但 profile 不存在
    for d in declared:
        if d not in profiles:
            issues.append(Issue("declared-missing", f"声明了不存在的 profile: {d}", str(path)))

    # 2) 内联了但源锚点不存在 / sha 过期
    declared_set = set(declared)
    for il in inlines:
        prof = profiles.get(il.source)
        if prof is None:
            issues.append(Issue("dangling", f"内联源不存在: {il.source}#{il.anchor}", str(path)))
            continue
        sec = prof.section(il.anchor)
        if sec is None:
            issues.append(Issue("dangling", f"锚点不存在: {il.source}#{il.anchor}", str(path)))
            continue
        if sec.sha != il.sha:
            issues.append(
                Issue("stale", f"内容已过期: {il.source}#{il.anchor} (文件 {il.sha} != 源 {sec.sha})", str(path))
            )
        if il.source not in declared_set:
            issues.append(
                Issue("undeclared", f"内联了但声明块没有: {il.source}#{il.anchor}", str(path))
            )

    # 3) 标记不成对
    begins = len(INLINE_BEGIN_RE.findall(text))
    ends = len(INLINE_END_RE.findall(text))
    if begins != ends:
        issues.append(Issue("unpaired", f"标记不成对: BEGIN={begins} END={ends}", str(path)))

    # 4) 预算
    size = len(text.encode("utf-8"))
    if size > budget:
        issues.append(Issue("budget", f"文件 {size} B 超过预算 {budget} B", str(path)))

    return issues


# ---------- 写入 ----------

def apply_inlines(text: str, wanted: list[tuple[str, Section]]) -> str:
    """把 wanted（source, section）列表写入 text，返回新文本。

    幂等：先移除文件中所有旧内联区，再按 wanted 顺序统一追加到末尾。
    这样同一输入重复执行得到完全相同的结果。
    """
    existing = parse_inlines(text)
    base = text
    for il in sorted(existing, key=lambda x: x.start, reverse=True):
        base = base[: il.start] + base[il.end :]

    base = base.rstrip("\n")
    if not wanted:
        return base + "\n" if base else ""
    blocks = [render_inline(source, section) for source, section in wanted]
    return base + "\n\n" + "\n\n".join(blocks) + "\n"
