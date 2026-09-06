---
name: opendesign
description: "Drive the OpenDesign MCP server for design output."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [opendesign, mcp, design, brand, video, deck, social-cards, output]
    related_skills: [opencode, claude-code, codex, hermes-agent]
---

# OpenDesign (MCP)

OpenDesign is an MCP server (NOT a CLI, NOT a code agent) exposed inside Hermes as the `mcp__open_design__*` tool family. It spawns **design-domain** sub-agents that produce visual / audio artifacts. It is the design-output counterpart to `opencode` / `claude-code` / `codex` (which are code-output counterparts).

## What it IS vs what it ISN'T — the #1 trap

Future sessions will reflexively try to use OpenDesign for tasks it cannot do. Read this section first.

| Task | OpenDesign? | Use instead |
|---|---|---|
| Audit your codebase, find bugs, review a diff | ❌ **No** | `repo-completion-audit` (6-dim), `dogfood` (browser QA), `code-review` (PR diff) |
| Run tests / debug a failing build | ❌ No | `systematic-debugging`, `terminal` + toolchain |
| Refactor code, scaffold modules | ❌ No | `opencode`, `claude-code`, or write directly |
| Reverse-engineer / pentest | ❌ No | `reverse-skill` family |
| **Author a DESIGN.md / tokens file** | ✅ Yes | — |
| **Generate brand kit from a live URL** | ✅ Yes | — |
| **Render a 1920×1080 deck** (pitch / report / magazine layout) | ✅ Yes | — |
| **Produce HTML→video** (Hyperframes) | ✅ Yes | — |
| **Make AI music / sound design** | ✅ Yes | — |
| **Generate social-media cards** (Twitter, etc.) | ✅ Yes | — |
| **Sketch a landing page / data viz / mockup** | ✅ Yes | — |

The mental model: **OpenDesign = Canva + Figma + Suno for AI agents, scoped to design/branding/media output**. It does not see your codebase. It does not run your tests. It does not open your app in a browser.

## Available MCP tools (11 total)

All under `mcp__open_design__*`. Use `tool_search` / `tool_describe` if a tool's schema isn't already in context.

| Tool | Purpose |
|---|---|
| `list_projects` | Enumerate existing OpenDesign projects. **Will often return `[]` — that's normal, not an error.** |
| `create_project` | Create a project; subsequent file ops + runs live inside it |
| `get_project` | Single-project metadata + previewUrl when ready |
| `list_files` / `get_file` / `get_artifact` | Read project files (prefer `get_artifact` over many `get_file`s) |
| `write_file` / `delete_file` | Mutate project files |
| `start_run` | Commission a run; returns `runId` immediately, work happens async |
| `get_run` | Poll run status (queued / running / succeeded / failed / canceled); on success returns `previewUrl` and optionally `agentMessage` |
| `cancel_run` | Cancel an in-flight run |
| `list_agents` / `list_skills` / `list_plugins` / `list_resources` | Discovery — list_resources returns 316 items |
| `start_vela_login` / `get_vela_login_status` | Optional Cloud sign-in (Local Codex mode does not require it) |
| `collect_brief` / `confirm_brief` | MCP-UI interactive brief card (renders in supported clients) |

## Procedure (the canonical flow)

1. **Check whether projects exist** before assuming one does:
   ```
   mcp__open_design__list_projects
   ```
   Empty list is normal on first contact — not a failure.
2. **If the user wants a design output, create a project first:**
   ```
   mcp__open_design__create_project({ name: "...", kind: "..." })
   ```
   Project becomes the container for files + runs.
3. **Read what's available** to pick the right skill for the run:
   ```
   mcp__open_design__list_skills({...})
   mcp__open_design__list_resources({...})
   ```
   The 162 skill names live under `od://skills/<name>/SKILL.md`; 152 design-system references live under `od://design-systems/<name>/DESIGN.md`. Read the skill's full SKILL.md before dispatching.
4. **Dispatch with `start_run`** — non-blocking, returns a `runId` immediately.
5. **Poll with `get_run`** until status is terminal (`succeeded` / `failed` / `canceled`).
6. **Surface the result** to the user — `previewUrl` for visual deliverables, `agentMessage` for text-only outcomes (e.g. when the inner agent asked a clarifying question instead of producing files).

## Workflow pitfall — DO NOT `clarify()` on first contact

When the user says "use OpenDesign to check my project" (or any first-touch request that doesn't name a specific output), **don't present a multiple-choice `clarify()` form asking which interpretation**. The user will likely not engage with it (empirically: empty `user_response: ""` on first attempts), and the question reveals nothing they couldn't read in 30 seconds.

**Do this instead**, in one assistant turn:

1. Run `list_projects` + `list_resources` to ground yourself.
2. State plainly: "OpenDesign is X (output tool). It is NOT Y (audit tool). If you meant Y, here are the right Hermes skills: `repo-completion-audit`, `dogfood`, `code-review`. If you meant X, I can do A / B / C."
3. Wait for a concrete answer.

This pattern preserves momentum, demonstrates the tool's actual capability surface, and avoids the "what do you mean?" loop.

## Project state and persistence

- OpenDesign projects live on the **local OpenDesign daemon**, addressable via MCP tools.
- They are **not in your filesystem by default** — they appear via `list_projects`, not via `ls`.
- After a run, `previewUrl` is the canonical deliverable handle. Open it in a browser; do not try to read preview URLs as raw HTML through Hermes — the daemon renders them.

## Hard rules

- **Never claim "OpenDesign can audit code."** It cannot. Audit = `repo-completion-audit` / `dogfood` / `code-review`.
- **Never dispatch `start_run` without first checking `list_projects` + `list_skills`.** A blind dispatch uses defaults you cannot predict.
- **Never try to "read" a previewUrl as text.** Return it to the user verbatim.
- **Never edit another profile's OpenDesign data** (cross-profile soft guard applies to writes; reads are fine for inspection).
- If the daemon is unresponsive (`list_projects` errors instead of returning `[]`), surface that as the first observation — do not assume the daemon is healthy.

## Verification

After a `start_run`:

```
mcp__open_design__get_run({ runId: "<id>" })
```

Until status is `succeeded`, treat the run as in-flight. The default delivery to the user is the `previewUrl` (open it) or the `agentMessage` (when no preview was produced).

Smoke test (no project needed — just confirm MCP connectivity):

```
mcp__open_design__list_resources
```

If this returns 316 items, the daemon is healthy. If it returns an error, the MCP server is down — do not proceed with `start_run`.

## Reference

- `references/resource-catalog.md` — full 316-resource breakdown (162 skills + 152 design-systems), grouped by output category, with the "what each skill actually produces" notes from this session.