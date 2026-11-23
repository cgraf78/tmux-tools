# shellcheck shell=bash
# Shared setup for the suites that prepend scratch commands.

tmux_fixture_path() {
  case "$1" in
    *:*)
      printf '%s\n' 'tmux-tools test: TMPDIR must not contain a colon (:) for mock PATH entries' >&2
      return 2
      ;;
  esac
}

tmux_fixture_git() {
  # Fixture commands must not reuse the caller's Git repository or hooks.
  unset GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_DIR GIT_GRAFT_FILE
  unset GIT_INDEX_FILE GIT_NAMESPACE GIT_NO_REPLACE_OBJECTS GIT_OBJECT_DIRECTORY
  unset GIT_PREFIX GIT_QUARANTINE_PATH GIT_REPLACE_REF_BASE GIT_SHALLOW_FILE
  unset GIT_TEMPLATE_DIR GIT_WORK_TREE GIT_IMPLICIT_WORK_TREE
  unset GIT_CONFIG GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS GIT_CONFIG_SYSTEM
  export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL="$1/gitconfig"
}

tmux_fixture_tools() {
  local fixture_bin="$1" tool tool_path
  shift
  mkdir -p "$fixture_bin" || return 1
  ln -s "$BASH" "$fixture_bin/bash" || return 1
  # Only these named commands should be discoverable. A system directory
  # could also supply the executable the individual case needs to be absent.
  for tool in "$@"; do
    tool_path=$(type -P "$tool") || {
      printf 'tmux-tools test: missing fixture utility: %s\n' "$tool" >&2
      return 1
    }
    [[ "$tool_path" == /* ]] || tool_path="$PWD/$tool_path"
    ln -s "$tool_path" "$fixture_bin/$tool" || return 1
  done
}
