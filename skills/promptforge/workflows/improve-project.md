# Improve Project Configuration

Use promptforge friction analysis to suggest improvements to CLAUDE.md, permissions, and memory files.

## Prerequisites

Run `/promptforge analyze-corrections` first to generate a Friction Report. If no friction report exists at `$SCOPE_FRICTION_REPORT`, inform the user and run the analysis.

## Steps

### 1. Gather context via task agent

Spawn a task agent to read and summarize config files at `$SCOPE_TARGET_DIR`:
- **Project scope**: `CLAUDE.md`, `.claude/settings.json`, `.claude/settings.local.json`, project memory files (`~/.claude/projects/*/memory/`)
- **Global scope**: `~/.claude/CLAUDE.md`, `~/.claude/settings.json`, `~/.claude/settings.local.json`, `~/.claude/memory/*`

> Return a condensed summary organized as:
> 1. **Key CLAUDE.md instructions** (one line each)
> 2. **Permission patterns** (what's allowed/denied)
> 3. **Memory entries** (key preferences and patterns stored)
> 4. **Potential gaps** (areas not covered by current instructions)

### 2. Read Friction Report

Read `$SCOPE_FRICTION_REPORT` for the top friction patterns.

### 3. Cross-reference

For each friction pattern, determine:
- Is there already a CLAUDE.md instruction that should prevent this? (instruction exists but is ignored/unclear)
- Is there a missing instruction? (no guidance exists for this situation)
- Is there a permission issue? (tool gets denied because it's not in the allow list)
- Is there a memory inconsistency? (memory says one thing, CLAUDE.md says another)

### 4. Generate suggestions

Produce actionable suggestions as diffs/patches:

**CLAUDE.md Changes**: New instructions to add (with exact text), existing instructions to clarify or modify. Cite the friction pattern that motivates each change.

**Permission Changes**: Tools to add to allow lists (commonly approved after denial), patterns for automatic approval.

**Memory File Updates**: New memory entries to add, existing entries to correct or update, entries that should be promoted to CLAUDE.md (stable enough).

### 5. Present suggestions

Number each suggestion with:
- **What**: The specific change
- **Why**: The friction pattern it addresses (with example from logs)
- **Where**: Exact file and location
- **Priority**: High (frequent friction) / Medium / Low

Ask the user which suggestions to apply before making any changes.
