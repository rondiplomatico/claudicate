# Rehab — Agent Improvement

Use claudicate agent analysis and friction data to suggest improvements to agent prompts, skill definitions, and CLAUDE.md instructions.

## Prerequisites

Run these workflows first:
1. `/claudicate diagnose` to generate a Friction Report
2. `/claudicate agent-xray` to generate an Agent Analysis Report

If the friction report doesn't exist at `$SCOPE_FRICTION_REPORT`, inform the user and run the analysis.

**Optional context**: Run `/claudicate cohort` (discovery) or `/claudicate cohort <target>` for a named group first if the agent/skill landscape is unclear — it surfaces which slash-commands and skills are actually driving subagent fanout, which makes the cross-referencing in step 4 sharper.

## Steps

### 1. Run agent analysis

Run the agent analysis script:

```bash
python3 <skill_dir>/scripts/analyze_agents.py --format markdown $SCOPE_PROJECT_FILTER --output /tmp/claudicate-agent-report.md
```

### 2. Gather context via task agent

Spawn a task agent to read and summarize:
- CLAUDE.md (look for agent-related instructions, skill references)
- Skill definitions in `.claude/skills/` (agent prompts, task templates)
- BMAD agent templates if present

> Return a condensed summary of:
> 1. **Agent-related CLAUDE.md instructions** (one line each)
> 2. **Skill definitions** that spawn agents (name, purpose, prompt patterns)
> 3. **BMAD agent templates** if any (name, purpose)

### 3. Read reports

Read the friction report at `$SCOPE_FRICTION_REPORT` and the agent analysis at `/tmp/claudicate-agent-report.md`.

### 4. Cross-reference and analyze

For each agent session with friction (denials, corrections):
- Identify the parent user prompt that spawned it
- Identify what went wrong (tool denied, wrong approach, wasted work)
- Check if a CLAUDE.md instruction could have prevented the issue
- Check if a skill prompt is too vague or missing constraints

### 5. Generate and present suggestions

Number each suggestion with:
- **What**: The specific change (instruction addition, skill prompt edit, permission update)
- **Why**: The friction pattern it addresses (with example from agent logs)
- **Where**: Exact file and location
- **Priority**: High (frequent friction) / Medium / Low

**CLAUDE.md Changes**: New agent-related instructions to add, existing instructions to clarify for agent behavior.

**Skill Prompt Improvements**: Task prompts that are too vague or miss constraints, agent instructions that lead to friction.

**Permission Changes**: Tools commonly denied in agent sessions that should be pre-approved.

Ask the user which suggestions to apply before making any changes.
