#!/usr/bin/env bash

set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="${BIN_DIR:-$PREFIX/bin}"
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

mkdir -p "$BIN_DIR"
ln -sf "$ROOT/bin/tmux-save-session" "$BIN_DIR/tmux-save-session"
ln -sf "$ROOT/bin/tmux-restore-session" "$BIN_DIR/tmux-restore-session"
ln -sf "$ROOT/bin/tmux-clip-paste" "$BIN_DIR/tmux-clip-paste"

printf 'installed tmux-tools to %s\n' "$BIN_DIR"
