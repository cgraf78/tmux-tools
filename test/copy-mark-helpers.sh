#!/usr/bin/env bash
# copy-mark-helpers.sh — assertions, temp directories, and a summary reporter
# for test/copy-mark-test.
#
# Usage:
#   . "$TEST_DIR/copy-mark-helpers.sh"
#   _assert_eq "description" "expected" "actual"
#   ...
#   _test_summary  # prints results, exits 0 or 1

PASS=0
FAIL=0
CLEANUP_DIRS=()

# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

_pass() {
  PASS=$((PASS + 1))
  echo "  PASS: $1"
}
_fail() {
  FAIL=$((FAIL + 1))
  echo "  FAIL: $1" >&2
}

_assert_eq() {
  local desc="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    _pass "$desc"
  else
    _fail "$desc (expected '$expected', got '$actual')"
  fi
}

_assert_contains() {
  local desc="$1" expected="$2" actual="$3"
  if [[ "$actual" == *"$expected"* ]]; then
    _pass "$desc"
  else
    _fail "$desc (expected to contain '$expected', got '$actual')"
  fi
}

_assert_exit() {
  local desc="$1" expected="$2" actual="$3"
  if [[ "$expected" -eq "$actual" ]]; then
    _pass "$desc"
  else
    _fail "$desc (expected exit $expected, got $actual)"
  fi
}

_assert_file_missing() {
  local desc="$1" path="$2"
  if [[ ! -f "$path" ]]; then
    _pass "$desc"
  else
    _fail "$desc (file should not exist: $path)"
  fi
}

_assert_file_content() {
  local desc="$1" expected="$2" path="$3"
  if [[ -f "$path" ]]; then
    local actual
    actual=$(cat "$path")
    if [[ "$actual" == "$expected" ]]; then
      _pass "$desc"
    else
      _fail "$desc (expected content '$expected', got '$actual')"
    fi
  else
    _fail "$desc (file not found: $path)"
  fi
}

# ---------------------------------------------------------------------------
# Temp directory management
# ---------------------------------------------------------------------------

_TEST_TMP_ROOT=$(mktemp -d) || {
  echo "failed to create test temp root" >&2
  exit 1
}
if [[ -z "$_TEST_TMP_ROOT" || ! -d "$_TEST_TMP_ROOT" ]]; then
  echo "mktemp returned invalid test temp root: $_TEST_TMP_ROOT" >&2
  exit 1
fi
CLEANUP_DIRS+=("$_TEST_TMP_ROOT")

_tmpdir() {
  local d
  d=$(mktemp -d "$_TEST_TMP_ROOT/tmp.XXXXXX") || {
    echo "failed to create test temp directory" >&2
    exit 1
  }
  if [[ -z "$d" || "$d" != "$_TEST_TMP_ROOT"/* || ! -d "$d" ]]; then
    echo "mktemp returned invalid test temp directory: $d" >&2
    exit 1
  fi
  echo "$d"
}

_cleanup() {
  for d in "${CLEANUP_DIRS[@]+"${CLEANUP_DIRS[@]}"}"; do
    rm -rf "$d"
  done
}
trap _cleanup EXIT

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

_test_summary() {
  echo ""
  echo "================================"
  echo "Results: $PASS passed, $FAIL failed"
  echo "================================"
  [[ $FAIL -eq 0 ]] && exit 0 || exit 1
}
