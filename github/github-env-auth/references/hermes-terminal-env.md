# Hermes terminal environment — how env vars actually reach terminal commands

Findings from the 2026-08-08 GitHub auth setup session (verified by inspecting
`/proc/<pid>/environ` up the process chain and shell flags):

## Facts

1. **Terminal commands run as `bash -c <cmd>` (non-interactive)** — `$-` shows
   `hBc`, no `i`. Non-interactive bash reads **no init files** (`~/.bashrc`,
   `/etc/profile`, `/etc/profile.d/*` are all skipped). Profile exports only
   help login shells, never Hermes terminal commands.

2. **`.env` is NOT injected into the terminal process env.** Hermes loads
   `$HERMES_HOME/.env` for its own use — provider/API tools consume it through
   *internal channels* (file read at call time; `read_file` on `.env` is
   refused with "credential store" message). But the `hermes-web-ui serve`
   process env contains only `HERMES_HOME` — no API keys, no `GITHUB_TOKEN`.
   Terminal children inherit from serve → they see nothing from `.env`.
   A Hermes restart does NOT fix this.

3. **Within a session, env persists via a snapshot file.** Every terminal
   command is prefixed with `source /tmp/hermes-snap-<hash>.sh >/dev/null 2>&1`
   (visible in the parent bash's cmdline). Exports made in one command are
   re-sourced before the next — so `export FOO=bar` persists for the rest of
   that session. The snapshot is per-session (tmp file); a new session starts
   from the serve env again.

4. **Process chain** (when running via Hermes Web UI):
   `pid 1 (systemd, user session scope) → node hermes-web-ui server → python
   serve → bash -c "source /tmp/hermes-snap-*.sh && <cmd>"`.

## Consequences for credential design

- Shell init files cannot make env vars available to agent-run tools.
- `.env` is a good *store* (single plaintext point, 0600) but must be read
  explicitly: either `source` it in the command, or (more robust) use helpers
  that parse it as a fallback.
- To make `git`/`gh` work in ANY shell with zero setup:
  - git: credential helper script that reads `$GITHUB_TOKEN`/`$GH_TOKEN` and
    falls back to grepping `.env`.
  - gh: wrapper binary in `/usr/local/bin` (PATH precedes `/usr/bin`) that
    injects `GH_TOKEN` from `.env` then `exec`s the real gh. gh natively
    prefers `GH_TOKEN` → `GITHUB_TOKEN` → `hosts.yml`, so no hosts.yml needed.
- For the user's own interactive terminals, `/etc/profile.d/*.sh` + a
  `~/.bashrc` hook still make sense — just don't rely on them for the agent.
