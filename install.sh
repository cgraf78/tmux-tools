#!/usr/bin/env bash

set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="${BIN_DIR:-$PREFIX/bin}"
MAN_DIR="${MAN_DIR:-$PREFIX/share/man/man1}"
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

mkdir -p "$BIN_DIR"
mkdir -p "$MAN_DIR"
ln -sf "$ROOT/bin/tmux-save-session" "$BIN_DIR/tmux-save-session"
ln -sf "$ROOT/bin/tmux-restore-session" "$BIN_DIR/tmux-restore-session"
ln -sf "$ROOT/bin/tmux-clip-paste" "$BIN_DIR/tmux-clip-paste"
ln -sf "$ROOT/bin/wezterm-move-tab" "$BIN_DIR/wezterm-move-tab"
ln -sf "$ROOT/bin/wezterm-switch-tab" "$BIN_DIR/wezterm-switch-tab"
ln -sf "$ROOT/man/man1/tmux-save-session.1" "$MAN_DIR/tmux-save-session.1"
ln -sf "$ROOT/man/man1/tmux-restore-session.1" "$MAN_DIR/tmux-restore-session.1"
ln -sf "$ROOT/man/man1/tmux-clip-paste.1" "$MAN_DIR/tmux-clip-paste.1"
ln -sf "$ROOT/man/man1/wezterm-move-tab.1" "$MAN_DIR/wezterm-move-tab.1"
ln -sf "$ROOT/man/man1/wezterm-switch-tab.1" "$MAN_DIR/wezterm-switch-tab.1"

printf 'installed tmux-tools to %s\n' "$BIN_DIR"
printf 'installed tmux-tools manpages to %s\n' "$MAN_DIR"
