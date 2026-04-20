# Cohort — Agent/Skill Group Analysis

Analyze usage for a named agent/skill group (e.g., BMAD, a slash-command, a skill family), or let the tool discover groups from your logs.

Two modes:
- **Targeted** (`/claudicate cohort <target>`): deep breakdown of one group.
- **Discovery** (`/claudicate cohort`): scan logs, list candidate groups, then pick one or show a generic overview.

## Prerequisites

None.

## Target selector syntax

| Form | Example | Meaning |
|------|---------|---------|
| `<family>` | `bmad` | Tag family — all tags starting with `<family>:` or `<family>_` |
| `<family>:<member>` | `bmad:dev` | Exact tag |
| `slash:/<cmd>` or `/<cmd>` | `/analyze-evaluation` | Prompts starting with that slash command |
| `skill:<name>` | `skill:claudicate` | Prompts invoking a skill (slash or `<command-message>`) |
| `tag:<x>` | `tag:planning` | Exact tag match |
| `skills` | `skills` | Skill family (any non-BMAD slash invocation) |

## Steps

### 1. If a target was provided on the command line → targeted mode

When `$ARGUMENTS` is non-empty, treat it as the target:

```bash
python3 <skill_dir>/scripts/analyze_cohort.py --target "$ARGUMENTS" --format markdown $SCOPE_PROJECT_FILTER
```

Jump to step 3.

### 2. If no target → discovery mode

Run the discovery list:

```bash
python3 <skill_dir>/scripts/analyze_cohort.py --list --format markdown $SCOPE_PROJECT_FILTER
```

Present the candidate table to the user. Then use `AskUserQuestion` to let them choose:
- One of the top groups from the list (options labelled with the `target` value)
- **Generic Overview** — show the discovery table itself as the final report (no deeper drilldown)
- **Other** (free text) — user supplies a target selector

If the user picks a specific group, re-run the script with `--target <selector>` as in step 1.
If the user picks **Generic Overview**, the discovery output *is* the report — skip step 3's script call and proceed to interpretation.

### 3. Present and interpret

Render the script output as-is (already markdown). Add interpretation:

- **Session-level adoption**: the "Prompts in cohort sessions" figure is the realistic "how much of my work runs in this mode" number. Call out the gap vs direct invocations.
- **Member breakdown**: highlight the dominant member and any near-zero ones.
- **Session length comparison**: if cohort sessions are materially longer than non-cohort, note it.
- **Combinations**: if the cohort has a family structure, flag recurring hand-offs (e.g., `po + sm`) and missed ones.
- **Declared vs Observed**: if unused members are listed, flag them as candidates for removal or re-evaluation.
- **Friction**: denials and negation density inside cohort sessions point at rough edges.
- **Subagent fanout**: large fanout ratios suggest the cohort is a major driver of agent-tool usage.

## Script reference

```bash
python3 <skill_dir>/scripts/analyze_cohort.py \
  [--target <selector>] [--list] \
  [--logs-dir DIR]... [--since YYYY-MM-DD] [--project-filter DIR] \
  [--format text|markdown] [--output FILE] \
  [--declared-from DIR] [--include-agents] [--min-discovery N]
```

- `--declared-from`: override path for declared-set detection (default: auto-find `.bmad-core/agents/` or `.claude/skills/` under project filter, CWD, or `$CLAUDE_PROJECT_DIR`).
- `--min-discovery`: threshold for a group to appear in discovery (default 5 invocations).
- `$SCOPE_PROJECT_FILTER` is `--project-filter <project_dir>` for project scope, omitted for global scope.

## Related workflows

- `gait` — overall volume numbers; cohort drills into one slice.
- `agent-xray` — analyzes subagent (agent-tool) sessions; complementary, not overlapping.
- `prescribe-bmad` — once the BMAD cohort surface is understood, this suggests concrete config/definition fixes.
- `rehab` — agent-behavior improvement suggestions.
