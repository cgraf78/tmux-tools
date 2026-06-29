#!/usr/bin/env bash

tmux_tools_default_session_dir() {
  if [[ -n "${TMUX_TOOLS_SESSION_DIR:-}" ]]; then
    printf '%s\n' "$TMUX_TOOLS_SESSION_DIR"
  else
    printf '%s\n' "${XDG_DATA_HOME:-$HOME/.local/share}/tmux/sessions"
  fi
}

tmux_tools_session_file() {
  local save_dir="$1" session="$2"
  printf '%s/%s.sh\n' "$save_dir" "$session"
}

tmux_tools_saved_sessions() {
  local save_dir="$1"
  local had_nullglob=0
  local files=()
  local file

  # Saved sessions are exactly the restore scripts created by
  # tmux-save-session. Keep the filename suffix here so listing and restoring
  # cannot drift from the writer's `${session}.sh` convention.
  shopt -q nullglob && had_nullglob=1
  shopt -s nullglob
  files=("$save_dir"/*.sh)
  [[ "$had_nullglob" -eq 1 ]] || shopt -u nullglob

  for file in "${files[@]}"; do
    basename "$file" .sh
  done | sort
}
