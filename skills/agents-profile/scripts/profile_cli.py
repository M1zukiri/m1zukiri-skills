# 创建时间: 2026-11-20 13:36:47
# 用途: agents-profile 命令行入口。
# 命令: list / add / sync / check / audit / apply
# 说明: 本文件随公开仓库分发，不得硬编码本机路径；仓库与项目位置一律探测解析。

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import profile_lib as L


def _project_file(arg: str) -> Path:
    p = Path(arg).expanduser().resolve()
    if p.is_dir():
        return p / "AGENTS.md"
    return p


def _project_roots() -> list[Path]:
    """从 local/projects.txt 读取本机项目清单（每行一个项目根路径）。"""
    try:
        profiles = L.resolve_profiles_dir()
    except RuntimeError:
        return []
    list_file = profiles / "local" / "projects.txt"
    if not list_file.is_file():
        return []
    roots = []
    for line in list_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        roots.append(Path(line).expanduser())
    return roots


def cmd_list(args) -> int:
    profiles = L.load_profiles(L.resolve_profiles_dir())
    if args.profile:
        key = args.profile if args.profile.endswith(".md") else args.profile + ".md"
        profiles = {k: v for k, v in profiles.items() if k == key}
    for rel, p in profiles.items():
        print(f"{rel}")
        print(f"  name          {p.name}")
        print(f"  last-verified {p.last_verified or '(未标注)'}")
        if p.inline_when:
            print(f"  inline-when   {'; '.join(p.inline_when)}")
        if p.exclude_when:
            print(f"  exclude-when  {'; '.join(p.exclude_when)}")
        for s in p.sections:
            print(f"    - {s.anchor}  ({s.title}, {len(s.body)} 字符, sha {s.sha})")
        print()
    return 0


def _wanted_from_declaration(text: str, profiles: dict[str, L.Profile]) -> list[tuple[str, L.Section]]:
    wanted: list[tuple[str, L.Section]] = []
    for rel in L.parse_declaration(text):
        prof = profiles.get(rel)
        if prof is None:
            print(f"  [跳过] 声明了不存在的 profile: {rel}", file=sys.stderr)
            continue
        for sec in prof.sections:
            wanted.append((rel, sec))
    return wanted


def cmd_add(args) -> int:
    pf = _project_file(args.project)
    profiles = L.load_profiles(L.resolve_profiles_dir())
    if not pf.is_file():
        print(f"项目文件不存在: {pf}", file=sys.stderr)
        return 2

    text = pf.read_text(encoding="utf-8")
    declared = L.parse_declaration(text)
    if not declared:
        print(f"{pf} 没有 <!-- profile --> 声明块，无内容可展开", file=sys.stderr)
        return 2

    wanted = _wanted_from_declaration(text, profiles)
    new_text = L.apply_inlines(text, wanted)

    size = len(new_text.encode("utf-8"))
    if size > L.INLINE_BUDGET:
        print(f"展开后 {size} B，超过预算 {L.INLINE_BUDGET} B。未写入。", file=sys.stderr)
        for rel, sec in sorted(wanted, key=lambda x: -len(x[1].body)):
            print(f"  {len(sec.body):>6} 字符  {rel}#{sec.anchor}", file=sys.stderr)
        return 3

    if new_text == text:
        print(f"{pf.name}: 无变化（已是最新）")
        return 0

    if args.dry_run:
        print(f"{pf.name}: 将展开 {len(wanted)} 段，{len(text.encode())} B -> {size} B（dry-run，未写入）")
        for rel, sec in wanted:
            print(f"  + {rel}#{sec.anchor}")
        return 0

    pf.write_text(new_text, encoding="utf-8")
    print(f"{pf.name}: 已展开 {len(wanted)} 段，{len(text.encode())} B -> {size} B")
    return 0


def cmd_sync(args) -> int:
    """只更新已存在的内联区，不按声明块重新展开。

    add 按声明块展开（决定「内联哪些」），sync 只刷新（决定「内容是否最新」）。
    两者职责分离，避免 sync 把 proposal 里刻意排除的段落又加回来。
    """
    pf = _project_file(args.project)
    profiles = L.load_profiles(L.resolve_profiles_dir())
    if not pf.is_file():
        print(f"项目文件不存在: {pf}", file=sys.stderr)
        return 2

    text = pf.read_text(encoding="utf-8")
    existing = L.parse_inlines(text)
    if not existing:
        print(f"{pf.name}: 没有内联区，无需同步（用 add 展开）", file=sys.stderr)
        return 0

    wanted: list[tuple[str, L.Section]] = []
    skipped = 0
    for il in existing:
        prof = profiles.get(il.source)
        sec = prof.section(il.anchor) if prof else None
        if sec is None:
            skipped += 1
            print(f"  [跳过] 源或锚点已不存在: {il.source}#{il.anchor}", file=sys.stderr)
            continue
        wanted.append((il.source, sec))

    new_text = L.apply_inlines(text, wanted)
    size = len(new_text.encode("utf-8"))
    if size > L.INLINE_BUDGET:
        print(f"同步后 {size} B 超过预算 {L.INLINE_BUDGET} B。未写入。", file=sys.stderr)
        return 3

    if new_text == text:
        print(f"{pf.name}: 已是最新（{len(wanted)} 段）")
        return 0

    if args.dry_run:
        print(f"{pf.name}: 将更新 {len(wanted)} 段，{len(text.encode())} B -> {size} B（dry-run）")
        return 0

    pf.write_text(new_text, encoding="utf-8")
    print(f"{pf.name}: 已同步 {len(wanted)} 段，{len(text.encode())} B -> {size} B")
    return 0


def cmd_check(args) -> int:
    profiles = L.load_profiles(L.resolve_profiles_dir())
    targets: list[Path] = []
    if args.all:
        roots = _project_roots()
        if not roots:
            print("--all 需要 agents/profiles/local/projects.txt（每行一个项目根路径）", file=sys.stderr)
            return 2
        targets = [r / "AGENTS.md" for r in roots]
    else:
        if not args.projects:
            print("需要指定项目路径，或用 --all", file=sys.stderr)
            return 2
        targets = [_project_file(p) for p in args.projects]

    total = 0
    for path in targets:
        issues = L.check_project(path, profiles)
        if not issues:
            print(f"[OK]    {path}")
            continue
        total += len(issues)
        print(f"[ISSUE] {path}")
        for it in issues:
            print(f"        {it.kind:<16} {it.detail}")

    print()
    if total == 0:
        print(f"check: {len(targets)} 个项目全部通过")
        return 0
    print(f"check: {total} 个问题")
    return 1


def cmd_audit(args) -> int:
    """输出交给 subagent 执行的审计任务说明与当前状态摘要。"""
    pf = _project_file(args.project)
    profiles = L.load_profiles(L.resolve_profiles_dir())
    if not pf.is_file():
        print(f"项目文件不存在: {pf}", file=sys.stderr)
        return 2

    text = pf.read_text(encoding="utf-8")
    declared = L.parse_declaration(text)
    inlines = L.parse_inlines(text)
    issues = L.check_project(pf, profiles)

    print("=" * 66)
    print("审计任务（交给 subagent 执行）")
    print("=" * 66)
    print(f"项目文件 : {pf}")
    print(f"项目根   : {pf.parent}")
    print(f"文件大小 : {len(text.encode('utf-8'))} B / 预算 {L.INLINE_BUDGET} B")
    print(f"声明块   : {', '.join(declared) if declared else '(无)'}")
    print(f"当前内联 : {len(inlines)} 段")
    print()
    print("--- 现有问题 ---")
    if issues:
        for it in issues:
            print(f"  {it.kind:<16} {it.detail}")
    else:
        print("  (无)")
    print()
    print("--- subagent 只读要求 ---")
    print("""
你本次只做分析，不修改任何文件。允许：
  1. 读项目 AGENTS.md 与项目文件结构
  2. 读 profiles 下所有非 local 的 md 文件
  3. 用 glob 探测项目结构，验证 inline-when 条件是否成立
  4. 核查正文提到的文件、命令、版本号是否仍然存在
禁止：修改任何文件、修改声明块、删除非标记区内容、执行 add/sync/apply

输出一个 proposal.json，格式：
{
  "project": "<项目 AGENTS.md 绝对路径>",
  "add":    [{"source": "platforms/windows.md", "anchor": "powershell-bom", "reason": "..."}],
  "remove": [{"source": "stacks/python.md", "anchor": "safe-print", "reason": "..."}],
  "warnings": ["正文提到的 xxx 已不存在"]
}

每条 add/remove 必须给出 reason。没有理由的条目一律不要输出。
""")
    return 0


def cmd_apply(args) -> int:
    proposal = json.loads(Path(args.proposal).read_text(encoding="utf-8"))
    pf = _project_file(proposal["project"])
    profiles = L.load_profiles(L.resolve_profiles_dir())
    if not pf.is_file():
        print(f"项目文件不存在: {pf}", file=sys.stderr)
        return 2

    text = pf.read_text(encoding="utf-8")
    current = {(il.source, il.anchor) for il in L.parse_inlines(text)}

    for item in proposal.get("add", []):
        current.add((item["source"], item["anchor"]))
    for item in proposal.get("remove", []):
        current.discard((item["source"], item["anchor"]))

    wanted: list[tuple[str, L.Section]] = []
    for source, anchor in sorted(current):
        prof = profiles.get(source)
        if prof is None:
            print(f"  [跳过] 源不存在: {source}", file=sys.stderr)
            continue
        sec = prof.section(anchor)
        if sec is None:
            print(f"  [跳过] 锚点不存在: {source}#{anchor}", file=sys.stderr)
            continue
        wanted.append((source, sec))

    new_text = L.apply_inlines(text, wanted)
    size = len(new_text.encode("utf-8"))
    if size > L.INLINE_BUDGET:
        print(f"应用后 {size} B 超过预算 {L.INLINE_BUDGET} B。未写入。", file=sys.stderr)
        return 3

    if new_text == text:
        print(f"{pf.name}: 无变化")
        return 0

    pf.write_text(new_text, encoding="utf-8")
    print(f"{pf.name}: 已应用 proposal（{len(wanted)} 段内联，{len(text.encode())} B -> {size} B）")
    for w in proposal.get("warnings", []):
        print(f"  warning: {w}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agents-profile", description="管理 profiles 向项目 AGENTS.md 的内联")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="列出可内联的 profile 与锚点")
    p.add_argument("--profile", help="只看某个 profile，如 platforms/windows")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("add", help="按声明块展开内联")
    p.add_argument("project")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("sync", help="重拉已声明 profile 的最新内容")
    p.add_argument("project")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("check", help="校验内联状态")
    p.add_argument("projects", nargs="*")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("audit", help="输出交给 subagent 的审计任务说明")
    p.add_argument("project")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("apply", help="应用 subagent 产出的 proposal.json")
    p.add_argument("proposal")
    p.set_defaults(func=cmd_apply)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
