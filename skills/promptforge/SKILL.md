---
user-invocable: true
disable-model-invocation: true
---

# PromptForge

Analyze Claude Code interaction logs for friction patterns and suggest improvements to project configuration and BMAD setup.

Usage: `/promptforge <workflow>` or `/promptforge` to choose interactively.

## Available workflows

| Workflow | Description |
|----------|-------------|
| `analyze-corrections` | Scan logs for corrections, negations, tool denials, and friction patterns |
| `analyze-usage` | Generate usage report (volume, time patterns, token usage, tags) |
| `analyze-agents` | Analyze agent/subagent session patterns and effectiveness |
| `improve-project` | Suggest improvements to CLAUDE.md, permissions, and memory files |
| `improve-bmad` | Suggest improvements to BMAD agent and task definitions |
| `improve-agents` | Suggest improvements to agent behavior and configuration |
| `improve-permissions` | Optimize settings.json permission patterns (redundancies, consolidation, new candidates) |

## Routing

If `$ARGUMENTS` is provided and `$0` matches a workflow name above, read and follow `workflows/$0.md` in this skill directory.

If `$ARGUMENTS` is empty, present the available workflows table above and ask the user which workflow to run using AskUserQuestion.

## Before any workflow

Read and follow `scope-preamble.md` in this skill directory. This sets scope variables (`SCOPE_PROJECT_FILTER`, `SCOPE_TARGET_DIR`, `SCOPE_FRICTION_REPORT`, `SCOPE_LABEL`) used by all workflows.

## Script references

All Python scripts are in the `scripts/` subdirectory of this skill directory. Reference them relative to this SKILL.md location.
