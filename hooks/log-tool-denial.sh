#!/bin/bash
# promptforge hook: PostToolUseFailure → JSONL
# Captures tool denials (user interrupts or explicit denials only)
set -e

# --- Shared log directory resolution ---
resolve_log_dir() {
  local project_dir
  project_dir=$(echo "$INPUT" | jq -r '.workspace.project_dir // empty')
  if [ -n "$project_dir" ] && [ -d "$project_dir/.promptforge/logs" ]; then
    echo "$project_dir/.promptforge/logs"
  elif [ -d "$HOME/.promptforge/logs" ]; then
    echo "$HOME/.promptforge/logs"
  else
    mkdir -p "$HOME/.promptforge/logs"
    echo "$HOME/.promptforge/logs"
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
PROJECT_DIR=$(echo "$INPUT" | jq -r '.workspace.project_dir // empty')
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
