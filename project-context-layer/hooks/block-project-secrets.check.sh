#!/usr/bin/env bash
set -u
hook="$(dirname "$0")/block-project-secrets.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
export SECRET_ROOTS_FILE="$tmp/roots"
secrets="SOME_TOKEN='s3cr3t-value-123'\nLLM_API_KEY='unused'\nDB_PASSWORD='postgres'\nAPP_USER_LOGIN='12345678'\n"

multi="$tmp/multi"
mkdir -p "$multi/.claude" "$multi/repo"
printf "$secrets" >"$multi/.claude/secrets.env"
git -C "$multi/repo" init -q
git -C "$multi/repo" -c user.name=t -c user.email=t@t commit -q --allow-empty -m init

single="$tmp/single"
mkdir -p "$single/.claude"
git -C "$single" init -q
git -C "$single" -c user.name=t -c user.email=t@t commit -q --allow-empty -m init
printf "$secrets" >"$single/.claude/secrets.env"
printf '%s\n%s\n' "$multi" "$single" >"$SECRET_ROOTS_FILE"

fail=0
run() {
  local expect=$1 cmd=$2 cwd=$3 title=$4 out
  out=$(jq -cn --arg c "$cmd" --arg w "$cwd" '{tool_input:{command:$c},cwd:$w}' | "$hook")
  if { [ "$expect" = deny ] && [[ "$out" == *deny* ]]; } || { [ "$expect" = allow ] && [ -z "$out" ]; }; then
    echo "ok   $expect: $title"
  else
    echo "FAIL $expect: $title -> $out"; fail=1
  fi
}

run allow "git commit -m 'чисто'" "$multi/repo" "папка с репозиториями, чисто"
run allow "ls" "$multi/repo" "не git-команда"
run allow "git commit -m x" "/tmp" "команда вне зарегистрированных папок"
run allow "git commit -m 'postgres unused 12345678'" "$multi/repo" "слова без цифр и логины не секреты"
run deny "git commit -m 's3cr3t-value-123'" "$multi/repo" "секрет в сообщении коммита"
echo "token=s3cr3t-value-123" >"$multi/repo/new.txt"
run deny "git add -A && git commit -m x" "$multi/repo" "секрет в неотслеживаемом файле"
git -C "$multi/repo" add new.txt
run deny "git commit -m x" "$multi/repo" "секрет в индексе"
git -C "$multi/repo" -c user.name=t -c user.email=t@t commit -q -m leak
run deny "git push" "$multi/repo" "секрет в незапушенном коммите"

run deny "git commit -m x" "$single" "папка-репозиторий, secrets.env не в исключениях"
echo ".claude/secrets.env" >>"$single/.git/info/exclude"
run allow "git commit -m x" "$single" "папка-репозиторий, secrets.env исключён"

wtroot="$tmp/wtroot"
mkdir -p "$wtroot/.claude"
printf "$secrets" >"$wtroot/.claude/secrets.env"
git -C "$tmp" init -q wtmain
git -C "$tmp/wtmain" -c user.name=t -c user.email=t@t commit -q --allow-empty -m init
git -C "$tmp/wtmain" worktree add -q -b wt "$wtroot/wt"
echo "$wtroot" >>"$SECRET_ROOTS_FILE"
run allow "git commit -m x" "$wtroot/wt" "worktree, чисто"
echo "token=s3cr3t-value-123" >"$wtroot/wt/new.txt"
run deny "git commit -m x" "$wtroot/wt" "секрет в неотслеживаемом файле worktree"
exit $fail
