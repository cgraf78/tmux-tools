# tmux-tools

![Tests](https://github.com/cgraf78/tmux-tools/actions/workflows/test.yml/badge.svg?branch=main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Bash Version](https://img.shields.io/badge/bash-%3E%3D3.2-blue.svg)](https://www.gnu.org/software/bash/)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20WSL-lightgrey.svg)](#)

Two small fixes for tmux setups that outgrow the defaults:

- **`tmux-continuum-default-server`**: if you run more than one tmux server
  (`tmux -L work`, test sockets, nested tmux), tmux-continuum saves and
  auto-restores from every one of them, and their snapshots clobber each
  other. This keeps save and restore on the default server only and turns the
  others into cheap no-ops.
- **`tmux-clip-paste`**: a `display-popup` picker cannot paste into the pane
  behind it. This hands the selection off and pastes it once the popup closes.

## Requirements

- Bash 3.2 or newer
- tmux
- tmux-continuum and tmux-resurrect for `tmux-continuum-default-server`
  (found under `$TMUX_PLUGIN_MANAGER_PATH`, which TPM sets, else
  `$HOME/.local/share/tmux-plugins`)

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

On upgrade, the installer removes retired session-command links only when they
still point into the same tmux-tools checkout. User-managed files and links to
other providers are left untouched.

## Commands

### `tmux-continuum-default-server`

```tmux
# Disable the plugin's per-server scheduler first. The command re-enables it
# only on the default socket.
set -g @continuum-save-interval 0
set -g @tmux-tools-continuum-save-interval 5
run-shell 'tmux-continuum-default-server'
```

Run it from `run-shell` after your tmux plugins and their options have loaded.

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
```

If `tmux` is not installed, the test suite skips tmux server integration cases.
