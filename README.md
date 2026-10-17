# tmux-tools

![Tests](https://github.com/cgraf78/tmux-tools/actions/workflows/test.yml/badge.svg?branch=main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Bash Version](https://img.shields.io/badge/bash-%3E%3D3.2-blue.svg)](https://www.gnu.org/software/bash/)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20WSL-lightgrey.svg)](#)

Small helpers for tmux setups that outgrow the defaults:

- **`tmux-continuum-default-server`**: tmux-continuum saves and restores
  only on a server that is the only tmux server running when it loads. If any
  other server is already up when your default server starts
  (`tmux -L scratch`, a test socket, nested tmux), your default server is not
  saved or restored. This pins save and restore to the default server,
  whatever order the servers start in, and makes the other servers cheap
  no-ops.
- **`tmux-clip-paste`**: a `display-popup` picker cannot paste into the pane
  behind it. This hands the selection off and pastes it once the popup closes.
- **`tmux-copy-last-output [N]`**: copy the last N commands and their output
  from the current pane to your clipboard, through `pbcopy`, `xclip`, or
  OSC 52 (which can reach your local clipboard over SSH). It is like "copy last
  output" in Warp or iTerm2, but inside tmux. **It needs a specific two-line
  prompt; see [Prompt format](#prompt-format).**
- **`term-notify-sound`**: ring the terminal bell. Call it when a job or agent
  finishes. Inside tmux it also marks which pane rang, which plain tmux does
  not track (tmux records a bell against the window).
- **`term-pane-mark`**: set or clear a `busy` or `pending` mark on your tmux
  pane, for example while a coding agent works on a prompt, so your tmux
  config can show it.

## Requirements

- Bash 3.2 or newer
- tmux
- tmux-continuum and tmux-resurrect for `tmux-continuum-default-server`
  (found under `$TMUX_PLUGIN_MANAGER_PATH`, which TPM sets, else
  `$HOME/.local/share/tmux-plugins`)
- For `tmux-copy-last-output`'s clipboard copy: `pbcopy` when it is on
  `PATH`, else `xclip` when `DISPLAY` is set, else a terminal that supports
  OSC 52 attached to the tmux client

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
bind P display-popup -E 'your-picker | tmux-clip-paste --pane "#{pane_id}" --publish' \; run-shell 'tmux-clip-paste --pane "#{pane_id}"'
```

The picker inside the popup pipes its selection to `--publish`. Once the popup
closes, the chained `run-shell` pastes it into the pane that opened the popup.

```sh
your-picker | tmux-clip-paste --publish   # publish a selection
tmux-clip-paste                           # paste it into the current pane
tmux-clip-paste --pane %3                 # paste into a specific pane
tmux-clip-paste --path                    # print the handoff file path
tmux-clip-paste --file /tmp/selection     # use a custom handoff file
```

How it works:

- Each tmux server and pane gets its own handoff file in a mode `0700`
  per-user runtime directory. Set `TMUX_TOOLS_CLIP_PASTE_FILE` or pass
  `--file` to override it.
- `--publish` replaces the handoff file atomically. Use it instead of
  redirecting to the path printed by `--path`.
- Each paste claims one payload and uses its own named tmux buffer, so
  concurrent pastes cannot overwrite each other. On failure the payload is
  kept and the diagnostic says where.

`man tmux-clip-paste` covers the claim, recovery, and exit-status details.

### `tmux-copy-last-output`

Copy the last command and its output with `prefix y`, or the last N with
`prefix Y`:

```tmux
bind y run-shell 'TMUX_PANE=#{pane_id} tmux-copy-last-output'
bind Y command-prompt -p 'Copy last N commands:' 'run-shell "TMUX_PANE=#{pane_id} tmux-copy-last-output %1"'
```

`tmux-copy-last-output [--print] [N]` copies the last N command blocks (the
default is 1) from the last 10,000 lines of the pane. `--print` writes them to
standard output instead, so a binding can route them elsewhere.

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

### `term-notify-sound` and `term-pane-mark`

- `term-notify-sound [--owner PID]`: write one BEL to `/dev/tty`
  (`TERM_NOTIFY_TTY` overrides it), falling back to the tmux pane's tty. Inside
  tmux it then runs `term-pane-mark set pending`. Typical use is
  `make; term-notify-sound`, or an agent's "finished" hook.
- `term-pane-mark set|clear pending|busy [--pane PANE] [--owner PID]`: set or
  clear `@term_notify_pending` or `@term_busy` on the caller's own pane.
  `--owner PID` limits changes to that process while it runs in the pane's
  foreground, so programs an agent launches cannot clear the agent's mark.

Both set the pane options `@term_notify_pending` and `@term_busy` to `1`.
Rendering and clearing the pending mark is up to your tmux config. For
example, show both in pane borders and clear the pending mark when you visit
the pane. The explicit hook index keeps any hooks you already have on those
events:

```tmux
set -g pane-border-status top
set -g pane-border-format '#{?@term_notify_pending,[!] ,}#{?@term_busy,[busy] ,}#{pane_current_command}'
set-hook -g after-select-pane[100] 'set-option -pu @term_notify_pending'
set-hook -g after-select-window[100] 'set-option -pu @term_notify_pending'
```

`man term-pane-mark` explains how it decides which pane is the caller's.

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
