# Analyze Agent Sessions

Analyze Claude Code agent session patterns from PromptForge interaction logs.

**Before running this command**, read and follow the scope selection procedure in the `_scope-preamble.md` file located alongside this command file.

## How to run

Locate `analyze-agents.py` by following the hook symlink back to the repo:

```bash
SCRIPT="$(dirname "$(readlink -f ~/.claude/promptforge/hooks/log-prompt.sh)")/../scripts/analyze-agents.py"
python3 "$SCRIPT" --format markdown $SCOPE_PROJECT_FILTER
```

Where `$SCOPE_PROJECT_FILTER` is either `--project-filter <project_dir>` (project scope) or omitted (global scope), as determined by the scope preamble.

Options: `--logs-dir DIR` (repeatable), `--since YYYY-MM-DD`, `--project-filter DIR`, `--format text|markdown`, `--output FILE`.

## After the script runs

Present the output as a well-formatted report. Highlight:
- Agent-to-user session ratio and whether it's growing
- Warmup noise volume
- Which user prompts spawn the most agents
- Agent sessions with friction (denials, corrections) and what parent prompt triggered them
- Suggestions for reducing agent friction (e.g., better CLAUDE.md instructions, skill improvements)
