#!/usr/bin/env bash

tmux_tools_resolve_session_dir() {
  if [[ "${TMUX_TOOLS_SESSION_DIR+x}" == x ]]; then
    REPLY="$TMUX_TOOLS_SESSION_DIR"
    return 0
  fi

  case "${XDG_DATA_HOME:-}" in
    /*)
      REPLY="$XDG_DATA_HOME/tmux/sessions"
      ;;
    *)
      if [[ -n "${HOME:-}" ]]; then
        REPLY="$HOME/.local/share/tmux/sessions"
      else
        REPLY=""
        return 1
      fi
      ;;
  esac
}

# Compatibility output API for existing sourced consumers. New shell callers
# that need byte-exact paths should use tmux_tools_resolve_session_dir and REPLY.
tmux_tools_default_session_dir() {
  tmux_tools_resolve_session_dir || return 1
  printf '%s\n' "$REPLY"
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
