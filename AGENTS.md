# AGENTS.md

## About

Eight Bash 3.2-compatible tmux helpers plus one man page each. Stock macOS
`/bin/bash` 3.2 is a hard contract with its own CI job.
`tmux-copy-last-output`, `term-pane-mark`, and `term-notify-sound` were
imported from cgraf78/cmdblocks@52aae58; that archived repo holds their
earlier history.

## Layout

- `bin/tmux-continuum-default-server`, `bin/tmux-continuum-save-gate`,
  `bin/tmux-clip-paste`, `bin/tmux-copy-last-output`,
  `bin/tmux-command-palette`, `bin/term-pane-mark`, `bin/term-notify-sound`,
  `bin/term-pane-state`: the commands. Each must
  stay self-contained.
- `man/man1/`: one page per command. Detailed behavior lives here, not in
  the README.
- `install.sh`: generated checkout installer (see below).
  `support/install-checkout.sh` is the repo-owned delegate it runs.
- `test/run`: entry point for `test/tmux-tools-harness-test`,
  `test/tmux-continuum-test`, `test/tmux-tools-test`,
  `test/copy-mark-test` (which sources `test/copy-mark-helpers.sh`),
  `test/term-pane-state-test` (mock tmux, plus
  `test/term-pane-state-delegate.py`), `test/term-pane-state-client.py`,
  `test/tmux-command-palette-client.py` (with a stand-in fzf) and
  `test/term-pane-mark-token-test` (all on a private real tmux).

## Invariants

- The continuum commands are activation helpers: they exit quietly when
  plugins, tmux state, or socket identity are missing, so a partial tmux
  config keeps working. Don't turn those paths into errors.
- `term-pane-mark` and `term-notify-sound` are best effort: missing tmux,
  panes, or helpers must not turn the caller's work into an error.
- `@term_notify_pending`, `@term_notify_exit_status`, `@term_busy` and
  `TERM_NOTIFY_TTY` are read or set by users' tmux configs, shell prompts,
  and agent hooks. Don't rename them. `@term_busy` is `1`.
  `@term_notify_pending` holds the attention kind: `done`, `waiting` or
  `blocked`; readers treat the legacy value `1` as `done`, and any non-empty
  value as pending. Exit status only accompanies `done`. Kinds, `--kind` and
  `--if waiting|blocked|sticky` are a cross-repo contract with agent hooks
  and the tmux config; don't add or rename one without updating them.
- `term-pane-state` reads the config predicates `@pane_busy`,
  `@pane_pending`, `@pane_waiting` (empty in older configs, so 0) and
  `@pane_failed`, and Termnav's leases `@termnav_child_attention`
  (`expiry:working:pending:failed`) and `@termnav_child_waiting`
  (`expiry:N`). Each pane counts once by effective state: failed, then
  waiting, then done, then working; attention hides the pane's own work.
  Its JSON carries `waiting`, with `failed + waiting <= pending`; it passes
  `termnav tmux attention --waiting N` only when N is non-zero and retries
  once without it when an older Termnav exits 2.
- `term-pane-mark` ends each mark change's tmux command queue with
  `if-shell -F '#{&&:#{==:#{@term_pane_state_publish},on},#{session_attached}}'` and a
  `run-shell -b` of `term-pane-state --session` for the pane's session, found
  on the server's PATH. `@term_pane_state_publish` is the config's opt-in;
  don't rename it. Keep that job's output and status discarded: a background run-shell
  prints both into a pane. The `test/copy-mark-test` mock logs that suffix
  apart from the mark.
- `tmux-command-palette` replays the picked key with `send-keys -K` only
  after its popup closes, so prompts open over the pane; before tmux 3.4 it
  names the key instead. Never run a binding's command text directly: its
  formats and prompts need the client's own key context.
- Exit 64 is reserved for bad arguments to the pane, copy and palette commands;
  `tmux-copy-last-output --print` exits 3 when it finds no block, and a
  tmux binding relies on that status.
- `tmux-copy-last-output` parses one two-line prompt shape (header comment
  and awk patterns in the script). If the patterns change, update the README
  "Prompt format" section and the man page with them.
- Every `bin/` command needs a `man/man1/<cmd>.1` with `.SH NAME`, a row in
  `commands=()` in `support/install-checkout.sh`, and a ShellCheck inventory
  row; `test/tmux-tools-test` checks the first two.
- `@tmux-tools-resurrect-auto-restore` is a published contract that ds reads.
  Don't rename it. `@tmux-tools-resurrect-restore-started-at` is internal.
- Default-server ownership is decided by the canonical
  `${TMUX_TMPDIR:-/tmp}/tmux-$(id -u)/default` path.

## Testing

- Local: `test/run`. It runs ShellCheck over the `program` rows of
  `.github/shellcheck-files.txt` when `shellcheck` is installed, then the
  four suites.
- CI: `TMUX_TOOLS_REQUIRE_TMUX=1 TMUX_TOOLS_SKIP_SHELLCHECK=1 test/run`
  through shared shell CI with the `base,tmux` profiles.
  `TMUX_TOOLS_REQUIRE_TMUX=1` only turns the skipped real-tmux
  `tmux-clip-paste` block into a failure when tmux is absent.
- Stock Bash 3.2 (macOS): `PREFIX=$tmp /bin/bash install.sh`, then for each
  installed command `/bin/bash -n`, plus `tmux-clip-paste --help`,
  `TMUX= tmux-continuum-default-server`, `tmux-continuum-save-gate`, and
  stub-tmux smokes of `tmux-copy-last-output --print`,
  `tmux-command-palette --list`, `term-pane-mark`, and `term-notify-sound`,
  all run with `/bin/bash`, as the `macos-bash32` job does.

## Test isolation

- Most cases use a mock `tmux` first on `PATH`. `test/copy-mark-test` also
  fakes `TMUX`/`TMUX_PANE`, capture files, and `/proc` (through
  `TERM_PANE_MARK_PROC_ROOT`), and must stay independent of a real tmux.
- Real-tmux cases use a private server only: `-S` on a socket under the
  suite temp root (kept short for the macOS `AF_UNIX` limit) or a unique
  `-L` name, always with `-f /dev/null`, and killed on exit. Never touch
  the default server.
- To test ownership, fake `TMUX` and `TMUX_TMPDIR`; never point them at the
  real default socket.

## CI and generated files

- CI's ShellCheck job fails on any shell program missing from
  `.github/shellcheck-files.txt` (untracked files included) and on stale
  rows; local `test/run` does not detect this. Before pushing, run
  `bash <actions@lock>/.github/actions/shellcheck-inventory/run.sh "$PWD" .github/shellcheck-files.txt`,
  where `<actions@lock>` is a cgraf78/actions checkout at the SHA in
  `.github/cgraf78-actions.lock`.
- `install.sh` is generated by cgraf78/actions checkout-installer and
  byte-checked by `actions-sync`; never edit it. Install logic lives in
  `support/install-checkout.sh`. After editing
  `scripts/checkout-installer.conf`, run `consumer-ci/sync.sh <this checkout>`
  from a cgraf78/actions checkout at the SHA in
  `.github/cgraf78-actions.lock`.
- `.github/cgraf78-actions.lock` and every `uses: cgraf78/actions/...@sha`
  move together, only via `consumer-ci/sync.sh`.
- The `Required` job needs `shell` and `macos-bash32`. `test/tmux-tools-test`
  pins its text, so edit the two together.
- `retry-infrastructure.yml` keys on the workflow name `Tests`; don't
  rename it.

## Release

None; installs track `main`.
