# created: 2026-11-02 14:33:54
"""Static checks for a corrected meeting transcript + correction log.

It catches the mechanical mistakes that are easy to miss when editing long
Markdown by hand: broken relative links, tables whose rows have different column
counts, invalid confidence labels, high-confidence rows that still admit
uncertainty, and (optionally) leftover ASR fragments in the corrected column.

Usage:
    python check_corrections.py 转写_校正版.md 校正说明.md 幻灯片原文.md
    python check_corrections.py 转写_校正版.md --suspect "Moe,Psnr,Ot side,token well"

Exit code: 1 if any ERROR found, 0 otherwise. Warnings do not fail the run.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

LINK_RE = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
TIME_ROW_RE = re.compile(r"^\|\s*`\d{2}:\d{2}:\d{2}`\s*\|")
CONFIDENCE_LABELS = {"高", "中", "低"}
UNCERTAIN_WORDS = ("存疑", "推断", "无法复原", "不确定", "〔")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checked = 0

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def check_links(path: Path, report: Report) -> None:
    text = path.read_text(encoding="utf-8")
    for match in LINK_RE.finditer(text):
        target = match.group(1)
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        resolved = (path.parent / target).resolve()
        if not resolved.exists():
            report.error(f"{path}: broken link -> {target}")


def check_tables(path: Path, report: Report) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    block: list[tuple[int, str]] = []

    def flush() -> None:
        if len(block) < 2:
            block.clear()
            return
        expected = block[0][1].count("|")
        for line_no, row in block:
            if row.count("|") != expected:
                report.error(
                    f"{path}:{line_no}: table column mismatch "
                    f"(expected {expected} pipes, got {row.count('|')})"
                )
        block.clear()

    for index, line in enumerate(lines + [""], start=1):
        if line.strip().startswith("|"):
            block.append((index, line))
        else:
            flush()


def split_cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def check_confidence(path: Path, report: Report) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    counts = {"高": 0, "中": 0, "低": 0}
    for line_no, line in enumerate(lines, start=1):
        if not TIME_ROW_RE.match(line):
            continue
        cells = split_cells(line)
        if len(cells) < 5:
            report.warn(f"{path}:{line_no}: time row has {len(cells)} columns, expected at least 5")
            continue
        label = cells[3]
        if label not in CONFIDENCE_LABELS:
            report.error(f"{path}:{line_no}: invalid confidence {label!r} (expected 高/中/低)")
            continue
        counts[label] += 1
        corrected = cells[2]
        evidence = " ".join(cells[4:])
        if label == "高" and "〔" in corrected:
            report.error(f"{path}:{line_no}: high confidence row contains a 〔補/存疑〕 marker")
        if label == "高" and any(word in evidence for word in UNCERTAIN_WORDS):
            report.error(f"{path}:{line_no}: high confidence row admits uncertainty in evidence column")
    if counts["高"] + counts["中"] + counts["低"]:
        print(
            f"confidence rows: {sum(counts.values())} "
            f"(高 {counts['高']} / 中 {counts['中']} / 低 {counts['低']})"
        )


def check_suspects(path: Path, report: Report, suspects: list[str]) -> None:
    if not suspects:
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    for line_no, line in enumerate(lines, start=1):
        if not TIME_ROW_RE.match(line):
            continue
        cells = split_cells(line)
        if len(cells) < 3:
            continue
        corrected = cells[2]
        for token in suspects:
            if token and token in corrected:
                report.warn(f"{path}:{line_no}: suspect ASR fragment {token!r} in corrected text")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check corrected transcript artifacts")
    parser.add_argument("files", nargs="+", help="Markdown files to check")
    parser.add_argument(
        "--suspect",
        default="",
        help="comma separated fragments that should never appear in the corrected column (optional)",
    )
    args = parser.parse_args()
    suspects = [item.strip() for item in args.suspect.split(",") if item.strip()]

    report = Report()
    for name in args.files:
        path = Path(name)
        if not path.is_file():
            report.error(f"missing file: {path}")
            continue
        check_links(path, report)
        check_tables(path, report)
        check_confidence(path, report)
        check_suspects(path, report, suspects)
        report.checked += 1

    print(f"checked {report.checked} artifact(s) / {len(args.files)} input file(s)")
    for warning in report.warnings:
        print(f"WARN  {warning}")
    for error in report.errors:
        print(f"ERROR {error}")
    if report.errors:
        raise SystemExit(1)
    print("OK")


if __name__ == "__main__":
    main()
