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

Saved restore scripts live in:

```sh
${TMUX_TOOLS_SESSION_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/tmux/sessions}
```

Use `--dir DIR` on either command to read or write a different directory.

## Requirements

- Bash
- tmux
- `fzf` for interactive restore when multiple saved sessions exist

## Install

Put `bin/` on `PATH`, or link the command files into a directory on `PATH`.

For a simple local install:

```sh
./install.sh
```

Set `PREFIX` or `BIN_DIR` to choose another destination.

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
