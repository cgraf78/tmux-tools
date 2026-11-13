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
    calls = root / "termnav-calls"
    bindir = root / "bin"
    bindir.mkdir()
    termnav = bindir / "termnav"
    termnav.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$@" >"$STATE_NATIVE_ARGS.tmp"\n'
        'mv "$STATE_NATIVE_ARGS.tmp" "$STATE_NATIVE_ARGS"\n'
        'printf "%s\\n" "$*" >>"$STATE_NATIVE_CALLS"\n'
    )
    termnav.chmod(0o700)
    # The server finds this checkout's term-pane-state first, so marks that
    # republish run the code under test.
    env = dict(
        os.environ,
        PATH=f"{bindir}:{ROOT / 'bin'}:{os.environ['PATH']}",
        STATE_NATIVE_ARGS=str(capture),
        STATE_NATIVE_CALLS=str(calls),
        TERM="xterm-256color",
    )

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

    client_pid = None
    master = None
    control = None
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
            lambda: tmux("list-clients", "-F", "#{client_flags}"),
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
        assert tmux("list-clients", "-F", "#{pane_id}") == first
        print("PASS: focused pane clears only its own local attention")

        os.write(master, b"\x1b[O")
        poll(
            "client unfocus",
            lambda: tmux("list-clients", "-F", "#{client_flags}"),
            lambda value: "focused" not in value,
        )
        unfocused = publish()
        assert unfocused["--pending"] == "2", unfocused
        assert unfocused["--failed"] == "2", unfocused
        print("PASS: unfocused client retains both local attention marks")

        os.write(master, b"\x1b[I")
        poll(
            "client refocus",
            lambda: tmux("list-clients", "-F", "#{client_flags}"),
            lambda value: "focused" in value,
        )
        tmux("split-window", "-h", "-t", "attention:0", "sleep 60")
        poll(
            "pane switch",
            lambda: tmux("list-clients", "-F", "#{pane_id}"),
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

        # A config older than @pane_waiting reports no waiting attention.
        tmux("new-window", "-d", "-t", "attention:", "sleep 60")
        waiting = tmux("display-message", "-p", "-t", "attention:2", "#{pane_id}")
        tmux("set-option", "-p", "-t", waiting, "@term_notify_pending", "waiting")
        tmux("set-option", "-p", "-t", waiting, "@term_busy", "1")
        tmux("new-window", "-d", "-t", "attention:", "sleep 60")
        busy = tmux("display-message", "-p", "-t", "attention:3", "#{pane_id}")
        tmux("set-option", "-p", "-t", busy, "@term_busy", "1")
        tmux("set-option", "-g", "@pane_busy", "#{@term_busy}")
        old_config = publish()
        assert "--waiting" not in old_config, old_config
        assert old_config["--pending"] == "2", old_config
        assert old_config["--working"] == "1", old_config
        print("PASS: a config without @pane_waiting reports no waiting attention")

        tmux(
            "set-option",
            "-g",
            "@pane_waiting",
            "#{&&:#{E:@pane_pending},#{==:#{@term_notify_pending},waiting}}",
        )
        effective = publish()
        assert effective["--waiting"] == "1", effective
        assert effective["--pending"] == "2", effective
        assert effective["--failed"] == "1", effective
        assert effective["--working"] == "1", effective
        print("PASS: a waiting pane counts as waiting, not working")

        def native_args() -> dict[str, str]:
            try:
                args = capture.read_text().splitlines()
            except FileNotFoundError:
                return {}
            return {args[index]: args[index + 1] for index in range(0, len(args) - 1, 2)}

        # Event hooks and marks publish a whole session at once. A control
        # client attached to the same session is never a publication target.
        control = subprocess.Popen(
            [TMUX, "-S", socket, "-C", "attach-session", "-t", "attention"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        poll(
            "control client attach",
            lambda: tmux("list-clients", "-F", "#{client_control_mode}"),
            lambda value: sorted(value.split()) == ["0", "1"],
        )
        calls.unlink(missing_ok=True)
        subprocess.run(
            [str(ROOT / "bin/term-pane-state"), "--socket", socket, "--session", session],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )
        assert len(calls.read_text().splitlines()) == 1, calls.read_text()
        session_wide = native_args()
        assert session_wide["--client-name"] == name, session_wide
        assert session_wide["--client-pid"] == pid, session_wide
        assert session_wide["--client-created"] == created, session_wide
        for flag in ("--working", "--pending", "--failed", "--waiting"):
            assert session_wide.get(flag) == effective.get(flag), (flag, session_wide, effective)
        print("PASS: a session publish reaches each terminal client with its own focus")

        # A mark change republishes from the server in the background, without
        # waiting for a status job: the selected pane's own new attention is
        # hidden from this focused client, a background pane's is not.
        tmux("set-option", "-g", "@term_pane_state_publish", "on")
        background = tmux("display-message", "-p", "-t", "attention:3", "#{pane_id}")
        mark_env = dict(env, TMUX=f"{socket},0,0", TMUX_PANE=background, TERM_PROGRAM="tmux")
        capture.unlink(missing_ok=True)
        subprocess.run(
            [str(ROOT / "bin/term-pane-mark"), "set", "pending", "--kind", "waiting"],
            check=True,
            timeout=5,
            env=mark_env,
        )
        marked = poll(
            "republish after a mark",
            lambda: json.dumps(native_args()),
            lambda value: json.loads(value).get("--waiting") == "2",
        )
        assert json.loads(marked)["--pending"] == "3", marked
        capture.unlink(missing_ok=True)
        subprocess.run(
            [str(ROOT / "bin/term-pane-mark"), "clear", "pending", "--if", "waiting"],
            check=True,
            timeout=5,
            env=mark_env,
        )
        poll(
            "republish after a clear",
            lambda: json.dumps(native_args()),
            lambda value: json.loads(value).get("--pending") == "2",
        )
        modes = tmux("list-panes", "-a", "-F", "#{pane_mode}")
        assert modes.strip() == "", modes
        print("PASS: a mark change republishes at once and prints into no pane")
    finally:
        if control is not None:
            control.kill()
            control.wait()
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
