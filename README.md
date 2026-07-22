# tmux-tools

![Tests](https://github.com/cgraf78/tmux-tools/actions/workflows/test.yml/badge.svg?branch=main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Bash Version](https://img.shields.io/badge/bash-%3E%3D3.2-blue.svg)](https://www.gnu.org/software/bash/)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20WSL-lightgrey.svg)](#)

Small reusable tmux workflow tools.

## Commands

### `tmux-save-session`

Saves a tmux session layout as an executable restore script. The saved layout
includes window names, pane layouts, pane working directories, and the active
window.

```sh
tmux-save-session
tmux-save-session work
tmux-save-session --dir /tmp/tmux-sessions work
```

When no session name is passed, the current tmux session is saved.

### `tmux-restore-session`

Restores a session saved by `tmux-save-session`.

```sh
tmux-restore-session
tmux-restore-session work
tmux-restore-session --list
tmux-restore-session --no-attach work
```

When no session name is passed, restore behaves as follows:

- no saved sessions: print an error
- one saved session: restore it directly
- multiple saved sessions: open an `fzf` picker

After restoring, the command attaches when run outside tmux and switches the
current client when run inside tmux. Use `--no-attach` for scripts and tests.

## Session Directory

Saved restore scripts use the first available path in this order:

```text
$TMUX_TOOLS_SESSION_DIR
$XDG_DATA_HOME/tmux/sessions
$HOME/.local/share/tmux/sessions
```

An explicitly set, non-empty `TMUX_TOOLS_SESSION_DIR` is used unchanged.
Otherwise, the tools use `XDG_DATA_HOME` only when it is absolute and fall back to
`$HOME/.local/share`; they report an error instead of inventing a root when
neither is available. Empty and relative `XDG_DATA_HOME` values are ignored as
required by the XDG base-directory specification.

Use `--dir DIR` on either command to read or write a different directory.

### `tmux-clip-paste`

Pastes text written by a tmux popup or picker into the current pane. This is
useful when a popup must write its selected text first and tmux should paste
after the popup closes.

```sh
tmux-clip-paste --path
tmux-clip-paste
tmux-clip-paste --file /tmp/selection
```

Example tmux binding:

```tmux
bind P display-popup -E 'your-picker > "$(tmux-clip-paste --path)"' \; run-shell tmux-clip-paste
```

Set `TMUX_TOOLS_CLIP_PASTE_FILE` or pass `--file FILE` to use a custom handoff
file.

The WezTerm tab helpers `wezterm-switch-tab` and `wezterm-move-tab` moved to
`termnav`, which owns cross-layer terminal navigation and OSC passthrough
helpers.

## Requirements

- Bash
- tmux
- `fzf` for interactive restore when multiple saved sessions exist

## Install

Put `bin/` on `PATH`, or link the command files into a directory on `PATH`.
Manual pages live in `man/man1/`.

For a simple local install:

```sh
./install.sh
```

Set `PREFIX`, `BIN_DIR`, or `MAN_DIR` to choose another destination.

## Test

Run the complete local test suite:

```sh
test/run
```

Or run the focused command test directly:

```sh
test/tmux-tools-test
```

If `tmux` is not installed, the test suite skips tmux server integration cases.
