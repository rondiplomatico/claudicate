# Improve Permissions

Analyze and optimize Claude Code permission patterns across `settings.json` (shared/versioned) and `settings.local.json` (personal/local). Detects redundancies, anomalies, generalization opportunities, and suggests new patterns from tool usage logs.

## Settings File Layout

Claude Code merges permissions from multiple files (deny → ask → allow, first match wins):

| File | Purpose | Versioned? |
|------|---------|------------|
| `~/.claude/settings.json` | Global shared settings | No (user home) |
| `~/.claude/settings.local.json` | Global personal settings | No |
| `<project>/.claude/settings.json` | Project shared settings | Yes (committed) |
| `<project>/.claude/settings.local.json` | Project personal settings | No (gitignored) |

Both `settings.json` and `settings.local.json` at each scope are merged. The analysis reads all applicable files; changes are written to the correct file based on which one contains the entry.

## Steps

### 1. Resolve settings files by scope

Based on scope variables from the scope preamble:

- **Project scope**:
  - shared = `$SCOPE_TARGET_DIR/.claude/settings.json`
  - local = `$SCOPE_TARGET_DIR/.claude/settings.local.json`
  - context-shared = `~/.claude/settings.json` (global settings also apply to this project)
  - context-local = `~/.claude/settings.local.json` (global local settings also apply)
- **Global scope**:
  - shared = `~/.claude/settings.json`
  - local = `~/.claude/settings.local.json`
  - no context files

In project scope, the context (global) settings are read-only but included in the analysis output — they affect which permissions are active and may contain patterns that are overly broad for this project.

### 2. Run analysis

Run the `extract_permissions.py` script from the `scripts/` directory:

```
python3 scripts/extract_permissions.py \
  --settings-file <shared> \
  [--local-settings-file <local>] \
  [--context-settings <context-shared>] \
  [--context-local-settings <context-local>] \
  --logs-dir ~/.promptforge/logs/ \
  [--logs-dir <project>/.promptforge/logs/] \
  [$SCOPE_PROJECT_FILTER] \
  --output /tmp/promptforge-permissions-data.json
```

### 3. Read and present findings

Read the output JSON. Each finding includes `source` / `entry_source` fields indicating which file the entry lives in. Present findings organized by category:

#### a. Duplicates
Exact duplicate entries (may be within one file or across shared/local). Safe to remove — just list them with their source file.

#### b. Redundant entries
Entries subsumed by broader patterns. For each:
- **Remove**: the redundant entry (and which file it's in)
- **Kept by**: the broader pattern that already covers it (and which file)
- **Scope**: "within" (same scope) or "cross" (covered by global settings)

#### c. Anomalies
Malformed or suspicious entries (bash comments, broken syntax). For each:
- **Entry**: the problematic pattern (and which file)
- **Issue**: what's wrong
- **Suggestion**: remove or fix

#### d. Generalizable groups
Multiple exact-match entries that share a common pattern. For each group:
- **Entries**: the specific patterns being consolidated (and which files)
- **Conservative proposal**: preserves subcommand specificity (e.g., `Bash(git -C * diff:*)`)
- **Broad proposal**: wider scope (e.g., `Bash(git:*)`)
- **Risk note**: explain what additional commands the broader pattern would allow

#### e. New candidates
Frequently used/denied tools not covered by current patterns. For each:
- **Proposed pattern**: the new allow entry
- **Target file**: suggest `settings.local.json` for machine-specific patterns (absolute paths), `settings.json` for general patterns
- **Evidence**: how many times it appeared in logs, with examples
- **Source**: from denials, successful uses, or both

#### f. Overly broad patterns (tightening)
The output JSON includes `wildcard_usage` — for each wildcard Bash pattern, the actual subcommands observed in logs. Use this data to evaluate which patterns are wider than necessary.

**For each wildcard pattern**, review it with these questions:
- Does this pattern allow executing commands that could cause unintended side effects? (e.g., `python3:*` allows arbitrary script execution, not just pytest)
- Does the actual usage suggest a much narrower scope? (e.g., all 12 uses of `python3` were `python3 -m pytest`)
- Would tightening break legitimate but rare use cases? (check the full subcommand list)

**For patterns you judge as overly broad**, propose:
- **Current**: the broad pattern and which file it's in
- **Actual usage**: the subcommand breakdown from logs
- **Proposed replacements**: one narrower pattern per observed subcommand (e.g., `Bash(python3 -m pytest:*)` instead of `Bash(python3:*)`)
- **What's lost**: what the broad pattern allowed that the replacements don't (user can then decide if they want that)

Patterns with no usage in logs and broad scope deserve special attention — they may be leftovers that should be removed or narrowed.

In project scope, also evaluate context (global) patterns visible in `wildcard_usage` — if a global pattern is overly broad, note it as a suggestion (the user would apply it to their global settings separately).

### 4. Ask user to select changes

Present all suggestions as a numbered list. Each suggestion has:
- **What**: the specific add/remove/replace
- **Where**: which settings file will be modified
- **Why**: the evidence (redundancy, frequency, anomaly)
- **Risk**: Low (removing redundant) / Medium (generalizing) / High (new broad pattern)

Ask the user which suggestions to apply (can select multiple by number, or "all").

### 5. Apply changes

After user approval, read each target settings file, modify its `permissions.allow` array:
1. Remove entries marked for removal (from the file that contains them)
2. Replace generalized groups (remove old entries, add consolidated pattern to the appropriate file)
3. Add new candidate patterns to the appropriate file

Write each updated file back, preserving all other fields (hooks, deny, ask, additionalDirectories, etc.). Machine-specific patterns (containing absolute paths) go to `settings.local.json`; general patterns go to `settings.json`.
