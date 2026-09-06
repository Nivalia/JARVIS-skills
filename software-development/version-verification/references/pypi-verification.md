# PyPI Live Version Verification — Recipes

Reproducible commands for "what is actually published on PyPI right now?" The package may or may not exist; the version you remember may be wrong; the version in your memory may be one that never got published.

## The canonical source

`https://pypi.org/pypi/<package>/json` — returns full release metadata. Works for any package name, no auth.

## Recipe 1 — single one-liner, latest version

```bash
curl -sS https://pypi.org/pypi/<package>/json \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['version'])"
```

Output: just the latest version string, e.g. `0.19.0`.

## Recipe 2 — last 8 releases with timestamps

```bash
curl -sS https://pypi.org/pypi/<package>/json \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('latest:', d['info']['version'])
rs = sorted(d['releases'].items(),
            key=lambda x: x[1][0]['upload_time'] if x[1] else '')
for v, files in rs[-8:]:
    if files:
        print(f'  {v}  ->  {files[0][\"upload_time\"][:10]}')
"
```

Output:

```
latest: 0.19.0
  0.15.1  ->  2026-05-29
  0.15.2  ->  2026-05-29
  0.16.0  ->  2026-06-06
  0.17.0  ->  2026-06-19
  0.18.0  ->  2026-07-01
  0.18.1  ->  2026-07-08
  0.18.2  ->  2026-07-08
  0.19.0  ->  2026-07-20
```

## Recipe 3 — pip CLI (faster, less detail)

```bash
pip index versions <package> 2>&1 | head -5
```

Output (with the WARNING header stripped):

```
<package> (0.19.0)
Available versions: 0.19.0, 0.18.2, 0.18.1, 0.18.0, 0.17.0, 0.16.0, 0.15.2, 0.15.1, 0.15.0, 0.14.0, 0.13.0
```

## Recipe 4 — combined: installed vs available

```bash
echo "INSTALLED:"; pip show <package> 2>/dev/null | grep -E "^(Name|Version|Location):"
echo "---"
echo "AVAILABLE (latest 3):"; pip index versions <package> 2>&1 | head -3
```

A real failure case (2026-08-25):

```
INSTALL: hermes-agent == 0.19.0 (2026-07-20)
MEMORY CLAIM: v0.20.0 (2026-08-03)
REALITY: latest published is 0.19.0; v0.20.0 never published
ACTION: nothing to upgrade, do not back up / stop services / reinstall
```

## Recipe 5 — pip install with --dry-run (safe preflight)

```bash
pip install --upgrade --dry-run <package> 2>&1 | tail -20
```

Output tells you what would happen without doing it. Good final sanity check before actually upgrading.

## Pitfalls — PyPI specific

- **Mirror lag**: `pip index versions` reads from the configured index (often a corporate mirror). Cross-check with the PyPI JSON API recipe above if you suspect lag.
- **Yanked versions**: appear in `pip index versions` but will fail on `pip install <pkg>==<ver>` with a YankedRelease error. Always check `info['yanked']` in the JSON if recommending a specific version.
- **Pre-releases hidden by default**: `0.20.0a1`, `0.20.0rc1` won't show in `pip index versions` without `--pre`. If user wants stable only, don't pass `--pre`.
- **Post-releases** like `0.19.0.post1` are real and ordered AFTER the parent. Use semver-aware tools to compare; string comparison on `0.19.0 < 0.19.0.post1` is correct.
- **Local dev installs**: if `pip show <pkg>` reports `Location: /some/dev/editable/path`, the package is installed in editable mode and PyPI version doesn't matter.
- **`pip index versions` is experimental** in some pip versions and emits a warning to stderr. Don't mistake the warning for a problem.

## When NOT to use these recipes

- The package is **not on PyPI** — it's a GitHub-only release. Use `gh release list --repo <owner>/<repo>` instead.
- The package was **renamed** — old name on PyPI is stale, new name is canonical. Check the package's GitHub README for canonical name.
- You're checking a **local mirror** — point curl at your mirror URL instead of `pypi.org`.
