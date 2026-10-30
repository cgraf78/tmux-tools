#!/usr/bin/env python3
"""Check client focus expansion against an isolated real tmux server."""

from __future__ import annotations

import json
import os
import pty
import select
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMUX = shutil.which("tmux")
if TMUX is None:
    if os.environ.get("TMUX_TOOLS_REQUIRE_TMUX") == "1":
        raise SystemExit("FAIL: real tmux is required")
    raise SystemExit("SKIP: real tmux unavailable")


def poll(label: str, read: Callable[[], str], match: Callable[[str], bool]) -> str:
    """Wait for an observable tmux state with a bounded diagnostic timeout."""
    deadline = time.monotonic() + 5
    last = None
    while time.monotonic() < deadline:
        last = read()
        if match(last):
            return last
        time.sleep(0.05)
    raise AssertionError(f"{label}: timed out; last state: {last!r}")


with tempfile.TemporaryDirectory(prefix="tps-client-") as directory:
    root = Path(directory)
    socket = str(root / "socket")
    capture = root / "termnav-args"
    bindir = root / "bin"
    bindir.mkdir()
    termnav = bindir / "termnav"
    termnav.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >"$STATE_NATIVE_ARGS"\n')
    termnav.chmod(0o700)
    env = dict(
        os.environ,
        PATH=f"{bindir}:{os.environ['PATH']}",
        STATE_NATIVE_ARGS=str(capture),
        TERM="xterm-256color",
    )

    def tmux(*args: str) -> str:
        """Query or mutate only the private test server."""
        return subprocess.run(
            [TMUX, "-S", socket, *args],
            text=True,
            capture_output=True,
            check=True,
            timeout=5,
            env=env,
        ).stdout.strip()

    client_pid = None
    master = None
    try:
        tmux("-f", "/dev/null", "new-session", "-d", "-s", "attention", "sleep 60")
        tmux("set-option", "-g", "focus-events", "on")
        tmux(
            "set-option",
            "-g",
            "@termnav_pane_is_focused_leaf",
            "#{&&:#{pane_active},#{&&:#{m:*focused*,#{client_flags}},#{==:#{@termnav_child_focus},}}}",
        )
        tmux(
            "set-option",
            "-g",
            "@pane_pending",
            "#{&&:#{@term_notify_pending},#{!=:#{&&:#{window_active},#{E:@termnav_pane_is_focused_leaf}},1}}",
        )
        tmux(
            "set-option",
            "-g",
            "@pane_failed",
            "#{&&:#{E:@pane_pending},#{>:#{@term_notify_exit_status},0}}",
        )
        first = tmux("display-message", "-p", "-t", "attention:", "#{pane_id}")
        tmux("set-option", "-p", "-t", first, "@term_notify_pending", "1")
        tmux("set-option", "-p", "-t", first, "@term_notify_exit_status", "1")
        tmux("new-window", "-d", "-t", "attention:", "sleep 60")
        other = tmux("display-message", "-p", "-t", "attention:1", "#{pane_id}")
        tmux("set-option", "-p", "-t", other, "@term_notify_pending", "1")
        tmux("set-option", "-p", "-t", other, "@term_notify_exit_status", "1")

        client_pid, master = pty.fork()
        if client_pid == 0:
            os.execvpe(TMUX, [TMUX, "-S", socket, "attach-session", "-t", "attention"], env)

        def client() -> str:
            return tmux(
                "list-clients",
                "-F",
                "#{client_name} #{client_pid} #{client_created} #{client_flags} #{session_id}",
            )

        try:
            row = poll("client attach", client, lambda value: bool(value))
        except AssertionError as error:
            output = os.read(master, 4096) if select.select([master], [], [], 0)[0] else b""
            raise AssertionError(f"{error}; client output={output!r}") from error
        name, pid, created, _, session = row.split()
        os.write(master, b"\x1b[I")
        poll(
            "client focus",
            lambda: tmux("display-message", "-p", "-c", name, "#{client_flags}"),
            lambda value: "focused" in value,
        )

        def publish() -> dict[str, str]:
            """Run the client publisher and capture Termnav's machine arguments."""
            try:
                capture.unlink()
            except FileNotFoundError:
                pass
            subprocess.run(
                [
                    str(ROOT / "bin/term-pane-state"),
                    "--socket",
                    socket,
                    "--client",
                    name,
                    "--client-pid",
                    pid,
                    "--client-created",
                    created,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
            )
            args = capture.read_text().splitlines()
            assert len(args) % 2 == 0, args
            return {args[index]: args[index + 1] for index in range(0, len(args), 2)}

        focused = publish()
        assert focused["--pending"] == "1", focused
        assert focused["--failed"] == "1", focused
        assert tmux("display-message", "-p", "-c", name, "#{pane_id}") == first
        print("PASS: focused pane clears only its own local attention")

        os.write(master, b"\x1b[O")
        poll(
            "client unfocus",
            lambda: tmux("display-message", "-p", "-c", name, "#{client_flags}"),
            lambda value: "focused" not in value,
        )
        unfocused = publish()
        assert unfocused["--pending"] == "2", unfocused
        assert unfocused["--failed"] == "2", unfocused
        print("PASS: unfocused client retains both local attention marks")

        os.write(master, b"\x1b[I")
        poll(
            "client refocus",
            lambda: tmux("display-message", "-p", "-c", name, "#{client_flags}"),
            lambda value: "focused" in value,
        )
        tmux("split-window", "-h", "-t", "attention:0", "sleep 60")
        poll(
            "pane switch",
            lambda: tmux("display-message", "-p", "-c", name, "#{pane_id}"),
            lambda value: value != first,
        )
        switched = publish()
        assert switched["--pending"] == "2", switched
        assert switched["--failed"] == "2", switched
        tmux("select-pane", "-t", first)
        restored = publish()
        assert restored["--pending"] == "1", restored
        assert restored["--failed"] == "1", restored
        print("PASS: attention follows the client's selected pane")

        printed = subprocess.run(
            [
                str(ROOT / "bin/term-pane-state"),
                "--socket",
                socket,
                "--session",
                session,
                "--print",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        ).stdout.strip()
        # tmux versions differ on whether list-panes has implicit client focus.
        # The print form must retain the server's unmodified list-panes view.
        rows = tmux(
            "list-panes",
            "-s",
            "-t",
            session,
            "-F",
            "#{?#{E:@pane_pending},1,0} #{?#{E:@pane_failed},1,0}",
        )
        expected = [sum(int(row.split()[index]) for row in rows.splitlines()) for index in (0, 1)]
        snapshot = json.loads(printed)
        assert [snapshot["pending"], snapshot["failed"]] == expected, (snapshot, expected)
        print("PASS: print snapshot retains the server's list-panes view")
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
