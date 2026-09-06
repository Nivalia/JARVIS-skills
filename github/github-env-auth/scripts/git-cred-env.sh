#!/usr/bin/env bash
# git credential helper: reads GITHUB_TOKEN / GH_TOKEN from the environment.
# Fallback: parse the token out of $HERMES_HOME/.env (the env-var store) when
# the variable is not exported in the current shell, so git works everywhere.
# Usage: git config --global credential.helper '!/usr/local/bin/git-cred-env'
set -u

op="${1:-get}"

# --- resolve token ---
token="${GITHUB_TOKEN:-$GH_TOKEN}"
if [ -z "$token" ]; then
  env_file="${HERMES_HOME:-$HOME/.hermes}/.env"
  if [ -f "$env_file" ]; then
    token="$(grep -m1 '^GITHUB_TOKEN=' "$env_file" 2>/dev/null | cut -d= -f2- | tr -d '\r')"
    [ -z "$token" ] && token="$(grep -m1 '^GH_TOKEN=' "$env_file" 2>/dev/null | cut -d= -f2- | tr -d '\r')"
  fi
fi

if [ "$op" = "get" ]; then
  if [ -n "$token" ]; then
    printf 'username=Nivalia\npassword=%s\n' "$token"
  fi
fi
exit 0
