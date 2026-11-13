# tmux-tools

[![Tests](https://github.com/cgraf78/tmux-tools/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/cgraf78/tmux-tools/actions/workflows/test.yml?query=branch%3Amain)
[![License](https://img.shields.io/badge/license-MIT-67ac09)](LICENSE)
[![Bash](https://img.shields.io/badge/bash-%3E%3D3.2-blue)](#requirements)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20WSL%20%7C%20Termux-lightgrey)](#requirements)

Small helpers for tmux setups that outgrow the defaults:

- **`tmux-continuum-default-server`**: tmux-continuum saves and restores
  only on a server that is the only tmux server running when it loads. If any
  other server is already up when your default server starts
  (`tmux -L scratch`, a test socket, nested tmux), your default server is not
  saved or restored. This pins save and restore to the default server,
  whatever order the servers start in, and makes the other servers cheap
  no-ops.
- **`tmux-clip-paste`**: claim a complete private handoff and paste it into an
  explicitly selected pane, including the pane behind a picker popup.
- **`tmux-copy-last-output [N]`**: copy the last N commands and their output
  from the current pane to your clipboard. `clip` owns transport and history
  when installed; explicit client targeting makes OSC 52 reach the initiating
  workstation over SSH. It is like "copy last
  output" in Warp or iTerm2, but inside tmux. **It needs a specific two-line
  prompt; see [Prompt format](#prompt-format).**
- **`tmux-command-palette`**: find a key binding by its description in an fzf
  popup and run it, like an editor's command palette. It lists every root and
  prefix binding that has a note (`bind-key -N`).
- **`term-notify-sound`**: ring the terminal bell. Call it when a job or agent
  finishes. Inside tmux it also marks which pane rang, which plain tmux does
  not track (tmux records a bell against the window).
- **`term-pane-mark`**: set or clear a `busy` or `pending` mark on your tmux
  pane, for example while a coding agent works on a prompt or waits for an
  answer, so your tmux config can show it.
- **`term-pane-state`**: count each pane's effective state (failed, waiting,
  done or working) and publish the attached session's state to its exact
  containing terminal client.

## Requirements

- Bash 3.2 or newer
- tmux
- tmux-continuum and tmux-resurrect for `tmux-continuum-default-server`
  (found under `$TMUX_PLUGIN_MANAGER_PATH`, which TPM sets, else
  `$HOME/.local/share/tmux-plugins`)
- For `tmux-copy-last-output`'s clipboard copy: `clip` when installed; otherwise
  `pbcopy`, `wl-copy` with `WAYLAND_DISPLAY`, `xclip` with `DISPLAY`, or an
  explicitly selected tmux client whose terminal supports OSC 52.
- For `tmux-command-palette`: `fzf`, and tmux 3.4 or newer to run the chosen
  key itself (older tmux asks you to press it)

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/cgraf78/tmux-tools/main/install.sh | bash
```

This keeps a managed checkout under `$XDG_DATA_HOME` when that path is
absolute, or under `$HOME/.local/share` otherwise, and links the commands and
man pages into `~/.local/bin` and `~/.local/share/man`. Rerun it to update.
Set `PREFIX`, `BIN_DIR`, or `MAN_DIR` to choose another destination.

To manage the checkout path yourself, run `./install.sh` from a stable
checkout, or put `bin/` on `PATH` and `man/` on `MANPATH`.

On upgrade, the installer removes links to retired commands only when they
still point into the same tmux-tools checkout. Your own files and links that
point elsewhere are left untouched.

`tmux-copy-last-output`, `term-notify-sound`, and `term-pane-mark` moved here
from [cmdblocks](https://github.com/cgraf78/cmdblocks) with the same names,
options, and exit statuses. The tmux-tools installer retargets existing
cmdblocks links, since it replaces any symlink at a command or man page path;
it still refuses a regular file.

## Commands

### `tmux-continuum-default-server`

```tmux
# Before your plugin manager loads the plugins:
# Turn off Continuum's per-server scheduler; the command re-enables it only on
# the default socket.
set -g @continuum-save-interval 0
set -g @tmux-tools-continuum-save-interval 5
# The command starts tmux-resurrect's restore itself. Continuum reads this
# when it loads, so leave it at its default of 'off' (or set it here) to
# avoid restoring a new server twice.
set -g @continuum-restore 'off'

run '~/.tmux/plugins/tpm/tpm'   # or your plugin manager's load line

# After the plugins have loaded:
run-shell 'tmux-continuum-default-server'
```

The order matters: the options go before the plugins load, and the command
runs after.

How it works:

- The default server is the one on
  `${TMUX_TMPDIR:-/tmp}/tmux-$(id -u)/default`, compared after resolving
  symlinks. A socket merely named `default` elsewhere does not count.
- On other servers, it swaps Continuum's status-line save hook for a disabled
  gate, so status refreshes stay cheap and those servers never save or
  restore.
- On the default server, it restores the save interval (five minutes when
  `@tmux-tools-continuum-save-interval` is absent or malformed), publishes
  `@tmux-tools-resurrect-auto-restore=on`, and starts tmux-resurrect once for
  a newly created server. [ds](https://github.com/cgraf78/ds) reads that
  option to coordinate with automatic restore.
- A `$HOME/tmux_no_auto_restore` file suppresses restore but keeps saving.
- It fails quietly when the plugins, tmux state, or socket identity are
  unavailable, so a partial tmux config stays usable.

The status-line gate is a separate command, `tmux-continuum-save-gate`, that
you never call directly; it `exec`s Continuum's own save script only when a
save is due. See `man tmux-continuum-default-server` and
`man tmux-continuum-save-gate` for every option.

### `tmux-clip-paste`

```tmux
bind P display-popup -E 'clip pick --paste-pane #{pane_id}'
```

With the optional dotfiles `clip` command installed, this picker creates a
private handoff per operation and invokes `tmux-clip-paste --file ... --pane ...`
only after a successful selection. Cancelling never pastes an older recovery
payload, and concurrent pickers in one pane cannot exchange selections. The
explicit target allows delivery to the underlying pane before the popup closes.
Standalone producers can likewise prepare a complete private file and pass it
with `--file` and `--pane`.

```sh
tmux-clip-paste --publish < complete.payload # serialized two-phase publication
tmux-clip-paste                           # consume that published selection
tmux-clip-paste --pane %3                 # paste into a specific pane
tmux-clip-paste --path                    # print the handoff file path
tmux-clip-paste --file /tmp/selection     # use a custom handoff file
```

How it works:

- Each tmux server and pane gets its own handoff file in a mode `0700`
  per-user runtime directory. Set `TMUX_TOOLS_CLIP_PASTE_FILE` or pass
  `--file` to override it.
- `--publish` replaces the handoff file atomically. Use it instead of
  redirecting to the path printed by `--path`. This explicit two-phase API
  shares one pending slot per server/pane; concurrent operations should use
  invocation-unique private files instead.
- Each paste claims one payload and uses its own named tmux buffer, so
  concurrent pastes cannot overwrite each other. On failure the payload is
  kept and the diagnostic says where. An unsuccessful paste command may have
  delivered its bytes before failing; do not retry automatically. A disappeared
  buffer alone cannot prove delivery.

`man tmux-clip-paste` covers the claim, recovery, and exit-status details.

### `tmux-copy-last-output`

Copy the last command and its output with `prefix y`:

```tmux
bind y run-shell 'tmux-copy-last-output --pane #{pane_id} --client #{q:client_name}'
```

`tmux-copy-last-output [--print] [--pane PANE] [--client CLIENT] [N]` copies the last N command blocks (the
default is 1) from the last 10,000 lines of the pane. `--print` writes them to
standard output instead, so a binding can route them elsewhere.
Clipboard targeting validates the exact client name/TTY instead of choosing
the most recently active attachment: without `clip`, it looks the name up in
`tmux list-clients`, since `display-message -p -c` answers for the most
recently active client and tmux 3.2 takes no argument to `-c`. Messages go to
that client too, except on tmux 3.2, which cannot aim a message at one client.
It does not pin a process generation across detach/reconnect and reuse of the
same terminal name.

#### Prompt format

`tmux-copy-last-output` finds command boundaries by reading the pane text for
a two-line prompt. It recognizes exactly this shape:

```text
[0] user@host:~/src/project (main)
$ make test
```

- **Line 1** starts with `user@host:`, optionally preceded by an exit code
  such as `[0] `. The user name may contain only letters, digits, and `_`;
  the host may also contain `.` and `-`. Anything after the colon is ignored.
- **Line 2**, immediately below, is `$` (bash) or `%` (zsh), optionally
  followed by a space and the command.

These prompts match:

```bash
# bash (~/.bashrc). Use a literal `$`: `\$` turns into `#` for root.
PS1='[$?] \u@\h:\w\n$ '
```

```zsh
# zsh (~/.zshrc)
PROMPT=$'[%?] %n@%m:%~\n%% '
```

With any other prompt, the command finds no blocks: it shows a tmux message,
"No command output found", and copies nothing. With `--print` it also exits
with status 3. Prompt colors are fine, because tmux captures the text without
them.

### `tmux-command-palette`

```tmux
bind -n M-Space run-shell 'tmux-command-palette --client #{q:client_name}'
```

The popup lists each noted binding as its note, then its key, such as
`Copy the last N command outputs   prefix O`, sorted by note. Enter runs the
chosen binding and Escape closes the popup. The popup only picks: after it
closes, the key is handed to the client as if typed (`send-keys -K`, tmux
3.4), so the binding acts on the pane you opened the palette from, and its
prompts and menus open over that pane. Before tmux 3.4 the palette turns the
prefix on and names the key, so one key press runs it.

Mouse bindings, tmux's `Select window N` notes on `prefix 0`-`9`, and a second
key with an earlier key's note are left out. `tmux-command-palette --list`
prints the entries. `man tmux-command-palette` has the details.

### `term-notify-sound` and `term-pane-mark`

- `term-notify-sound [--owner PID] [--kind KIND] [--exit-status CODE]`:
  write one BEL to `/dev/tty` (`TERM_NOTIFY_TTY` overrides it), falling back
  to the tmux pane's tty. Inside tmux it then runs `term-pane-mark set
  pending` with the same options. Typical use is `make; term-notify-sound`,
  or an agent's "finished" hook.
- `term-pane-mark set|clear|reset pending|busy [--pane PANE] [--owner PID]
  [--kind KIND] [--exit-status CODE] [--if waiting|blocked|sticky]`: set or
  clear `@term_notify_pending` or `@term_busy` on the caller's own pane.
  `--owner PID` limits changes to that process while it runs in the pane's
  foreground, so programs an agent launches cannot clear the agent's mark.

`@term_busy` is set to `1`. `@term_notify_pending` holds the kind of
attention, chosen with `--kind`:

| Kind | Meaning |
| --- | --- |
| `done` (default) | finished and not yet seen; with `--exit-status N`, a failed command |
| `waiting` | needs an answer, such as a permission prompt |
| `blocked` | stopped on an error and needs the user to resume it |

Older versions stored `1`; treat it as `done`. `waiting` and `blocked` are
sticky: a glance should not clear them. Their producer clears them with
`term-pane-mark clear pending --if waiting|blocked|sticky`, which removes the
mark only while it still holds that kind (`sticky` means either), so a newer
`done` survives. `term-pane-mark reset busy --owner PID`, run by a shell
prompt after a killed child, also clears sticky kinds.

Rendering and clearing the pending mark is up to your tmux config. For
example, show both in pane borders and clear informational marks when you
visit the pane. The explicit hook index keeps any hooks you already have on
those events:

```tmux
set -g pane-border-status top
set -g pane-border-format '#{?@term_notify_pending,[#{@term_notify_pending}] ,}#{?@term_busy,[busy] ,}#{pane_current_command}'
set-hook -g after-select-pane[100] 'if -F "#{||:#{==:#{@term_notify_pending},waiting},#{==:#{@term_notify_pending},blocked}}" "" "set-option -pu @term_notify_pending ; set-option -pu @term_notify_exit_status"'
set-hook -g after-select-window[100] 'if -F "#{||:#{==:#{@term_notify_pending},waiting},#{==:#{@term_notify_pending},blocked}}" "" "set-option -pu @term_notify_pending ; set-option -pu @term_notify_exit_status"'
```

`man term-pane-mark` explains how it decides which pane is the caller's.
Where the config sets `@term_pane_state_publish` to `on`, each mark
change in an attached session also starts a background `term-pane-state
--session` run in the same tmux command queue, so the terminal sees the
change at once (see below).

Busy producers can add `--token SESSION:TURN` to both set and clear. Tokens
keep a delayed Stop from clearing a newer turn, while `--owner PID` still
requires the producer to own the foreground terminal. Untagged legacy stops
do not clear tagged work. A shared background backend has no such terminal;
it must supply a verified frontend association instead of guessing a pane.

### `term-pane-state`

`term-pane-state --socket SOCKET --session ID --print` emits a versioned JSON
snapshot with `working`, `pending`, `failed` and `waiting` counts. The
embedding config supplies the structured `@pane_busy`, `@pane_pending`,
`@pane_waiting` and `@pane_failed` predicates that also drive its local
display; a config without `@pane_waiting` reports no waiting panes. Each
pane counts once, by its effective state: failed, then waiting, then done,
then working. `pending` counts every pane with attention, `failed` and
`waiting` are disjoint parts of it, and the rest of `pending` is done. A pane
with attention does not count as working. Fresh leased child summaries from
Termnav (`@termnav_child_attention` and the separate `@termnav_child_waiting`)
contribute to the same snapshot; expired or malformed children cannot leave a
ghost badge.

For client-specific status jobs, use `--client NAME --client-pid PID
--client-created EPOCH` instead of `--session ID --print`. The helper validates
that exact non-control client and evaluates the embedding config's attention
predicates for its selected pane. This makes a focused pane's local attention
clear in WezTerm as it does in tmux, while attention from other panes and child
sessions remains visible. It publishes the `TERM_PANE_STATE` user variable
through Termnav's hierarchical attention route or its bounded native direct
terminal writer. Legacy Termnav status 3 fails closed and requires an update;
the shell never writes to a client tty. The payload's heartbeat
lets a GUI expire stale state after detach or transport failure. The helper
passes `--waiting` only while a pane is waiting; a Termnav that predates it
exits 2, and the helper retries once without it, so that layer shows waiting
attention as done. No display
text is written. Publication requires Termnav's foreground ownership checks;
without it the helper emits nothing. Display snapshots can briefly arrive
out of order and reconcile on the next successful poll; they never control
lifecycle operations. See `man term-pane-state` for activation and lifetime details.

tmux reruns a status job at most once a second, and otherwise only on its
status interval, so the terminal can lag a window switch or a focus change by
seconds. `term-pane-state --socket SOCKET --session ID`, without `--print`,
publishes at once to every terminal client of the session, each with its own
focus. Run it from the hooks for those events in the background, discarding
its output, which a background `run-shell` would print into a pane:

```tmux
set -g @term_pane_state_publish on
set-hook -g session-window-changed[140] "run-shell -b 'term-pane-state --socket #{q:socket_path} --session #{q:session_id} >/dev/null 2>&1 || true'"
```

The WezTerm tab helpers `wezterm-switch-tab` and `wezterm-move-tab` moved to
[termnav](https://github.com/cgraf78/termnav).

## Test

Run the complete local test suite:

```sh
test/run
```

Or run the focused command test directly:

```sh
test/tmux-tools-test
test/tmux-continuum-test
test/copy-mark-test
```

If `tmux` is not installed, the test suite skips tmux server integration cases.
