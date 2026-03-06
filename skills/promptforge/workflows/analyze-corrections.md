# Analyze Corrections and Friction

Scan PromptForge interaction logs for corrections, negations, contradictions, and repeated friction.

## Prerequisites

None. This is typically the first workflow to run.

## Steps

### 1. Pre-filter logs

Run the extraction script to pre-filter and aggregate friction signals from logs:

```bash
python3 <skill_dir>/scripts/extract_friction.py --output /tmp/promptforge-friction-data.json $SCOPE_PROJECT_FILTER
```

Where `$SCOPE_PROJECT_FILTER` is `--project-filter <project_dir>` for project scope or omitted for global scope.

If the script is unavailable or fails, fall back to reading logs directly with jq.

### 2. Analyze friction patterns

Read the pre-filtered data (or raw logs) and identify:
- **Tool denials**: frequency by tool name, `is_interrupt` vs explicit, repeated patterns
- **Negation language**: "no", "not that", "stop", "undo", "wrong", "instead", "actually" — weight by position (start = stronger)
- **Sequential contradictions**: prompt N negates prompt N-1 in same session
- **Repeated clarifications**: same `ask_response` question across sessions = unclear instructions
- **Correction chains**: tool_denial -> follow-up prompt patterns, grouped by denied tool

### 3. Write Friction Report

Write the report to `$SCOPE_FRICTION_REPORT` (project scope: `<project>/.promptforge/friction-report.md`, global scope: `~/.promptforge/friction-report.md`) with:

1. **Top 10 Friction Patterns** ranked by frequency, each with: category, frequency, 2-3 examples, root cause hypothesis, suggested fix area (`CLAUDE.md` / `BMAD agent` / `BMAD task` / `permissions` / `workflow`)
2. **Summary Statistics**: total friction events, friction rate, trend over time

### 4. Display summary

Present the summary of top friction patterns in conversation.
