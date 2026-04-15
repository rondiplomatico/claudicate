#!/bin/bash
# claudicate hook: PostToolUse → JSONL
# Captures successful tool uses (filtered to Bash, Write, Edit only)
set -e

# --- Resolve project root directory ---
resolve_project_dir() {
  local pd cwd
  pd=$(echo "$INPUT" | jq -r '.workspace.project_dir // empty' | sed 's|\\|/|g')
  if [ -n "$pd" ]; then
    echo "$pd"
    return
  fi
  cwd=$(echo "$INPUT" | jq -r '.cwd // empty' | sed 's|\\|/|g')
  if [ -n "$cwd" ]; then
    local root
    root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null | sed 's|\\|/|g') || true
    echo "${root:-$cwd}"
  fi
}

# --- Shared log directory resolution ---
resolve_log_dir() {
  local project_dir
  project_dir=$(resolve_project_dir)
  if [ -n "$project_dir" ] && [ -d "$project_dir/.claudicate/logs" ]; then
    echo "$project_dir/.claudicate/logs"
  elif [ -d "$HOME/.claudicate/logs" ]; then
    echo "$HOME/.claudicate/logs"
  else
    mkdir -p "$HOME/.claudicate/logs"
    echo "$HOME/.claudicate/logs"
  fi
}

# --- Main ---
INPUT=$(cat)

# Filter: only log Bash, Write, Edit tools (skip Read/Glob/Grep/Agent — too noisy)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
case "$TOOL_NAME" in
  Bash|Write|Edit) ;;
  *) exit 0 ;;
esac

LOG_DIR=$(resolve_log_dir)
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).jsonl"

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
PROJECT_DIR=$(resolve_project_dir)
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

# Truncate tool_input to 500 chars (as string to avoid broken JSON from mid-truncation)
TOOL_INPUT=$(echo "$INPUT" | jq -c '.tool_input // {}' | head -c 500)

jq -n -c \
  --arg ts "$TIMESTAMP" \
  --arg et "tool_use" \
  --arg sid "$SESSION_ID" \
  --arg pd "$PROJECT_DIR" \
  --arg cwd "$CWD" \
  --arg tool "$TOOL_NAME" \
  --arg input "$TOOL_INPUT" \
  --argjson tags "$(if [[ "$SESSION_ID" == agent-* ]]; then echo '["agent"]'; else echo '[]'; fi)" \
  '{timestamp: $ts, event_type: $et, session_id: $sid, project_dir: $pd, cwd: $cwd, tool_name: $tool, tool_input: $input, tags: $tags}' \
  >> "$LOG_FILE"

exit 0
