#!/bin/bash
# claudicate hook: UserPromptSubmit → JSONL
# Captures user prompts with auto-tagging
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

# --- Auto-tagging ---
auto_tag() {
  local prompt="$1"
  local tags=()

  # BMAD agent invocation
  if [[ "$prompt" =~ ^/BMad:agents:([a-zA-Z_-]+) ]]; then
    tags+=("bmad" "bmad:${BASH_REMATCH[1]}")
  elif [[ "$prompt" =~ ^/BMad:tasks:([a-zA-Z_-]+) ]]; then
    tags+=("bmad" "bmad_task:${BASH_REMATCH[1]}")
  fi

  # Slash command
  if [[ "$prompt" =~ ^/ ]]; then
    tags+=("slash_command")
  fi

  # Planning indicators
  if [[ "$prompt" =~ (plan[[:space:]]mode|planning|/plan|enter[[:space:]]plan) ]]; then
    tags+=("planning")
  fi

  # Testing
  if [[ "$prompt" =~ (test|pytest|verify|spec[[:space:]]) ]]; then
    tags+=("testing")
  fi

  # Git operations
  if [[ "$prompt" =~ (commit|push|pull[[:space:]]request|merge|pr[[:space:]]) ]]; then
    tags+=("git_ops")
  fi

  # Compaction (context window summary injection)
  if [[ "$prompt" =~ ^This[[:space:]]session[[:space:]]is[[:space:]]being[[:space:]]continued[[:space:]]from[[:space:]]a[[:space:]]previous[[:space:]]conversation ]]; then
    tags+=("compaction")
  fi

  # Output as JSON array
  printf '%s\n' "${tags[@]}" | jq -R . | jq -s .
}

# --- Main ---
INPUT=$(cat)

LOG_DIR=$(resolve_log_dir)
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).jsonl"

PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
PROJECT_DIR=$(resolve_project_dir)
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

TAGS=$(auto_tag "$PROMPT")

# Agent session detection (session_id format: agent-XXXXXXX)
if [[ "$SESSION_ID" == agent-* ]]; then
  TAGS=$(echo "$TAGS" | jq '. + ["agent"]')
fi

jq -n -c \
  --arg ts "$TIMESTAMP" \
  --arg et "prompt" \
  --arg sid "$SESSION_ID" \
  --arg pd "$PROJECT_DIR" \
  --arg cwd "$CWD" \
  --arg prompt "$PROMPT" \
  --argjson tags "$TAGS" \
  '{timestamp: $ts, event_type: $et, session_id: $sid, project_dir: $pd, cwd: $cwd, prompt: $prompt, tags: $tags}' \
  >> "$LOG_FILE"

exit 0
