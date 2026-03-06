# Improve Permissions

Analyze and optimize Claude Code permission patterns in settings.json. Detects redundancies, anomalies, generalization opportunities, and suggests new patterns from tool usage logs.

## Steps

### 1. Resolve settings files by scope

Based on scope variables from the scope preamble:

- **Project scope**: primary = `$SCOPE_TARGET_DIR/.claude/settings.json`, context = `~/.claude/settings.json`
- **Global scope**: primary = `~/.claude/settings.json`, no context file

Also check if `settings.local.json` exists alongside the primary file. If so, note its contents but target the shared settings file.

### 2. Run analysis

Run the `extract_permissions.py` script from the `scripts/` directory:

```
python3 scripts/extract_permissions.py \
  --settings-file <primary> \
  [--context-settings <context>] \
  --logs-dir ~/.promptforge/logs/ \
  [--logs-dir <project>/.promptforge/logs/] \
  [$SCOPE_PROJECT_FILTER] \
  --output /tmp/promptforge-permissions-data.json
```

### 3. Read and present findings

Read the output JSON. Present findings organized by category:

#### a. Duplicates
Exact duplicate entries. Safe to remove — just list them.

#### b. Redundant entries
Entries subsumed by broader patterns. For each:
- **Remove**: the redundant entry
- **Kept by**: the broader pattern that already covers it
- **Scope**: "within" (same file) or "cross" (covered by global settings)

#### c. Anomalies
Malformed or suspicious entries (bash comments, broken syntax). For each:
- **Entry**: the problematic pattern
- **Issue**: what's wrong
- **Suggestion**: remove or fix

#### d. Generalizable groups
Multiple exact-match entries that share a common pattern. For each group:
- **Entries**: the specific patterns being consolidated
- **Conservative proposal**: preserves subcommand specificity (e.g., `Bash(git -C * diff:*)`)
- **Broad proposal**: wider scope (e.g., `Bash(git:*)`)
- **Risk note**: explain what additional commands the broader pattern would allow

#### e. New candidates
Frequently used/denied tools not covered by current patterns. For each:
- **Proposed pattern**: the new allow entry
- **Evidence**: how many times it appeared in logs, with examples
- **Source**: from denials, successful uses, or both

### 4. Ask user to select changes

Present all suggestions as a numbered list. Each suggestion has:
- **What**: the specific add/remove/replace
- **Why**: the evidence (redundancy, frequency, anomaly)
- **Risk**: Low (removing redundant) / Medium (generalizing) / High (new broad pattern)

Ask the user which suggestions to apply (can select multiple by number, or "all").

### 5. Apply changes

After user approval, read the target settings.json, modify the `permissions.allow` array:
1. Remove entries marked for removal
2. Replace generalized groups (remove old entries, add consolidated pattern)
3. Add new candidate patterns

Write the updated settings.json back, preserving all other fields (hooks, deny, ask, additionalDirectories, etc.).
