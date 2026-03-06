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
- Resolve log directory (project-local `.promptforge/logs/` first, global `~/.promptforge/logs/` fallback)
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

`log-prompt.sh` applies auto-tags via regex (bmad, slash_command, planning, testing, git_ops, compaction, etc.). `log-tool-denial.sh` filters to only user interrupts and explicit denials. `log-tool-use.sh` filters to only Bash, Write, and Edit tools (Read/Glob/Grep/Agent are too noisy and not permission-relevant); tool_input is stored as a string (truncated to 500 chars) to avoid broken JSON from mid-truncation. `log-ask-response.sh` handles both single-question (`tool_input.question`) and multi-question (`tool_input.questions[]`) AskUserQuestion formats. All hooks detect agent sessions (session_id starting with `agent-`) and add the `agent` tag automatically.

Hook entries in settings files use Claude Code's nested object format:
```json
{ "hooks": { "EventName": [{ "matcher": "...", "hooks": [{ "type": "command", "command": "..." }] }] } }
```

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
- `extract_permissions.py` — analyzes permissions across `settings.json` (shared) and `settings.local.json` (personal) for redundancies, anomalies, generalization opportunities, and new candidates from tool usage/denial logs; tracks which file each entry comes from

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
- **Permission optimization**: `improve-permissions` (analyzes both `settings.json` and `settings.local.json` for redundancies, consolidation, and new candidates from tool usage/denial logs; scope-aware with cross-scope redundancy detection; writes changes back to the correct file)

### Installation (`install.sh`, `uninstall.sh`)
Interactive scripts (no CLI args). Install supports link (symlink) or copy mode. Data (hooks, logs, schema, config) goes to `.promptforge/`; skills go to `.claude/skills/`. Hook entries are registered in the appropriate settings file: **global installs** use `.claude/settings.json` (Claude Code doesn't support `settings.local.json` at the global `~/.claude/` level), **project installs** use `.claude/settings.local.json` (local, not committed — hooks use absolute paths and write to local `.promptforge/`). Writes `install.manifest` and `setup.yaml` with install metadata. For project installs in git repos, offers to add `.promptforge/` to `.gitignore` (warns about log data exposure if skipped). Uninstall reads manifest for clean removal.

Installed layout:
```
<target>/.promptforge/
  hooks/                 ← hook scripts
  logs/                  ← JSONL log files
  schema.json
  setup.yaml             ← install metadata (scope, mode, source, manifest)
  install.manifest
<target>/.claude/
  skills/promptforge/    ← unified skill directory (SKILL.md, workflows/, scripts/)
  settings.json          ← hook entries (global installs)
  settings.local.json    ← hook entries (project installs, not committed)
```

### Scope Selection
For **global installs** (`scope: global` in `setup.yaml`), all workflows ask the user whether to run in project or global scope:
- **Project scope**: filters log entries by `project_dir` via `--project-filter`, targets project-local config
- **Global scope**: analyzes all log entries, targets `~/.claude/` config files

For **project-local installs**, project scope is used automatically. The scope preamble (`skills/promptforge/scope-preamble.md`) is read before each workflow — it reads `~/.promptforge/setup.yaml` via the Read tool (no Bash needed) and sets scope variables (`SCOPE_PROJECT_FILTER`, `SCOPE_TARGET_DIR`, `SCOPE_FRICTION_REPORT`, `SCOPE_LABEL`).

## Development Conventions

- Hook scripts duplicate `resolve_log_dir()` intentionally (isolation over DRY)
- Python scripts use only stdlib (no pip dependencies)
- jq is the only external dependency for hooks; python3 is optional (for analysis)
- Tags are the primary mechanism for filtering and categorization across the system
- Log files are append-only, daily-partitioned, never overwritten
- **ALWAYS** update both `CLAUDE.md` and `README.md` after any code change to reflect the current state of the codebase. This is mandatory — no change is complete without updating the docs.
