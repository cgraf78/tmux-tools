# AGENTS.md

## About

Nine Bash 3.2-compatible tmux helpers plus one man page each. Stock macOS
`/bin/bash` 3.2 is a hard contract with its own CI job.
`tmux-copy-last-output`, `term-pane-mark`, and `term-notify-sound` were
imported from cgraf78/cmdblocks@52aae58; that archived repo holds their
earlier history.

## Layout

- `bin/tmux-continuum-default-server`, `bin/tmux-continuum-save-gate`,
  `bin/tmux-clip-paste`, `bin/tmux-copy-last-output`,
  `bin/tmux-command-palette`, `bin/tmux-pane`, `bin/term-pane-mark`,
  `bin/term-notify-sound`, `bin/term-pane-state`: the commands. Each must
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
  `test/tmux-command-palette-client.py` (with a stand-in fzf),
  `test/tmux-pane-test` and `test/term-pane-mark-token-test` (all on a
  private real tmux).

## Invariants

- The continuum commands are activation helpers: they exit quietly when
  plugins, tmux state, or socket identity are missing, so a partial tmux
  config keeps working. Don't turn those paths into errors.
- `term-pane-mark` and `term-notify-sound` are best effort: missing tmux,
  panes, or helpers must not turn the caller's work into an error.
- `@term_notify_pending`, `@term_notify_exit_status`, `@term_busy`,
  `@term_busy_seq` and `TERM_NOTIFY_TTY` are read or set by users' tmux
  configs, shell prompts, and agent hooks. Don't rename them. `@term_busy` is
  `1`. `@term_notify_pending` holds the attention kind: `done`, `waiting` or
  `blocked`; readers treat the legacy value `1` as `done`, and any non-empty
  value as pending. Exit status only accompanies `done`. Kinds, `--kind` and
  `--if waiting|blocked|sticky` are a cross-repo contract with agent hooks and
  the tmux config; don't add or rename one without updating them.
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
- `term-pane-mark set busy` bumps `@term_busy_seq` with
  `set-option -pF ... '#{e|+:#{?@term_busy_seq,#{@term_busy_seq},0},1}'`
  after `@term_busy 1`, in the same queue, so a count never exists without
  its busy mark. `tmux-pane wait --agent` reads it; clearing busy leaves it.
- `tmux-copy-last-output` and `tmux-pane` parse one two-line prompt shape
  with the same awk program, carried byte for byte between
  `# BEGIN prompt-parser` and `# END prompt-parser` in both scripts (each
  command stays self-contained); `test/tmux-pane-test` fails if the two
  regions differ or a marker is missing or doubled. If the parser changes,
  change both copies and update the README "Prompt format" section and both
  man pages with them.
- `tmux-pane`'s one hard guardrail is an explicit, exact, existing `%N` on
  the chosen server; never add a fallback to the current or any other pane,
  and never add refusals (busy, sync, own pane) beyond it. Its exit codes
  (0, the command's N, 1, 3, 4, 64-70, 124, 130/143), the `tp1:` marker
  grammar, and the final stderr line
  `result=<kind> exact=yes|no|- status=N|unknown [reason=R] [marker=M]` are
  read by scripts and agents; change them only with their man page. Exit 4
  belongs to a standalone `read --since` alone.
- `tmux-pane`'s subcommands, options, exit statuses, result kinds, inexact
  reasons, option defaults and tmux floor live once, in the interface block
  at the top of the script (`tmux-pane --interface` prints it). Add or rename
  one there first: `test/tmux-pane-test` fails until the code, the parser's
  case labels, the usage and help text, `tmux-pane.1`, and every
  `tmux-pane SUB ...` reference in the README, AGENTS.md and the man pages
  agree with it. The only version gate is `tp_tmux_floor`; newer behaviour is
  detected from tmux (the "Capabilities" comment lists each detection).
- Every `bin/` command needs a `man/man1/<cmd>.1` with `.SH NAME`, a row in
  `commands=()` in `support/install-checkout.sh`, and a ShellCheck inventory
  row; `test/tmux-tools-test` checks the first two.
- `@tmux-tools-resurrect-auto-restore` is a published contract that ds reads.
  Don't rename it. `@tmux-tools-resurrect-restore-started-at` is internal.
- Default-server ownership is decided by the canonical
  `${TMUX_TMPDIR:-/tmp}/tmux-$(id -u)/default` path.

## Testing

- Local: `test/run`. It runs ShellCheck over the `program` rows of
  `.github/shellcheck-files.txt` when `shellcheck` is installed, then every
  suite listed under Layout.
- CI: `TMUX_TOOLS_REQUIRE_TMUX=1 TMUX_TOOLS_SKIP_SHELLCHECK=1 test/run`
  through shared shell CI with the `base,tmux` profiles.
  `TMUX_TOOLS_REQUIRE_TMUX=1` turns a missing tmux (and Python, for the
  two client tests) into a failure instead of a skip: the real-tmux
  `tmux-clip-paste` block, `test/tmux-pane-test` and the Python clients.
- tmux versions: `tmux-pane` supports 3.2 and later. 3.6 is the primary
  target, and newer releases are first-class. Gates are always "at least
  X", a version that does not parse counts as the newest, and features are
  detected directly where tmux exposes them (`list-commands paste-buffer`
  for `-S`, empty `pane_key_mode`, empty history counters). Run
  `test/tmux-pane-test` on the oldest and newest tmux you touch;
  `TMUX_PANE_TEST_DISABLE` forces each feature off for the other side.
- Stock Bash 3.2 (macOS): `PREFIX=$tmp /bin/bash install.sh`, then for each
  installed command `/bin/bash -n`, plus `tmux-clip-paste --help`,
  `TMUX= tmux-continuum-default-server`, `tmux-continuum-save-gate`, and
  stub-tmux smokes of `tmux-copy-last-output --print`,
  `tmux-command-palette --list`, `term-pane-mark`, and `term-notify-sound`,
  all run with `/bin/bash`, as the `macos-bash32` job does. That job also
  installs tmux and runs `/bin/bash test/tmux-pane-test`, which starts the
  tool with `"$BASH"` so it runs under Bash 3.2.

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
