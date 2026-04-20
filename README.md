# Claudicate

![Claudicate](claudicate_banner.png)

[![Version](https://img.shields.io/badge/version-1.1.0-blue)](https://github.com/rondiplomatico/claudicate)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Shell](https://img.shields.io/badge/shell-bash-89e051)](https://www.gnu.org/software/bash/)
[![Python](https://img.shields.io/badge/python-3.6%2B-3776ab)](https://www.python.org/)
[![Claude Code](https://img.shields.io/badge/Claude_Code-hooks-cc785c)](https://docs.anthropic.com/en/docs/claude-code)

*claudicate* (v.) — from Latin *claudicāre*, to limp.

Your workflow is limping. You just haven't measured the gait yet. Claudicate hooks into every Claude Code interaction — every hedged prompt, every tool denial, every correction you mumble after the third clarification question — and writes it all down. It doesn't fix anything. It just makes the limp impossible to ignore.

A self-improvement toolkit for Claude Code. Captures user interactions (prompts, clarification answers, tool denials, tool uses, turn metadata) as structured JSONL, then analyzes friction patterns and suggests improvements to your project configuration, permissions, and BMAD setup.

Agent sessions (from Claude Code sub-agents) are automatically detected and tagged. Analysis scripts exclude agent noise by default (`--include-agents` to opt in), and dedicated agent analysis tools let you inspect and improve agent behavior separately.

## Install / Uninstall

**Prerequisites**: `jq` (required), `python3` (optional, for analysis)

**Platform note**: Works on Linux, macOS, and Windows (WSL/Git Bash). Hooks normalize Windows backslash paths to forward slashes before logging.

    ./install.sh    # interactive
    ./uninstall.sh  # manifest-based removal

Both scripts ask where to install: globally (`~/.claudicate/`), a project path, or the current directory.

- **Symlink mode** — auto-updates when you `git pull` the repo
- **Copy mode** — standalone, re-run `./install.sh` to update
- Hooks land in `.claudicate/hooks/`; skills in `.claude/skills/`
- Global installs register hooks in `.claude/settings.json`; project installs use `.claude/settings.local.json` (not committed)
- Installer writes `setup.yaml` and `install.manifest` to `.claudicate/` for scope detection and clean uninstall
- For project installs in git repos, offers to add `.claudicate/` to `.gitignore` (your logs contain prompts and timestamps — skip at your own risk)
- Run install multiple times for different targets

## Scope Selection

For **global installs**, each workflow asks whether to run in **project** or **global** scope:

- **Project scope**: analyzes only log entries from the current project and targets project-local config (`CLAUDE.md`, `.claude/settings.json`, project memory)
- **Global scope**: analyzes all log entries across projects and targets global config (`~/.claude/CLAUDE.md`, `~/.claude/settings.json`, `~/.claude/memory/`)

For **project-local installs**, project scope is used automatically — no question is asked.

The scope is detected from `setup.yaml` (written at install time), so no Bash/readlink tool use is needed.

## How to Use

All workflows are accessed through a single skill: `/claudicate <workflow>`. Type `/claudicate` with no arguments to see an interactive menu.

### `/claudicate gait` — Usage Report

How much are you actually using this thing, and where does the time go? Generates a report on interaction volume, activity distribution, token usage, time patterns, and project breakdown. Scope-aware: in project scope, only entries from the current project are included.

```bash
# Or run the script directly with options:
python3 skills/claudicate/scripts/analyze_usage.py --since 2026-01-01 --format markdown --output report.md
python3 skills/claudicate/scripts/analyze_usage.py --project-filter /path/to/project --format markdown
```

### `/claudicate diagnose` — Friction Analysis

Finds the patterns you'd rather not see. Detects repeated clarifications, tool denials, negation language, contradictions, and correction chains. Writes a Friction Report to the scope-appropriate location (project: `<project>/.claudicate/friction-report.md`, global: `~/.claudicate/friction-report.md`).

Uses `skills/claudicate/scripts/extract_friction.py` to pre-aggregate signals, reducing context load for analysis. Agent sessions are excluded by default.

### `/claudicate prescribe` — Project Config Improvements

Takes your friction report and tells you what to fix. Whether you listen is between you and your config. Reads the Friction Report (from `diagnose`) and cross-references it with your current config. In project scope, targets `CLAUDE.md`, `.claude/settings.json`, and project memory. In global scope, targets `~/.claude/CLAUDE.md`, `~/.claude/settings.json`, and `~/.claude/memory/`.

**Requires**: Run `diagnose` first to generate the friction report.

### `/claudicate prescribe-bmad` — BMAD Config Improvements

Filters friction patterns for BMAD-related items and cross-references with your `.bmad-core/` agents, tasks, and checklists. Suggests defaults, template additions, and checklist adjustments. Only works in project scope (BMAD is project-local).

**Requires**: Run `diagnose` first. Only useful if you use BMAD.

### `/claudicate agent-xray` — Agent Session Analysis

Analyzes Claude Code sub-agent sessions separately from user sessions. Reports agent-to-user ratio, prompt characteristics (including warmup noise), agent-specific friction, parent-child session correlation (which user prompts spawned which agents), and session complexity.

```bash
python3 skills/claudicate/scripts/analyze_agents.py --format markdown
python3 skills/claudicate/scripts/analyze_agents.py --since 2026-02-01 --project-filter /path/to/project
```

### `/claudicate cohort` — Agent/Skill Group Analysis

Picks a slice and shows you what's actually happening inside it. Targeted mode analyzes one group (`/claudicate cohort bmad`, `/claudicate cohort bmad:dev`, `/claudicate cohort /analyze-evaluation`, `/claudicate cohort skill:claudicate`). Discovery mode (`/claudicate cohort` with no argument) scans the logs, surfaces candidate groups, and lets you pick one — or asks for the generic overview if you just want the landscape.

Reports per cohort:
- Direct invocations and per-member breakdown (e.g., `bmad:dev` vs `bmad:po`)
- **Session-level adoption** — sessions containing ≥1 invocation and the total prompts inside those sessions (the realistic "how much of my work happens in this mode" figure; usually much larger than raw invocation count)
- Session-length comparison vs non-cohort sessions
- Member combinations per session (which members are used together)
- Daily volume and friction (tool denials + negation language) inside cohort sessions
- Agent-tool subagent fanout attributable to the cohort
- **Declared vs Observed** — for BMAD families, auto-reads `.bmad-core/agents/` and flags unused roles; for skill families, reads `.claude/skills/`

```bash
python3 skills/claudicate/scripts/analyze_cohort.py --target bmad --format markdown
python3 skills/claudicate/scripts/analyze_cohort.py --list --project-filter /path/to/project
```

### `/claudicate rehab` — Agent Improvement Suggestions

Uses agent analysis and friction data to suggest improvements to agent prompts, skill definitions, and CLAUDE.md agent instructions. Correlates agent friction back to the parent user intent that triggered it.

**Requires**: Run `diagnose` first. Works best after `agent-xray` too.

### `/claudicate clean` — Reset Logs and Reports

Sometimes you want a fresh start. Interactively delete accumulated log data and/or friction reports within the current scope. Options:

- **All logs** — wipe all JSONL log files
- **Logs before a date** — prune logs older than a cutoff (uses `YYYY-MM-DD.jsonl` filenames)
- **Friction reports** — remove generated friction report files

Scope-aware: in project scope, only touches project-local data; in global scope, touches `~/.claudicate/`.

### `/claudicate tighten` — Permission Optimization

Finds the wildcard patterns you added at 2am and gently suggests you didn't mean `Bash(*)`. Analyzes permission patterns across both `settings.json` (shared/versioned) and `settings.local.json` (personal/local) and suggests optimizations:

- **Redundancies**: entries already covered by broader patterns (e.g., `Bash(grep -h:*)` when `Bash(grep:*)` exists) — including cross-file redundancies (local entry covered by shared pattern)
- **Anomalies**: malformed entries (bash comments, broken syntax)
- **Consolidation**: groups of one-off exact commands that can be replaced by a single wildcard pattern
- **New candidates**: frequently denied/used tools from logs that should be added to the allow list
- **Tightening**: overly broad wildcard patterns (e.g., `Bash(python3:*)`) evaluated against actual usage from logs, with narrower replacements proposed (e.g., `Bash(python3 -m pytest:*)`)

Scope-aware: in project scope, also reads global settings (which apply to the project) and detects cross-scope redundancies. Changes are written back to the correct file (machine-specific patterns to `settings.local.json`, general patterns to `settings.json`).

```bash
# Or run the analysis script directly:
python3 skills/claudicate/scripts/extract_permissions.py \
  --settings-file ~/.claude/settings.json \
  --local-settings-file ~/.claude/settings.local.json \
  --logs-dir ~/.claudicate/logs/ \
  --output /tmp/claudicate-permissions-data.json
```

### Recommended Workflow

The loop that makes the limp visible:

**User-focused improvement:**
1. Use Claude Code normally to accumulate logs
2. `/claudicate gait` — understand your patterns
3. `/claudicate diagnose` — generate friction report
4. `/claudicate prescribe` and/or `/claudicate prescribe-bmad` — get actionable suggestions

**Permission cleanup:**
1. Use Claude Code normally to accumulate tool usage/denial logs
2. `/claudicate tighten` — get redundancy, consolidation, and new pattern suggestions

**Maintenance:**
- `/claudicate clean` — prune old logs or start fresh

**Agent-focused improvement:**
1. `/claudicate agent-xray` — understand agent usage patterns
2. `/claudicate diagnose` — generate friction report (agents excluded by default)
3. `/claudicate rehab` — get suggestions for agent prompt and skill improvements

**Skillset analysis:**
1. `/claudicate cohort` — discovery: find which agent/skill groups exist in your logs
2. `/claudicate cohort <target>` — deep breakdown for one group (e.g., `bmad`, `/analyze-evaluation`)
3. Feed findings into `/claudicate prescribe-bmad` or `/claudicate rehab` for concrete fixes

### Utility Scripts

```bash
# Backfill from existing Claude Code sessions
python3 scripts/extract-sessions.py --include-old-logs
python3 scripts/extract-sessions.py --since 2026-01-01 --project myproject

# Validate log files against schema
python3 scripts/validate-logs.py
```

## License

MIT License with attribution requirement. See [LICENSE](LICENSE) for details.

Any use or distribution must include credit: "Built with Claudicate"
