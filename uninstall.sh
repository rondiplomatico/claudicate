#!/bin/bash
# promptforge uninstaller — interactive, no CLI arguments
# Removes hooks, skill, and optionally logs from a target directory
set -e

echo "=== promptforge uninstaller ==="
echo ""

# --- Prerequisites ---
if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq is required but not installed."
  exit 1
fi

# --- [1] Uninstall target ---
echo "[1] Uninstall target"
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

# Check both old and new locations for manifest
MANIFEST="$TARGET_PF_DIR/install.manifest"
if [ ! -f "$MANIFEST" ]; then
  # Fall back to old location
  MANIFEST="$TARGET_CLAUDE_DIR/promptforge/install.manifest"
fi

if [ ! -f "$MANIFEST" ]; then
  echo ""
  echo "Error: No install manifest found."
  echo "promptforge does not appear to be installed at $TARGET_BASE."
  exit 1
fi

ENTRY_COUNT=$(wc -l < "$MANIFEST")
echo ""
echo "  Found manifest with $ENTRY_COUNT entries"
echo ""

# --- [2] WARNING ---
echo "    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
echo "    !!  WARNING: THIS WILL REMOVE ALL PROMPTFORGE FILES FROM  !!"
echo "    !!  $TARGET_BASE"
echo "    !!  THIS ACTION CANNOT BE UNDONE.                         !!"
echo "    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
echo ""
printf "    Type 'YES' to continue: "
read -r CONFIRM

if [ "$CONFIRM" != "YES" ]; then
  echo "Aborted."
  exit 0
fi

echo ""

# --- [3] Remove manifest files ---
echo "[3] Removing installed files..."
REMOVED=0
MISSING=0

while IFS= read -r filepath; do
  [ -z "$filepath" ] && continue
  if [ -e "$filepath" ] || [ -L "$filepath" ]; then
    rm -rf "$filepath"
    echo "  Removed  $filepath"
    ((REMOVED++))
  else
    ((MISSING++))
  fi
done < "$MANIFEST"

echo "  $REMOVED removed, $MISSING already missing"
echo ""

# --- [4] Remove hook entries from settings.json ---
SETTINGS_FILE="$TARGET_CLAUDE_DIR/settings.json"

if [ -f "$SETTINGS_FILE" ]; then
  echo "[4] Cleaning settings.json..."
  BEFORE=$(jq '.hooks // [] | length' "$SETTINGS_FILE")
  UPDATED=$(jq '
    .hooks = ((.hooks // []) | map(select(.command | tostring | contains("promptforge") | not)))
  ' "$SETTINGS_FILE")
  echo "$UPDATED" > "$SETTINGS_FILE"
  AFTER=$(echo "$UPDATED" | jq '.hooks | length')
  HOOKS_REMOVED=$((BEFORE - AFTER))
  echo "  Removed $HOOKS_REMOVED hook entries from $SETTINGS_FILE"
  echo ""
fi

# --- [5] Check for user-added files ---
echo "[5] Checking for user-added files..."

check_user_files() {
  local dir="$1"
  local label="$2"
  [ -d "$dir" ] || return 0

  local user_files=()
  while IFS= read -r -d '' f; do
    user_files+=("$f")
  done < <(find "$dir" -type f -print0 2>/dev/null)

  if [ ${#user_files[@]} -gt 0 ]; then
    echo "  Found ${#user_files[@]} user-added file(s) in $label:"
    for f in "${user_files[@]}"; do
      echo "    - $f"
    done
    printf "  Remove these files? (y/n) > "
    read -r REMOVE_CHOICE
    if [ "$REMOVE_CHOICE" = "y" ]; then
      for f in "${user_files[@]}"; do
        rm -f "$f"
        echo "  Removed  $f"
      done
    else
      echo "  Kept user files in $label"
    fi
  fi
}

check_user_files "$TARGET_PF_DIR/hooks" ".promptforge/hooks/"
check_user_files "$TARGET_CLAUDE_DIR/skills/promptforge" ".claude/skills/promptforge/"

# Also check old layout directories from previous installs
check_user_files "$TARGET_CLAUDE_DIR/promptforge/hooks" ".claude/promptforge/hooks/"
check_user_files "$TARGET_CLAUDE_DIR/commands/promptforge" ".claude/commands/promptforge/"
for skill_dir in "$TARGET_CLAUDE_DIR/skills/promptforge-"*/; do
  [ -d "$skill_dir" ] || continue
  check_user_files "$skill_dir" ".claude/skills/$(basename "$skill_dir")/"
done

echo ""

# --- [6] Log data ---
LOG_DIR="$TARGET_PF_DIR/logs"
# Also check old location
if [ ! -d "$LOG_DIR" ]; then
  LOG_DIR="$TARGET_CLAUDE_DIR/promptforge/logs"
fi

if [ -d "$LOG_DIR" ]; then
  LOG_COUNT=$(find "$LOG_DIR" -type f 2>/dev/null | wc -l)
  if [ "$LOG_COUNT" -gt 0 ]; then
    echo "[6] Found $LOG_COUNT log file(s) in $LOG_DIR"
    echo "    (k) Keep logs"
    echo "    (d) Delete logs"
    printf "    > "
    read -r LOG_CHOICE
    if [ "$LOG_CHOICE" = "d" ]; then
      rm -rf "$LOG_DIR"
      echo "  Deleted  $LOG_DIR"
    else
      echo "  Kept logs at $LOG_DIR"
    fi
    echo ""
  fi
fi

# --- [7] Remove empty directories ---
echo "[7] Cleaning up empty directories..."

rm -f "$MANIFEST"
echo "  Removed  $MANIFEST"

# Remove setup.yaml
rm -f "$TARGET_PF_DIR/setup.yaml"

# Remove directories if empty
cleanup_dir() {
  local dir="$1"
  if [ -d "$dir" ] && [ -z "$(ls -A "$dir" 2>/dev/null)" ]; then
    rmdir "$dir"
    echo "  Removed  $dir/"
  fi
}

# New layout
cleanup_dir "$TARGET_PF_DIR/hooks"
cleanup_dir "$TARGET_PF_DIR/logs"
cleanup_dir "$TARGET_PF_DIR"

# .claude skill dirs
cleanup_dir "$TARGET_CLAUDE_DIR/skills/promptforge"

# Old layout cleanup
cleanup_dir "$TARGET_CLAUDE_DIR/promptforge/hooks"
cleanup_dir "$TARGET_CLAUDE_DIR/promptforge/logs"
cleanup_dir "$TARGET_CLAUDE_DIR/promptforge"
cleanup_dir "$TARGET_CLAUDE_DIR/commands/promptforge"
for skill_dir in "$TARGET_CLAUDE_DIR/skills/promptforge-"*/; do
  [ -d "$skill_dir" ] || continue
  cleanup_dir "$skill_dir"
done

cleanup_dir "$TARGET_CLAUDE_DIR/commands"
cleanup_dir "$TARGET_CLAUDE_DIR/skills"

echo ""

# --- [8] Summary ---
echo "Done! promptforge has been uninstalled from $TARGET_BASE."
if [ -d "$LOG_DIR" ]; then
  echo "  Note: Log data was kept at $LOG_DIR"
fi
