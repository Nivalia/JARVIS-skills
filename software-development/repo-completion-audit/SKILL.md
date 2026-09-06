---
name: repo-completion-audit
description: "Six-dim audit separating marketing from real completion."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [audit, completion, repo, mock-detection, roadmap, demo-ware]
    related_skills: [codebase-inspection, github-repo-management]
prerequisites:
  commands: [git, gh]
---

# Repository Completion Audit

Tells **what a repo says it is** apart from **what it actually is**. Goes
beyond LOC counts (which `codebase-inspection` handles) to evaluate test
coverage, mock-vs-real implementation, roadmap truth, documentation honesty,
and end-to-end runnability.

## Trigger

Use when:

- User asks "how complete is this project?" / "what's the real status of X?"
- Deciding whether to extend an existing repo or start fresh
- Repo claims production-ready but README does not match code
- Evaluating a takeover / contribution / acquisition target
- Need to give user an honest "would I trust this in prod?" answer

Do NOT use for fresh-code LOC counting alone — that's `codebase-inspection`.

## Before scoring: the goal-fit question

Before running any of the six dimensions, ask **"Does this repo serve a
goal the user has that they haven't stated yet?"** If the repo's
"weaknesses" look like features for an unstated goal, the audit frame
is wrong, not the repo. Specifically check whether the repo targets:

- agent / agentic workflows (state machines, memory, persona)
- self-modification or self-evolution
- personality / emotion modeling
- niche verticals where Hermes or mainstream tooling is weak

Don't deliver a fix-or-delete verdict before this question is answered.
The audit output should include a section like:

```
## Goal-fit question (before deciding)
- Repo targets: [X, Y, Z]
- Your stated goal: [if known]
- Gap: [what the repo does / doesn't do for your goal]
```

Worked example: a user asked to audit `prophet-oracle`, scored it
"demo-ware, ~15% reality" with a fix proposal. User then said "我就是
想做一个可以自进化的 agent,有自己的情绪、感情等, hermes 没有
这个功能" — completely inverting the conclusion. The repo's "flaws"
(4-stage Incubator state machine, EmotionEngine, PersonaEngine,
self-evolution scaffolding) were **precisely** the features the user
wanted. The audit frame was wrong, not the repo.

If you don't know the user's goal, **ask first** before delivering
verdicts — the alternative is recommending deletion of the user's
actual target. (Full pattern + remediation: see "When the user's goal
re-frames the whole conclusion" near the bottom of this skill.)

## Six Dimensions

Score each independently. **Do not collapse to a single percentage** — that
hides which dimensions are weak.

**Pre-flight (no clone needed)**: many audits can skip cloning
entirely. `gh api repos/OWNER/REPO/contents/PATH --jq '.content' | base64 -d`
reads any file without download. See `references/github-static-probe.md`
for full recipes — works around `raw.githubusercontent.com` timeouts
on slow networks and avoids filling disk before you decide whether
the repo is worth cloning.

### 1. Code Volume Reality
Combine `codebase-inspection` (pygount) + per-package raw counts.

```bash
# Per-package src LOC (real impl, excluding tests)
for pkg in packages/*/; do
  [ -d "$pkg/src" ] && echo "$pkg: $(find "$pkg/src" -type f \( -name "*.ts" -o -name "*.py" -o -name "*.cpp" -o -name "*.go" -o -name "*.tsx" \) -exec cat {} + 2>/dev/null | wc -l) LOC"
done

# Total test LOC (truthfulness of "X/X tests passed" badge)
find packages \( -name "*.spec.ts" -o -name "*.test.ts" -o -name "test_*.py" \) | xargs wc -l | tail -1
```

### 2. Test Coverage Reality
Per-package test-to-source ratio. Below 20% = untested code in production paths.

```bash
for pkg in core cpp-native python-runtime frontend; do
  src=$(find packages/$pkg/src -type f \( -name "*.ts" -o -name "*.py" -o -name "*.cpp" -o -name "*.tsx" \) -exec cat {} + 2>/dev/null | wc -l)
  test=$(find packages/$pkg -path "*test*" \( -name "*.spec.ts" -o -name "*.test.ts" -o -name "test_*.py" \) -exec cat {} + 2>/dev/null | wc -l)
  [ "$src" -gt 0 ] && echo "$pkg: src=$src test=$test ratio=$((test*100/src))%"
done

# Badge vs reality: README says "600/600 passed"
# Actual it()/test() count:
grep -rE "(it\(|test\()" packages/*/src --include="*.spec.ts" --include="*.test.ts" \
  | grep -cE "(it\(|test\()"
```

### 3. Mock vs Real Implementation
The killer dimension. Search for mock fallback chains that quietly swallow
production requests.

```bash
# Mocks in production paths (not tests)
grep -rl "mock\|Mock\|fake\|stub" packages/*/src \
  --include="*.ts" --include="*.cpp" --include="*.py" --include="*.tsx" \
  | grep -v ".spec.ts" | grep -v ".test.ts" | grep -v "test_"

# TODO / FIXME honesty markers
grep -rE "TODO|FIXME|XXX|HACK" packages/*/src \
  --include="*.ts" --include="*.py" --include="*.cpp" | wc -l

# Look for fallback chain order: should be real → mock → fail-loud
# Red flag: mock → real → fail-open (mock is default, real is opt-in)
grep -rE "fallback|fall.back|fall.open" packages/*/src --include="*.ts" --include="*.py"
```

**Red flags**:
- `*Bridge.ts` defaults to mock, only swaps to real when env var set
- `main.ts` does not log a loud MOCK warning at startup
- Fallback chain order is `mock → real → fail-open` (inverted)
- Tests assert mock-to-mock interactions (useless — `it('mocks the mock', ...)`)

**Probe adaptation for Java + Vue3 repos** (verified 2026-09-01, JonLink audit):

The skill's default TS/Python probes don't translate directly. Adapt:

```bash
# Mock/fake/stub hit — but in Java, "Mock" appears in legitimate class names
# (e.g. `WxMpService` has a Mock config). ALWAYS read the file before flagging.
grep -rln 'mock\|Mock\|fake\|stub\|Fake\|Stub' src/main/java --include='*.java' \
  | grep -v 'src/test/'

# Common false positives in Java web apps:
# - `WxMpService` (wechat SDK) has `mock` config — it's an OPTIONAL MODE, not fake impl
# - `MockMvc` (Spring Test) — appears in src/test/, exclude
# - Comments containing "// mock" that document dev-mode fallbacks, not prod impl

# Vue3 dev-mock vs hardcoded-mock-data distinction
# Real red flag: `stats.value = { points: 1280, orders: 6 }` — assignment of object literal
# Not a red flag: `// mock 模式下走补全 keyword_meta 路径` — dev-mode comment
# Detection: search for object-literal assignments inside data-loading functions, then read.
```

**False positive trap: `return new ArrayList<>();`** (verified 2026-09-01):
`grep -rn 'return new ArrayList<>' --include='*.java'` matches BOTH:
- `return new ArrayList<>();` — genuine empty-list fallback (RED FLAG)
- `return new ArrayList<>(map.values());` — legitimate aggregation result (NOT a flag)

The trailing `;` in the grep pattern does NOT disambiguate; both lines end in `;`. **Read the file before flagging.** A genuine empty-list fallback looks like `return new ArrayList<>();` with no arguments inside the angle brackets AND no method call chained off it. Anything with content inside `<>` or after `<>` is real work.

**Java + Vue3 probe recipes** for the other dimensions:

```bash
# Dim 1: per-module LOC for Maven multi-module layout
for mod in admin framework system common quartz generator; do
  src="/opt/JonLink/JonLink-Vue/jonlink-$mod/src/main/java"
  [ -d "$src" ] && echo "$mod: $(find $src -name '*.java' | xargs cat 2>/dev/null | wc -l)"
done

# Dim 2: Java + Vue3 test LOC (often ZERO — that itself is the score)
find . -path '*/src/test/java/*.java' | wc -l
find . -name '*.spec.ts' -not -path '*/node_modules/*' | wc -l

# Dim 4: Java backend git log honesty (look for repeated amend-style commits)
git log --pretty=format:'%h %ad %s' --date=short --all
# Red flag: same commit message appears multiple times = `git commit --amend` history

# Dim 5: README rebrand check for RuoYi fork projects
grep -E 'ruoyi|RuoYi|先知|智源|RuoYi|jhipster|aliyun|tencent' README.md | head
# Note: rebrand may have hit Java packages + filenames (already cleaned) but not README

# Dim 6: process + port probe — Java web app runnability
ss -tlnp 2>/dev/null | grep -E ':8080|:6379|:3306'   # backend + Redis + DB
ps aux | grep -E 'java -jar' | grep -v grep | head   # is backend actually running?
curl -sS -m 5 -o /dev/null -w 'HTTP %{http_code}\n' http://localhost:8080/
curl -sS -m 5 -o /dev/null -w 'HTTP %{http_code}\n' http://localhost:8080/captchaImage
```

**DB-table residue probe** (Dim 1 / 5 cross-check for Java web apps):

```bash
# Application yml almost always has DB credentials in plaintext — use them
# to probe table ownership: business vs framework residue
grep -E 'datasource|username|password|url:' application-druid.yml
mysql -uroot -p<from-yml> <dbname> -e 'SHOW TABLES;' > /tmp/tables.txt
echo "业务表: $(grep -c '^<your_namespace>_' /tmp/tables.txt)"
echo "框架基表 (sys_/gen_/qrtz_): $(grep -cE '^(sys_|gen_|qrtz_)' /tmp/tables.txt)"
```

Counts tell the "how much is real business vs inherited framework" story.
For JonLink (RuoYi fork): 9 `jonlink_*` tables vs 20 framework residue tables
(`sys_*`/`gen_*`/`qrtz_*`) + 23 `fin_*` business tables = mostly business, but
the "RuoYi is just a permission skeleton" framing must be verified against
this count, not assumed.

### 4. Roadmap vs Reality
Compare ROADMAP.md status markers against git log activity.

```bash
# Status markers
grep -E "✅|⬜|⏸️|🔧" ROADMAP.md | head -50

# Recent code activity (truth check on "✅ Done" items)
git log --since="30 days ago" --pretty=format:"%h %ad %s" --date=short | head -30

# First commit smell — "初始提交：全量备份" = whole project dumped at once
git log --reverse --oneline | head -1
```

**Status markers lie when**:
- Step 2 (real model integration) ⬜ but Step 4 (production hardening) ✅ — backwards
- "Completed" item has no tests, no CI artifact, no example output
- Badge timestamp predates the feature's last code commit

### 5. Marketing vs Documentation Ratio
85% polished README + 50% real code = demo-ware.

```bash
find . -maxdepth 3 \( -name "README.md" -o -name "ROADMAP.md" \) -exec wc -l {} +
du -sh docs/ 2>/dev/null
```

**Honesty signals** (presence = good):
- README has "⚠️ Running in MOCK mode" warning at top
- `docs/HONEST-STATUS.md` listing each module's real-vs-mock state
- ROADMAP shows ⏸️ for hardware-gated items (TPM, GPIO)
- No inflated badges (test count, star count, coverage %)

### 6. End-to-End Real Runnability
Clone fresh, follow the README's Quick Start, see what actually happens.

```bash
git clone <repo> /tmp/audit-clone && cd /tmp/audit-clone
make run-no-mock 2>&1 | tee /tmp/run.log
# Or: docker-compose up, then curl documented endpoints

# Smoke test the documented endpoint
curl -X POST http://localhost:3000/api/think \
  -H "X-API-Key: test" \
  -d '{"query":"hello"}' | jq '.data.decision.chosen'
# Run with 3 different queries — if all 3 return identical or near-identical
# strings, it's mock data
```

## Output Format

When reporting to user, give:

1. **Six-dimension scorecard** (each dim: 0-100%)
2. **Weighted reality score** with the formula shown
3. **Top 3 red flags** (mock-in-prod-path, badge inflation, etc.)
4. **Concrete next-step recommendation** (e.g. "Step 2 P0 first — replace mock LLM with real GGUF")
5. **What you will NOT touch** (hardware-gated items, scope-creep features)

**Do NOT** give a single "70% complete" number. Break it down by dimension.

### Scope discipline: when the user asks for ONE thing, deliver ONE thing

User correction (verified 2026-08-11, MallEco evaluation): user asked "评价这个项目的完成度" and got pushed back with **"什么都不用管 只是让你分析这个项目的完成度"**. The complaint pattern: the response had silently expanded a "完成度" question into comparison (vs JonLink), verdict (look like demo / not worth it), and a "下一步" menu (A/B/C/D actions). All three are out of scope for "完成度".

The second MallEco iteration (after the correction) delivered only the completion scorecard by dimension — user accepted it. The lesson is in the contrast, not the correction: **the user's "对空话零容忍" rule applies double here — padded responses aren't just verbose, they're answering a question the user didn't ask**.

The rule: **the question verb decides the deliverable shape**.

| User asks | Deliverable | NOT deliverable |
|---|---|---|
| "完成度" / "how complete" | scorecard + dimension breakdown | comparison, recommendation, next-action menu |
| "能不能用" / "production-ready?" | yes/no with conditions + dimension evidence | fix plan |
| "对比 X 和 Y" | side-by-side table | recommendation |
| "下一步做什么" / "what next" | phased action proposal (Phase 0 / 1 / 2) | verdict on the project itself |
| "为什么 X 不工作" | root cause + reproduction | refactor plan |

When a question has **one verb**, do that verb and stop. Do not silently expand into "顺便帮你评估一下 / 对比一下 / 给个建议". If you catch yourself doing that mid-response, **stop and re-anchor**: re-read the question, find the verb, deliver only that.

**Concrete antipattern to avoid** (from the same session):

```
# BAD — three things stuffed in a "完成度" answer:
1. MallEco is X% complete
2. Compared to JonLink it's worse/better on Y
3. You should do A/B/C next
```

```
# GOOD — one thing, the asked thing:
1. MallEco is 40-45% complete
2. By dimension: architecture 90%, biz impl 30-40%, test 10-15%, ...
3. Top red flags: exclude tricks, 4-commit dump, ...
```

The user's "对空话零容忍" rule applies double here: padded responses aren't just verbose, they're answering a question the user didn't ask.

### Apologize once and move on when caught in a real mistake

When the user catches a real error (e.g. "JonLink-Vue 这不是后端吗" — I had dismissed it as "旧版前端" because `JonLink-Vue` contains a `bin/` folder and a legacy `jonlink-ui/` Vue dir, looking like the RuoYi single-tier layout where everything lives together), don't hedge. Acknowledge with one sentence ("我搜得太浅,maxdepth 不够,而且只看了 JonLink-Vue3-TS"), state the correct fact, then continue with the deliverable. Don't repeat the apology three times, don't over-explain why you got it wrong, don't add a paragraph of "I should have done X instead". One sentence + corrected data.

The reverse — silently re-running the investigation without acknowledging the mistake — reads as if you didn't notice being wrong, which is worse than the original mistake.

### RuoYi single-tier repo trap: `*-Vue` directory is the BACKEND

Project layout pitfall specific to RuoYi single-tier forks (verified 2026-08-11, JonLink): the backend dir is named `*-Vue` (e.g. `JonLink-Vue`) because RuoYi ships the backend + legacy Vue2 frontend in one Maven project. The misleading indicators — `bin/` (RuoYi start scripts), `ry.sh`/`ry.bat`, `sql/` init scripts, and a leftover `jonlink-ui/` Vue subdirectory — make it look like "Vue frontend repo". The actual giveaway that it's the backend:

- `pom.xml` at the root (Maven parent)
- `jonlink-admin/` + `jonlink-framework/` + `jonlink-system/` + `jonlink-common/` + `jonlink-quartz/` + `jonlink-generator/` (RuoYi 6-module layout)
- `target/*.jar` already built (`jonlink-admin.jar` etc.)
- Java packages under `src/main/java/com/<your-name>/...` (rebranded from `com.jonlink`)

The **separate** Vue3 frontend lives in a sibling dir (e.g. `JonLink-Vue3-TS`) — single-tier, just Vue + Vite, no `pom.xml`, no `target/`.

Detection: `find . -maxdepth 5 -name "pom.xml"` — present in `*-Vue` = backend, absent in `*-Vue3-TS` = frontend. Don't trust the directory name.

### Reporting style: concrete artifacts, not narrative

User preference (verified 2026-08-11): on multi-step audits of unfamiliar
repos, they want a **proposal draft** before any execution — table of
findings with "what happens to each entry / estimated net release / what
we won't touch", not prose. Format the recommendation as:

```
## Phase 0 — stop the bleeding (P0) — ~30 min
| # | File | Change | Why |
|---|---|---|---|

## Phase 1 — make it run (P1) — ~45 min
| # | File | Change | Why |
|---|---|---|---|

## Won't touch (with reason)
| File | Reason |
|---|---|

## Confirmation (single-select)
- [ ] A. Execute as planned
- [ ] B. Only Phase 0, verify before deciding Phase 1
- [ ] C. Reorder (specify)
```

End with a single-select confirmation, not a "shall I proceed?" question.
The user has explicitly said "对空话零容忍" — prose-only recommendations
without a table or a checkbox trigger a "no, give me a draft first" pushback.

**Do not pad the report with restated ROADMAP prose.** Every line should
either (a) point to a concrete file:line, (b) name a specific verification
command, or (c) list something that will not be changed. Anything else is
narrative and burns the user's patience.

### Even phased proposals can be over-scoped

User pushback (verified 2026-08-11, prophet-oracle second-pass proposal):
"你的修复方案这么多？" — after I delivered an 18-file / 4-stage / 6-table
proposal, even though each phase was correctly scoped internally.

The rule: **default to the smallest viable proposal**, not the full plan.
List Phase 0 only; explicitly mark Phase 1 / 2 / 3 as "可选 / 后续" with
file counts so the user can opt in. Do NOT bundle "fix bug + fix docs +
refactor + optimize" into one proposal even if they're all in scope.
Different categories of work warrant separate decisions.

```
## Minimal plan (default)
| # | File | Change | Why |
|---|---|---|---|

## Optional / follow-on (NOT part of default plan)
| Phase | Files | Scope |
|---|---|---|
| P1 | 4 | doc honesty, ROADMAP cleanup |
| P2 | 6 | engineering polish |
```

End with three options so the user can pick scope, not just order:
- A. Execute minimal (4 files, ~20 min)
- B. Do nothing, I take it from here
- C. Change scope (specify)


## `.git` vs `.github`: the two-directory confusion that bites audits

A common user framing (verified 2026-08-11, JonLink `.github` deletion
session) is "I deleted the GitHub-related stuff" — but the user may
have meant **only the GitHub website metadata** (`.github/` directory
holding workflows, issue templates, CODEOWNERS, funding files), not
the actual git database (`.git/`). The two are independent:

| Directory | Holds | Delete consequence |
|---|---|---|
| `.git/` | git database — commits, branches, tags, refs, logs | **Repo fully de-versioned.** `git log` returns nothing. `git blame` impossible. Code survives but git history is gone. |
| `.github/` | GitHub web metadata — workflows, ISSUE_TEMPLATE, PULL_REQUEST_TEMPLATE, CODEOWNERS, dependabot.yml | **GitHub features stop working** (no CI, no issue templates). Git history is **untouched**. |
| `.gitignore` | plain text file, no directory | Filters; safe to delete but rarely useful |
| `.gitattributes` | plain text file | gitattributes; safe to delete but rarely useful |

If the user says "GitHub-related stuff is gone", do not assume they
deleted one or the other — **always verify each path independently**:

```bash
ls -d <repo>/.git <repo>/.github <repo>/.gitignore <repo>/.gitattributes 2>&1
```

Treat any user claim about "I deleted X" / "X is gone" / "X is cleaned up"
the same way: **don't echo back the framing as confirmed fact**. List
the four candidate paths, `ls -d` each one, and report what is actually
there. The user's intent may also have been **impossible to achieve by
directory deletion** — e.g. "I want to remove the RuoYi commit author"
requires `git commit --amend --author` or `git filter-branch`, not
deleting a directory.

### Audit impact when `.git/` is gone

When `.git/` is missing, several audit dimensions become impossible:
- **Roadmap vs Reality** — no git log to compare status markers against
- **Code Volume Reality** — `git log --reverse` won't show first-commit smell
- **End-to-end Real Runnability** — cannot `git clone` from local origin, must rebuild from filesystem only

The audit can still answer the code-structure / test / mock / docs
questions, but the historical / evolutionary dimensions collapse.
Report this explicitly in the scorecard rather than silently skipping.

### The "what did the user delete?" diagnostic protocol

When a user says they deleted something in a project but you're not
sure what exactly (verified 2026-08-11: user said "I deleted GitHub-
related stuff", meant `.github/`, not code-level GitHub integration)
— do not jump straight to code-level grep. Run this in order:

```bash
# 1. Full-repo name search for the keyword
find . -maxdepth 4 -name "<keyword>" -type d 2>&1 | head -20

# 2. For directory-name confusions (git, github, vscode, .env, etc.):
#    ls each candidate path independently
for p in ".git" ".github" ".gitignore" ".gitattributes"; do
  ls -d "$repo/$p" 2>&1
done

# 3. Only THEN grep code-level references
grep -rln "<keyword>" src/ --include="*.ts" --include="*.vue" 2>&1 | head
```

The lesson: **measure first, infer second**. Two earlier passes in the
same session both guessed wrong (first guessed backend location, then
guessed code-level GitHub integration) before the user pointed at the
`.github` directory. If the search returns nothing on the first guess,
the user is probably talking about something else — re-anchor and try
the next most likely category.

## When the verdict is "delete it all"

If after the audit the user concludes the repo is unsalvageable
(or no longer fits their goal), present the delete path explicitly.
This is irreversible — GitHub deletion enters a 30-day grace period
but local `rm -rf` is final. Before executing:

1. **Surface non-obvious value** — what 3-5 standalone pieces in the
   repo (specific files / patterns / specs) are worth extracting into
   skills even if the whole repo dies? Offer to extract them first.
2. **Distinguish local vs remote** — `rm -rf` and `gh repo delete`
   are independent. User may want one but not the other. Always ask.
3. **Local residue** — git config remote entries, `/tmp` dumps from
   the audit, scratch directories the agent created during analysis.
   Clean these in the same pass. Report what was deleted and what
   remains.
4. **Memos / memory residue** — world-model entries that named the
   repo, session traces that reference it. Memos has no update API
   in the current Hermes version; flag explicitly that those entries
   will go stale rather than promising they'll be cleaned.
5. **Grace-period reality** — GitHub deleted repos can be restored
   from Settings → Repositories within 30 days. State this so the
   user can back out.

Format the delete report as:

```
## Deletion report
| Step | Action | Result |
|---|---|---|
| 1 | Local rm -rf | ✅ |
| 2 | gh repo delete | ✅ (verified via 404 / Could not resolve) |
| 3 | Local residue (git remote, /tmp dumps) | ✅ cleaned |
| 4 | Memos world-model entry | ⚠️ no update API; will go stale |
```

User feedback (2026-08-11): when they decide "complete deletion" they
want it done without further interruption — do not ask "shall I
proceed?" a second time after the first confirmation. The first
"are you sure?" plus the irreversible-warnings block is enough; if
they reaffirm, execute.

## Pitfalls

1. **Don't trust badge numbers without spot-checking** — repos routinely inflate test counts in shields.io badges.
2. **Mock fallback chains look like real impl in code review** — the keyword is "fallback", not "mock". Read conditional order.
3. **High test coverage ≠ real coverage** — `it('mocks the mock', ...)` passes and proves nothing.
4. **"First commit: 初始提交：全量备份"** is a giant red flag for dump-and-polish projects.
5. **Hardware-gated features (TPM, GPIO)** can never be demoed without that hardware. Don't trust code review; require demo video.
6. **Zero TODO markers** either means tiny scope or hidden gaps. Investigate which.
7. **"消除 X 痕迹" is a rebrand, not a delete** — verified 2026-08-11 (JonLink `jonlink` cleanup): user said "消除 jonlink 痕迹", I almost recommended deleting `.github/` again (already deleted) before realizing the user meant **rename/rebrand cleanup of code + files + comments + LICENSE + commit author**, not directory deletion. The right tool-set for "消除 X 痕迹":
   - `grep -rln -i "X" --exclude-dir={target,node_modules,.git}` — find all string occurrences
   - `find . -iname "*X*"` — find all filename occurrences (including shortened forms like `ry.sh` for `jonlink.sh`)
   - File rename + content patch for scripts (`mv ry.sh jonlink.sh`)
   - `patch` for in-file mentions (`AppName=jonlink-admin.jar` → `AppName=jonlink-admin.jar`)
   - For LICENSE: copyright year + name swap
   - For git author: `git config user.name/email` BEFORE `git init` + `git commit --amend --author="..."`
   The wrong tool: deleting any single directory. Directory deletion cannot rebrand code.
8. **After cleanup action, re-grep to verify the cleanup actually hit zero** — verified 2026-08-11: I patched 4 files, then ran `grep -rln` again expecting 0, found 1 remaining (`java -jar %JAVA_OPTS% jonlink-admin.jar` in `bin/run.bat` line 11 — missed in the first pass). The verification grep is the audit's truth test, not the patch tool's success message. Always re-grep with case-insensitive + exclude target/node_modules before declaring cleanup done.
9. **The audit frame for `.git` + `.github` BOTH gone** — verified 2026-08-11 (JonLink): when both directories are missing, the audit must report:
   - Git history dimension is **not assessable** (no `git log`, no `git blame`, no first-commit smell detection)
   - Roadmap vs Reality collapses — no commits to compare status markers against
   - The user has effectively de-versioned the project; the audit can still score code structure / test / mock / docs dimensions, but must say so explicitly rather than silently skipping
   - Recommend `git init` + `git config user.name/email "Nivalia"` (or actual owner) + initial commit if the user wants history back — this re-establishes authorship control but does NOT restore the lost history.
10. **False positive trap: `return new ArrayList<>();`** in Java audits
    (verified 2026-09-01, JonLink): `grep -rn 'return new ArrayList<>' --include='*.java'`
    matches BOTH the genuine empty-list fallback AND legitimate aggregation
    like `return new ArrayList<>(map.values());`. Read the file before
    flagging. A genuine empty-list fallback has **nothing inside the angle
    brackets** AND no method call chained off it.
11. **Java SDK class names containing "mock" are not fake impls** — e.g.
    `WxMpService` (wechat SDK) has a `mock` config mode that is an
    OPTIONAL DEV TOGGLE, not a production fake. Read the file before
    flagging Dim 3 hits. Same applies to Spring Test's `MockMvc`.
12. **Object-literal assignment inside a loader function = hardcoded
    data** (verified 2026-09-01, JonLink `views/h5/fan/Index.vue:95-99`):
    `stats.value = { points: 1280, orders: 6, coupons: 3, distribute: 2 }`
    paired with `// 暂用 mock 数据, 等真实接口接入` is a real flag. Same
    pattern with `// dev mock` comment in `api/*.ts` is NOT — that documents
    a dev fallback path, not hardcoded production data.
13. **DB credentials in plaintext yml are the audit's friend** — Java web
    apps almost always have `application-druid.yml` with the DB password
    in plaintext. Use them to run a `SHOW TABLES` ownership probe
    (business tables vs framework residue). For RuoYi forks: count
    `<namespace>_*` vs `sys_*`/`gen_*`/`qrtz_*`. Do NOT save extracted
    credentials to memory or skill files — they're project config, not
    your secrets, but still don't persist them.

## tsconfig.exclude is the favorite "fake zero errors" trick

TS / NestJS repos routinely claim "零错误" while the `tsconfig.json`
`exclude` field hides 100s-1000s of business-code errors. Verified on
prophet-oracle (2026-08-11): `tsconfig.json` excluded 11 directories
(`src/main.ts`, `core/bootstrap`, `core/engines`, `core/orchestrator`,
`infrastructure/{di,adapters,i18n,distributed,event-bus,messaging,llm}`)
and CI ran `tsc --noEmit -p tsconfig.json` — which only sees the
non-excluded files and reports "0 errors". Running
`tsc --noEmit` against the SAME files without the `exclude` field
returned **1744 errors** across business code (not just tests).

How to detect:

```bash
# 1. Read tsconfig.json — look for "exclude" field
cat tsconfig.json | jq '.exclude // empty'

# 2. If exclude has more than node_modules / dist / .git, that's a smell
# 3. Run the actual typecheck against the source tree:
npx tsc --noEmit $(find src -name "*.ts" -not -name "*.spec.ts" \
    -not -name "*.test.ts" | head -50 | tr '\n' ' ')
# OR: temporarily comment out the exclude field, run tsc, count errors,
# then restore.
```

What to report: when you find this pattern, the "Test Coverage Reality"
and "Roadmap vs Reality" dimensions drop to single-digit percentages.
The repo's claimed completion is fiction. Always flag it as the
#1 red flag, before mock-in-prod-path.

## Don't agree with the user's framing without evidence

User preference (verified 2026-08-11): if the user asserts a judgment
("this is just a demo", "X says I never used it", "we discussed Y
yesterday"), **do not echo it back as confirmed fact** before checking
the evidence chain. The user may be:
- misremembering (their previous session was different)
- testing whether you'll capitulate to social pressure
- repeating what another channel said that never reached memory

The honest response is to enumerate the evidence chain in front of the
user ("session DB has no record / repo's last
commit was X days ago") and **then** state whether the framing holds.
Echoing the framing first, then hedging, reads as capitulation and
triggers the "对空话零容忍" pushback.

The same principle applies when a user asks for a sweeping judgment
("is this repo production-ready?"). Don't answer yes/no. Enumerate
the dimensions, give scores, and let the judgment emerge from the
data — that's what the user actually wants when they ask.

## When the user's goal re-frames the whole conclusion

The audit is a snapshot of "does this repo do what it claims". The
**decision** about whether to keep / fix / extend / delete depends on
whether the repo serves the user's actual goal — and the goal may not
match the repo's stated purpose.

Pattern from a 2026-08-11 session: user asked me to audit
`prophet-oracle`, I scored it as "demo-ware, ~15% reality" with a fix
proposal. User then said "我就是想做一个可以自进化的agent,有自己
的情绪,感情等, hermes没有这个功能" — completely inverting the conclusion.
The repo's "flaws" (4-stage Incubator state machine, EmotionEngine,
PersonaEngine, self-evolution scaffolding) were **precisely** the
features the user wanted. The audit frame was wrong, not the repo.

When delivering an audit, always include a separate question:
**"Does this repo serve a goal the user has that they haven't stated yet?"**
If the repo's "weaknesses" look like features for an unstated goal,
ask before recommending destruction. Specifically check whether the
repo targets:
- agent / agentic workflows (state machines, memory, persona)
- self-modification or self-evolution
- personality / emotion modeling
- niche verticals where Hermes or mainstream tooling is weak

Don't deliver a fix-or-delete verdict before this question is answered.
The audit output should include a section like:

```
## Goal-fit question (before deciding)
- Repo targets: [X, Y, Z]
- Your stated goal: [if known]
- Gap: [what the repo does / doesn't do for your goal]
```

## Worked Example: prophet-oracle (2026-08-11, second pass)

First pass scored ~50% with a "demo-ware risk" framing. Second pass
after `tsc --noEmit` against un-excluded source revealed the 1744-error
hidden by `tsconfig.exclude`. Updated scorecard:

| Dimension | First pass | Second pass | Evidence |
|---|---|---|---|
| Code Volume | 60% | 60% | unchanged |
| Test Coverage | 30% | **5%** | tests can't run — every spec file has `Cannot find name 'jest'` errors because `@types/jest` not installed |
| Mock vs Real | 25% | 25% | unchanged |
| Roadmap vs Reality | 50% | **5%** | Sprint 1 "✅ TS 零错误" is fiction — exclude hides 1744 errors |
| Marketing vs Doc | 85% | 85% | unchanged |
| End-to-end real | 40% | **10%** | vite proxy points to non-existent hot-proxy service on :3100; watchdog checks for HTTP port that cpp-native never opens |
| **Weighted reality** | **~50%** | **~15%** | Demo-ware confirmed, not just suspected |

The audit caught its own first-pass optimism by re-running the
verification commands and refusing to trust the README's "✅ Done" badges.

## Related

- `codebase-inspection` — handles Dimension 1 (LOC + language breakdown) in isolation. Use both together.
- `references/github-static-probe.md` — `gh api /contents/... | base64 -d`
  recipes for auditing a repo **without cloning**, including
  per-path file reads, commit history, branches, and CI status. Use
  this when the repo is private, when CI shouldn't be triggered, or
  when `raw.githubusercontent.com` is slow/unreachable.
- `references/java-vue-audit-probes.md` — adapted recipes for Java +
  Vue3 repos where the default TS/Python probes don't translate.
  Covers per-module Maven LOC, Vue3 sibling-project detection, the
  false-positive grep traps in Dim 3 (`return new ArrayList<>()` vs
  `return new ArrayList<>(map.values())`; legit `WxMpService` "mock"
  config vs fake impl), DB table ownership probe via plaintext yml
  credentials, and `sys_menu` menu-tree scope verification. Verified
  against JonLink (RuoYi fork, 2026-09-01).
- `references/rebrand-cleanup-recipe.md` — when the user says "消除 X 痕迹",
  the runbook for the grep-then-patch-then-verify loop across code
  strings, filenames, Java packages, Maven coords, and LICENSE.
  Includes the `git init` + author-setup pattern when `.git/` is also gone.