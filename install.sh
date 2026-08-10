#!/usr/bin/env bash

set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="${BIN_DIR:-$PREFIX/bin}"
MAN_DIR="${MAN_DIR:-$PREFIX/share/man/man1}"
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

_retire_owned_link() {
  local link="$1"
  local retired_target="$2"
  local current_target

  [[ -L "$link" ]] || return 0
  current_target=$(readlink "$link") || return 0
  [[ "$current_target" == "$retired_target" ]] || return 0
  rm -f -- "$link"
}

mkdir -p "$BIN_DIR"
mkdir -p "$MAN_DIR"

# The manual session commands were retired in favor of the Continuum provider.
# Remove only links created from this exact checkout. A same-named command or
# manpage managed by the user or another package must remain untouched.
_retire_owned_link "$BIN_DIR/tmux-save-session" \
  "$ROOT/bin/tmux-save-session"
_retire_owned_link "$BIN_DIR/tmux-restore-session" \
  "$ROOT/bin/tmux-restore-session"
_retire_owned_link "$MAN_DIR/tmux-save-session.1" \
  "$ROOT/man/man1/tmux-save-session.1"
_retire_owned_link "$MAN_DIR/tmux-restore-session.1" \
  "$ROOT/man/man1/tmux-restore-session.1"

ln -sf "$ROOT/bin/tmux-continuum-default-server" \
  "$BIN_DIR/tmux-continuum-default-server"
ln -sf "$ROOT/bin/tmux-continuum-save-gate" \
  "$BIN_DIR/tmux-continuum-save-gate"
ln -sf "$ROOT/bin/tmux-clip-paste" "$BIN_DIR/tmux-clip-paste"
ln -sf "$ROOT/man/man1/tmux-continuum-default-server.1" \
  "$MAN_DIR/tmux-continuum-default-server.1"
ln -sf "$ROOT/man/man1/tmux-continuum-save-gate.1" \
  "$MAN_DIR/tmux-continuum-save-gate.1"
ln -sf "$ROOT/man/man1/tmux-clip-paste.1" "$MAN_DIR/tmux-clip-paste.1"

printf 'installed tmux-tools to %s\n' "$BIN_DIR"
printf 'installed tmux-tools manpages to %s\n' "$MAN_DIR"
