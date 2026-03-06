#!/bin/bash
# promptforge hook: PostToolUse[AskUserQuestion] → JSONL
# Captures questions Claude asked and user's answers
set -e

# --- Shared log directory resolution ---
resolve_log_dir() {
  local project_dir
  project_dir=$(echo "$INPUT" | jq -r '.workspace.project_dir // empty')
  if [ -n "$project_dir" ] && [ -d "$project_dir/.claude/promptforge/logs" ]; then
    echo "$project_dir/.claude/promptforge/logs"
  elif [ -d "$HOME/.claude/promptforge/logs" ]; then
    echo "$HOME/.claude/promptforge/logs"
  else
    mkdir -p "$HOME/.claude/promptforge/logs"
    echo "$HOME/.claude/promptforge/logs"
  fi
}

# --- Main ---
INPUT=$(cat)

LOG_DIR=$(resolve_log_dir)
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).jsonl"

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
PROJECT_DIR=$(echo "$INPUT" | jq -r '.workspace.project_dir // empty')
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

# Extract question from tool_input
QUESTION=$(echo "$INPUT" | jq -r '.tool_input.question // "unknown"')

# Extract user's answer from tool_response
ANSWER=$(echo "$INPUT" | jq -r '.tool_response // empty')

TAGS='["clarification"]'

# Agent session detection (session_id format: agent-XXXXXXX)
if [[ "$SESSION_ID" == agent-* ]]; then
  TAGS=$(echo "$TAGS" | jq '. + ["agent"]')
fi

jq -n -c \
  --arg ts "$TIMESTAMP" \
  --arg et "ask_response" \
  --arg sid "$SESSION_ID" \
  --arg pd "$PROJECT_DIR" \
  --arg cwd "$CWD" \
  --arg question "$QUESTION" \
  --arg answer "$ANSWER" \
  --argjson tags "$TAGS" \
  '{timestamp: $ts, event_type: $et, session_id: $sid, project_dir: $pd, cwd: $cwd, question: $question, answer: $answer, tags: $tags}' \
  >> "$LOG_FILE"

exit 0
