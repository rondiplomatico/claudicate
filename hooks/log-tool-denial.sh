#!/bin/bash
# claudicate hook: PostToolUseFailure → JSONL
# Captures tool denials (user interrupts or explicit denials only)
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

# Filter: only log user interrupts or explicit denials
IS_INTERRUPT=$(echo "$INPUT" | jq -r '.is_interrupt // false')
ERROR=$(echo "$INPUT" | jq -r '.error // empty')

if [ "$IS_INTERRUPT" != "true" ] && [[ ! "$ERROR" =~ "user doesn't want to proceed" ]] && [[ ! "$ERROR" =~ "User denied" ]]; then
  exit 0
fi

LOG_DIR=$(resolve_log_dir)
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).jsonl"

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
PROJECT_DIR=$(resolve_project_dir)
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
# Truncate tool_input to 500 chars
TOOL_INPUT=$(echo "$INPUT" | jq -c '.tool_input // {}' | head -c 500)
DENIAL_REASON="$ERROR"

jq -n -c \
  --arg ts "$TIMESTAMP" \
  --arg et "tool_denial" \
  --arg sid "$SESSION_ID" \
  --arg pd "$PROJECT_DIR" \
  --arg cwd "$CWD" \
  --arg tool "$TOOL_NAME" \
  --argjson input "$TOOL_INPUT" \
  --arg reason "$DENIAL_REASON" \
  --argjson interrupt "$IS_INTERRUPT" \
  --argjson tags "$(if [[ "$SESSION_ID" == agent-* ]]; then echo '["correction","agent"]'; else echo '["correction"]'; fi)" \
  '{timestamp: $ts, event_type: $et, session_id: $sid, project_dir: $pd, cwd: $cwd, denied_tool: $tool, denied_input: $input, denial_reason: $reason, is_interrupt: $interrupt, tags: $tags}' \
  >> "$LOG_FILE"

exit 0
