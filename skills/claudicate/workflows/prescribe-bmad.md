# Prescribe BMAD — BMAD Config Improvements

Use claudicate friction analysis to suggest improvements to BMAD agents, tasks, checklists, and configuration.

**Note**: BMAD configuration (`.bmad-core/`) is project-local. If global scope was selected, inform the user that this workflow only works in project scope. Offer to switch to project scope or abort.

## Prerequisites

Run `/claudicate diagnose` first to generate a Friction Report. If no friction report exists at `$SCOPE_FRICTION_REPORT`, inform the user and run the analysis.

**Tip**: Run `/claudicate cohort bmad` beforehand to get a structured breakdown of BMAD agent distribution, session-level adoption, and unused BMAD roles (auto-detected from `.bmad-core/agents/`). The cohort report is useful context when deciding which agent definitions are worth touching.

## Steps

### 1. Identify BMAD-related friction

Read the friction report and filter for patterns tagged with `bmad`, `bmad:<agent>`, or `bmad_task:<task>`. Also look for:
- Friction during BMAD agent sessions (session contains bmad-tagged prompts)
- Repeated clarifications about BMAD workflow
- Tool denials during BMAD task execution

### 2. Gather BMAD context via task agent

Based on the agents/tasks identified in step 1, spawn a task agent:

> Read and summarize the following BMAD files:
> - `.bmad-core/core-config.yaml` — current BMAD settings
> - `.bmad-core/agents/<name>.md` — for each agent mentioned in friction patterns
> - `.bmad-core/tasks/<name>.md` — for each task mentioned in friction patterns
> - `.bmad-core/checklists/*.md` — relevant validation checklists
> - Project memory files — for cross-referencing stored preferences
>
> Return a condensed summary organized as:
> 1. **Core config settings** (key values)
> 2. **Agent instructions** (key behaviors for each relevant agent)
> 3. **Task definitions** (key steps for each relevant task)
> 4. **Checklist items** (gates and quality checks)
> 5. **Memory preferences** (that should propagate to BMAD)

### 3. Cross-reference and generate suggestions

For each BMAD-related friction pattern:
- Does the agent ask unnecessary questions? -> Add defaults
- Is the task template missing steps? -> Add guidance
- Is a checklist too strict/lenient? -> Adjust gates
- Does core-config need settings? -> Add/modify values

Produce actionable suggestions:

**Agent Instruction Patches**: Specific text to add/modify in agent .md files. Example: "QA agent asks for test framework every time -> add default: pytest"

**Task Template Adjustments**: Steps to add, remove, or clarify in task definitions. Default values to set to reduce clarification questions.

**Checklist Refinements**: Items to add or relax based on friction patterns. Quality gates that cause unnecessary rework.

**core-config.yaml Tweaks**: Settings to add or modify. devLoadAlwaysFiles updates.

### 4. Present suggestions

Number each suggestion with:
- **What**: The specific change (with exact text for patches)
- **Why**: The friction pattern it addresses (with example from logs)
- **Where**: Exact file path and section
- **Priority**: High (frequent friction) / Medium / Low

Ask the user which suggestions to apply before making any changes.
