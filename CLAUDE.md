# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is claudicate?

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
- Resolve log directory (project-local `.claudicate/logs/` first, global `~/.claudicate/logs/` fallback)
- Normalize `project_dir` paths (backslash → forward slash via `sed 's|\\|/|g'`) for Windows compatibility
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
- `extract-sessions.py` — backfills logs from Claude Code session transcripts; `--project` filter encodes paths to match Claude Code's directory naming convention (slashes → hyphens) and also filters individual records by `cwd` field
- `validate-logs.py` — validates JSONL against schema

Analysis scripts co-located in `skills/claudicate/scripts/`:
- `analyze_usage.py` — generates usage report (volume, time patterns, token usage, tags); excludes agent sessions by default (`--include-agents` to include)
- `analyze_agents.py` — agent-specific analysis (overview, prompt characteristics, friction, parent-child session correlation, complexity)
- `extract_friction.py` — pre-aggregates friction signals (denials, negations, contradictions, repeated clarifications) into JSON; excludes agent sessions by default (`--include-agents` to include)
- `extract_permissions.py` — analyzes permissions across `settings.json` (shared) and `settings.local.json` (personal) for redundancies, anomalies, generalization opportunities, new candidates from tool usage/denial logs, and actual usage breakdown per wildcard pattern (for LLM-driven tightening analysis); tracks which file each entry comes from
- `analyze_cohort.py` — cohort analysis for a named agent/skill group (`--target bmad`, `--target bmad:dev`, `--target slash:/x`, `--target skill:x`, `--target tag:x`) or discovery mode (`--list`) that scans logs and ranks candidate groups by invocation count. Reports direct invocations, per-member breakdown, session-level adoption (sessions containing ≥1 invocation + prompts inside those sessions — the realistic "how much work happens in this mode" figure), session-length comparison vs non-cohort, member combinations, daily volume, friction (denials + negation language) within cohort sessions, and agent-tool subagent fanout. Auto-detects declared sets for unused-member reporting (BMAD family → `.bmad-core/agents/*.md`, skill family → `.claude/skills/*/SKILL.md`); `--declared-from` overrides. Discovery dedupes across detection paths: BMAD tag family absorbs `/BMad:agents:*` slashes; `<command-message>` entries covered by a slash-cluster are suppressed.

All analysis scripts support `--logs-dir` (repeatable), `--since`, auto-discover log directories, and `--project-filter DIR` to restrict analysis to entries from a specific project. Path comparison in `--project-filter` normalizes backslashes to forward slashes for Windows compatibility.

### Unified Skill (`skills/claudicate/`)
A single skill directory provides all claudicate workflows via `/claudicate <workflow>`. The `SKILL.md` router accepts arguments (`$0`) to dispatch to workflow files, or presents an interactive menu if no argument is given.

```
skills/claudicate/
  SKILL.md              ← router (user-invocable, no auto-trigger)
  scope-preamble.md     ← shared scope selection logic
  workflows/            ← one .md per workflow (merged command+skill docs)
    diagnose.md
    gait.md
    agent-xray.md
    cohort.md
    prescribe.md
    prescribe-bmad.md
    rehab.md
    tighten.md
    clean.md
  scripts/              ← co-located Python analysis scripts
    extract_friction.py
    extract_permissions.py
    analyze_usage.py
    analyze_agents.py
    analyze_cohort.py
```

Two workflow chains:
- **User friction**: `diagnose` (generates friction report) → `prescribe` or `prescribe-bmad` (consumes friction report, cross-references with current config, suggests changes)
- **Agent improvement**: `agent-xray` (agent session analysis) + friction report → `rehab` (suggests agent prompt, skill, and instruction improvements)
- **Skillset analysis**: `cohort` (targeted or auto-discovered group breakdown — session-level adoption, member distribution, declared-vs-observed) — feeds qualitative input into `prescribe-bmad` and `rehab`
- **Log management**: `clean` (delete logs and/or friction reports by scope, optionally filtered by date)
- **Permission optimization**: `tighten` (analyzes both `settings.json` and `settings.local.json` for redundancies, consolidation, new candidates from tool usage/denial logs, and overly broad patterns with tightening suggestions based on actual usage; scope-aware with cross-scope redundancy detection; in project scope, also reads global settings; writes changes back to the correct file)

### Installation (`install.sh`, `uninstall.sh`)
Interactive scripts (no CLI args). Install supports link (symlink) or copy mode. For project-specific installs, the initial session import filters to only the target project's sessions (`--project`). Data (hooks, logs, schema, config) goes to `.claudicate/`; skills go to `.claude/skills/`. Hook entries are registered in the appropriate settings file: **global installs** use `.claude/settings.json` (Claude Code doesn't support `settings.local.json` at the global `~/.claude/` level), **project installs** use `.claude/settings.local.json` (local, not committed — hooks use absolute paths and write to local `.claudicate/`). Writes `install.manifest` and `setup.yaml` with install metadata. For project installs in git repos, offers to add `.claudicate/` to `.gitignore` (warns about log data exposure if skipped). Uninstall reads manifest for clean removal.

Installed layout:
```
<target>/.claudicate/
  hooks/                 ← hook scripts
  logs/                  ← JSONL log files
  schema.json
  setup.yaml             ← install metadata (scope, mode, source, manifest)
  install.manifest
<target>/.claude/
  skills/claudicate/    ← unified skill directory (SKILL.md, workflows/, scripts/)
  settings.json          ← hook entries (global installs)
  settings.local.json    ← hook entries (project installs, not committed)
```

### Scope Selection
For **global installs** (`scope: global` in `setup.yaml`), all workflows ask the user whether to run in project or global scope:
- **Project scope**: filters log entries by `project_dir` via `--project-filter`, targets project-local config
- **Global scope**: analyzes all log entries, targets `~/.claude/` config files

For **project-local installs**, project scope is used automatically. The scope preamble (`skills/claudicate/scope-preamble.md`) is read before each workflow — it reads `~/.claudicate/setup.yaml` via the Read tool (no Bash needed) and sets scope variables (`SCOPE_PROJECT_FILTER`, `SCOPE_TARGET_DIR`, `SCOPE_FRICTION_REPORT`, `SCOPE_LABEL`).

## Development Conventions

- Hook scripts duplicate `resolve_log_dir()` intentionally (isolation over DRY)
- Python scripts use only stdlib (no pip dependencies)
- jq is the only external dependency for hooks; python3 is optional (for analysis)
- Tags are the primary mechanism for filtering and categorization across the system
- Log files are append-only, daily-partitioned, never overwritten
- **ALWAYS** update both `CLAUDE.md` and `README.md` after any code change to reflect the current state of the codebase. This is mandatory — no change is complete without updating the docs.
- When bumping the version, update the static badge in `README.md` (line 5: `version-X.Y.Z-blue`)
