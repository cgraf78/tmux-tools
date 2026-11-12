#!/usr/bin/env python3
"""Run tmux-command-palette against an isolated real tmux server and client."""

from __future__ import annotations

import os
import pty
import re
import select
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PALETTE = ROOT / "bin/tmux-command-palette"
TMUX = shutil.which("tmux")
if TMUX is None:
    if os.environ.get("TMUX_TOOLS_REQUIRE_TMUX") == "1":
        raise SystemExit("FAIL: real tmux is required")
    raise SystemExit("SKIP: real tmux unavailable")

VERSION = subprocess.run([TMUX, "-V"], text=True, capture_output=True, check=False).stdout
MATCH = re.search(r"(\d+)\.(\d+)", VERSION)
# send-keys -K, which types the chosen key for the client, arrived in tmux 3.4.
TYPES_FOR_CLIENT = MATCH is not None and (int(MATCH[1]), int(MATCH[2])) >= (3, 4)

# The popup runs this stand-in instead of fzf. It records its arguments and
# the entries it was offered, then prints the first entry containing
# $PALETTE_PICK, or exits 130 (fzf's cancel status) when that is empty.
STUB_FZF = """#!/usr/bin/env sh
printf '%s\\n' "$@" >"$PALETTE_LOG.args"
cat >"$PALETTE_LOG.offered"
[ -n "$PALETTE_PICK" ] || exit 130
grep -F -m 1 -- "$PALETTE_PICK" "$PALETTE_LOG.offered" || exit 1
"""

master: int | None = None
screen = bytearray()


def pump(duration: float) -> None:
    """Keep the client's terminal output, so tmux never blocks writing it."""
    deadline = time.monotonic() + duration
    while master is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        ready, _, _ = select.select([master], [], [], remaining)
        if ready:
            try:
                screen.extend(os.read(master, 65536))
            except OSError:
                return


def poll(label: str, read: Callable[[], str], match: Callable[[str], bool]) -> str:
    """Wait for an observable state with a bounded diagnostic timeout."""
    deadline = time.monotonic() + 5
    last = None
    while time.monotonic() < deadline:
        last = read()
        if match(last):
            return last
        pump(0.05)
    raise AssertionError(f"{label}: timed out; last state: {last!r:.600}")


with tempfile.TemporaryDirectory(prefix="tcp-client-") as directory:
    root = Path(directory)
    socket = str(root / "socket")
    bindir = root / "bin"
    bindir.mkdir()
    (bindir / "tmux-command-palette").symlink_to(PALETTE)
    fzf = bindir / "fzf"
    fzf.write_text(STUB_FZF)
    fzf.chmod(0o700)
    record = root / "record"
    log = root / "fzf"
    # A minimal environment: no TMUX, and no caller shell startup hooks
    # (BASH_ENV) that could add commands such as fzf back.
    env = {
        "HOME": str(root),
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "TERM": "xterm-256color",
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    }
    for variable in ("LANG", "LC_ALL", "LC_CTYPE"):
        if variable in os.environ:
            env[variable] = os.environ[variable]

    def tmux(*args: str) -> str:
        """Query or mutate only the private test server."""
        result = subprocess.run(
            [TMUX, "-S", socket, *args],
            check=False,
            text=True,
            capture_output=True,
            timeout=5,
            env=env,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, result.args, output=result.stdout, stderr=result.stderr
            )
        return result.stdout.strip()

    def recorder(label: str) -> str:
        """A run-shell command that appends label and the pane it ran for."""
        return f"run-shell \"echo {label} #{{pane_id}} >>'{record}'\""

    client_pid = None
    try:
        tmux("-f", "/dev/null", "new-session", "-d", "-s", "palette", "-x", "120", "-y", "40")
        tmux("set-environment", "-g", "PATH", env["PATH"])
        tmux("set-environment", "-g", "PALETTE_LOG", str(log))
        first = tmux("display-message", "-p", "#{pane_id}")
        second = tmux("split-window", "-h", "-P", "-F", "#{pane_id}", "sleep 600")
        if not first or not second:
            raise AssertionError(f"pane ids are empty: {first!r} {second!r}")
        tmux("respawn-pane", "-k", "-t", first, "sleep 600")
        tmux("select-pane", "-t", second)
        # A clean slate: only the bindings below carry notes.
        tmux("unbind-key", "-a", "-T", "prefix")
        tmux("unbind-key", "-a", "-T", "root")
        tmux("bind-key", "-N", "Record the pane", "r", recorder("r"))
        tmux("bind-key", "-N", "Record from a semicolon", "\\;", recorder("semi"))
        tmux("bind-key", "-N", "Record from Meta-semicolon", "M-\\;", recorder("msemi"))
        tmux("bind-key", "-N", "Record from the root table", "-n", "F7", recorder("root"))
        tmux(
            "bind-key",
            "-N",
            "Confirm, then record",
            "y",
            "confirm-before",
            "-p",
            "go? (y/n)",
            recorder("confirmed"),
        )
        # Left out: digit window selection, mouse keys, a second key with the
        # same note, and keys without a note.
        tmux("bind-key", "-N", "Select window 1", "1", "select-window", "-t", ":=1")
        tmux("bind-key", "-N", "Open a menu", "-n", "MouseDown3Pane", "display-message", "x")
        tmux("bind-key", "-N", "Scroll", "-n", "C-M-WheelUpPane", "display-message", "x")
        tmux("bind-key", "-N", "Record the pane", "-n", "F8", "display-message", "duplicate")
        tmux("bind-key", "-n", "F9", "display-message", "no note")
        # A tab in a note would split the entry's fields.
        tmux("bind-key", "-N", "zebra\tlast", "z", "display-message", "z")
        tmux("bind-key", "-n", "F5", "run-shell", "tmux-command-palette --client #{q:client_name}")

        listing = subprocess.run(
            [str(PALETTE), "--list"],
            check=True,
            text=True,
            capture_output=True,
            timeout=5,
            env=dict(env, TMUX=f"{socket},1,0"),
        ).stdout.splitlines()
        expected = [
            ("Confirm, then record", "prefix y", "prefix", "y"),
            ("Record from a semicolon", "prefix ;", "prefix", ";"),
            ("Record from Meta-semicolon", "prefix M-;", "prefix", "M-;"),
            ("Record from the root table", "F7", "root", "F7"),
            ("Record the pane", "prefix r", "prefix", "r"),
            ("zebra last", "prefix z", "prefix", "z"),
        ]
        width = max(len(note) for note, *_ in expected)
        assert listing == [
            f"{note.ljust(width)}   {shown}\t{table}\t{key}" for note, shown, table, key in expected
        ], listing
        print("PASS: --list offers noted keys by note, without mouse, digits or duplicates")

        bad = subprocess.run(
            [str(PALETTE)], check=False, text=True, capture_output=True, timeout=5, env=env
        )
        assert bad.returncode == 64, bad
        print("PASS: a missing client is a usage error")

        client_pid, master = pty.fork()
        if client_pid == 0:
            os.execvpe(TMUX, [TMUX, "-S", socket, "attach-session", "-t", "palette"], env)
        name = poll("client attach", lambda: tmux("list-clients", "-F", "#{client_name}"), bool)

        def recorded() -> str:
            return record.read_text() if record.exists() else ""

        def messages() -> str:
            return tmux("show-messages", "-t", name)

        def pick(text: str) -> None:
            """Open the palette with F5 and have the stand-in pick text."""
            for suffix in (".offered", ".args"):
                Path(f"{log}{suffix}").unlink(missing_ok=True)
            tmux("set-environment", "-g", "PALETTE_PICK", text)
            os.write(master, b"\x1b[15~")
            poll(
                "the popup offers the entries",
                lambda: str(Path(f"{log}.offered").exists()),
                lambda value: value == "True",
            )

        def asked() -> int:
            return messages().count("to run it")

        def press_if_asked(key: bytes, before: int) -> None:
            """Before tmux 3.4 the palette asks for the last key; press it.

            The message log keeps earlier requests, so wait for a new one.
            """
            if not TYPES_FOR_CLIENT:
                poll(
                    "the palette names the key to press",
                    lambda: str(asked()),
                    lambda v: int(v) > before,
                )
                os.write(master, key)

        def run_pick(text: str, key: bytes, expected_line: str) -> None:
            before = recorded()
            count = asked()
            pick(text)
            press_if_asked(key, count)
            poll(f"{text} runs", recorded, lambda value: value == before + expected_line + "\n")

        run_pick("Record the pane", b"r", f"r {second}")
        args = Path(f"{log}.args").read_text().splitlines()
        assert "--with-nth=1" in args, args
        print("PASS: a prefix pick runs on the pane the palette came from")

        run_pick("Record from the root table", b"\x1b[18~", f"root {second}")
        print("PASS: a root pick runs on the pane the palette came from")

        run_pick("Record from a semicolon", b";", f"semi {second}")
        run_pick("Record from Meta-semicolon", b"\x1b;", f"msemi {second}")
        print("PASS: keys ending in ; replay")

        # The prompt must open over the pane once the popup has closed: an
        # answer typed into a still-open popup would never reach it.
        before = recorded()
        count = asked()
        pick("Confirm, then record")
        press_if_asked(b"y", count)
        poll("the prompt is drawn", lambda: str(b"go? (y/n)" in screen), lambda v: v == "True")
        os.write(master, b"y")
        poll(
            "the confirmed binding runs",
            recorded,
            lambda value: value == before + f"confirmed {second}\n",
        )
        print("PASS: a picked binding's prompt opens after the popup closes")

        before = recorded()
        pick("")
        pump(0.5)
        assert recorded() == before
        assert tmux("display-message", "-p", "-t", second, "#{pane_in_mode}") == "0"
        assert tmux("list-clients", "-F", "#{client_key_table}") == "root"
        print("PASS: cancelling runs nothing and leaves no error view")

        # Without fzf the palette says so instead of failing.
        nofzf = root / "nofzf"
        nofzf.mkdir()
        for tool in ("bash", "env", "sh"):
            found = shutil.which(tool)
            assert found, tool
            (nofzf / tool).symlink_to(found)
        (nofzf / "tmux").symlink_to(TMUX)
        (nofzf / "tmux-command-palette").symlink_to(PALETTE)
        tmux("set-environment", "-g", "PATH", str(nofzf))
        os.write(master, b"\x1b[15~")
        poll("the missing fzf is reported", messages, lambda v: "needs fzf" in v)
        print("PASS: a missing fzf is reported as a message")
    finally:
        try:
            tmux("kill-server")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        if client_pid:
            try:
                os.kill(client_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(client_pid, 0)
            except ChildProcessError:
                pass
        if master is not None:
            os.close(master)
