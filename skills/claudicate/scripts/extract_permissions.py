#!/usr/bin/env python3
"""
claudicate: extract_permissions.py
Analyze settings.json permission patterns for redundancies, anomalies,
generalization opportunities, and new candidates from tool usage logs.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load_logs(logs_dir):
    """Load all JSONL entries from a logs directory."""
    entries = []
    logs_path = Path(logs_dir)
    if not logs_path.exists():
        return entries
    for jsonl_file in sorted(logs_path.glob("*.jsonl")):
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return entries


def parse_pattern(raw):
    """Parse a permission entry into structured form.

    Examples:
        "Bash(grep:*)" -> {tool: "Bash", specifier: "grep:*", prefix: "grep", has_wildcard: True}
        "Bash(done)"   -> {tool: "Bash", specifier: "done", prefix: "done", has_wildcard: False}
        "Read"         -> {tool: "Read", specifier: None, prefix: "", has_wildcard: True}
        "Read(//home/user/**)" -> {tool: "Read", specifier: "//home/user/**", prefix: "//home/user/", has_wildcard: True}
    """
    m = re.match(r'^(\w+)(?:\((.+)\))?$', raw)
    if not m:
        return {"raw": raw, "tool": None, "specifier": None, "prefix": "", "has_wildcard": False, "malformed": True}

    tool = m.group(1)
    specifier = m.group(2)  # None if bare tool name

    if specifier is None:
        # Bare tool name like "Read" — matches everything
        return {"raw": raw, "tool": tool, "specifier": None, "prefix": "", "has_wildcard": True}

    # Check for wildcard patterns
    has_wildcard = '*' in specifier

    # Extract prefix (everything before the wildcard pattern)
    if specifier.endswith(':*'):
        # Bash-style: "grep:*" -> prefix "grep"
        prefix = specifier[:-2]
    elif specifier.endswith('*'):
        # Path-style: "//home/**" -> prefix "//home/"
        prefix = specifier.rstrip('*')
    else:
        # Exact match: "done" or "source ../.venv/bin/activate"
        prefix = specifier

    return {"raw": raw, "tool": tool, "specifier": specifier, "prefix": prefix, "has_wildcard": has_wildcard}


def is_subsumed(broad, narrow):
    """Check if broad pattern subsumes narrow pattern (both parsed).

    Rules:
    - Bare tool (specifier=None) subsumes all entries for that tool
    - For Bash: "grep:*" subsumes "grep -h:*" (word boundary: prefix + space)
    - For Read/Edit: path prefix matching with ** glob awareness
    """
    if broad["tool"] != narrow["tool"]:
        return False

    # Bare tool subsumes everything
    if broad["specifier"] is None:
        return True

    # Non-wildcard can't subsume anything except exact duplicates
    if not broad["has_wildcard"]:
        return broad["raw"] == narrow["raw"]

    bp = broad["prefix"]
    np = narrow["prefix"]

    if broad["tool"] == "Bash":
        # "grep" covers "grep -h" (space = word boundary)
        # "grep" covers "grep" (exact)
        # "grep" does NOT cover "grep2" (no word boundary)
        if np == bp:
            return True
        if np.startswith(bp + " "):
            return True
        return False

    # For Read/Edit/other: path-prefix matching
    if np == bp:
        return True
    if np.startswith(bp):
        return True

    return False


def find_redundancies(patterns, context_patterns=None):
    """Find entries subsumed by broader patterns.

    Returns list of {entry, subsumed_by, scope} dicts.
    """
    redundant = []

    # Within-scope redundancies
    for i, narrow in enumerate(patterns):
        if narrow.get("malformed"):
            continue
        for j, broad in enumerate(patterns):
            if i == j or broad.get("malformed"):
                continue
            if is_subsumed(broad, narrow):
                redundant.append({
                    "entry": narrow["raw"],
                    "entry_source": narrow.get("source", ""),
                    "subsumed_by": broad["raw"],
                    "subsumed_by_source": broad.get("source", ""),
                    "scope": "within",
                    "explanation": f'"{narrow["raw"]}" is already covered by "{broad["raw"]}"',
                })
                break

    # Cross-scope redundancies (project entries covered by global)
    if context_patterns:
        for narrow in patterns:
            if narrow.get("malformed"):
                continue
            # Skip if already flagged as within-scope redundant
            if any(r["entry"] == narrow["raw"] and r["scope"] == "within" for r in redundant):
                continue
            for broad in context_patterns:
                if broad.get("malformed"):
                    continue
                if is_subsumed(broad, narrow):
                    redundant.append({
                        "entry": narrow["raw"],
                        "entry_source": narrow.get("source", ""),
                        "subsumed_by": broad["raw"],
                        "subsumed_by_source": broad.get("source", ""),
                        "scope": "cross",
                        "explanation": f'"{narrow["raw"]}" is already covered by global pattern "{broad["raw"]}"',
                    })
                    break

    return redundant


def find_anomalies(patterns):
    """Find malformed or suspicious entries."""
    anomalies = []
    for i, p in enumerate(patterns):
        if p.get("malformed"):
            anomalies.append({"entry": p["raw"], "index": i, "issue": "malformed syntax — does not match ToolName(pattern) format"})
            continue
        if p["tool"] == "Bash" and p["specifier"]:
            spec = p["specifier"]
            if spec.startswith('#'):
                anomalies.append({"entry": p["raw"], "index": i, "issue": "bash comment, not a valid command pattern"})
            elif spec.startswith('//') or spec.startswith('/*'):
                anomalies.append({"entry": p["raw"], "index": i, "issue": "looks like a path, not a bash command"})
            elif ' ' not in spec and not spec.endswith(':*') and len(spec) > 50:
                anomalies.append({"entry": p["raw"], "index": i, "issue": "very long exact match — consider generalizing"})
    return anomalies


def extract_skeleton(command_str):
    """Replace variable parts of a command with placeholders for grouping."""
    s = command_str
    # Replace absolute paths
    s = re.sub(r'/home/\S+', '<PATH>', s)
    s = re.sub(r'/tmp/\S+', '<PATH>', s)
    s = re.sub(r'/var/\S+', '<PATH>', s)
    s = re.sub(r'/usr/\S+', '<PATH>', s)
    s = re.sub(r'/opt/\S+', '<PATH>', s)
    # Replace branch..branch refs
    s = re.sub(r'\b[\w./-]+\.\.[\w./-]+\b', '<REF>', s)
    # Replace file paths after --
    s = re.sub(r'-- .+$', '-- <FILES>', s)
    # Collapse multiple <PATH> into one
    s = re.sub(r'(<PATH>\s*)+', '<PATH> ', s).strip()
    return s


def find_generalizable(patterns, threshold=3):
    """Find groups of exact-match entries that could be consolidated."""
    # Only consider non-wildcard Bash entries
    exact_entries = [p for p in patterns
                     if p["tool"] == "Bash" and not p["has_wildcard"] and not p.get("malformed")]

    groups = defaultdict(list)
    for p in exact_entries:
        skeleton = extract_skeleton(p["prefix"])
        groups[skeleton].append(p)

    generalizable = []
    for skeleton, entries in groups.items():
        if len(entries) < threshold:
            continue

        # Find common command prefix for conservative suggestion
        prefixes = [e["prefix"] for e in entries]
        common = os.path.commonprefix(prefixes).rstrip()
        # Find the last complete word in common prefix
        if ' ' in common:
            common_words = common.rsplit(' ', 1)[0] if not common.endswith(' ') else common.rstrip()
        else:
            common_words = common

        proposals = []
        if common_words:
            proposals.append(f"Bash({common_words}:*)")
        # Also suggest the skeleton-based pattern
        skel_pattern = re.sub(r'<\w+>', '*', skeleton).strip()
        if skel_pattern and f"Bash({skel_pattern}:*)" not in proposals:
            proposals.append(f"Bash({skel_pattern}:*)")

        generalizable.append({
            "skeleton": skeleton,
            "entry_count": len(entries),
            "entries": [e["raw"] for e in entries],
            "proposed": proposals,
        })

    return generalizable


def collect_usage_for_patterns(patterns, log_entries):
    """For each wildcard pattern, collect actual commands from logs that match it.

    Returns a dict mapping pattern raw string to {source, subcommands: Counter}.
    Used by the LLM to evaluate whether broad patterns can be tightened.
    """
    # Collect all Bash tool_use commands from logs
    bash_commands = []
    for e in log_entries:
        if e.get("event_type") == "tool_use" and e.get("tool_name") == "Bash":
            cmd = extract_bash_command(e.get("tool_input", {}))
            if cmd:
                bash_commands.append(cmd)

    usage_map = {}
    for p in patterns:
        if p.get("malformed") or p["tool"] != "Bash" or not p["has_wildcard"]:
            continue

        prefix = p["prefix"]
        matched = [cmd for cmd in bash_commands
                   if cmd == prefix or cmd.startswith(prefix + " ")]
        if not matched:
            usage_map[p["raw"]] = {
                "source": p.get("source", ""),
                "matched_count": 0,
                "subcommands": [],
            }
            continue

        # Extract subcommand patterns from actual usage
        subcommand_counts = Counter()
        for cmd in matched:
            words = cmd.split()
            if len(words) >= 3 and words[1] == "-m":
                # python3 -m <module> pattern
                subcommand_counts[f"{words[0]} -m {words[2]}"] += 1
            elif len(words) >= 2:
                subcommand_counts[f"{words[0]} {words[1]}"] += 1
            else:
                subcommand_counts[words[0]] += 1

        usage_map[p["raw"]] = {
            "source": p.get("source", ""),
            "matched_count": len(matched),
            "subcommands": [
                {"prefix": sub, "count": cnt}
                for sub, cnt in subcommand_counts.most_common()
            ],
        }

    return usage_map


def matches_pattern(parsed_pattern, tool_name, command_str):
    """Check if a tool invocation matches a parsed permission pattern."""
    if parsed_pattern.get("malformed"):
        return False
    if parsed_pattern["tool"] != tool_name:
        return False
    if parsed_pattern["specifier"] is None:
        return True  # bare tool name matches all
    if not parsed_pattern["has_wildcard"]:
        return command_str == parsed_pattern["prefix"]

    bp = parsed_pattern["prefix"]
    if parsed_pattern["tool"] == "Bash":
        return command_str == bp or command_str.startswith(bp + " ") or command_str.startswith(bp)
    # Path patterns
    return command_str.startswith(bp)


def extract_bash_command(tool_input):
    """Extract the bash command string from tool_input."""
    if isinstance(tool_input, dict):
        return tool_input.get("command", tool_input.get("cmd", ""))
    if isinstance(tool_input, str):
        return tool_input
    return ""


def analyze_log_candidates(entries, patterns, denial_threshold=2):
    """Analyze tool_denial and tool_use entries for new permission candidates."""
    # Gather all tool invocations from denials and uses
    invocations = []

    for e in entries:
        if e.get("event_type") == "tool_denial":
            tool = e.get("denied_tool", "")
            cmd = extract_bash_command(e.get("denied_input", {}))
            if tool and cmd:
                invocations.append({"tool": tool, "command": cmd, "source": "denial"})
        elif e.get("event_type") == "tool_use":
            tool = e.get("tool_name", "")
            cmd = extract_bash_command(e.get("tool_input", {}))
            if tool and cmd:
                invocations.append({"tool": tool, "command": cmd, "source": "use"})

    # Check which invocations are NOT covered by existing patterns
    uncovered = []
    for inv in invocations:
        covered = any(matches_pattern(p, inv["tool"], inv["command"]) for p in patterns)
        if not covered:
            uncovered.append(inv)

    # Group uncovered by command prefix (first word)
    prefix_groups = defaultdict(list)
    for inv in uncovered:
        words = inv["command"].split()
        if words:
            prefix_groups[(inv["tool"], words[0])].append(inv)

    # Propose patterns for frequent uncovered commands
    candidates = []
    for (tool, cmd_prefix), group in sorted(prefix_groups.items(), key=lambda x: -len(x[1])):
        if len(group) < denial_threshold:
            continue

        denial_count = sum(1 for g in group if g["source"] == "denial")
        use_count = sum(1 for g in group if g["source"] == "use")
        examples = list(set(g["command"][:200] for g in group[:10]))

        candidates.append({
            "proposed": f"{tool}({cmd_prefix}:*)",
            "evidence_count": len(group),
            "denial_count": denial_count,
            "use_count": use_count,
            "examples": examples[:5],
        })

    return candidates


def find_duplicates(patterns):
    """Find exact duplicate entries."""
    seen = {}
    duplicates = []
    for i, p in enumerate(patterns):
        if p["raw"] in seen:
            duplicates.append({"entry": p["raw"], "index": i, "first_index": seen[p["raw"]], "source": p.get("source", "")})
        else:
            seen[p["raw"]] = i
    return duplicates


def load_settings_allow(path):
    """Load the permissions.allow list from a settings file. Returns [] if missing."""
    p = Path(path)
    if not p.exists():
        return []
    with open(p, 'r', encoding='utf-8') as f:
        settings = json.load(f)
    return settings.get("permissions", {}).get("allow", [])


def main():
    parser = argparse.ArgumentParser(description="Analyze settings.json permissions for optimization")
    parser.add_argument("--settings-file", required=True,
                        help="Primary settings.json (shared/versioned)")
    parser.add_argument("--local-settings-file",
                        help="Companion settings.local.json (personal, not versioned)")
    parser.add_argument("--context-settings",
                        help="Global settings.json for cross-scope redundancy detection (read-only)")
    parser.add_argument("--context-local-settings",
                        help="Global settings.local.json for cross-scope redundancy detection (read-only)")
    parser.add_argument("--logs-dir", action="append", default=[],
                        help="Log directory (repeatable)")
    parser.add_argument("--project-filter",
                        help="Only include log entries matching this project directory")
    parser.add_argument("--generalization-threshold", type=int, default=3,
                        help="Minimum entries to suggest generalization (default: 3)")
    parser.add_argument("--denial-threshold", type=int, default=2,
                        help="Minimum uncovered invocations to suggest new pattern (default: 2)")
    parser.add_argument("--output", default="/tmp/claudicate-permissions-data.json",
                        help="Output JSON file")
    args = parser.parse_args()

    # Load primary settings (shared + local)
    shared_allow = load_settings_allow(args.settings_file)
    local_allow = load_settings_allow(args.local_settings_file) if args.local_settings_file else []

    # Tag each pattern with its source file
    shared_patterns = [parse_pattern(raw) for raw in shared_allow]
    for p in shared_patterns:
        p["source"] = args.settings_file
    local_patterns = [parse_pattern(raw) for raw in local_allow]
    for p in local_patterns:
        p["source"] = args.local_settings_file

    # Combined = all patterns that apply at this scope
    patterns = shared_patterns + local_patterns

    if not patterns:
        print("No permission entries found in allow lists.", file=sys.stderr)
        result = {"error": "no_data", "message": "No entries in permissions.allow"}
        Path(args.output).write_text(json.dumps(result, indent=2))
        sys.exit(0)

    # Load context settings for cross-scope analysis (global shared + local)
    context_patterns = None
    ctx_files = [f for f in [args.context_settings, args.context_local_settings] if f]
    if ctx_files:
        context_patterns = []
        for cf in ctx_files:
            ctx_allow = load_settings_allow(cf)
            ctx_parsed = [parse_pattern(raw) for raw in ctx_allow]
            for p in ctx_parsed:
                p["source"] = cf
            context_patterns.extend(ctx_parsed)

    print(f"Analyzing {len(shared_patterns)} shared + {len(local_patterns)} local permission entries")
    if context_patterns:
        print(f"Cross-referencing with {len(context_patterns)} entries from context settings")

    # Analysis
    duplicates = find_duplicates(patterns)
    redundancies = find_redundancies(patterns, context_patterns)
    anomalies = find_anomalies(patterns)
    generalizable = find_generalizable(patterns, args.generalization_threshold)

    # Load logs for denial/usage analysis
    entries = []
    log_dirs = args.logs_dir or [os.path.expanduser("~/.claudicate/logs/")]
    for ld in log_dirs:
        entries.extend(load_logs(ld))

    if args.project_filter:
        filter_path = os.path.normpath(args.project_filter).replace('\\', '/')

        def matches_project(entry):
            pd = os.path.normpath(entry.get('project_dir', '')).replace('\\', '/')
            if pd == filter_path:
                return True
            cwd = os.path.normpath(entry.get('cwd', '')).replace('\\', '/')
            return cwd == filter_path or cwd.startswith(filter_path + '/')

        entries = [e for e in entries if matches_project(e)]

    # Combine primary + context patterns for coverage check
    all_patterns = patterns[:]
    if context_patterns:
        all_patterns.extend(context_patterns)

    candidates = analyze_log_candidates(entries, all_patterns, args.denial_threshold)

    # Collect actual usage data for wildcard patterns (for LLM tightening analysis)
    usage_data = collect_usage_for_patterns(all_patterns, entries)

    # Compute summary
    removable = len(duplicates) + len(redundancies) + len(anomalies)
    generalizable_entries = sum(g["entry_count"] for g in generalizable)
    projected = len(patterns) - removable - generalizable_entries + len(generalizable) + len(candidates)

    result = {
        "settings_file": args.settings_file,
        "local_settings_file": args.local_settings_file,
        "context_file": args.context_settings,
        "context_local_file": args.context_local_settings,
        "total_entries": len(patterns),
        "shared_entries": len(shared_patterns),
        "local_entries": len(local_patterns),
        "analysis": {
            "duplicates": duplicates,
            "redundant": redundancies,
            "anomalies": anomalies,
            "generalizable": generalizable,
            "new_candidates": candidates,
            "wildcard_usage": usage_data,
        },
        "summary": {
            "duplicates": len(duplicates),
            "redundant_within": sum(1 for r in redundancies if r["scope"] == "within"),
            "redundant_cross": sum(1 for r in redundancies if r["scope"] == "cross"),
            "anomalies": len(anomalies),
            "generalizable_groups": len(generalizable),
            "generalizable_entries": generalizable_entries,
            "new_candidates": len(candidates),
            "projected_total": max(projected, 0),
            "log_entries_analyzed": len(entries),
        },
    }

    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Permission analysis written to {args.output}")

    print(f"\nSummary:")
    print(f"  Total entries: {len(patterns)} ({len(shared_patterns)} shared, {len(local_patterns)} local)")
    print(f"  Duplicates: {len(duplicates)}")
    print(f"  Redundant (within scope): {result['summary']['redundant_within']}")
    print(f"  Redundant (cross scope): {result['summary']['redundant_cross']}")
    print(f"  Anomalies: {len(anomalies)}")
    print(f"  Generalizable groups: {len(generalizable)} ({generalizable_entries} entries)")
    print(f"  New candidates from logs: {len(candidates)} (from {len(entries)} log entries)")
    print(f"  Projected entry count: {result['summary']['projected_total']}")


if __name__ == "__main__":
    main()
