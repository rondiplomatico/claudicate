#!/bin/bash
# promptforge installer — interactive, no CLI arguments
# Installs hooks, scripts, and skill to a target directory
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST_FILES=()

echo "=== promptforge installer ==="
echo "Source: $REPO_DIR"
echo ""

# --- Prerequisites ---
echo -n "Checking prerequisites... "
if ! command -v jq >/dev/null 2>&1; then
  echo "FAILED"
  echo "Error: jq is required but not installed."
  echo "Install it with: sudo apt install jq  (or brew install jq)"
  exit 1
fi
echo "jq ✓"
echo ""

# --- [1] Install target ---
echo "[1] Install target"
echo "    (g) Global (~/.promptforge/ + ~/.claude/)"
echo "    (p) Project — enter path"
echo "    (.) Current directory ($(pwd))"
printf "    > "
read -r TARGET_CHOICE

case "$TARGET_CHOICE" in
  g)
    TARGET_BASE="$HOME"
    ;;
  p)
    printf "    Enter project path: "
    read -r PROJECT_PATH
    if [ ! -d "$PROJECT_PATH" ]; then
      echo "Error: Directory '$PROJECT_PATH' does not exist."
      exit 1
    fi
    TARGET_BASE="$PROJECT_PATH"
    ;;
  .)
    TARGET_BASE="$(pwd)"
    ;;
  *)
    echo "Error: Invalid choice '$TARGET_CHOICE'. Use g, p, or ."
    exit 1
    ;;
esac

TARGET_PF_DIR="$TARGET_BASE/.promptforge"
TARGET_CLAUDE_DIR="$TARGET_BASE/.claude"
echo ""

# --- [2] Install mode ---
echo "[2] Install mode"
echo "    (l) Link — symlink back to this repo (auto-updates on git pull)"
echo "    (c) Copy — standalone copy (requires manual re-install for updates)"
printf "    > "
read -r MODE_CHOICE

case "$MODE_CHOICE" in
  l) INSTALL_MODE="link" ;;
  c) INSTALL_MODE="copy" ;;
  *)
    echo "Error: Invalid choice '$MODE_CHOICE'. Use l or c."
    exit 1
    ;;
esac
echo ""

# --- Execute installation ---
echo "Installing to $TARGET_PF_DIR (data) + $TARGET_CLAUDE_DIR (skill/hooks config)..."

# Helper: install a file (symlink or copy)
install_file() {
  local src="$1" dst="$2"
  if [ "$INSTALL_MODE" = "link" ]; then
    ln -sf "$src" "$dst"
    echo "  Linked   $dst → $src"
  else
    cp "$src" "$dst"
    echo "  Copied   $dst"
  fi
  MANIFEST_FILES+=("$dst")
}

# Helper: install a directory (symlink or copy)
install_dir() {
  local src="$1" dst="$2"
  if [ "$INSTALL_MODE" = "link" ]; then
    ln -sfn "$src" "$dst"
    echo "  Linked   $dst → $src"
    MANIFEST_FILES+=("$dst")
  else
    rm -rf "$dst"
    cp -r "$src" "$dst"
    echo "  Copied   $dst"
    # Add all files in the copied directory to manifest
    while IFS= read -r -d '' f; do
      MANIFEST_FILES+=("$f")
    done < <(find "$dst" -type f -print0)
  fi
}

# Create .promptforge directories
mkdir -p "$TARGET_PF_DIR/logs"
echo "  Created  $TARGET_PF_DIR/logs/"
mkdir -p "$TARGET_PF_DIR/hooks"

# Install hook scripts to .promptforge/hooks/
chmod +x "$REPO_DIR/hooks/"*.sh
for hook in "$REPO_DIR/hooks/"*.sh; do
  install_file "$hook" "$TARGET_PF_DIR/hooks/$(basename "$hook")"
done

# Always copy schema (small file)
cp "$REPO_DIR/schema.json" "$TARGET_PF_DIR/schema.json"
echo "  Copied   $TARGET_PF_DIR/schema.json"
MANIFEST_FILES+=("$TARGET_PF_DIR/schema.json")

# Migrate: remove old .claude/promptforge/ layout from previous installs
if [ -d "$TARGET_CLAUDE_DIR/promptforge" ]; then
  # Preserve logs if they exist in old location
  if [ -d "$TARGET_CLAUDE_DIR/promptforge/logs" ] && [ "$(ls -A "$TARGET_CLAUDE_DIR/promptforge/logs" 2>/dev/null)" ]; then
    echo "  Migrating logs from .claude/promptforge/logs/ to .promptforge/logs/..."
    cp -n "$TARGET_CLAUDE_DIR/promptforge/logs/"*.jsonl "$TARGET_PF_DIR/logs/" 2>/dev/null || true
  fi
  rm -rf "$TARGET_CLAUDE_DIR/promptforge"
  echo "  Migrated: removed old .claude/promptforge/"
fi

# Migrate: remove old command/skill layout from previous installs
if [ -d "$TARGET_CLAUDE_DIR/commands/promptforge" ]; then
  rm -rf "$TARGET_CLAUDE_DIR/commands/promptforge"
  echo "  Migrated: removed old commands/promptforge/"
  rmdir "$TARGET_CLAUDE_DIR/commands" 2>/dev/null || true
fi
for old_skill in "$TARGET_CLAUDE_DIR/skills/promptforge-"*/; do
  [ -d "$old_skill" ] || continue
  rm -rf "$old_skill"
  echo "  Migrated: removed old $(basename "$old_skill")/"
done

# Install unified skill to .claude/skills/
mkdir -p "$TARGET_CLAUDE_DIR/skills"
install_dir "$REPO_DIR/skills/promptforge" "$TARGET_CLAUDE_DIR/skills/promptforge"

# --- Write install manifest ---
printf '%s\n' "${MANIFEST_FILES[@]}" > "$TARGET_PF_DIR/install.manifest"
echo "  Written  $TARGET_PF_DIR/install.manifest (${#MANIFEST_FILES[@]} entries)"

# --- Write setup.yaml ---
case "$TARGET_CHOICE" in
  g) SCOPE="global" ;;
  *) SCOPE="project" ;;
esac

{
  echo "# Written by promptforge installer"
  echo "scope: $SCOPE"
  echo "install_mode: $INSTALL_MODE"
  echo "source: $REPO_DIR"
  echo "installed: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "manifest:"
  for f in "${MANIFEST_FILES[@]}"; do
    echo "  - $f"
  done
} > "$TARGET_PF_DIR/setup.yaml"
echo "  Written  $TARGET_PF_DIR/setup.yaml"

# --- Update settings.json with hook entries ---
SETTINGS_FILE="$TARGET_CLAUDE_DIR/settings.json"

# Ensure settings.json exists
if [ ! -f "$SETTINGS_FILE" ]; then
  echo '{}' > "$SETTINGS_FILE"
fi

HOOKS_DIR="$TARGET_PF_DIR/hooks"

# Build the hooks array using jq
# Read existing settings, remove old promptforge hooks, add new ones
UPDATED=$(jq --arg hdir "$HOOKS_DIR" '
  # Remove existing promptforge hook entries (by command path containing "promptforge")
  .hooks = ((.hooks // []) | map(select(.command | tostring | contains("promptforge") | not)))
  # Also remove old log-prompts.sh hook
  | .hooks = (.hooks | map(select(.command | tostring | contains("log-prompts.sh") | not)))
  # Add new promptforge hooks
  | .hooks += [
    {
      "event": "UserPromptSubmit",
      "command": ($hdir + "/log-prompt.sh"),
      "timeout": 5000
    },
    {
      "event": "PostToolUse",
      "matcher": "AskUserQuestion",
      "command": ($hdir + "/log-ask-response.sh"),
      "timeout": 5000
    },
    {
      "event": "PostToolUseFailure",
      "command": ($hdir + "/log-tool-denial.sh"),
      "timeout": 5000
    },
    {
      "event": "PostToolUse",
      "command": ($hdir + "/log-tool-use.sh"),
      "timeout": 5000
    },
    {
      "event": "Stop",
      "command": ($hdir + "/log-stop.sh"),
      "timeout": 10000
    }
  ]
' "$SETTINGS_FILE")

echo "$UPDATED" > "$SETTINGS_FILE"
echo "  Updated  $SETTINGS_FILE (5 hook entries)"

# Check if old log-prompts.sh was removed
if echo "$UPDATED" | jq -e '.hooks | map(select(.command | tostring | contains("log-prompts.sh"))) | length == 0' >/dev/null 2>&1; then
  echo "  Removed  old log-prompts.sh hook entry (if present)"
fi

echo ""
echo "Done!"
echo ""

# --- [3] Gitignore check (project installs only) ---
if [ "$TARGET_CHOICE" != "g" ] && [ -d "$TARGET_BASE/.git" ]; then
  GITIGNORE="$TARGET_BASE/.gitignore"
  NEEDS_ADD=true

  if [ -f "$GITIGNORE" ]; then
    # Check if .promptforge is already ignored (exact line or with trailing slash)
    if grep -qxF '.promptforge' "$GITIGNORE" 2>/dev/null || \
       grep -qxF '.promptforge/' "$GITIGNORE" 2>/dev/null || \
       grep -qxF '/.promptforge' "$GITIGNORE" 2>/dev/null || \
       grep -qxF '/.promptforge/' "$GITIGNORE" 2>/dev/null; then
      NEEDS_ADD=false
      echo "[3] .promptforge/ is already in .gitignore ✓"
    fi
  fi

  if [ "$NEEDS_ADD" = true ]; then
    echo "[3] This is a git repository. .promptforge/ contains usage logs"
    echo "    (session prompts, tool invocations, timestamps) that should"
    echo "    NOT be committed to version control."
    echo ""
    echo "    (a) Add '.promptforge/' to .gitignore (Recommended)"
    echo "    (s) Skip — I'll handle it myself"
    printf "    > "
    read -r GITIGNORE_CHOICE

    case "$GITIGNORE_CHOICE" in
      a)
        # Add with a comment header if .gitignore doesn't exist or doesn't have it
        if [ ! -f "$GITIGNORE" ]; then
          echo "# promptforge interaction logs" > "$GITIGNORE"
          echo ".promptforge/" >> "$GITIGNORE"
          echo "  Created  $GITIGNORE with .promptforge/ entry"
        else
          # Add a blank line separator if file doesn't end with newline
          [ -s "$GITIGNORE" ] && [ "$(tail -c 1 "$GITIGNORE")" != "" ] && echo "" >> "$GITIGNORE"
          echo "" >> "$GITIGNORE"
          echo "# promptforge interaction logs" >> "$GITIGNORE"
          echo ".promptforge/" >> "$GITIGNORE"
          echo "  Added    .promptforge/ to $GITIGNORE"
        fi
        ;;
      *)
        echo ""
        echo "    ⚠  WARNING: .promptforge/logs/ contains full usage logs including"
        echo "    session prompts, tool arguments, and timestamps. Without a .gitignore"
        echo "    entry, this data WILL be committed to version control."
        echo ""
        ;;
    esac
  fi
  echo ""
fi

# --- [4] Import existing session data ---
echo "[4] Import existing session history into promptforge logs?"
echo "    (y) Yes — parse existing Claude Code sessions + old prompt logs (may take a moment)"
echo "    (n) No — start fresh, only capture new interactions going forward"
printf "    > "
read -r IMPORT_CHOICE

if [ "$IMPORT_CHOICE" = "y" ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo ""
    echo "Warning: python3 is required for import but not found. Skipping."
  else
    echo ""
    echo "Importing session history..."
    python3 "$REPO_DIR/scripts/extract-sessions.py" \
      --include-old-logs \
      --output "$TARGET_PF_DIR/logs/" \
      && echo "Import complete." \
      || echo "Warning: Import encountered errors (partial data may have been written)."
  fi
fi

echo ""
echo "Installation complete. Run again to install to additional targets."
