#!/bin/bash
# claudicate hook: Stop → JSONL
# Captures turn-end metadata including model and best-effort token usage
set -e

# --- Shared log directory resolution ---
resolve_log_dir() {
  local project_dir
  project_dir=$(echo "$INPUT" | jq -r '.workspace.project_dir // empty' | sed 's|\\|/|g')
  if [ -n "$project_dir" ] && [ -d "$project_dir/.claudicate/logs" ]; then
    echo "$project_dir/.claudicate/logs"
  elif [ -d "$HOME/.claudicate/logs" ]; then
    echo "$HOME/.claudicate/logs"
  else
    mkdir -p "$HOME/.claudicate/logs"
    echo "$HOME/.claudicate/logs"
  fi
}

# --- Token usage extraction (best-effort, offset-tracked) ---
#
# WHY OFFSET TRACKING IS NEEDED:
#
# Claude Code's transcript file is cumulative — it contains ALL assistant
# messages from every turn in the session. Each assistant message carries a
# "usage" object with that single API call's token counts. A multi-turn
# session with tool use can accumulate thousands of assistant messages.
#
# The Stop hook fires once per turn. Without tracking, we'd either:
#   (a) Sum ALL messages in the transcript → astronomically inflated totals
#       because turn N's Stop would re-count turns 1..N-1, and turn N+1
#       would re-count turns 1..N, etc.
#   (b) Take only the last message → miss output from intermediate tool-call
#       roundtrips within the turn, and risk attributing a later turn's data
#       to an earlier turn if the transcript was already updated.
#
# OFFSET APPROACH:
#   1. Store the count of assistant messages already processed in a temp file
#      per session: /tmp/claudicate-offset-<session_id>
#   2. On each Stop event, collect all assistant messages with usage from the
#      transcript and slice to only the NEW ones (index prev_count .. end).
#   3. Output tokens: SUM across new messages (captures all tool-call
#      roundtrip output within this turn).
#   4. Context tokens (input, cache_read, cache_create): take the LAST new
#      message's values (snapshot of context window size at turn end).
#   5. Write the new total count back to the offset file.
#
# The offset file lives in /tmp/ and is cleaned on reboot — harmless if lost,
# the next Stop event simply starts from offset 0 (slight overcount for that
# one turn, then accurate again).

extract_token_usage() {
  local transcript_path="$1"
  local session_id="$2"
  if [ -z "$transcript_path" ] || [ ! -f "$transcript_path" ]; then
    echo "null"
    return
  fi

  local offset_file="/tmp/claudicate-offset-${session_id}"
  local prev_count=0
  if [ -f "$offset_file" ]; then
    prev_count=$(cat "$offset_file" 2>/dev/null || echo 0)
  fi

  # Extract all assistant usage objects, then slice to only new ones.
  # Produces: { total_count, output_tokens (summed), context snapshot (last) }
  # Uses -R (raw input) + try fromjson to tolerate any malformed lines.
  local result
  result=$(jq -Rsc --argjson offset "$prev_count" '
    [split("\n")[] | select(length > 0) | try fromjson |
     select(.type == "assistant" and .message.usage != null) | .message.usage] |
    . as $all |
    ($all | length) as $total |
    $all[$offset:] |
    if length == 0 then { total_count: $total, usage: null }
    else {
      total_count: $total,
      usage: {
        input_tokens:                last.input_tokens,
        output_tokens:               (map(.output_tokens               // 0) | add),
        cache_read_input_tokens:     last.cache_read_input_tokens,
        cache_creation_input_tokens: last.cache_creation_input_tokens
      }
    }
    end
  ' "$transcript_path" 2>/dev/null)

  if [ -z "$result" ]; then
    echo "null"
    return
  fi

  # Update offset for next turn
  local new_count
  new_count=$(echo "$result" | jq -r '.total_count')
  echo "$new_count" > "$offset_file"

  # Return just the usage object (or null)
  echo "$result" | jq -c '.usage'
}

# --- Main ---
INPUT=$(cat)

# Debug dump on first run
DEBUG_FILE="/tmp/claudicate-stop-debug.json"
if [ ! -f "$DEBUG_FILE" ]; then
  echo "$INPUT" > "$DEBUG_FILE"
fi

LOG_DIR=$(resolve_log_dir)
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).jsonl"

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
PROJECT_DIR=$(echo "$INPUT" | jq -r '.workspace.project_dir // empty' | sed 's|\\|/|g')
MODEL=$(echo "$INPUT" | jq -r '.model.id // .model // empty')
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty')
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

TOKEN_USAGE=$(extract_token_usage "$TRANSCRIPT_PATH" "$SESSION_ID")

# Agent session detection (session_id format: agent-XXXXXXX)
if [[ "$SESSION_ID" == agent-* ]]; then
  TAGS='["agent"]'
else
  TAGS='[]'
fi

# Build the JSON entry, conditionally including token_usage
if [ "$TOKEN_USAGE" = "null" ]; then
  jq -n -c \
    --arg ts "$TIMESTAMP" \
    --arg et "turn_end" \
    --arg sid "$SESSION_ID" \
    --arg pd "$PROJECT_DIR" \
    --arg cwd "$CWD" \
    --arg model "$MODEL" \
    --argjson tags "$TAGS" \
    '{timestamp: $ts, event_type: $et, session_id: $sid, project_dir: $pd, cwd: $cwd, model: $model, tags: $tags}' \
    >> "$LOG_FILE"
else
  jq -n -c \
    --arg ts "$TIMESTAMP" \
    --arg et "turn_end" \
    --arg sid "$SESSION_ID" \
    --arg pd "$PROJECT_DIR" \
    --arg cwd "$CWD" \
    --arg model "$MODEL" \
    --argjson usage "$TOKEN_USAGE" \
    --argjson tags "$TAGS" \
    '{timestamp: $ts, event_type: $et, session_id: $sid, project_dir: $pd, cwd: $cwd, model: $model, token_usage: $usage, tags: $tags}' \
    >> "$LOG_FILE"
fi

exit 0
