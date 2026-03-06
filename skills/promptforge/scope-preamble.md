# PromptForge Scope Selection

Follow this procedure before executing any promptforge workflow.

## Step 1: Detect install type

Read `~/.promptforge/setup.yaml`. Check the `scope` field:
- If `scope: global` -> this is a **global install**, proceed to Step 2
- If the file does not exist, or `scope: project` -> this is a **project-local install**, skip to Step 3 with **project scope**

## Step 2: Ask scope question (global installs only)

Ask the user using AskUserQuestion:

> **PromptForge Scope**: This is a global install. Run this command for:
> 1. **Project** — analyze only data from the current project and modify project-local config
> 2. **Global** — analyze all data across projects and modify global (`~/.claude/`) config

## Step 3: Set scope variables

Based on the selected scope, use these values throughout the workflow:

### Project scope
- **SCOPE_PROJECT_FILTER**: `--project-filter <current working directory>` (pass to Python scripts)
- **SCOPE_TARGET_DIR**: the current project directory (where `CLAUDE.md`, `.claude/settings.json`, and memory live)
- **SCOPE_FRICTION_REPORT**: `<project>/.promptforge/friction-report.md`
- **SCOPE_LABEL**: "project"

### Global scope
- **SCOPE_PROJECT_FILTER**: (omit — no project filter, analyze all entries)
- **SCOPE_TARGET_DIR**: `~/.claude` (target `~/.claude/CLAUDE.md`, `~/.claude/settings.json`, `~/.claude/memory/`)
- **SCOPE_FRICTION_REPORT**: `~/.promptforge/friction-report.md`
- **SCOPE_LABEL**: "global"

Carry these values forward into the workflow that follows.
