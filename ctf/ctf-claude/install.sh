#!/usr/bin/env bash
# install.sh — Install claude-code-ctf-skills into ~/.claude/skills/

set -e

SKILLS_DIR="$HOME/.claude/skills"
SOURCE_DIR="$(cd "$(dirname "$0")/skills" && pwd)"

echo "Installing CTF skills to $SKILLS_DIR ..."
mkdir -p "$SKILLS_DIR"

for skill_dir in "$SOURCE_DIR"/*/; do
  skill_name=$(basename "$skill_dir")
  dest="$SKILLS_DIR/$skill_name"

  if [ -d "$dest" ]; then
    echo "  [update] $skill_name"
  else
    echo "  [install] $skill_name"
  fi

  mkdir -p "$dest"
  cp "$skill_dir/SKILL.md" "$dest/SKILL.md"
done

echo ""
echo "Done! $(ls "$SOURCE_DIR" | wc -l | tr -d ' ') skills installed."
echo "Restart Claude Code and use /ctf-recon <IP> to get started."
