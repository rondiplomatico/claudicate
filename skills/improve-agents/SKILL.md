# Skill: Improve Agent Usage

## Description
Uses promptforge agent analysis and friction data to suggest improvements to agent prompts, skill definitions, and CLAUDE.md agent instructions.

## Trigger
When user runs `/promptforge:improve-agents` or asks to improve agent behavior based on friction analysis.

## Steps

1. **Check for Friction Report**:
   Look for `$SCOPE_FRICTION_REPORT`. If it doesn't exist, inform the user to run `/promptforge:analyze-corrections` first.

2. **Run agent analysis**:
   Locate and run `analyze-agents.py`:
   ```bash
   SCRIPT="$(dirname "$(readlink -f ~/.claude/promptforge/hooks/log-prompt.sh)")/../scripts/analyze-agents.py"
   python3 "$SCRIPT" --format markdown $SCOPE_PROJECT_FILTER --output /tmp/promptforge-agent-report.md
   ```

3. **Gather context via task agent**:
   Spawn a task agent to read:
   - CLAUDE.md (look for agent-related instructions, skill references)
   - Skill definitions in `.claude/skills/` (agent prompts, task templates)
   - BMAD agent templates if present

   > Return a condensed summary of:
   > 1. **Agent-related CLAUDE.md instructions** (one line each)
   > 2. **Skill definitions** that spawn agents (name, purpose, prompt patterns)
   > 3. **BMAD agent templates** if any (name, purpose)

4. **Read agent analysis report**:
   Read `/tmp/promptforge-agent-report.md`.

5. **Cross-reference and analyze**:
   For each agent session with friction (denials, corrections):
   - Identify the parent user prompt that spawned it
   - Identify what went wrong (tool denied, wrong approach, wasted work)
   - Check if a CLAUDE.md instruction could have prevented the issue
   - Check if a skill prompt is too vague or missing constraints

6. **Present suggestions**:
   Number each suggestion with:
   - **What**: The specific change (instruction addition, skill prompt edit, permission update)
   - **Why**: The friction pattern it addresses (with example from agent logs)
   - **Where**: Exact file and location
   - **Priority**: High (frequent friction) / Medium / Low

   Ask user which to apply before making changes.

## Input
No explicit input. Uses friction report, agent analysis, and project files.

## Output
- Numbered list of suggestions with diffs
- Applied changes (after user approval)
