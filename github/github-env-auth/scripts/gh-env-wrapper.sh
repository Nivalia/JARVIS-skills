#!/usr/bin/env bash
# gh wrapper: ensures GH_TOKEN is available from ~/.hermes/.env (the env-var
# credential store), then execs the real gh CLI. Token lives only in env vars
# / the .env store — no plaintext credential files.
# Install: install -m 755 gh-env-wrapper.sh /usr/local/bin/gh && hash -r
if [ -z "${GH_TOKEN:-}" ]; then
  env_file="${HERMES_HOME:-$HOME/.hermes}/.env"
  if [ -f "$env_file" ]; then
    GH_TOKEN="$(grep -m1 '^GH_TOKEN=' "$env_file" 2>/dev/null | cut -d= -f2- | tr -d '\r')"
    [ -z "$GH_TOKEN" ] && GH_TOKEN="$(grep -m1 '^GITHUB_TOKEN=' "$env_file" 2>/dev/null | cut -d= -f2- | tr -d '\r')"
    [ -n "$GH_TOKEN" ] && export GH_TOKEN
  fi
fi
exec /usr/bin/gh "$@"
