# Pitfall 46 — Browser console error from a stale `dist/` ≠ your src is wrong

This is the "dist hijack" trap that bites **after** the bootstrap is
working and your code "looks right" but the browser keeps showing
errors. Lesson:

> **A browser error trace like `chunk-X.js:74:9745` is a pointer into
> WHATEVER dist nginx (or whichever static server) is currently
> serving — NOT into your `src/` tree. Before debugging the source
> code, prove which `dist/` directory the browser is actually
> loading and confirm that dist was built from the `src/` you think
> you're editing.**

---

## Symptom

You wrote code, did `npx vite build`, the build succeeded, but the
browser devtools console shows errors like:

```
policy-view:1 Uncaught (in promise) Error: 请求参数类型不匹配，参数[articleId]要求类型为：'java.lang.Long'，但输入值为：'undefined'
    at index-DvTuw3T8.js:74:9745
    at async Ei.request (index-DvTuw3T8.js:73:2001)
    at Ei.request (index-DvTuw3T8.js:73:2097)
```

You `grep` your `src/` for the offending call site — it's gone.
You `grep` your **last `dist/`** — it's gone there too. You're
looking at an error from a **different build of the project** that
is **still being served** by the static layer (nginx or
equivalent). The error trace points into a chunk you didn't emit
from your last build.

## Diagnostic recipe — do this BEFORE debugging anything else

Run all six in one shell, ~30 seconds, they pinpoint the source:

```bash
# 1. The dist the static server (nginx / vite preview / vue dev) is serving
grep -E "root |alias " /etc/nginx/sites-enabled/* 2>/dev/null
# OR for vite preview / dev:
ss -lntp | grep -E ":81|:82|:4173"  # vite dev 5173, preview 4173; project-ports vary

# 2. mtime of the index.html the static layer sees
curl -sI http://127.0.0.1/ | grep -i last-modified
stat -c '%y %n' /opt/<project>/<frontend>/dist/index.html

# 3. The MAIN entry chunk hash the live page references
curl -s http://127.0.0.1/ | grep -oE 'index-[A-Za-z0-9_-]+\.js'
# Compare to what your last vite build emitted
ls /opt/<project>/<frontend>/dist/static/js/index-*.js | head -5

# 4. Does your current src match what's in dist?
grep -r "policy/view/history" /opt/<project>/<frontend>/src 2>/dev/null
grep -r "policy/view/history" /opt/<project>/<frontend>/dist/static/js 2>/dev/null
# If src says one thing and dist says another → your last build
# didn't reflect your last edit

# 5. Is anyone ELSE currently holding a vite / node process?
ps aux | grep -E "vite|node" | grep -v hermes

# 6. Anything on the port the browser is hitting?
ss -lntp | grep -E ":82|:83"
# Parallel vue dev / preview servers on 81/82/4173 will silently
# answer the same URL the browser used (history-mode SPA)
```

If step 1 + 4 together show that nginx serves a dist directory
whose contents include a function call that is **not** in your
current src tree, **the dist was not built from the src you think
it was**. The browser is correct. Your src is correct. They're
simply different artifacts.

## Three production scenarios that all collapse to this

### A. You forgot to `npx vite build` after the last src edit

`vue dev` (`npx vite` for dev server) hot-reloads only the browser
that opened it. **Anything served by nginx / apache / s3 is the
`dist/` directory**, which only updates when you run
`npx vite build`. Editing `src/views/<module>/index.vue` while
iterating in `vite dev` does NOT update the file the user's
browser loads when they go through the proxy.

Symptom: src has the fix, dist doesn't. Step 4 above is the
decider.

**Fix:** `cd /opt/<project>/<frontend> && npx vite build 2>&1 | tail`.
Don't `nohup ... &` for a one-shot build — wait for the foreground
process to exit 0 before trusting the dist.

### B. A different process / agent / human built the dist before you did

Common in multi-contributor setups or where autonomous flows
scaffold side projects. Birth times on
`dist/static/js/index-*.js` are earlier than birth times on files
in `src/`. Devtools error references the chunk hash from that
older build, not your most recent build.

Symptom: step 3 shows a chunk hash that doesn't appear in your
latest `npx vite build` output. The `Last-Modified` header points
to a `dist/` older than the files in `src/`.

**Fix:** don't try to chase the old code path. Blow away the dist
and rebuild:

```bash
mv /opt/<project>/<frontend>/dist /tmp/<project>-dist-<date>-backup
cd /opt/<project>/<frontend>
npx vite build 2>&1 | tail -20
# verify: new index.html, new chunk hash, mtime > src mtime
```

Also check for sibling scaffolding dirs:
`ls /opt/<project>/policy-view-app/`,
`ls /opt/<project>/something-app/`. If they exist, they're
potentially serving on a parallel port (82, 83, etc.) and may be
the actual target the browser hit.

### C. `git status` shows the src edits are deleted / untracked

You look at the git working tree, your edits are NOT there. What
you remember writing isn't on disk at all.

**Don't recreate from memory.** Stop and tell the user. A
`git reflog --since="2 hours ago"` plus a `stat` on the suspected
paths will tell you if a `git reset` ran, or if some autonomous
process rm'd them. If the files were rm'd by something other than
you, the user needs to know — they may have a hook, a deploy
script, or another agent that interferes with this directory.

If the reflog is empty (no recent commits from you) and the
working tree is clean, the edits were never committed. They were
either:
- written via `write_file` then dropped by a hook that pruned
  uncommitted files
- written into a different path than you intended

For the typo-path case:
```bash
grep -r "<a unique signature from your edit>" / 2>/dev/null | head
```
A comment, an unusual string, or a route path you introduced.
If it shows up under `/opt/<project>/X-vue3-TS-bak/` or similar,
you wrote into the wrong directory.

## Recovery template

```bash
# Step 0 — figure out which dist the user is actually seeing
echo "nginx root:"
grep -E "^\s+root " /etc/nginx/sites-enabled/* 2>/dev/null
echo "live chunk hash:"
curl -s http://127.0.0.1/ | grep -oE 'index-[A-Za-z0-9_-]+\.js'

# Step 1 — is the on-disk dist salvageable, or must it be nuked?
# Salvageable if its source files match what you want it to say.

# Step 2 — backup before nuking so other contributors' work survives
mv /opt/<project>/<frontend>/dist /tmp/<project>-dist-$(date +%Y%m%d-%H%M)-backup

# Step 3 — rebuild clean (foreground, NOT nohup)
cd /opt/<project>/<frontend>
npx vite build 2>&1 | tee /tmp/vite-build.log

# Step 4 — verify (don't trust the build command alone — verify)
echo "=== new dist contents ==="
ls /opt/<project>/<frontend>/dist/
echo "=== new chunk hash from index.html ==="
grep -oE 'index-[A-Za-z0-9_-]+\.js' /opt/<project>/<frontend>/dist/index.html
echo "=== new dist mtime (must be newer than src mtime) ==="
stat -c '%y %n' /opt/<project>/<frontend>/dist/index.html
stat -c '%y %n' /opt/<project>/<frontend>/src/

# Step 5 — confirm nginx now serves the new dist
curl -sI http://127.0.0.1/ | grep -i 'last-modified'

# Step 6 — tell the user: hard-refresh Ctrl+Shift+R
```

## When this is NOT the trap

If step 4 of the diagnostic recipe shows the dist on disk DOES
contain the same call site as your src, and the chunk hash nginx
serves matches what your last build produced, then your code IS
the problem. Switch to Pitfall 40 (silent `_withKeys(undefined)`)
or the appropriate runtime-trap reference instead.

Decision matrix:

| dist chunk hash | src has the call? | dist has the call? | diagnosis |
|---|---|---|---|
| matches your last build | yes | yes | your code's bug — debug normally |
| matches your last build | yes | no | build emitted partial output — read the full log |
| differs from your last build | yes | maybe | stale dist — nuke & rebuild (Pitfall 46) |
| differs from your last build | no | yes | someone else's build — ask the user (Pitfall 46, case B) |

## Pitfalls within the pitfall

### Don't `nohup ... &` a one-shot vite build

The shell's foreground timeout is 5 minutes, and a RuoYi-Vue3
full-build takes ~3–5 minutes. Tempting to background. Don't. You
need to read the FULL log output to catch
"warning: chunk size > 500kB",
"transform error: TS18046", or
"Rollup failed to resolve import" — these are not fatal but they
mean the build emitted a partial dist. Spawning background means
you'll see "OK exit 0" while the dist is silently broken.

If the build exceeds 5 minutes, debug that separately. Don't
paper over it with `&`.

### `dist/` is a real failure surface, not a cache

When you `mv dist /tmp/backup` and rebuild, vite re-emits every
chunk with a fresh hash. The old `index.html` referenced the old
chunks; if nginx (or browser HTTP cache) still serves any cached
response with `Last-Modified` from the old dist, the browser
fetches stale assets that don't match the new JS. Always tell the
user to **hard refresh** (`Ctrl + Shift + R`) — that's what clears
the per-URL cache and re-asks nginx.

Verify post-rebuild:
```bash
stat -c '%y %n' /opt/<project>/<frontend>/dist/index.html
curl -sI http://127.0.0.1/ | grep -i last-modified
# The two timestamps must match (or curl should be newer)
```

### A vue dev server on a parallel port can also answer

If another process launched
`npm exec vite --host 0.0.0.0 --port 82` as a "live demo"
(common scaffold gesture from an autonomous flow), and the user's
browser tab points to port 82 instead of port 80 (nginx), **all of
your nginx-side dist changes are irrelevant** — the browser is
talking to the dev server directly, which has its own hot-reload
state and may even be running against a different clone of the
repo.

Always `curl http://127.0.0.1:82/` and check what HTML / JS it
serves. If the user reported a browser error against a URL on
port 82 and nginx is on port 80, you've been editing the wrong
deployment target.

### Don't mistake `vue-tsc` errors for build errors

`vue-tsc --noEmit` will print hundreds of pre-existing type errors
that have nothing to do with your edits. RuoYi-Vue3 forks often
have a broken tsconfig that produces ~200 "Module 'vue' has no
exported member 'ref'" errors project-wide. Watch the actual
**vite output** at the end:
- `✓ built in X.XXs` = OK
- `✓ 2838 modules transformed.` then `rendering chunks...` = OK
- `Rollup failed to resolve import "X"` = real failure
- A terse `error during build:` with no further detail = check
  `tee /tmp/vite-build.log` for the actual stack

A successful `vite build` is NOT a successful `vue-tsc`.
`vue-tsc` is for type-checking; vite is what builds the dist.
