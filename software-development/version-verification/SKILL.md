---
name: version-verification
description: "Verify package version live. Use before any upgrade."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [upgrade, version, pip, npm, preflight, verification, devops]
    related_skills: [hermes-agent, self-improvement]
    homepage: https://hermes-agent.nousresearch.com/docs/
---

# Version Verification

Verify the actual latest version of any software package, library, or tool **from live sources** (registries, Git tags, package managers) **before** recommending or executing an upgrade. Memory of past versions is informational, not authoritative — packages get unpublished, yanked, deprecated, or simply outdated without warning.

**Trigger this skill when:**
- User says "升级 X / 更新 Y / bump version / upgrade to latest / install newest Z"
- Agent is about to claim "there is a newer version" (from memory, assumption, or a sibling memory entry)
- Before running `pip install --upgrade`, `npm update`, `brew upgrade`, `apt upgrade`, `cargo update`
- Before recommending a version pin in config, docs, or code
- Before `hermes update`, `pip install hermes-agent`, or any "self-upgrade" CLI

## Why this exists

The agent's long-term memory holds version numbers from prior sessions that are:

- **Stale** — newer releases happened after that memory was written
- **Wrong** — hallucinated, copy-pasted from a near-miss version, or written from assumption. e.g. memory said "v0.20.0 (2026.8.3)" but only v0.19.0 was ever published
- **Locally correct but globally outdated** — your dev machine has a newer version than what's published, or vice versa
- **Cross-contaminated** — one package's version got conflated with another during a long session

**Real failure case (2026-08-25):** user said "upgrade hermes agent". Memory claimed `v0.20.0 (2026.8.3)` existed. Agent built an upgrade plan with backup/stop-services steps. `pip index versions hermes-agent` then `curl https://pypi.org/pypi/hermes-agent/json` showed `0.19.0` was still the latest and `0.20.0` had never been published. User stopped the session with "不用做了". One stale memory entry caused a real wasted cycle.

## Quick verification commands (by ecosystem)

| Ecosystem | Command | Output |
|---|---|---|
| **PyPI (CLI)** | `pip index versions <pkg> 2>&1 \| head -5` | List of available versions |
| **PyPI (JSON)** | `curl -sS https://pypi.org/pypi/<pkg>/json \| python3 -c "import sys,json; d=json.load(sys.stdin); print('latest:', d['info']['version']); rs=sorted(d['releases'].items(), key=lambda x: x[1][0]['upload_time'] if x[1] else '')[-8:]; [print(' ', v, '->', f[0]['upload_time'][:10]) for v,f in rs]"` | Latest + recent releases with timestamps |
| **npm** | `npm view <pkg> version` (latest only) or `npm view <pkg> versions --json` (all) | Version string or list |
| **Cargo** | `cargo search <pkg>` or `cargo info <pkg>` | Latest version on crates.io |
| **Docker Hub** | `curl -sS "https://registry.hub.docker.com/v2/repositories/<image>/tags/?page_size=10&ordering=last_updated" \| python3 -c ...` | Recent tags with timestamps |
| **GitHub releases** | `gh release list --repo <owner>/<repo> --limit 5` or `curl -sS https://api.github.com/repos/<owner>/<repo>/releases/latest \| grep -E '"(tag_name|published_at)"'` | Latest release tag + date |
| **Git tags** | `git ls-remote --tags https://github.com/<owner>/<repo>.git \| tail -10` | All remote tags |
| **APT (Debian/Ubuntu)** | `apt-cache policy <pkg>` or `apt list --all-versions <pkg> 2>/dev/null` | Installed + candidate versions |
| **Homebrew** | `brew info --json=v2 <pkg> \| python3 -c "import sys,json; d=json.load(sys.stdin); print('latest:', d['formulae'][0]['versions']['stable'])"` | Latest stable |
| **Snap** | `snap info <pkg>` | Channel + version table |
| **Hermes itself** | `hermes --version` + `pip show hermes-agent \| grep Version` | Compare tool's self-report vs pip |

## Recommended workflow

### Step 1 — Before claiming "an upgrade is available"

1. **Run a live query** with one command from the table above.
2. **Extract the latest** — `pip show <pkg> | grep Version` for installed, `pip index versions` for available.
3. **Compare** — Is `installed < latest`? If equal, installed ≥ latest, or no published package exists, **say so and stop.** Do not proceed with backup/stop-services/upgrade.
4. **Cross-check with a second source** for any non-trivial claim (PyPI JSON API as canonical source; npm view + curl registry as belt-and-suspenders).
5. **Report concrete numbers**, not generalities: "Installed: 0.19.0 (2026-07-20). Latest on PyPI: 0.19.0. No upgrade available. Released versions since 0.15.1: 0.16.0, 0.17.0, 0.18.0, 0.18.1, 0.18.2, 0.19.0."

### Step 2 — Before executing an upgrade (when one is genuinely needed)

1. **Backup state** — for stateful installs: `cp -a ~/.hermes ~/.hermes.backup-preupgrade-$(date +%Y%m%d-%H%M%S)` (1.3 GB on this machine). For git repos: `git tag preupgrade-<timestamp>`.
2. **Document rollback in one line** — `pip install <pkg>==<old.version>` is your undo. Write it down before upgrading.
3. **Stop dependent services** — anything holding locks or sockets on the package's data files. For Hermes: hermes-bridge.py + any gateway process.
4. **Upgrade** — `pip install --upgrade <pkg>` (or equivalent).
5. **Verify three ways** — `pip show <pkg>`, `pip index versions <pkg> | head -3`, and the tool's own `--version`. **All three must agree.**
6. **Run health check** — `hermes doctor` (or ecosystem equivalent) and compare warning count to pre-upgrade baseline.
7. **Restart services** in reverse order, then **smoke-test** with a real end-to-end call, not just version printing.
8. **If something is off** — `pip install <pkg>==<old.version>` and you are back in 30 seconds.

## Pitfalls (read these)

- **One keystroke in a version number is a real version** — "v0.20.0" vs "v0.19.0" is a single digit, but if you only have memory, you cannot tell which is real. Always re-query the registry.
- **Git `main` branch version ≠ published version** — A repo's `main` may have `0.20.0.dev0` in `__version__`, but the published package on PyPI is `0.19.0`. Always query the **registry**, not the source.
- **Mirror / cache lag** — pip behind a corporate mirror can show older versions for hours. Cross-check with the canonical registry (PyPI JSON API, npm registry HTTP endpoint).
- **`pip install --pre` reveals pre-releases** — `0.20.0a1`, `0.20.0rc1`. Without `--pre`, pip hides them. If the user wants stable only, do NOT trust `--pre` output to mean "stable latest."
- **Yanked versions still appear in `pip index versions`** — PyPI can yank a release for security. Always sanity-check with `pip install <pkg>==<ver>` (will error with "This version is a yanked release") before recommending a specific version.
- **Satisficing on one source** — One query can lie. PyPI mirror may lag, npm registry cache may be stale, GH API may rate-limit. Spend 30 seconds on a second source for any version-sensitive claim.
- **"Latest" ≠ "Safe" or "Compatible"** — latest may be a 0.x.0 with breaking API changes. Always check `gh release view <tag> --repo <owner/repo>` or CHANGELOG before recommending an upgrade to a downstream dependency.
- **`pip show` Version vs code `__version__`** — they may differ (e.g. `Version: 0.19.0` vs `__version__ = "0.19.0.post1"`). Pick one canonical source per project and stick to it.
- **"Up to date" lie from CLIs** — `hermes --version` for pip-installed Hermes may say "Up to date" even when there IS a newer version on PyPI, because the CLI's update-checker may be hardcoded to a specific feed. Don't trust "Up to date" as the answer; verify independently.
- **No published package at all** — some tools only exist as source (e.g. `curl -fsSL https://example.com/install.sh | bash` installers). For these, "latest" means "latest commit on main" or "latest release tag." Query the git remote.

## Verification block (run after every upgrade)

```bash
# Three-line confirmation; all three must agree:
pip show <pkg> 2>/dev/null | grep -E "^(Name|Version|Location):"
pip index versions <pkg> 2>/dev/null | head -3
<command> --version   # or `hermes --version`, `node --version`, etc.
```

If any of the three disagree, **stop** and investigate. Don't proceed to "smoke-test passed."

## When NOT to use this skill

- The user explicitly says "I know the version, just upgrade" and provides the version number directly — they own the claim.
- Upgrading internal/local code that's not published anywhere (just `git pull` and re-deploy).
- The user is asking about historical versions ("what version was released in March?") — same live-query discipline applies but the comparison target is the date, not "latest."

## Support files

- `references/pypi-verification.md` — full PyPI JSON API recipes, including the `installed vs available` 3-line diagnostic that surfaced the 2026-08-25 failure.
- `references/ecosystem-checks.md` — npm / Cargo / Docker Hub / GitHub releases / git tags / APT / Homebrew / Snap live-query recipes with ecosystem-specific pitfalls.

## Related skills

- `hermes-agent` (bundled, protected) — Hermes-specific upgrade flow via `hermes update`; **note: `hermes update` only works for git-checkout installs, NOT pip-installed Hermes. For pip: use `pip install --upgrade hermes-agent` directly.**
- `self-improvement` (`software-development`) — meta-skill for capturing general learnings. The 2026-08-25 failure prompted this skill.
- `repo-completion-audit` — separate concern (verifies project completeness, not version).
