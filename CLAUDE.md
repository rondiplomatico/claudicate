# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is promptforge?

A self-improvement toolkit for Claude Code. Five bash hooks capture user interactions (prompts, clarification answers, tool denials, tool uses, turn ends) as structured JSONL logs. Python scripts and Claude-driven skills then analyze these logs to detect friction patterns and suggest improvements to project configuration (CLAUDE.md, permissions, memory) and BMAD setup.

## Data Flow

```
Claude Code events → 5 hook scripts → JSONL daily logs → Python analysis / Skills → Recommendations
```

## Architecture

### Hooks (`hooks/`)
Bash scripts triggered by Claude Code events. All share a common pattern:
- Read JSON from stdin (`INPUT=$(cat)`)
- Extract fields with `jq -r`
- Resolve log directory (project-local `.claude/promptforge/logs/` first, global `~/.claude/promptforge/logs/` fallback)
- Append one JSON line to `YYYY-MM-DD.jsonl`
- Use `set -e` and exit 0

| Hook | Event | event_type |
|------|-------|------------|
| `log-prompt.sh` | `UserPromptSubmit` | `prompt` |
| `log-ask-response.sh` | `PostToolUse[AskUserQuestion]` | `ask_response` |
| `log-tool-denial.sh` | `PostToolUseFailure` | `tool_denial` |
| `log-tool-use.sh` | `PostToolUse` | `tool_use` |
| `log-stop.sh` | `Stop` | `turn_end` |

PostToolUse hooks receive data in `tool_input` / `tool_response` fields (not `inputs` / `response`).

`log-prompt.sh` applies auto-tags via regex (bmad, slash_command, planning, testing, git_ops, etc.). `log-tool-denial.sh` filters to only user interrupts and explicit denials. `log-tool-use.sh` filters to only Bash, Write, and Edit tools (Read/Glob/Grep/Agent are too noisy and not permission-relevant). All hooks detect agent sessions (session_id starting with `agent-`) and add the `agent` tag automatically.

### Log Format (`schema.json`)
JSONL with required fields: `timestamp` (ISO 8601 UTC), `event_type`, `session_id`. Event-specific required fields: `prompt` (prompt), `question`+`answer` (ask_response), `denied_tool` (tool_denial), `tool_name` (tool_use). All events have optional `tags` array.

### Python Scripts
Utility scripts in `scripts/`:
- `extract-sessions.py` — backfills logs from Claude Code session transcripts
- `validate-logs.py` — validates JSONL against schema

Analysis scripts co-located in `skills/promptforge/scripts/`:
- `analyze_usage.py` — generates usage report (volume, time patterns, token usage, tags); excludes agent sessions by default (`--include-agents` to include)
- `analyze_agents.py` — agent-specific analysis (overview, prompt characteristics, friction, parent-child session correlation, complexity)
- `extract_friction.py` — pre-aggregates friction signals (denials, negations, contradictions, repeated clarifications) into JSON; excludes agent sessions by default (`--include-agents` to include)
- `extract_permissions.py` — analyzes settings.json permissions for redundancies, anomalies, generalization opportunities, and new candidates from tool usage/denial logs

All analysis scripts support `--logs-dir` (repeatable), `--since`, auto-discover log directories, and `--project-filter DIR` to restrict analysis to entries from a specific project.

### Unified Skill (`skills/promptforge/`)
A single skill directory provides all promptforge workflows via `/promptforge <workflow>`. The `SKILL.md` router accepts arguments (`$0`) to dispatch to workflow files, or presents an interactive menu if no argument is given.

```
skills/promptforge/
  SKILL.md              ← router (user-invocable, no auto-trigger)
  scope-preamble.md     ← shared scope selection logic
  workflows/            ← one .md per workflow (merged command+skill docs)
    analyze-corrections.md
    analyze-usage.md
    analyze-agents.md
    improve-project.md
    improve-bmad.md
    improve-agents.md
    improve-permissions.md
  scripts/              ← co-located Python analysis scripts
    extract_friction.py
    extract_permissions.py
    analyze_usage.py
    analyze_agents.py
```

Two workflow chains:
- **User friction**: `analyze-corrections` (generates friction report) → `improve-project` or `improve-bmad` (consumes friction report, cross-references with current config, suggests changes)
- **Agent improvement**: `analyze-agents` (agent session analysis) + friction report → `improve-agents` (suggests agent prompt, skill, and instruction improvements)
- **Permission optimization**: `improve-permissions` (analyzes settings.json for redundancies, consolidation, and new candidates from tool usage/denial logs; scope-aware with cross-scope redundancy detection)

### Installation (`install.sh`, `uninstall.sh`)
Interactive scripts (no CLI args). Install supports link (symlink) or copy mode to global/project/.claude/ directories. Writes `install.manifest` tracking all installed files and `setup.yaml` with install metadata (scope, mode, source, timestamp, manifest). Updates `settings.json` with hook entries via jq. Uninstall reads manifest for clean removal. Both handle migration from the old commands+skills layout.

Installed layout:
```
<target>/.claude/
  promptforge/hooks/     ← hook scripts
  promptforge/logs/      ← JSONL log files
  promptforge/schema.json
  promptforge/setup.yaml ← install metadata (scope, mode, source, manifest)
  promptforge/install.manifest
  skills/promptforge/    ← unified skill directory (SKILL.md, workflows/, scripts/)
```

### Scope Selection
For **global installs** (`scope: global` in `setup.yaml`), all workflows ask the user whether to run in project or global scope:
- **Project scope**: filters log entries by `project_dir` via `--project-filter`, targets project-local config
- **Global scope**: analyzes all log entries, targets `~/.claude/` config files

For **project-local installs**, project scope is used automatically. The scope preamble (`skills/promptforge/scope-preamble.md`) is read before each workflow — it reads `setup.yaml` via the Read tool (no Bash needed) and sets scope variables (`SCOPE_PROJECT_FILTER`, `SCOPE_TARGET_DIR`, `SCOPE_FRICTION_REPORT`, `SCOPE_LABEL`).

## Development Conventions

- Hook scripts duplicate `resolve_log_dir()` intentionally (isolation over DRY)
- Python scripts use only stdlib (no pip dependencies)
- jq is the only external dependency for hooks; python3 is optional (for analysis)
- Tags are the primary mechanism for filtering and categorization across the system
- Log files are append-only, daily-partitioned, never overwritten
- **ALWAYS** update both `CLAUDE.md` and `README.md` after any code change to reflect the current state of the codebase. This is mandatory — no change is complete without updating the docs.
