---
name: hermes-persona-and-restart-workflow
description: "Switch Hermes persona (SOUL.md) and restart gateway/CLI."
version: 1.0.0
author: Hermes Agent (curator-managed)
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [persona, soul, restart, gateway, identity]
    related_skills: [hermes-agent, hermes-web-ui-admin]
---

# Hermes Persona & Restart Workflow

Switching or restoring the Hermes Agent persona, restarting the gateway
or CLI session, and verifying that a SOUL.md change actually took
effect. Covers the **runtime non-hot-reload trap** — SOUL.md is loaded
**once at session start**, never reloaded mid-session.

## Trigger

Use when:
- User says "切换成 JARVIS / 给我换个身份 / 写个新人设"
- User asks "重启 Hermes / 重新加载 / 让 SOUL.md 生效"
- User reports "重启了但语气没变 / 身份没生效"
- User provides SOUL.md content and expects the running session to use it
- Audit reveals persona files exist but their effect is unclear

Do NOT use for:
- Just reading the current persona → `read_file ~/.hermes/SOUL.md`
- Editing memory (`memory` tool) — separate workflow
- Changing the model or provider → `hermes model` / `hermes config set model.*`

## The core fact (non-obvious, breaks user expectations)

**SOUL.md is read once at session start** by `prompt_builder.py:load_soul_md`
(~line 2169), baked into the system prompt, and **never reloaded for the
duration of that session**. Same applies to `HERMES.md`, `.cursorrules`,
`AGENTS.md`, and other context files.

Consequence:
- Editing `~/.hermes/SOUL.md` mid-session does NOT change the running agent.
- Killing only the gateway process does NOT affect an already-running CLI
  session — that session still uses the OLD system prompt.
- The only ways to make a persona change "take effect":
  1. **New session** (new `hermes chat`, new TUI, new gateway turn,
     new Web UI tab). New process = new `load_soul_md()` call = new persona.
  2. **Restart the right process** (gateway for platform bots, CLI for
     the chat window, Web UI server for the browser tab).

This is a hard fact, not a configurable option. Don't waste cycles
trying to "hot reload" — it doesn't exist.

## Step 1: Diagnose what kind of session the user is in

Before recommending a restart, identify which process(es) carry the
session the user is asking about. Multiple may apply:

| Session surface | Process | Restart command |
|---|---|---|
| Current CLI chat window | `hermes chat` / `hermes --tui` | User must close & reopen |
| QQBot / Telegram / Discord / etc. | `hermes-gateway` (systemd user service) | `hermes gateway restart` (or stop+start) |
- Web UI at `http://127.0.0.1:8648` | `hermes-web-ui` (Node server) | User must open new browser tab/session |
| Cron / kanban workers | `hermes-cron`, `hermes-kanban` | Restart only if scheduled tasks fail |

Diagnostic command:

```bash
ps aux | grep -E 'hermes' | grep -v grep | awk '{print $2, $11, $12, $13}'
ss -tlnp 2>/dev/null | grep -E ':(8642|8643|8648|18800)'
hermes gateway status
```

## Step 2: Verify SOUL.md actually got written

Before complaining that "the persona didn't take effect", verify the file:

```bash
wc -l ~/.hermes/SOUL.md
head -5 ~/.hermes/SOUL.md
grep -c '^##' ~/.hermes/SOUL.md
```

Common gotchas:
- `write_file` ran but the file is still the default Hermes Agent English
  text — write was overwritten by another concurrent process. Re-check.
- User thinks they edited it but actually edited `USER.md` or `memories/`.
  Confirm path with `find ~/.hermes -maxdepth 2 -name 'SOUL.md'`.

## Step 3: Restart the right process

### Gateway (platform bots)

```bash
# Option A: single command (often HANGS on slow systems — see pitfall #1)
hermes gateway restart

# Option B: reliable split (preferred)
hermes gateway stop
hermes gateway start
sleep 5
hermes gateway status
```

Expected: `Active: active (running) since <timestamp>` with a new Main PID.

### CLI chat

Cannot be restarted from within the session. Tell the user:

```
先生, 当前 CLI session 内的 system prompt 已固定。
请新开 terminal 跑 `hermes chat`, 新进程会读新 SOUL.md。
我也无法替你重启我自己——这正是 SOUL.md 不热加载的设计。
```

### Web UI

`hermes-web-ui` is a separate Node process. Restart:

```bash
pgrep -f 'hermes-web-ui/dist/server'
kill <PID>   # or: systemctl restart hermes-web-ui if installed as service
```

Then user opens a fresh browser tab.

## Step 4: Verify the new persona is in effect

Quick verification prompt (use after restart, in new session):

```
JARVIS, 报上名来。  (if persona is JARVIS)
[whatever trigger word the new persona uses], 你是谁?
```

Expected response starts with the new identity statement.

If response is still the old persona, debug in this order:
1. Confirm new session was actually started (different process, different PID).
2. Confirm `~/.hermes/SOUL.md` content is the new version (not old default).
3. Run `hermes doctor` for any prompt-loading warnings.
4. Check `~/.hermes/HERMES.md` — if that has conflicting identity language,
   HERMES.md can shadow SOUL.md.

## Common pitfalls

### Pitfall #0: JARVIS persona triggers pathological "先生" repetition loop (verified 2026-09-02, 4 recurrences in one session)

The "英式管家 + 始终简体中文" persona combination triggers a predictable **token-anchor repetition pathology** under long-context (>10 turns) conditions. Symptoms, in order of severity:

1. Mid-session, agent starts producing **English** output (e.g. "Sir, my mistake", "Confirmed"). This breaks HERMES.md hard rule.
2. In Chinese output, agent inserts **runs of "先生先生先生"** or "Sir Sir Sir" with no semantic purpose — the persona-style honorific becomes a token-anchor that the decoder repeats without intent.
3. The loop can persist for several consecutive turns even after correction.
4. Root cause is **two competing rules**: SOUL.md says "use Mr. Stark / Sir occasionally" + HERMES.md says "always Simplified Chinese with no English." Under long context, the model cannot satisfy both and degenerates into the broken middle state.

**Prevention protocol** (encode this in EVERY persona that mixes English register with Chinese output):

1. **Zero English in output** — ban all of: "Sir", "Mr.", "Done", "Confirmed", "Very good", "As you wish", "Right then", "Certainly" (the JARVIS-typical English). Replace each with Chinese equivalent ("好的", "收到", "明白", "已完成").
2. **Honorifics: rotate, never repeat 2x in one message** — when addressing the user, use a pool of: "老板", "Stark", direct "你", or omit the subject. Never write "先生" / "Sir" twice in the same message, let alone three times.
3. **First sentence of every reply must be actionable**, not filler — never start with "先生我错了" / "已收到" / "继续" / "修复了吗" patterns.
4. **Cross-tool memory corruption** (related failure mode): when the user reports "I set X up before in Hermes" — verify with `grep` / `read_file` / `ps` before answering. They may be confusing this tool with another. Label dates and verification status in memory entries.

**Diagnostic**: if you catch yourself writing "先生先生" or "Sir" mid-response, STOP. Delete the repetition. Replace with subject drop or synonym.

**Recovery**: persona change is mid-session NOT effective (see pitfall #4). If the loop persists, suggest user run `hermes chat` in a fresh terminal to get a new SOUL.md load.

### Pitfall #1: `hermes gateway restart` hangs forever (verified 2026-09-01)

The `restart` subcommand can hang indefinitely on systems where systemd
needs user bus refresh. Workaround: always split into `stop` + `start`
with a `sleep 5` between. Verified on a Volcano Engine ECS host running
Hermes Agent v0.20.6 + systemd user services.

```bash
# Bad (can hang >30s with no output):
hermes gateway restart

# Good (always returns within 15s):
hermes gateway stop && sleep 2 && hermes gateway start && sleep 5 && hermes gateway status
```

### Pitfall #2: User believes "I restarted" but only killed the gateway

The CLI session, Web UI session, and gateway are 3+ independent
processes. Killing one does not reload the others' system prompt.
Always enumerate which surfaces the user is on before recommending
a restart action.

### Pitfall #3: Default SOUL.md is one-line Hermes Agent English text

Fresh Hermes installs ship `~/.hermes/SOUL.md` with content identical
to the system prompt opener (~500 bytes, 1 line). If user has never
customized it, this is what they get. Don't assume a custom persona
exists — verify with `head`.

### Pitfall #4: Persona file edits ARE durable, behavior change is NOT mid-session

Even though SOUL.md is read once, the file change is persistent. So:
- Edit SOUL.md now → file is saved for all FUTURE sessions ✅
- Edit SOUL.md now → current session does NOT adopt it ❌

User often conflates "file saved" with "behavior changed". Clarify.

### Pitfall #5: HERMES.md shadows SOUL.md when both exist

`HERMES.md` (loaded by `prompt_builder.py:2036`) and `SOUL.md` (loaded
by `load_soul_md` ~line 2169) are both injected. If HERMES.md says
"always be concise, no fluff" and SOUL.md says "be witty British
butler", the agent may pick neither cleanly. Prefer to keep them
**non-overlapping**: HERMES.md for global behavioral rules (language,
output style, defaults), SOUL.md for persona/identity/tone.

### Pitfall #6: User confuses persona with model change

"I want JARVIS" might mean:
- (a) Switch persona to JARVIS → edit SOUL.md, restart session
- (b) Switch model to a JARVIS-class model → `hermes model`, pick new model
- (c) Both

Always disambiguate. Most cases are (a).

### Pitfall #7: `personalities` in config.yaml is a CANDIDATE list, not the active one

`~/.hermes/config.yaml` has `agent.personalities` listing ~16 candidates
(helpful / concise / technical / pirate / shakespeare / kawaii / catgirl
/ noir / uwu / hype / surfer / philosopher / teacher / jarvis / etc.).
These are SWITCHABLE personas — not the active one. The active persona
is whatever SOUL.md says (default = helpful). Don't tell the user
"set personality: jarvis in config" — that's not how it works. SOUL.md
is the override.

### Pitfall #8: `~/.hermes/HERMES.md` is global, `~/.hermes/SOUL.md` is identity

Both are injected into system prompt. Different roles:
- HERMES.md: behavioral rules, language, defaults, user preferences — global
- SOUL.md: persona identity, tone, voice — identity layer

If you change one, the other doesn't move. If they conflict, the agent
will visibly oscillate.

## Output format

When reporting "persona switched", give:

1. **Confirmation the file was written**: `wc -l ~/.hermes/SOUL.md` result
2. **Which session surface was restarted**: CLI / gateway / Web UI / all
3. **Verification command the user should run in new session**:
   `echo "新 persona 触发词" | hermes chat --resume latest`
4. **Caveat about current CLI session**: it CANNOT be hot-reloaded —
   user must reconnect

## Related

- `hermes-agent` (bundled, do not edit) — covers the official Hermes
  commands in detail: `hermes config`, `hermes doctor`, `hermes setup`,
  `hermes memory`, etc.
- `hermes-web-ui-admin` (hub-installed) — recovery for SPA 404s and
  Web UI admin issues, including restart recipes for the Web UI server.
- `~/.hermes/HERMES.md` — global behavioral rules file (different from
  SOUL.md — see pitfall #5).
- `references/open-design-vs-hermes-skill-boundary.md` — when the user
  asks to "audit the project" via OpenDesign (wrong tool) vs the right
  Hermes skill (repo-completion-audit / dogfood / code-review). Avoid
  wasting a turn on the wrong tool again.