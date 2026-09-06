# GitHub Static Probe — Auditing Repos Without Cloning

Recipes for inspecting a GitHub repository **without `git clone`** —
faster, no disk use, no npm install, no build pre-reqs. Useful when you
just need an opinion on whether the repo is worth cloning at all, when
you're auditing many repos in batch, or when the repo is private and you
want a non-destructive read-only review.

## When this matters

- Triaging many candidate repos at once
- Pre-flight review before `git clone` (saves disk and time)
- Reviewing a repo whose CI / build you don't want to trigger
- Reading files that are too large to comfortably inspect in a browser
- Domestic / China-network conditions where `raw.githubusercontent.com`
  is slow or unreachable

## Prerequisites

- `gh` authenticated (`gh auth status`)
- A repo you have at least read access to

## 1. Top-level repo metadata

```bash
gh api repos/OWNER/REPO --jq '{
  name: .full_name,
  stars: .stargazers_count,
  forks: .forks_count,
  language: .language,
  size_kb: .size,
  default_branch: .default_branch,
  license: .license.spdx_id,
  description: .description,
  topics: .topics,
  created: .created_at,
  updated: .updated_at,
  archived: .archived,
  disabled: .disabled
}'
```

**Red flags**:
- `stars: 0` + `forks: 0` + `updated` > 6 months ago → **personal project,
  possibly abandoned**. Verify before investing.
- `license: null` while README claims "MIT License" → **license
  inconsistency**. Public repo with no license = "all rights reserved"
  regardless of what the README says.
- `size_kb > 50000` → huge repo, consider shallow clone or `gh api`
  per-path instead of clone.

## 2. List directory contents

```bash
# List top-level of a path inside the repo
gh api repos/OWNER/REPO/contents/PATH --jq '[.[] | {type, name, size}]'

# Examples:
gh api repos/Nivalia/MallEco/contents/api/src --jq '.[].name'
gh api repos/Nivalia/MallEco/contents/api/src/modules --jq '. | length'
```

**Pattern**: walk the tree breadth-first by repeatedly listing
`contents/PATH`. Use this to count modules, locate README files, find
test directories, etc.

## 3. Read a single file (most common operation)

`/contents/path` returns the file as a base64-encoded blob. Decode with
`base64 -d`. Pair this with `head`/`sed`/`wc` to inspect without
download.

```bash
# Full file
gh api repos/OWNER/REPO/contents/PATH --jq '.content' | base64 -d

# First N lines
gh api repos/OWNER/REPO/contents/api/README.md --jq '.content' | base64 -d | head -120

# Just the length
gh api repos/OWNER/REPO/contents/api/package.json --jq '.content' | base64 -d | wc -l

# Search within a single file
gh api repos/OWNER/REPO/contents/api/tsconfig.json --jq '.content' | base64 -d | grep -E '"strict"|exclude'
```

**Why this beats `curl raw.githubusercontent.com`**:
- `raw.githubusercontent.com` can hang / timeout on slow networks
- `gh api` routes through the authenticated API endpoint, which is more
  resilient
- Auth headers are handled by `gh auth` — no token in shell history
- Rate-limit info comes back in the response headers (visible via
  `gh api --include`)

**Pagination caveat**: files > 1 MB return a different shape — they
point to a `git_url` (blob) or `raw_url`. For very large files, use
the `git_url` and pipe through `git archive` instead.

```bash
# Large-file recipe (sparse fetch, no full clone)
git archive --remote=<git_url> HEAD:path/to/file 2>/dev/null | head -100
```

## 4. Read multiple files in batch

For a known list of files (e.g. all `tsconfig*.json` and all `Dockerfile*`):

```bash
for f in api/tsconfig.json api/tsconfig.build.json api/Dockerfile api/Dockerfile.prod; do
  echo "===== $f ====="
  gh api repos/OWNER/REPO/contents/$f --jq '.content' 2>/dev/null \
    | base64 -d 2>/dev/null \
    | head -40
done
```

Skip files that 404 (they don't exist) — `2>/dev/null` and a missing
file just produces an empty line, no error.

## 5. Commit history

```bash
# Last N commits
gh api repos/OWNER/REPO/commits?per_page=10 --jq \
  '.[] | (.sha[:7]) + "  " + (.commit.author.date) + "  " + (.commit.message | split("\n")[0])'

# Total commit count
gh api repos/OWNER/REPO/commits?per_page=100 --jq '. | length'

# Contributors
gh api repos/OWNER/REPO/contributors --jq \
  '.[] | .login + " (" + (.contributions|tostring) + ")"'
```

**Red flags** (apply to commit shape):
- First commit is "初始提交：全量备份" / "first commit" / "init" and last
  commit is also months old → **dump-and-polish**. No iteration.
- Single contributor with `contributions == total_commits` → single-
  author. Fine for personal, red flag if claimed as team project.
- `commits?per_page=100` returns **< 20** with 1.5 MB of code →
  **whole repo dumped at once**. Audit the marketing claims hard.

## 6. Branches, tags, releases, CI

```bash
# Branches (active dev signal)
gh api repos/OWNER/REPO/branches --jq '.[].name'

# Tags
gh api repos/OWNER/REPO/tags --jq '.[].name'

# Releases
gh api repos/OWNER/REPO/releases --jq '.[].tag_name'

# Active workflows (CI signal)
gh api repos/OWNER/REPO/actions/workflows --jq '.workflows[].name'
```

**Red flags**:
- 0 active workflows but README claims "CI/CD ready" → **CI is fiction**
- Branches only `main` + no tags + no releases → code lives in one
  untested place

## 7. Common audit queries for completion-audit skill

| Question | Command |
|---|---|
| Module count | `gh api repos/OWNER/REPO/contents/api/src/modules --jq '. \| length'` |
| Shared infra dirs | `gh api repos/OWNER/REPO/contents/api/src/shared --jq '.[].name'` |
| License | `gh api repos/OWNER/REPO --jq '.license.spdx_id // "NONE"'` |
| Test dir exists? | `gh api repos/OWNER/REPO/contents/api/test --jq '.message // "exists"'` |
| Has CI? | `gh api repos/OWNER/REPO/actions/workflows --jq '.total_count'` |
| Recent activity | `gh api repos/OWNER/REPO/commits?per_page=1 --jq '.[0].commit.author.date'` |

## 8. When to stop probing and clone instead

Switch from `gh api` to `git clone` when you need to:

- Run any code (`tsc`, `pytest`, `go build`, `make`)
- Inspect `.gitignore`'d files (lock files, build artifacts)
- Diff between two branches / tags
- See git history of a single file (`git log -p`)
- Check binary files (images, compiled artifacts)
- Verify that `package-lock.json` matches `package.json`

For a real completion audit, the static probe gets you to a **decision**:
is this repo worth cloning? If yes, clone and run the heavier checks
in `repo-completion-audit/SKILL.md` Six Dimensions.

## 9. Pitfalls

1. **`/contents/PATH` 404 ≠ file does not exist** for files in `.gitignore`
   — only tracked files are returned. Use `git ls-tree` for that.
2. **Files in `node_modules` and `vendor` are not in `/contents`** — same
   reason. Don't waste calls probing them.
3. **Rate limit**: 5000/hr authenticated. A single static probe of a
   200-file repo with ~50 file reads is well under. Don't panic.
4. **`base64 -d` on Windows** is `certutil -decode` or use `git base64`
   shim. If running cross-platform, prefer `python3 -c "import base64,sys; sys.stdout.buffer.write(base64.b64decode(sys.stdin.buffer.read()))"`.
5. **Empty `.content` field** = binary file (image, etc). `base64 -d`
   on empty input is fine; you'll get garbage. Check `encoding` field
   first if available.
6. **Don't probe private repos you don't have access to** — `gh api`
   will 401/404 and you learn nothing. Confirm access with
   `gh repo view OWNER/REPO` first.
