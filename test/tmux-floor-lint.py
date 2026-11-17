#!/usr/bin/env python3
"""Fail on any mention of a tmux release older than the supported floor.

The floor is tmux_minimum in the tools' tmux_supported block. Text is read
with comment and roff markers removed and its lines joined, so a mention
wrapped across lines still reads as one. A mention that has to stay names
its file and words in ALLOWED.
"""

from __future__ import annotations

import pathlib
import sys

import tmux_version

ROOT = pathlib.Path(__file__).resolve().parent.parent
SELF = pathlib.Path(__file__).resolve().relative_to(ROOT).as_posix()

# (file, words): a mention in that file containing those words is history,
# not a claim about what is supported.
ALLOWED = [
    ("bin/tmux-agent-picker", "tmux 3.2a, older than any"),
    ("man/man1/tmux-agent-picker.1", "tmux 3.2a, older than any"),
]

SCANNED = ["README.md", "AGENTS.md", "install.sh", "bin", "man", "support", "test", ".github"]


def joined(text: str) -> str:
    """Each line without its leading space and comment or roff markers, joined."""
    lines = []
    for line in text.splitlines():
        line = line.lstrip().lstrip("/#*!;->")
        if line.startswith("."):
            line = line[1:].lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
        lines.append(line.replace("\\-", "-").strip())
    return " ".join(lines)


def old_mentions(text: str, minimum: tuple[int, int]) -> list[str]:
    """Each "tmux <version>" below MINIMUM, case-insensitive, allowing a - or
    space and then >=, before or v between the two."""
    lower = text.lower()
    found = []
    start = 0
    while (at := lower.find("tmux", start)) >= 0:
        start = at + 4
        rest = lower[at + 4 :]
        if rest[:1] in (" ", "-"):
            rest = rest[1:]
        for word in (">= ", ">=", "before ", "v"):
            if rest.startswith(word):
                rest = rest[len(word) :]
                break
        if not rest[:1].isdigit():
            continue
        release = tmux_version.parse(rest)
        if release is not None and release < minimum:
            found.append(text[at : at + 40])
    return found


def files() -> list[pathlib.Path]:
    found = []
    for name in SCANNED:
        path = ROOT / name
        if path.is_dir():
            found.extend(p for p in sorted(path.rglob("*")) if p.is_file())
        elif path.is_file():
            found.append(path)
    return [p for p in found if "__pycache__" not in p.parts]


def main() -> int:
    floor = tmux_version.MINIMUM
    assert old_mentions("needs tmux\n# 3.2a here", floor) == []
    assert len(old_mentions(joined("needs tmux\n# 3.2a here"), floor)) == 1
    assert len(old_mentions(joined(".B tmux\n3.2 or newer"), floor)) == 1
    assert len(old_mentions("tmux before 3.1 and tmux >= 3.2 and tmux-3.0", floor)) == 3
    assert old_mentions("tmux 3.3a, tmux 3.10, tmux v3.4, Bash 3.2", floor) == []
    offenders = []
    for path in files():
        relative = path.relative_to(ROOT).as_posix()
        if relative == SELF:
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for mention in old_mentions(joined(text), floor):
            if not any(relative == file and words in mention for file, words in ALLOWED):
                offenders.append(f"{relative}: {mention}")
    if offenders:
        for offender in offenders:
            print(f"FAIL: names a tmux older than the floor: {offender}", file=sys.stderr)
        return 1
    print(f"ok - nothing names a tmux older than {floor[0]}.{floor[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
