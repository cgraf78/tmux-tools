#!/usr/bin/env python3
"""Smoke-test tmux-agent-picker with the real fzf in a private tmux popup."""

from __future__ import annotations

import os
import pty
import re
import select
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import tmux_version

ROOT = Path(__file__).resolve().parent.parent
PICKER = ROOT / "bin/tmux-agent-picker"
TMUX, _ = tmux_version.require_tmux()
FZF = shutil.which("fzf")
if FZF is None:
    if os.environ.get("TMUX_TOOLS_REQUIRE_FZF") == "1":
        raise SystemExit("FAIL: real fzf is required")
    print("SKIP: real fzf unavailable")
    raise SystemExit(0)

# The fixture config: the man page's example predicates and acknowledgement
# hooks.
CONFIG = ROOT / "test/tmux-agent-picker.conf"


def copy_bash(target: Path) -> None:
    """Copy a bash that runs from TARGET, so it reports TARGET's name.

    Only the bytes and mode are copied: shutil.copy2 also copies file flags,
    which macOS refuses for its system-protected /bin/bash. Each bash on PATH
    is tried in turn, in case a copy cannot run where it lands.
    """
    candidates = [
        str(Path(directory) / "bash")
        for directory in os.environ.get("PATH", "").split(os.pathsep)
        if directory and os.access(Path(directory) / "bash", os.X_OK)
    ]
    for source in dict.fromkeys(candidates + ["/bin/bash"]):
        if not os.access(source, os.X_OK):
            continue
        shutil.copyfile(source, target)
        target.chmod(0o755)
        try:
            ran = subprocess.run([str(target), "-c", ":"], timeout=10, check=False)
        except OSError:
            continue
        if ran.returncode == 0:
            return
    raise SystemExit(f"FAIL: no copy of bash runs as a stand-in agent from {target.parent}")


CSI = re.compile(
    rb"\x1b\[[0-9;?:<=>]*[ -/]*[@-~]|\x1b[()][0-9A-Za-z]|\x1b[=>78]|\x1b\][^\x07]*\x07"
)
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


def poll(label: str, read: Callable[[], object], match: Callable[[object], bool]) -> object:
    """Wait for an observable state with a bounded diagnostic timeout."""
    deadline = time.monotonic() + 8
    last = None
    while time.monotonic() < deadline:
        last = read()
        if match(last):
            return last
        pump(0.05)
    raise AssertionError(f"{label}: timed out; last state: {last!r:.1500}")


def text(since: int = 0) -> str:
    """The client's output since an offset, without escape sequences."""
    return CSI.sub(b"", bytes(screen[since:])).decode("utf-8", "replace")


version = subprocess.run([FZF, "--version"], text=True, capture_output=True, check=False)
print(f"note: fzf {version.stdout.strip() or version.stderr.strip()}")

with tempfile.TemporaryDirectory(prefix="tap-fzf-") as directory:
    root = Path(directory)
    socket = str(root / "socket")
    bindir = root / "bin"
    bindir.mkdir()
    (bindir / "tmux-agent-picker").symlink_to(PICKER)
    agent = root / "agents" / "codex"
    agent.parent.mkdir()
    copy_bash(agent)
    flag = root / "refresh"
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in ("TMUX", "TMUX_PANE", "BASH_ENV", "ENV", "ZDOTDIR", "FZF_DEFAULT_OPTS")
    }
    env.update(
        HOME=str(root),
        PATH=f"{bindir}:{os.environ['PATH']}",
        SHELL=shutil.which("sh") or "/bin/sh",
        TERM="xterm-256color",
    )
    # fzf draws the dots only in a UTF-8 locale.
    if "UTF-8" not in (env.get("LC_ALL") or env.get("LC_CTYPE") or env.get("LANG") or "").upper():
        env["LC_ALL"] = "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"

    def tmux(*args: str) -> str:
        """Query or mutate only the private test server."""
        result = subprocess.run(
            [TMUX, "-S", socket, *args],
            check=True,
            text=True,
            capture_output=True,
            timeout=5,
            env=env,
            cwd=root,
        )
        return result.stdout.strip()

    def agent_session(name: str, script: str) -> str:
        pane = tmux(
            "new-session",
            "-d",
            "-s",
            name,
            "-P",
            "-F",
            "#{pane_id}",
            # dash and busybox sh do not exec a -c string's last command.
            "exec " + shlex.join([str(agent), "-c", script + "; sleep 600; :"]),
        )
        assert re.fullmatch(r"%[0-9]+", pane), pane
        return pane

    client_pid = None
    try:
        tmux(
            "-f",
            str(CONFIG),
            "new-session",
            "-d",
            "-s",
            "home",
            "-x",
            "150",
            "-y",
            "45",
            "sleep 600",
        )
        tmux("set-environment", "-g", "PATH", env["PATH"])
        tmux(
            "bind-key",
            "-n",
            "F5",
            "run-shell",
            "tmux-agent-picker --socket #{q:socket_path} --client #{q:client_name}",
        )
        if "LC_ALL" in env:
            tmux("set-environment", "-g", "LC_ALL", env["LC_ALL"])
        first = agent_session("first", "echo FIRST-MARKER")
        second = agent_session(
            "second",
            f"echo SECOND-MARKER; while [ ! -e {shlex.quote(str(flag))} ]; do sleep 0.05; done;"
            " echo REFRESHED-MARKER",
        )
        for pane in (first, second):
            poll(
                "the stand-in agent runs as codex",
                lambda p=pane: tmux("display-message", "-p", "-t", p, "#{pane_current_command}"),
                lambda v: v == "codex",
            )
        tmux("set-option", "-p", "-t", first, "@term_notify_pending", "waiting")
        tmux("set-option", "-p", "-t", second, "@term_notify_pending", "waiting")
        for pane, marker in ((first, "FIRST-MARKER"), (second, "SECOND-MARKER")):
            poll(
                f"{marker} printed",
                lambda p=pane: tmux("capture-pane", "-p", "-t", p),
                lambda v, m=marker: m in str(v),
            )

        client_pid, master = pty.fork()
        if client_pid == 0:
            os.execvpe(TMUX, [TMUX, "-u", "-S", socket, "attach-session", "-t", "home"], env)
        name = poll("client attach", lambda: tmux("list-clients", "-F", "#{client_name}"), bool)

        # The rows render with ANSI dots and without their id fields, and the
        # preview shows the first row's pane.
        start = len(screen)
        os.write(master, b"\x1b[15~")
        poll(
            "the popup draws the rows",
            lambda: text(start),
            lambda v: "Agents>" in str(v) and "second:" in str(v),
        )
        poll(
            "the preview shows the first pane",
            lambda: text(start),
            lambda v: "FIRST-MARKER" in str(v),
        )
        drawn = text(start)
        assert "Enter jump" in drawn, drawn
        assert re.search(r"@[0-9]+", drawn) is None, "the window ids are hidden"
        assert re.search(rb"\x1b\[[0-9;]*33m\xe2\x97\x8f", bytes(screen[start:])), "a yellow dot"
        print("PASS: the popup shows coloured rows without their ids, with a preview")

        # Moving the cursor previews the other pane: {1} reached the command.
        start = len(screen)
        os.write(master, b"\x1b[B")
        poll(
            "the preview follows the cursor",
            lambda: text(start),
            lambda v: "SECOND-MARKER" in str(v),
        )
        print("PASS: moving the cursor previews the pane under it")

        # ctrl-r reloads from this server and refreshes the preview.
        tmux("set-option", "-p", "-t", first, "@term_notify_pending", "blocked")
        flag.touch()
        poll(
            "the pane printed again",
            lambda: tmux("capture-pane", "-p", "-t", second),
            lambda v: "REFRESHED-MARKER" in str(v),
        )
        start = len(screen)
        os.write(master, b"\x12")
        poll(
            "ctrl-r refreshes the preview",
            lambda: text(start),
            lambda v: "REFRESHED-MARKER" in str(v),
        )
        poll(
            "ctrl-r reloads the rows",
            lambda: bytes(screen[start:]),
            lambda v: re.search(rb"\x1b\[[0-9;]*31m\xe2\x97\x8f", v) is not None,
        )
        print("PASS: ctrl-r reloads the rows and refreshes the preview")

        # Enter jumps to the row under the cursor: the reloaded list puts the
        # now red first pane at the top.
        os.write(master, b"\x1b[A")
        pump(0.2)
        os.write(master, b"\x1b[A")
        pump(0.2)
        os.write(master, b"\r")
        poll(
            "Enter jumps to the chosen pane",
            lambda: tmux("list-clients", "-F", "#{session_name} #{pane_id}"),
            lambda v: v == f"first {first}",
        )
        print("PASS: Enter jumps to the chosen pane")
    finally:
        try:
            subprocess.run(
                [TMUX, "-S", socket, "kill-server"], env=env, capture_output=True, timeout=5
            )
        except subprocess.TimeoutExpired:
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
