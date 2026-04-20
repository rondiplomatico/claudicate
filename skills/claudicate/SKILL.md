---
user-invocable: true
disable-model-invocation: true
---

# Claudicate

Analyze Claude Code interaction logs for friction patterns and suggest improvements to project configuration and BMAD setup.

Usage: `/claudicate <workflow>` or `/claudicate` to choose interactively.

## Available workflows

| Workflow | Description |
|----------|-------------|
| `diagnose` | Scan logs for corrections, negations, tool denials, and friction patterns |
| `gait` | Generate usage report (volume, time patterns, token usage, tags) |
| `agent-xray` | Analyze agent/subagent session patterns and effectiveness |
| `cohort` | Analyze a specific agent/skill group (BMAD, slash-commands, skills) or auto-detect groups |
| `prescribe` | Suggest improvements to CLAUDE.md, permissions, and memory files |
| `prescribe-bmad` | Suggest improvements to BMAD agent and task definitions |
| `rehab` | Suggest improvements to agent behavior and configuration |
| `tighten` | Optimize settings.json permission patterns (redundancies, consolidation, new candidates) |
| `clean` | Delete logs and/or friction reports to start fresh |

## Routing

If `$ARGUMENTS` is provided and `$0` matches a workflow name above, read and follow `workflows/$0.md` in this skill directory.

If `$ARGUMENTS` is empty:

1. Read and follow `scope-preamble.md` first (to set scope variables).
2. Check whether a friction report exists at `$SCOPE_FRICTION_REPORT` (use the Read tool — a missing file is fine, just note it).
3. Based on the state, suggest a starting workflow:
   - **No logs exist** at the scope's log directory → Tell the user to use Claude Code for a while first to accumulate data, then come back.
   - **Logs exist but no friction report** → Suggest `diagnose` ("You have logs but no friction report yet — start with `diagnose` to see where it hurts.")
   - **Friction report exists** → Suggest `prescribe` ("You have a friction report ready — run `prescribe` to get actionable fixes.")
4. Present the full workflows table and ask the user which workflow to run using AskUserQuestion. Include the suggestion as context, not a default — the user picks.

## Before any workflow

Read and follow `scope-preamble.md` in this skill directory. This sets scope variables (`SCOPE_PROJECT_FILTER`, `SCOPE_TARGET_DIR`, `SCOPE_FRICTION_REPORT`, `SCOPE_LABEL`) used by all workflows.

## Script references

All Python scripts are in the `scripts/` subdirectory of this skill directory. Reference them relative to this SKILL.md location.
