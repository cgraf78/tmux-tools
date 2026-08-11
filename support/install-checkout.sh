#!/usr/bin/env bash

set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="${BIN_DIR:-$PREFIX/bin}"
MAN_DIR="${MAN_DIR:-$PREFIX/share/man/man1}"
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

_retire_owned_link() {
  local link="$1"
  local retired_target="$2"
  local current_target

  [[ -L "$link" ]] || return 0
  current_target=$(readlink "$link") || return 0
  [[ "$current_target" == "$retired_target" ]] || return 0
  rm -f -- "$link"
}

commands=(
  tmux-continuum-default-server
  tmux-continuum-save-gate
  tmux-clip-paste
)

# A checkout-backed install is only valid while every public artifact exists.
# Check the whole set before retiring old links or creating directories so an
# interrupted or incomplete checkout cannot produce a mixed installation.
for command in "${commands[@]}"; do
  source="$ROOT/bin/$command"
  if [[ ! -f "$source" || ! -x "$source" ]]; then
    printf 'tmux-tools: command source is not executable: %s\n' "$source" >&2
    exit 1
  fi
  manpage="$ROOT/man/man1/$command.1"
  if [[ ! -f "$manpage" ]]; then
    printf 'tmux-tools: manpage source is missing: %s\n' "$manpage" >&2
    exit 1
  fi
done

# Retarget links owned by an earlier checkout, but never replace a real path.
# Preflight every destination before making any change so a late manpage
# collision cannot leave the command links partially updated.
for command in "${commands[@]}"; do
  for target in "$BIN_DIR/$command" "$MAN_DIR/$command.1"; do
    if [[ (-e "$target" || -L "$target") && ! -L "$target" ]]; then
      printf 'tmux-tools: refusing to replace non-symlink path: %s\n' \
        "$target" >&2
      exit 1
    fi
  done
done

LINK_SOURCES=()
LINK_TARGETS=()
for command in "${commands[@]}"; do
  LINK_SOURCES+=("$ROOT/bin/$command")
  LINK_TARGETS+=("$BIN_DIR/$command")
done
for command in "${commands[@]}"; do
  LINK_SOURCES+=("$ROOT/man/man1/$command.1")
  LINK_TARGETS+=("$MAN_DIR/$command.1")
done

# A complete destination preflight still cannot make six separate ln calls
# atomic. Preserve each old symlink selection so a later filesystem failure
# can put the prior installation back exactly; newly published links are
# removed. Parallel indexed arrays keep the installer compatible with Bash 3.2.
LINK_WAS_SYMLINK=()
LINK_OLD_TARGETS=()
for target in "${LINK_TARGETS[@]}"; do
  if [[ -L "$target" ]]; then
    LINK_WAS_SYMLINK+=(1)
    LINK_OLD_TARGETS+=("$(readlink "$target")")
  else
    LINK_WAS_SYMLINK+=(0)
    LINK_OLD_TARGETS+=("")
  fi
done

_rollback_links() {
  local last="$1" index target

  for ((index = last; index >= 0; index--)); do
    target="${LINK_TARGETS[index]}"
    if [[ (-e "$target" || -L "$target") && ! -L "$target" ]]; then
      printf 'tmux-tools: rollback preserved non-symlink path: %s\n' \
        "$target" >&2
      continue
    fi
    if [[ "${LINK_WAS_SYMLINK[index]}" -eq 1 ]]; then
      if ! ln -sfn -- "${LINK_OLD_TARGETS[index]}" "$target"; then
        printf 'tmux-tools: rollback could not restore symlink: %s\n' \
          "$target" >&2
      fi
    elif [[ -L "$target" ]] && ! rm -f -- "$target"; then
      printf 'tmux-tools: rollback could not remove new symlink: %s\n' \
        "$target" >&2
    fi
  done
}

mkdir -p "$BIN_DIR" "$MAN_DIR"
for ((link_index = 0; link_index < ${#LINK_TARGETS[@]}; link_index++)); do
  if ln -sfn -- "${LINK_SOURCES[link_index]}" "${LINK_TARGETS[link_index]}"; then
    continue
  else
    link_status=$?
    _rollback_links "$link_index"
    exit "$link_status"
  fi
done

# The manual session commands were retired in favor of the Continuum provider.
# Remove only links created from this exact checkout. A same-named command or
# manpage managed by the user or another package must remain untouched. Retire
# them only after every replacement link is live so failed publication leaves
# the previous command surface intact.
_retire_owned_link "$BIN_DIR/tmux-save-session" \
  "$ROOT/bin/tmux-save-session"
_retire_owned_link "$BIN_DIR/tmux-restore-session" \
  "$ROOT/bin/tmux-restore-session"
_retire_owned_link "$MAN_DIR/tmux-save-session.1" \
  "$ROOT/man/man1/tmux-save-session.1"
_retire_owned_link "$MAN_DIR/tmux-restore-session.1" \
  "$ROOT/man/man1/tmux-restore-session.1"

printf 'installed tmux-tools to %s\n' "$BIN_DIR"
printf 'installed tmux-tools manpages to %s\n' "$MAN_DIR"
