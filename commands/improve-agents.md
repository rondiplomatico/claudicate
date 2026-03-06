# Improve Agent Usage

Use promptforge agent analysis and friction data to suggest improvements to agent prompts, skill definitions, and CLAUDE.md instructions.

**Before running this command**, read and follow the scope selection procedure in the `_scope-preamble.md` file located alongside this command file.

## Prerequisites

This command works best after running:
1. `/promptforge:analyze-corrections` to generate a Friction Report
2. `/promptforge:analyze-agents` to generate an Agent Analysis Report

If the friction report doesn't exist at `$SCOPE_FRICTION_REPORT`, run the analysis first.

## Data Sources

1. **Friction Report**: `$SCOPE_FRICTION_REPORT`
2. **Agent Analysis**: output of `analyze-agents.py` (run inline if not cached)
3. **PromptForge logs**: `~/.claude/promptforge/logs/*.jsonl` and project logs
4. **Current config** (read via task agent to avoid context flooding), resolved by scope:
   - **Project scope**: `CLAUDE.md`, `.claude/skills/`, BMAD templates
   - **Global scope**: `~/.claude/CLAUDE.md`, `~/.claude/skills/`

## Process

### Step 1: Run Agent Analysis
Run `analyze-agents.py` to get agent session overview, friction patterns, and parent-child correlations.

### Step 2: Gather Context
Spawn a task agent to read and summarize: CLAUDE.md agent instructions, skill definitions, BMAD agent templates.

### Step 3: Cross-Reference
For each agent session with friction:
- What parent user prompt triggered the agent?
- What went wrong in the agent session (denied tools, corrections, wasted work)?
- Could a CLAUDE.md instruction, skill prompt improvement, or permission change have prevented it?

### Step 4: Generate Suggestions

#### CLAUDE.md Changes
- New agent-related instructions to add
- Existing instructions to clarify for agent behavior

#### Skill Prompt Improvements
- Task prompts that are too vague or miss constraints
- Agent instructions that lead to friction

#### Permission Changes
- Tools commonly denied in agent sessions that should be pre-approved

## Output

Present suggestions as a numbered list with:
- **What**: The specific change
- **Why**: The friction pattern it addresses (with example from agent logs)
- **Where**: Exact file and location
- **Priority**: High (frequent friction) / Medium / Low

Ask the user which suggestions to apply before making any changes.
