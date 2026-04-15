#!/bin/bash
# claudicate hook: PostToolUse[AskUserQuestion] → JSONL
# Captures questions Claude asked and user's answers
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

LOG_DIR=$(resolve_log_dir)
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).jsonl"

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
PROJECT_DIR=$(resolve_project_dir)
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

# Extract question from tool_input (single-question or multi-question format)
QUESTION=$(echo "$INPUT" | jq -r '
  if .tool_input.question then .tool_input.question
  elif .tool_input.questions then
    [.tool_input.questions[].question] | join(" | ")
  else "unknown"
  end')

# Extract user's answer from tool_response (string or structured)
ANSWER=$(echo "$INPUT" | jq -r '
  if (.tool_response | type) == "string" then .tool_response
  elif (.tool_response | type) == "object" then (.tool_response | tostring)
  else empty
  end')

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
