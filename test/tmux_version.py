"""The tmux version rule the test clients share.

master and OpenBSD's base tmux (openbsd-*) are newer than any release;
otherwise one leading next- is ignored and the leading MAJOR.MINOR
compares, so 3.3a, 3.3-rc and next-3.3 all read as 3.3. A version this
cannot read counts as newest, as the tools' own tmux_supported does.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess

_RELEASE = re.compile(r"(\d+)\.(\d+)")


def _minimum() -> tuple[int, int]:
    """The floor, read from the tools' tmux_supported block."""
    picker = pathlib.Path(__file__).resolve().parent.parent / "bin" / "tmux-agent-picker"
    match = re.search(r"^tmux_minimum=(\d+)\.(\d+)$", picker.read_text(), re.MULTILINE)
    if match is None:
        raise RuntimeError(f"{picker} sets no tmux_minimum")
    return int(match[1]), int(match[2])


MINIMUM = _minimum()


def parse(version: str) -> tuple[int, int] | None:
    """Return (major, minor), or None for a build newer than any release."""
    version = version.strip()
    version = version.removeprefix("tmux ")
    if version == "master" or version.startswith("openbsd-"):
        return None
    match = _RELEASE.match(version.removeprefix("next-"))
    return None if match is None else (int(match[1]), int(match[2]))


def at_least(version: str, minimum: tuple[int, int]) -> bool:
    """Whether VERSION is MINIMUM or newer; unreleased and unknown builds are."""
    release = parse(version)
    return release is None or release >= minimum


def require_tmux() -> tuple[str, str]:
    """Return the tmux to test and its tmux -V, or skip without a supported one.

    test/run settles this once for every suite; this repeats it for a client
    run on its own. Under TMUX_TOOLS_REQUIRE_TMUX=1 the skip is a failure.
    """
    tmux = shutil.which("tmux")
    reason = "real tmux unavailable"
    version = ""
    if tmux is not None:
        version = subprocess.run(
            [tmux, "-V"], text=True, capture_output=True, check=False
        ).stdout.strip()
        if at_least(version, MINIMUM):
            return tmux, version
        reason = f"{version} is older than tmux {MINIMUM[0]}.{MINIMUM[1]}"
    if os.environ.get("TMUX_TOOLS_REQUIRE_TMUX") == "1":
        raise SystemExit(f"FAIL: a supported tmux is required ({reason})")
    print(f"SKIP: {reason}")
    raise SystemExit(0)


# The canonical vectors, shared verbatim by every repository that checks the
# tmux floor: each version and how it reads (MAJOR.MINOR, newest or
# unknown). Whether each is supported follows from the floor.
VECTORS = [
    ("1.8", "1.8"),
    ("2.9a", "2.9"),
    ("next-2.9", "2.9"),
    ("3.0", "3.0"),
    ("3.1c", "3.1"),
    ("3.2", "3.2"),
    ("3.2a", "3.2"),
    ("3.2-rc3", "3.2"),
    ("next-3.2", "3.2"),
    ("next-3.2-rc", "3.2"),
    ("3.3", "3.3"),
    ("3.3a", "3.3"),
    ("3.3-rc", "3.3"),
    ("next-3.3", "3.3"),
    ("3.4", "3.4"),
    ("3.10", "3.10"),
    ("next-3.10", "3.10"),
    ("master", "newest"),
    ("openbsd-7.6", "newest"),
    ("openbsd-7.6-current", "newest"),
    ("3.x", "unknown"),
    ("3.", "unknown"),
    ("foo-2.9", "unknown"),
    ("", "unknown"),
]


def floor_rows(minimum: tuple[int, int]) -> list[tuple[str, str]]:
    """Rows at the floor's edge, so a floor bump is tested where it bites."""
    major, minor = minimum
    if minor == 0:
        raise ValueError(f"the floor-edge rows cannot express a floor of {major}.0")
    below = f"{major}.{minor - 1}"
    floor = f"{major}.{minor}"
    above = f"{major}.{minor + 1}"
    # The next major's first release, which a comparison of the minor alone
    # would refuse.
    next_major = f"{major + 1}.0"
    return [
        (below, below),
        (f"{below}a", below),
        (f"{below}-rc", below),
        (f"next-{below}", below),
        (floor, floor),
        (above, above),
        (next_major, next_major),
    ]


if __name__ == "__main__":
    rows = VECTORS + floor_rows(MINIMUM)
    for version, reads in rows:
        release = parse(version)
        shown = "newest" if release is None else f"{release[0]}.{release[1]}"
        assert shown == ("newest" if reads == "unknown" else reads), (version, shown)
        supported = reads in ("newest", "unknown") or (
            tuple(int(part) for part in reads.split(".")) >= MINIMUM
        )
        assert at_least(version, MINIMUM) is supported, version
        assert at_least(f"tmux {version}", MINIMUM) is supported, version
    print(f"ok - tmux_version.py reads all {len(rows)} vectors")
