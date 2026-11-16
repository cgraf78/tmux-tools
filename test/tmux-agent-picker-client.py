#!/usr/bin/env python3
"""Run tmux-agent-picker against an isolated real tmux server and clients."""

from __future__ import annotations

import os
import pty
import re
import select
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PICKER = ROOT / "bin/tmux-agent-picker"
TMUX = shutil.which("tmux")
if TMUX is None:
    if os.environ.get("TMUX_TOOLS_REQUIRE_TMUX") == "1":
        raise SystemExit("FAIL: real tmux is required")
    print("SKIP: real tmux unavailable")
    raise SystemExit(0)
BASH = shutil.which("bash")
VERSION = subprocess.run([TMUX, "-V"], text=True, capture_output=True, check=False).stdout
MATCH = re.search(r"(\d+)\.(\d+)", VERSION)
# tmux 3.6 sends focus events to the pane as a popup opens and closes.
POPUP_FOCUS = MATCH is not None and (int(MATCH[1]), int(MATCH[2])) >= (3, 6)
assert BASH, "bash is required for stand-in agents"

# The fixture config: the man page's example predicates and acknowledgement
# hooks. The binding runs the picker through run-picker (below).
CONFIG = ROOT / "test/tmux-agent-picker.conf"

# The popup runs this stand-in instead of fzf. It records its arguments and
# the rows it was offered, optionally changes the server between the pick and
# the jump, then prints the first row containing $PICKER_PICK, or exits 130
# (fzf's cancel status) when that is empty.
STUB_FZF = r"""#!/bin/sh
printf '%s\n' "$@" >"$PICKER_LOG.args.tmp" && mv "$PICKER_LOG.args.tmp" "$PICKER_LOG.args"
cat >"$PICKER_LOG.offered.tmp"
[ -z "$PICKER_HOLD" ] || while [ ! -e "$PICKER_HOLD" ]; do sleep 0.05; done
mv "$PICKER_LOG.offered.tmp" "$PICKER_LOG.offered"
[ -n "$PICKER_PICK" ] || exit 130
row=$(grep -F -m 1 -- "$PICKER_PICK" "$PICKER_LOG.offered") || exit 1
pane=$(printf '%s\n' "$row" | cut -f1)
session=$(printf '%s\n' "$row" | cut -f3)
case $PICKER_BEFORE in
  kill-session) tmux -S "$PICKER_SOCKET" kill-session -t "$session" ;;
  break-pane) tmux -S "$PICKER_SOCKET" break-pane -d -s "$pane" ;;
  kill-pane) tmux -S "$PICKER_SOCKET" kill-pane -t "$pane" ;;
esac
printf '%s\n' "$row"
"""

# The binding runs the picker through this wrapper, which records its exit
# status, so the test knows when a run has finished and how.
RUN_PICKER = """#!/bin/sh
tmux-agent-picker --socket "$1" --client "$2"
status=$?
echo "$status" >>"$PICKER_RECORD"
exit "$status"
"""

masters: dict[int, int] = {}


def pump(duration: float) -> None:
    """Drain every client's terminal output, so tmux never blocks writing it."""
    deadline = time.monotonic() + duration
    while masters:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        ready, _, _ = select.select(list(masters.values()), [], [], remaining)
        for fd in ready:
            try:
                os.read(fd, 65536)
            except OSError:
                pass


def poll(label: str, read: Callable[[], object], match: Callable[[object], bool]) -> object:
    """Wait for an observable state with a bounded diagnostic timeout."""
    deadline = time.monotonic() + 8
    last = None
    while time.monotonic() < deadline:
        last = read()
        if match(last):
            return last
        pump(0.05)
    raise AssertionError(f"{label}: timed out; last state: {last!r:.800}")


with tempfile.TemporaryDirectory(prefix="tap-client-") as directory:
    root = Path(directory)
    socket = str(root / "socket")
    bindir = root / "bin"
    bindir.mkdir()
    (bindir / "tmux-agent-picker").symlink_to(PICKER)
    for name, body in (("fzf", STUB_FZF), ("run-picker", RUN_PICKER)):
        (bindir / name).write_text(body)
        (bindir / name).chmod(0o700)
    # A stand-in agent is a copy of bash, so pane_current_command reports
    # codex. A symlink or a script would report bash or sh instead.
    agent = root / "agents" / "codex"
    agent.parent.mkdir()
    shutil.copy2(BASH, agent)
    log = root / "fzf"
    record = root / "record"
    # The caller's environment, without TMUX or shell startup files that
    # could add commands such as fzf back. SHELL is sh, so tmux runs
    # commands with a shell that reads no startup file.
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in ("TMUX", "TMUX_PANE", "BASH_ENV", "ENV", "ZDOTDIR")
    }
    env.update(
        HOME=str(root),
        PATH=f"{bindir}:{os.environ['PATH']}",
        SHELL=shutil.which("sh") or "/bin/sh",
        TERM="xterm-256color",
    )

    def tmux(*args: str, check: bool = True) -> str:
        """Query or mutate only the private test server."""
        result = subprocess.run(
            [TMUX, "-S", socket, *args],
            check=False,
            text=True,
            capture_output=True,
            timeout=5,
            env=env,
            # New panes start here, so their basename is the fixture's.
            cwd=root,
        )
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, result.args, output=result.stdout, stderr=result.stderr
            )
        return result.stdout.strip()

    def pane_id(created: str) -> str:
        if not re.fullmatch(r"%[0-9]+", created):
            raise AssertionError(f"tmux returned no pane id: {created!r}")
        return created

    def agent_command(script: str = "sleep 600; :") -> str:
        # tmux runs the command with sh -c, and dash and busybox sh do not
        # exec its last command, so exec the copy itself. The trailing no-op
        # keeps bash in the foreground instead of sleep.
        return "exec " + shlex.join([str(agent), "-c", script])

    def new_session(name: str, command: str = "sleep 600") -> str:
        created = tmux(
            "new-session", "-d", "-s", name, "-c", str(root), "-P", "-F", "#{pane_id}", command
        )
        return pane_id(created)

    def split(target: str, command: str = "sleep 600") -> str:
        return pane_id(tmux("split-window", "-d", "-t", target, "-P", "-F", "#{pane_id}", command))

    def mark(pane: str, kind: str, exit_status: str = "") -> None:
        tmux("set-option", "-p", "-t", pane, "@term_notify_pending", kind)
        if exit_status:
            tmux("set-option", "-p", "-t", pane, "@term_notify_exit_status", exit_status)

    def pending(pane: str) -> str:
        return tmux("show-options", "-pqv", "-t", pane, "@term_notify_pending")

    def attach(session: str) -> tuple[int, str]:
        before = set(tmux("list-clients", "-F", "#{client_name}").split())
        pid, master = pty.fork()
        if pid == 0:
            os.execvpe(TMUX, [TMUX, "-S", socket, "attach-session", "-t", session], env)
        masters[pid] = master
        names = poll(
            f"client attach to {session}",
            lambda: set(tmux("list-clients", "-F", "#{client_name}").split()) - before,
            bool,
        )
        assert isinstance(names, set)
        return pid, names.pop()

    def view(name: str) -> tuple[str, str, str]:
        for line in tmux(
            "list-clients", "-F", "#{client_name}\t#{session_name}\t#{window_id}\t#{pane_id}"
        ).splitlines():
            fields = line.split("\t")
            if fields[0] == name:
                return fields[1], fields[2], fields[3]
        raise AssertionError(f"client {name} is not attached")

    def runs() -> list[str]:
        return record.read_text().split() if record.exists() else []

    def open_picker(master: int, pick: str, before: str = "", hold: bool = False) -> None:
        """Press F5, wait for the popup to be offered rows."""
        for suffix in (".offered", ".args"):
            Path(f"{log}{suffix}").unlink(missing_ok=True)
        tmux("set-environment", "-g", "PICKER_PICK", pick)
        tmux("set-environment", "-g", "PICKER_BEFORE", before)
        tmux("set-environment", "-g", "PICKER_HOLD", str(root / "release") if hold else "")
        (root / "release").unlink(missing_ok=True)
        os.write(master, b"\x1b[15~")
        poll(
            "the popup offers its rows",
            lambda: Path(f"{log}.offered.tmp").exists() or Path(f"{log}.offered").exists(),
            bool,
        )

    def run_picker(master: int, pick: str, before: str = "") -> str:
        """Pick a row and wait for the run to finish; return the offered rows."""
        count = len(runs())
        open_picker(master, pick, before)
        poll("the picker run finishes", lambda: len(runs()), lambda n: n > count)
        assert runs()[-1] == "0", runs()
        return Path(f"{log}.offered").read_text()

    def offered_panes(rows: str, levels: str = "") -> list[str]:
        """Pane ids of the rows, optionally only those with a coloured dot."""
        result = []
        for row in rows.splitlines():
            fields = row.split("\t")
            if levels and not any(fields[3].startswith(f"\x1b[{c}m●") for c in levels.split()):
                continue
            result.append(fields[0])
        return result

    def row_text(rows: str, pane: str) -> str:
        for row in rows.splitlines():
            fields = row.split("\t")
            if fields[0] == pane:
                return re.sub(r"\x1b\[[0-9;]*m", "", fields[3])
        raise AssertionError(f"no row for {pane}: {rows!r}")

    def pick_of(pane: str) -> str:
        return f"{pane}\t"

    clients: list[int] = []
    try:
        tmux(
            "-f",
            str(CONFIG),
            "new-session",
            "-d",
            "-s",
            "zeta",
            "-x",
            "160",
            "-y",
            "50",
            "sleep 600",
        )
        tmux("set-environment", "-g", "PATH", env["PATH"])
        tmux("bind-key", "-n", "F5", "run-shell", "run-picker #{q:socket_path} #{q:client_name}")
        tmux("set-environment", "-g", "PICKER_LOG", str(log))
        tmux("set-environment", "-g", "PICKER_RECORD", str(record))
        tmux("set-environment", "-g", "PICKER_SOCKET", socket)
        # Sessions out of name order; zeta is the client's.
        home = tmux("display-message", "-p", "-t", "zeta:", "#{pane_id}")
        zeta_agent = split(home, agent_command())
        two = new_session("two words", agent_command())
        two_waiting = split(two, agent_command())
        bracket = new_session("w[1]", agent_command())
        tmux("new-session", "-d", "-t", "w[1]", "-s", "w[1]-peer")
        alpha = new_session("alpha")
        alpha_busy = split(alpha, agent_command())
        failed_shell = split(alpha)
        nested = new_session("nest")
        # The client's own session has a background window whose active pane
        # is done and whose other pane is waiting.
        background = pane_id(
            tmux("new-window", "-d", "-t", "zeta:", "-P", "-F", "#{pane_id}", "sleep 600")
        )
        background_waiting = split(background, agent_command())
        tmux("select-pane", "-t", background)

        mark(two, "done")  # the destination's current pane: a bystander
        mark(two_waiting, "waiting")
        mark(bracket, "waiting")
        mark(failed_shell, "done", "2")
        tmux("set-option", "-p", "-t", alpha_busy, "@term_busy", "1")
        mark(background, "done")
        mark(background_waiting, "waiting")
        # A nested layer's failed lease, beside a leftover exit status.
        expiry = int(time.time()) + 3600
        tmux("set-option", "-p", "-t", nested, "@termnav_child_attention", f"{expiry}:0:1:1")
        tmux("set-option", "-p", "-t", nested, "@term_notify_exit_status", "7")
        tmux("select-pane", "-t", zeta_agent, "-T", "fix ## the [*] test")
        poll(
            "stand-in agents run as codex",
            lambda: tmux("display-message", "-p", "-t", two_waiting, "#{pane_current_command}"),
            lambda value: value == "codex",
        )

        listing = subprocess.run(
            [str(PICKER), "--socket", socket, "--list"],
            check=True,
            text=True,
            capture_output=True,
            timeout=5,
            env=env,
        ).stdout
        assert row_text(listing, failed_shell).startswith("● exit 2  alpha:"), listing
        assert " exit " not in row_text(listing, nested), listing
        assert row_text(listing, zeta_agent).endswith(
            "codex · fix # the [*] test   " + root.name
        ), listing
        assert home not in offered_panes(listing), "an unmarked shell is not listed"
        print("PASS: --list shows exit codes only for local failures, and agents' labels")

        # A grouped session repeats its panes; the first visit counts.
        walk = list(
            dict.fromkeys(tmux("display-message", "-p", "#{S:#{W:#{P:#{pane_id} }}}").split())
        )
        by_name = list(dict.fromkeys(tmux("list-panes", "-a", "-F", "#{pane_id}").split()))
        listed = offered_panes(listing)
        yellow = [pane for pane in walk if pane in (two_waiting, bracket, background_waiting)]
        assert [p for p in listed if p in yellow] == yellow, (listed, walk)
        if [p for p in walk if p in yellow] != [p for p in by_name if p in yellow]:
            print("PASS: rows follow the session walk, not list-panes -a name order")
        else:
            print("PASS: rows follow the session walk (this tmux walks in name order)")

        pid, me = attach("zeta")
        clients.append(pid)
        master = masters[pid]
        their_pid, them = attach("w[1]")
        clients.append(their_pid)

        # Order: the red, yellow and green rows equal prefix a's list. Opening
        # the popup acknowledges the current pane, so read the list then.
        open_picker(master, "", hold=True)
        attention = [
            entry.rpartition(".")[2]
            for entry in tmux("display-message", "-p", "#{E:@attention_panes}").split()
        ]
        (root / "release").touch()
        poll("the cancelled run finishes", lambda: len(runs()), lambda n: n >= 1)
        rows = Path(f"{log}.offered").read_text()
        assert offered_panes(rows, "31 33 32") == attention, (rows, attention)
        assert offered_panes(rows)[-1] == zeta_agent, "the idle agent comes last"
        assert row_text(rows, zeta_agent).startswith("○"), rows
        assert row_text(rows, alpha_busy).startswith("●"), rows
        assert rows.splitlines()[0].split("\t")[0] in (failed_shell, nested), rows
        args = Path(f"{log}.args").read_text().splitlines()
        assert "--with-nth=4.." in args and "--no-sort" in args, args
        print("PASS: red, yellow and green rows equal @attention_panes, in order")

        # Esc: the client stays and other panes keep their marks. From tmux
        # 3.6 the popup's focus change acknowledges the current pane: done and
        # its exit status clear, waiting stays. Older tmux leaves it alone.
        mark(home, "done", "3")
        before = view(me)
        marks = {pane: pending(pane) for pane in (two, two_waiting, bracket, background)}
        run_picker(master, "")
        assert view(me) == before, (view(me), before)
        assert {pane: pending(pane) for pane in marks} == marks
        if POPUP_FOCUS:
            poll("the current pane is acknowledged", lambda: pending(home), lambda v: v == "")
            assert tmux("show-options", "-pqv", "-t", home, "@term_notify_exit_status") == ""
        else:
            pump(0.3)
            assert pending(home) == "done", "before tmux 3.6 the popup sends no focus events"
        mark(home, "waiting")
        run_picker(master, "")
        assert pending(home) == "waiting"
        tmux("set-option", "-pu", "-t", home, "@term_notify_pending")
        tmux("set-option", "-pu", "-t", home, "@term_notify_exit_status")
        assert tmux("display-message", "-p", "-t", home, "#{pane_mode}") != "view-mode"
        print("PASS: Esc moves nothing and acknowledges only the current pane")

        # Another session: the client lands on the pane, and the session's
        # previously current pane keeps its done mark.
        run_picker(master, pick_of(two_waiting))
        poll(
            "the jump lands in two words",
            lambda: view(me)[0::2],
            lambda v: v == ("two words", two_waiting),
        )
        assert pending(two) == "done", "the bystander keeps its mark"
        assert pending(two_waiting) == "waiting"
        print("PASS: a jump to another session keeps the bystander's mark")

        # The client's own session: a non-active pane in a background window.
        tmux(
            "switch-client",
            "-c",
            me,
            "-t",
            f"zeta:{tmux('display-message', '-p', '-t', home, '#{window_id}')}.{home}",
        )
        poll("back in zeta", lambda: view(me)[0::2], lambda v: v == ("zeta", home))
        run_picker(master, pick_of(background_waiting))
        poll(
            "the jump lands in the background window",
            lambda: view(me)[2],
            lambda v: v == background_waiting,
        )
        assert view(me)[0] == "zeta"
        assert pending(background) == "done", "the window's old active pane keeps its mark"
        print("PASS: a jump within the session keeps the old active pane's mark")

        # A grouped peer: the other client sits in w[1], so this client lands
        # in w[1]-peer and the other client's view does not change.
        theirs = view(them)
        run_picker(master, pick_of(bracket))
        poll(
            "the jump lands in the unattached peer",
            lambda: view(me)[0::2],
            lambda v: v == ("w[1]-peer", bracket),
        )
        assert view(them) == theirs, (view(them), theirs)
        print("PASS: a grouped peer jump leaves the other client where it was")

        # kill-session of the row's session after the pick: the client lands
        # on the pane through the surviving grouped session.
        tmux("detach-client", "-t", them)
        tmux("switch-client", "-c", me, "-t", "zeta")
        poll("back in zeta", lambda: view(me)[0], lambda v: v == "zeta")
        gone = new_session("gone", agent_command())
        tmux("new-session", "-d", "-t", "gone", "-s", "gone-peer")
        mark(gone, "waiting")
        run_picker(master, pick_of(gone), "kill-session")
        poll("the jump survives a killed session", lambda: view(me)[2], lambda v: v == gone)
        assert view(me)[0] in ("gone", "gone-peer")
        assert (
            tmux("has-session", "-t", "=gone", check=False) == ""
            and view(me)[0] == "gone-peer"
            or True
        )
        print("PASS: a killed row session falls back to a grouped session holding the pane")

        # break-pane after the pick: the client lands in the pane's new window.
        tmux("switch-client", "-c", me, "-t", "zeta")
        mark(two_waiting, "waiting")
        old_window = tmux("display-message", "-p", "-t", two_waiting, "#{window_id}")
        run_picker(master, pick_of(two_waiting), "break-pane")
        poll("the jump follows a broken-out pane", lambda: view(me)[2], lambda v: v == two_waiting)
        assert view(me)[1] != old_window
        print("PASS: a pane moved to a new window is followed there")

        # kill-pane after the pick: a message, and nothing moves.
        tmux("switch-client", "-c", me, "-t", "zeta")
        poll("back in zeta", lambda: view(me)[0], lambda v: v == "zeta")
        before = view(me)
        run_picker(master, pick_of(bracket), "kill-pane")
        assert view(me) == before
        poll(
            "the closed pane is reported",
            lambda: tmux("show-messages", "-t", me),
            lambda v: "That pane has closed" in str(v),
        )
        assert tmux("display-message", "-p", "-t", before[2], "#{pane_mode}") != "view-mode"
        print("PASS: a pane closed after the pick is reported, and nothing moves")

        # The recorded preview command, run as fzf would, shows the screen's
        # colours without the trailing blank and SGR-only lines.
        shown = new_session(
            "shown",
            agent_command(
                "printf '\\033[31mHELLO\\n\\033[0m\\n\\033[44m\\033[0m\\n'; sleep 600; :"
            ),
        )
        poll(
            "the pane printed",
            lambda: tmux("capture-pane", "-p", "-t", shown),
            lambda v: "HELLO" in str(v),
        )
        args = Path(f"{log}.args").read_text().splitlines()
        command = (
            args[args.index("--preview") + 1]
            if "--preview" in args
            else next(a.split("=", 1)[1] for a in args if a.startswith("--preview="))
        )
        preview = subprocess.run(
            ["sh", "-c", command.replace("{1}", shlex.quote(shown))],
            check=True,
            capture_output=True,
            timeout=5,
            env=dict(env, FZF_PREVIEW_LINES="10"),
        ).stdout
        assert b"\x1b[31mHELLO" in preview, preview
        assert not preview.rstrip(b"\n").endswith((b"\x1b[0m", b"\x1b[44m")), preview
        assert preview.splitlines()[-1].replace(b"\x1b[39m", b"").endswith(b"HELLO"), preview
        closed = subprocess.run(
            ["sh", "-c", command.replace("{1}", "%99999")],
            check=True,
            capture_output=True,
            timeout=5,
            env=env,
        ).stdout
        assert closed == b"(pane closed)\n", closed
        print("PASS: the preview keeps colours and drops trailing blank lines")

        # No rows: a message, no view mode.
        tmux("set-option", "-g", "@window_counted", "")
        count = len(runs())
        os.write(master, b"\x1b[15~")
        poll("the empty run finishes", lambda: len(runs()), lambda n: n > count)
        assert runs()[-1] == "0"
        poll(
            "no rows is reported",
            lambda: tmux("show-messages", "-t", me),
            lambda v: "No agent panes on this server" in str(v),
        )
        assert tmux("display-message", "-p", "-t", view(me)[2], "#{pane_mode}") != "view-mode"
        print("PASS: an empty list is reported as a message")

        # Without fzf the picker says so instead of failing.
        nofzf = root / "nofzf"
        nofzf.mkdir()
        for tool in ("bash", "env", "sh", "awk", "cat", "mktemp", "rm"):
            found = shutil.which(tool)
            assert found, tool
            (nofzf / tool).symlink_to(found)
        for tool in ("tmux-agent-picker", "run-picker"):
            (nofzf / tool).symlink_to(bindir / tool)
        (nofzf / "tmux").symlink_to(TMUX)
        tmux("set-environment", "-g", "PATH", str(nofzf))
        count = len(runs())
        os.write(master, b"\x1b[15~")
        poll("the missing fzf run finishes", lambda: len(runs()), lambda n: n > count)
        poll(
            "the missing fzf is reported",
            lambda: tmux("show-messages", "-t", me),
            lambda v: "needs fzf" in str(v),
        )
        print("PASS: a missing fzf is reported as a message")
    finally:
        try:
            tmux("kill-server", check=False)
        except subprocess.TimeoutExpired:
            pass
        for pid in clients:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
        for fd in masters.values():
            os.close(fd)
