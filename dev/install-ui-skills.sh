#!/usr/bin/env bash
# Install the generic UI skills (ui-audit, ui-critique, ui-polish) for every project on this computer:
# copies them to ~/.claude/skills (on Windows, Git Bash puts that at C:\Users\<you>\.claude\skills).
# olympus-design stays project-only: it is this repo's design system.
set -euo pipefail
cd "$(dirname "$0")/.."
dest="$HOME/.claude/skills"
mkdir -p "$dest"
for s in ui-audit ui-critique ui-polish; do
  rm -rf "${dest:?}/$s"
  cp -r ".claude/skills/$s" "$dest/$s"
  echo "installed $s -> $dest/$s"
done
echo "Each project still needs a states file and the browser tools: see $dest/ui-audit/SKILL.md (\"New project\")."
