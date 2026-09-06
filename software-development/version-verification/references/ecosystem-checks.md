# npm, Cargo, Docker, Git Tags — Live Verification Recipes

Companion to `references/pypi-verification.md`. Same discipline (query the registry, not memory) applied to non-PyPI ecosystems.

## npm (registry.npmjs.org)

```bash
# Latest version only
npm view <package> version

# All versions (JSON)
npm view <package> versions --json

# Combined: installed (from package.json in cwd) vs latest
echo "INSTALLED:";  grep '"<package>"' package.json 2>/dev/null || echo "(not in package.json)"
echo "LATEST:";      npm view <package> version
echo "ALL (last 5):"; npm view <package> versions --json | python3 -c "import sys,json; vs=json.load(sys.stdin); print(vs[-5:])"

# Full metadata dump (license, repository, deprecated flag)
npm view <package> --json | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps({k:d.get(k) for k in ['name','version','license','deprecated','repository','dist-tags']}, indent=2))"
```

**Pitfall — deprecated packages**: `npm view <package>` returns silently for deprecated packages. Check the `deprecated` field — if it's a string, the package is dead. Recommend a fork.

**Pitfall — beta tags**: `npm view <package> version` returns the `latest` dist-tag, which is usually stable. For pre-releases: `npm view <package> dist-tags`.

## Cargo (crates.io)

```bash
# Latest version on crates.io
cargo search <pkg>

# Detailed info
cargo info <pkg>

# Direct API (no cargo needed)
curl -sS https://crates.io/api/v1/crates/<pkg> \
  | python3 -c "import sys,json; d=json.load(sys.stdin)['crate']; print(f\"latest: {d['max_stable_version']} (newest: {d['newest_version']})\")"
```

`max_stable_version` excludes pre-releases; `newest_version` includes them. Always report both.

## Docker Hub

```bash
# Last 10 tags, newest first (Docker Hub registry v2)
curl -sS "https://registry.hub.docker.com/v2/repositories/<image>/tags/?page_size=10&ordering=last_updated" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
for t in d.get('results', []):
    print(f\"  {t['name']}  ->  {t['last_updated'][:10]}  size={t.get('full_size', '?')}\")
"
```

For full images: `https://registry.hub.docker.com/v2/repositories/<namespace>/<image>/tags/?page_size=10&ordering=last_updated`

## GitHub releases (no local git required)

```bash
# Last 5 releases for a repo
gh release list --repo <owner>/<repo> --limit 5

# Latest release only (JSON, no auth needed)
curl -sS https://api.github.com/repos/<owner>/<repo>/releases/latest \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"{d['tag_name']}  ->  {d['published_at'][:10]}\")"

# Latest tag (lighter, may include non-release tags)
curl -sS https://api.github.com/repos/<owner>/<repo>/tags?per_page=5 \
  | python3 -c "import sys,json; [print(t['name']) for t in json.load(sys.stdin)]"
```

**Pitfall — rate limits**: GitHub API allows 60 unauthenticated requests/hour per IP. Cross-check with `git ls-remote` if you hit 403.

## Git tags (no GitHub API needed)

```bash
# All tags, last 10
git ls-remote --tags https://github.com/<owner>/<repo>.git | tail -10

# Just the top one (lightest)
git ls-remote --tags --sort=-v:refname https://github.com/<owner>/<repo>.git \
  | head -1 \
  | awk '{print $2}' \
  | sed 's|refs/tags/||; s|\^{}$||'
```

**Pitfall — `^{}` peeled tags**: annotated tags appear twice (`refs/tags/v1.0` then `refs/tags/v1.0^{}`); the `^{}` form is the commit SHA, the other is the tag object. Strip it.

## APT (Debian / Ubuntu)

```bash
# Installed + candidate
apt-cache policy <package>

# All known versions (any repo)
apt list --all-versions <package> 2>/dev/null
```

The `Candidate:` line is the version `apt install` will pick. The `Installed:` line is what's on the machine now. If they match, you're current.

## Homebrew

```bash
brew info <package> | head -10
# Or JSON
brew info --json=v2 <package> \
  | python3 -c "import sys,json; d=json.load(sys.stdin); f=d['formulae'][0]; print(f\"stable: {f['versions']['stable']}  installed: {f.get('installed', [{}])[0].get('version', 'not installed')}\")"
```

## Snap

```bash
snap info <package>
```

Output has a table with `latest/stable`, `latest/candidate`, etc. channels.

## Cross-ecosystem rule

If two sources disagree (e.g. `npm view` says latest is `1.2.3` but `curl https://registry.npmjs.org/<pkg>` says `1.2.4`):

1. The **direct registry HTTP endpoint** is the canonical source.
2. CLI tools cache for varying durations.
3. Reflect the disagreement in your report; do not paper over it.
