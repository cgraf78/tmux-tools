#!/usr/bin/env python3
"""Fail on any mention of a tmux release older than the supported floor.

The floor is tmux_minimum in the tools' tmux_supported block. Text is read
with comment and roff markers removed and its lines joined, so a mention
wrapped across lines still reads as one. A mention that has to stay names
its file and words in ALLOWED.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
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
    """Each "tmux <version>" or "older than <version>" below MINIMUM,
    case-insensitive. After "tmux", a - or space and then >=, before or v
    may come between the two. "older than" catches the floor stated without
    the word tmux, which would go stale silently after a bump."""
    lower = text.lower()
    found = []
    for key in ("tmux", "older than"):
        found += _mentions_after(text, lower, key, minimum)
    return found


def _mentions_after(text: str, lower: str, key: str, minimum: tuple[int, int]) -> list[str]:
    found = []
    start = 0
    while (at := lower.find(key, start)) >= 0:
        start = at + len(key)
        rest = lower[at + len(key) :]
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


def is_checkout() -> bool:
    """Whether ROOT is the top of a Git checkout. A tree outside Git (a
    release tarball, or one unpacked inside another repo) has no tracked
    files to scan."""
    try:
        top = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    path = top.stdout.decode(errors="replace").strip()
    return top.returncode == 0 and bool(path) and pathlib.Path(path).resolve() == ROOT


def files() -> list[pathlib.Path]:
    """Every tracked file, so no directory can drop out of the scan."""
    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=False
    )
    if listed.returncode != 0:
        raise SystemExit(f"FAIL: git ls-files: {listed.stderr.decode(errors='replace')}")
    names = [name for name in listed.stdout.decode().split("\0") if name]
    if "AGENTS.md" not in names:
        raise SystemExit("FAIL: git ls-files lists no AGENTS.md")
    return [ROOT / name for name in names]


def main() -> int:
    floor = tmux_version.MINIMUM
    major, minor = floor
    if minor == 0:
        raise SystemExit(f"FAIL: the lint's samples cannot express a floor of {major}.0")
    # Samples built from the floor, so they stay true after a bump.
    below, at, above = (
        f"{major}.{minor - 1}",
        f"{major}.{minor}",
        f"{major}.{minor + 1}",
    )
    older = f"{major - 1}.0"
    assert old_mentions(f"needs tmux\n# {below}a here", floor) == []
    assert len(old_mentions(joined(f"needs tmux\n# {below}a here"), floor)) == 1
    assert len(old_mentions(joined(f".B tmux\n{below} or newer"), floor)) == 1
    assert (
        len(old_mentions(f"tmux before {older} and tmux >= {below} and tmux-{older}", floor)) == 3
    )
    assert len(old_mentions(joined(f"The server is older\nthan {below}."), floor)) == 1
    assert old_mentions(f"older than {at}, older than tmux {at}", floor) == []
    assert (
        old_mentions(f"tmux {at}a, tmux {major}.{minor + 7}, tmux v{above}, Bash 3.2", floor) == []
    )
    offenders = []
    if not is_checkout():
        # CI always has a checkout, so the lint can never be skipped there.
        if os.environ.get("GITHUB_ACTIONS"):
            raise SystemExit("FAIL: not a Git checkout under GitHub Actions")
        print("note: not a Git checkout, so the old-tmux lint is skipped")
        return 0
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
