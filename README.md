# tmux-tools

![Tests](https://github.com/cgraf78/tmux-tools/actions/workflows/test.yml/badge.svg?branch=main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Bash Version](https://img.shields.io/badge/bash-%3E%3D3.2-blue.svg)](https://www.gnu.org/software/bash/)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20WSL-lightgrey.svg)](#)

Small reusable tmux workflow tools.

## Commands

### `tmux-continuum-default-server`

Keeps tmux-continuum and tmux-resurrect ownership on the conventional default
tmux server when multiple socket-isolated servers are running. The command is
intended for `run-shell` after tmux plugins and their options have loaded:

```tmux
# Disable the plugin's per-server scheduler first. The provider re-enables it
# only for the conventional default socket.
set -g @continuum-save-interval 0
set -g @tmux-tools-continuum-save-interval 5
run-shell 'tmux-continuum-default-server'
```

The conventional socket is
`${TMUX_TMPDIR:-/tmp}/tmux-$(id -u)/default`. Both the active socket and the
expected socket are canonicalized through their parent directories, so a
symlinked `TMUX_TMPDIR` still identifies the same server. A socket merely named
`default` elsewhere is not treated as the owner.

On non-default servers, the command replaces Continuum's native status
interpolation with a disabled gate. That keeps frequent status refreshes cheap
without granting those servers save or restore ownership. On the default
server, it:

- restores the configured Continuum interval;
- publishes `@tmux-tools-resurrect-auto-restore=on` for consumers that need to
  coordinate with automatic restore;
- injects a gated save interpolation if Continuum did not install one; and
- starts tmux-resurrect once for a newly created server, after plugin loading
  has settled.

`@tmux-tools-resurrect-restore-started-at` records the server start time that
has already launched restore. This makes repeated config reloads idempotent
without keeping a process or lock alive. The marker belongs to this provider;
downstream tools should observe `@tmux-tools-resurrect-auto-restore` instead.

The default interval is five minutes when
`@tmux-tools-continuum-save-interval` is absent or malformed. A
`$HOME/tmux_no_auto_restore` file suppresses the fallback restore while leaving
automatic saving repaired. Restore also stays suppressed once the server is
older than Continuum's `@continuum-restore-max-delay` window.

The command deliberately fails quietly when the plugins, tmux state, or socket
identity are unavailable. It is an activation helper: a partial tmux config
must remain usable even when optional persistence plugins are missing.

### `tmux-continuum-save-gate`

Avoids running Continuum's save script on every `status-right` refresh. It is a
companion implementation detail of `tmux-continuum-default-server`, installed
as a separate command because tmux executes status interpolations independently.

The gate receives tmux's escaped last-save timestamp, the effective save
interval, and Continuum's native save script. It exits immediately when the
interval is zero or the next save is not due. When a save is due it `exec`s the
native script, preserving Continuum as the authority for the actual save.
Missing or malformed state fails open to that script rather than silently
disabling backups. Callers should use the exact interpolation emitted by the
default-server command; the leading `x` arguments preserve empty tmux options
as distinct shell arguments.

### `tmux-clip-paste`

Pastes text written by a tmux popup or picker into the current pane. This is
useful when a popup must write its selected text first and tmux should paste
after the popup closes.

```sh
tmux-clip-paste --path
tmux-clip-paste
tmux-clip-paste --file /tmp/selection
tmux-clip-paste --pane %3
your-picker | tmux-clip-paste --publish
```

Example tmux binding:

```tmux
bind P display-popup -E 'your-picker | tmux-clip-paste --pane "#{pane_id}" --publish' \; run-shell 'tmux-clip-paste --pane "#{pane_id}"'
```

Set `TMUX_TOOLS_CLIP_PASTE_FILE` or pass `--file FILE` to use a custom handoff
file. By default, each tmux server and pane uses a different handoff file inside
a mode `0700` per-user runtime directory. `--publish` reads standard input into
a restrictive temporary file and atomically publishes the complete payload;
use it instead of redirecting directly to the path printed by `--path`.
The binding passes the originating pane ID explicitly so both commands retain
the same target even if another pane becomes active while the popup is open.
Each consumer uses and deletes a unique named tmux buffer, so concurrent pastes
cannot replace one another through tmux's shared unnamed buffer. Atomic
publication assumes other users cannot rename or replace entries in the
handoff file's parent directory. The private default directory provides that
boundary; an intentionally shared override directory does not. Consumers
atomically claim one payload before loading it, so a newer publication remains
available for the next invocation. On a load or paste failure, the claimed
payload always remains at the private path reported in the diagnostic. A
best-effort hard link also restores the public path when it is still vacant;
that convenience never removes the private claim or overwrites a newer
payload. Only non-symlink regular files are accepted as handoffs. Pasting uses
tmux's delete-after-paste operation, so an interrupted client can distinguish a
committed paste from a retryable failure by checking its unique buffer. Once a
paste commits, later local cleanup failures produce warnings without changing
the successful status or inviting a duplicate retry.

The WezTerm tab helpers `wezterm-switch-tab` and `wezterm-move-tab` moved to
`termnav`, which owns cross-layer terminal navigation and OSC passthrough
helpers.

## Requirements

- Bash 3.2 or newer
- tmux
- tmux-continuum and tmux-resurrect for the Continuum provider commands

## Install

Put `bin/` on `PATH`, or link the command files into a directory on `PATH`.
Manual pages live in `man/man1/`.

For a simple local install:

```sh
./install.sh
```

Set `PREFIX`, `BIN_DIR`, or `MAN_DIR` to choose another destination.
On upgrade, the installer removes retired session-command links only when they
still point into the same tmux-tools checkout. User-managed files and links to
other providers are left untouched.

## Test

Run the complete local test suite:

```sh
test/run
```

Or run the focused command test directly:

```sh
test/tmux-tools-test
test/tmux-continuum-test
```

If `tmux` is not installed, the test suite skips tmux server integration cases.
