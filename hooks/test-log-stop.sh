#!/bin/bash
# Manual test for log-stop.sh token extraction with offset tracking.
#
# Simulates a 3-turn session where each turn has multiple tool-call roundtrips.
# Verifies that each Stop event captures only the NEW turn's tokens:
#   - output_tokens: summed across all API calls within that turn
#   - context tokens: snapshot from the last API call of that turn
#
# Usage:
#   cd hooks && bash test-log-stop.sh
#
# Expected output shows 3 turns with correct per-turn values (no inflation).
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT

SESSION_ID="test-session-$$"
TRANSCRIPT="$TEST_DIR/transcript.jsonl"

# Clean any leftover offset file
rm -f "/tmp/claudicate-offset-${SESSION_ID}"

# Helper: append an assistant message to the transcript
add_msg() {
  local input_tokens=$1 output_tokens=$2 cache_read=$3 cache_create=$4
  printf '{"type":"assistant","message":{"usage":{"input_tokens":%d,"output_tokens":%d,"cache_read_input_tokens":%d,"cache_creation_input_tokens":%d}}}\n' \
    "$input_tokens" "$output_tokens" "$cache_read" "$cache_create" >> "$TRANSCRIPT"
}

# Source only the extract_token_usage function from log-stop.sh
eval "$(sed -n '/^extract_token_usage()/,/^}/p' "$SCRIPT_DIR/log-stop.sh")"

echo "=== log-stop.sh offset tracking test ==="
echo ""

# ========== TURN 1: 3 API calls ==========
add_msg 100 200 9000 900       # tool_use roundtrip 1
add_msg 100 150 11000 900      # tool_use roundtrip 2
add_msg 100 500 13000 900      # end_turn (final response)

echo "Turn 1: 3 API calls"
echo "  Expected: output=850 (200+150+500), context=14000 (100+13000+900)"
T1=$(extract_token_usage "$TRANSCRIPT" "$SESSION_ID")
echo "  Got:      $T1"

# ========== TURN 2: 2 API calls ==========
add_msg 200 300 19000 800      # tool_use roundtrip
add_msg 200 700 21000 800      # end_turn

echo "Turn 2: 2 API calls"
echo "  Expected: output=1000 (300+700), context=22000 (200+21000+800)"
T2=$(extract_token_usage "$TRANSCRIPT" "$SESSION_ID")
echo "  Got:      $T2"

# ========== TURN 3: 1 API call ==========
add_msg 300 100 24000 700      # end_turn (simple response)

echo "Turn 3: 1 API call"
echo "  Expected: output=100, context=25000 (300+24000+700)"
T3=$(extract_token_usage "$TRANSCRIPT" "$SESSION_ID")
echo "  Got:      $T3"

echo ""
echo "=== Verification ==="

PASS=true
verify() {
  local turn=$1 field=$2 expected=$3 json=$4
  local actual
  actual=$(echo "$json" | jq ".$field")
  if [ "$actual" != "$expected" ]; then
    echo "FAIL: Turn $turn $field: expected $expected, got $actual"
    PASS=false
  fi
}

verify 1 output_tokens               850   "$T1"
verify 1 input_tokens                100   "$T1"
verify 1 cache_read_input_tokens     13000 "$T1"
verify 1 cache_creation_input_tokens 900   "$T1"

verify 2 output_tokens               1000  "$T2"
verify 2 input_tokens                200   "$T2"
verify 2 cache_read_input_tokens     21000 "$T2"
verify 2 cache_creation_input_tokens 800   "$T2"

verify 3 output_tokens               100   "$T3"
verify 3 input_tokens                300   "$T3"
verify 3 cache_read_input_tokens     24000 "$T3"
verify 3 cache_creation_input_tokens 700   "$T3"

# ========== EDGE CASE: offset file missing (reboot scenario) ==========
echo ""
echo "=== Edge case: offset file deleted mid-session ==="
rm -f "/tmp/claudicate-offset-${SESSION_ID}"

# Next call should re-read entire transcript (8 messages), summing all output
echo "  After offset reset, next call processes all 8 messages"
T_RESET=$(extract_token_usage "$TRANSCRIPT" "$SESSION_ID")
RESET_OUT=$(echo "$T_RESET" | jq '.output_tokens')
# Should sum all 8 messages' output: 200+150+500+300+700+100 = 1950
# Context should be last message's: 300+24000+700 = 25000
echo "  Expected: output=1950 (all 8 msgs), context=25000 (last msg)"
echo "  Got:      $T_RESET"
verify reset output_tokens               1950  "$T_RESET"
verify reset input_tokens                300   "$T_RESET"
verify reset cache_read_input_tokens     24000 "$T_RESET"
verify reset cache_creation_input_tokens 700   "$T_RESET"

echo ""
if [ "$PASS" = true ]; then
  echo "ALL TESTS PASSED"
else
  echo "SOME TESTS FAILED"
  exit 1
fi

# Cleanup offset file
rm -f "/tmp/claudicate-offset-${SESSION_ID}"
