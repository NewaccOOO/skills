#!/usr/bin/env bash
roots_file="${SECRET_ROOTS_FILE:-$HOME/.claude/secret-roots}"
[ -r "$roots_file" ] || exit 0
input=$(cat)
cmd=$(jq -r '.tool_input.command // ""' <<<"$input")
cwd=$(jq -r '.cwd // ""' <<<"$input")
case "$cmd" in *git*commit*|*git*push*) ;; *) exit 0 ;; esac

patterns=$(mktemp)
trap 'rm -f "$patterns"' EXIT
leaks=""
while IFS= read -r root || [ -n "$root" ]; do
  [ -n "$root" ] && [ -r "$root/.claude/secrets.env" ] || continue
  case "$cmd $cwd" in *"$root"*) ;; *) continue ;; esac
  sed -nE "s/^[A-Z0-9_]*(TOKEN|KEY|SECRET|PASSWORD|PASSWD|PWD|PASS|AUTH|DSN|CREDENTIALS?|DATABASE_URL)[A-Z0-9_]*='([^']{8,})'\$/\2/p" "$root/.claude/secrets.env" \
    | grep -E '[0-9]|[^A-Za-z0-9]' >"$patterns"
  [ -s "$patterns" ] || continue
  printf '%s' "$cmd" | grep -qF -f "$patterns" && leaks="$leaks команда"
  repos=$(git -C "$root" rev-parse --show-toplevel 2>/dev/null)
  for sub in "$root"/*/; do [ -e "$sub.git" ] && repos="$repos"$'\n'"${sub%/}"; done
  while IFS= read -r repo; do
    [ -n "$repo" ] || continue
    if { git -C "$repo" diff HEAD; git -C "$repo" log -p HEAD --not --remotes; } 2>/dev/null | grep '^+' | grep -qF -f "$patterns" \
      || git -C "$repo" ls-files -o --exclude-standard -z 2>/dev/null | (cd "$repo" && xargs -0 grep -lsF -f "$patterns") | grep -q .; then
      leaks="$leaks $(basename "$repo")"
    fi
  done <<<"$repos"
done <"$roots_file"
[ -n "$leaks" ] || exit 0

reason="Запрещено: значение из .claude/secrets.env попадёт в git ($leaks). Убери секрет из изменений, коммитов и сообщения и повтори."
jq -cn --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
