# PromptForge

A self-improvement toolkit for Claude Code. Captures user interactions (prompts, clarification answers, tool denials, tool uses, turn metadata) as structured JSONL, then analyzes friction patterns and suggests improvements to your project configuration, permissions, and BMAD setup.

Agent sessions (from Claude Code sub-agents) are automatically detected and tagged. Analysis scripts exclude agent noise by default (`--include-agents` to opt in), and dedicated agent analysis tools let you inspect and improve agent behavior separately.

## Install / Uninstall

**Prerequisites**: `jq` (required), `python3` (optional, for analysis scripts)

```bash
./install.sh    # interactive: choose target, link/copy mode, optional history import
./uninstall.sh  # interactive: manifest-based removal with user-file detection
```

Both scripts prompt for the target: global (`~/.promptforge/` + `~/.claude/`), a project path, or the current directory. Data (hooks, logs, schema, config) goes to `.promptforge/`; skills go to `.claude/skills/`. Hook entries are registered in the appropriate settings file using Claude Code's nested object format (`{ "hooks": { "EventName": [{ "hooks": [...] }] } }`): **global installs** use `.claude/settings.json` (Claude Code doesn't support `settings.local.json` at `~/.claude/`), **project installs** use `.claude/settings.local.json` (local, not committed — hooks use absolute paths). The `PostToolUse` hook for `log-tool-use.sh` uses a `matcher` (`Bash|Write|Edit`) to filter at registration rather than in the script. Install supports **symlink** mode (auto-updates on `git pull`) or **copy** mode. Run install multiple times for different targets.

The installer writes an `install.manifest` and a `setup.yaml` (scope, mode, source, manifest metadata) to `.promptforge/`, used by the skill and the uninstaller. For project installs in git repos, the installer offers to add `.promptforge/` to `.gitignore` (with a clear warning if skipped — logs contain session prompts, tool arguments, and timestamps that shouldn't be committed). Uninstall also checks for user-added files and optionally preserves log data.

**Updating** (symlink mode): `git pull` in the promptforge repo. Copy mode: re-run `./install.sh`.

## Scope Selection

For **global installs**, each promptforge workflow asks whether to run in **project** or **global** scope:

- **Project scope**: analyzes only log entries from the current project and targets project-local config (`CLAUDE.md`, `.claude/settings.json`, project memory)
- **Global scope**: analyzes all log entries across projects and targets global config (`~/.claude/CLAUDE.md`, `~/.claude/settings.json`, `~/.claude/memory/`)

For **project-local installs**, project scope is used automatically — no question is asked.

The scope is detected from `setup.yaml` (written at install time), so no Bash/readlink tool use is needed.

## How to Use

All workflows are accessed through a single skill: `/promptforge <workflow>`. Type `/promptforge` with no arguments to see an interactive menu.

### `/promptforge analyze-usage` — Usage Report

Generates a report on interaction volume, activity distribution, token usage, time patterns, and project breakdown. Scope-aware: in project scope, only entries from the current project are included.

```bash
# Or run the script directly with options:
python3 skills/promptforge/scripts/analyze_usage.py --since 2026-01-01 --format markdown --output report.md
python3 skills/promptforge/scripts/analyze_usage.py --project-filter /path/to/project --format markdown
```

### `/promptforge analyze-corrections` — Friction Analysis

Detects friction patterns: repeated clarifications, tool denials, negation language, contradictions, and correction chains. Writes a Friction Report to the scope-appropriate location (project: `<project>/.promptforge/friction-report.md`, global: `~/.promptforge/friction-report.md`).

Uses `skills/promptforge/scripts/extract_friction.py` to pre-aggregate signals, reducing context load for analysis. Agent sessions are excluded by default.

### `/promptforge improve-project` — Project Config Improvements

Reads the Friction Report (from analyze-corrections) and cross-references it with your current config. In project scope, targets `CLAUDE.md`, `.claude/settings.json`, and project memory. In global scope, targets `~/.claude/CLAUDE.md`, `~/.claude/settings.json`, and `~/.claude/memory/`.

**Requires**: Run `analyze-corrections` first to generate the friction report.

### `/promptforge improve-bmad` — BMAD Config Improvements

Filters friction patterns for BMAD-related items and cross-references with your `.bmad-core/` agents, tasks, and checklists. Suggests defaults, template additions, and checklist adjustments. Only works in project scope (BMAD is project-local).

**Requires**: Run `analyze-corrections` first. Only useful if you use BMAD.

### `/promptforge analyze-agents` — Agent Session Analysis

Analyzes Claude Code sub-agent sessions separately from user sessions. Reports agent-to-user ratio, prompt characteristics (including warmup noise), agent-specific friction, parent-child session correlation (which user prompts spawned which agents), and session complexity.

```bash
python3 skills/promptforge/scripts/analyze_agents.py --format markdown
python3 skills/promptforge/scripts/analyze_agents.py --since 2026-02-01 --project-filter /path/to/project
```

### `/promptforge improve-agents` — Agent Improvement Suggestions

Uses agent analysis and friction data to suggest improvements to agent prompts, skill definitions, and CLAUDE.md agent instructions. Correlates agent friction back to the parent user intent that triggered it.

**Requires**: Run `analyze-corrections` first. Works best after `analyze-agents` too.

### `/promptforge improve-permissions` — Permission Optimization

Analyzes permission patterns across both `settings.json` (shared/versioned) and `settings.local.json` (personal/local) and suggests optimizations:

- **Redundancies**: entries already covered by broader patterns (e.g., `Bash(grep -h:*)` when `Bash(grep:*)` exists) — including cross-file redundancies (local entry covered by shared pattern)
- **Anomalies**: malformed entries (bash comments, broken syntax)
- **Consolidation**: groups of one-off exact commands that can be replaced by a single wildcard pattern
- **New candidates**: frequently denied/used tools from logs that should be added to the allow list

Scope-aware: in project scope, also detects cross-scope redundancies (project entries already covered by global settings). Changes are written back to the correct file (machine-specific patterns to `settings.local.json`, general patterns to `settings.json`).

```bash
# Or run the analysis script directly:
python3 skills/promptforge/scripts/extract_permissions.py \
  --settings-file ~/.claude/settings.json \
  --local-settings-file ~/.claude/settings.local.json \
  --logs-dir ~/.promptforge/logs/ \
  --output /tmp/promptforge-permissions-data.json
```

### Recommended Workflow

**User-focused improvement:**
1. Use Claude Code normally to accumulate logs
2. `/promptforge analyze-usage` — understand your patterns
3. `/promptforge analyze-corrections` — generate friction report
4. `/promptforge improve-project` and/or `/promptforge improve-bmad` — get actionable suggestions

**Permission cleanup:**
1. Use Claude Code normally to accumulate tool usage/denial logs
2. `/promptforge improve-permissions` — get redundancy, consolidation, and new pattern suggestions

**Agent-focused improvement:**
1. `/promptforge analyze-agents` — understand agent usage patterns
2. `/promptforge analyze-corrections` — generate friction report (agents excluded by default)
3. `/promptforge improve-agents` — get suggestions for agent prompt and skill improvements

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

Any use or distribution must include credit: "Built with PromptForge"
