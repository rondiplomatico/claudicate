#!/usr/bin/env python3
"""
claudicate: extract_friction.py
Pre-filter and aggregate friction signals from claudicate logs.
Reduces the data volume that Claude needs to process for friction analysis.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

NEGATION_PATTERNS = [
    r'\bno\b',
    r'\bnot that\b',
    r'\bstop\b',
    r'\bundo\b',
    r'\bwrong\b',
    r'\binstead\b',
    r'\bactually\b',
    r'\brather\b',
    r"\bdon't\b",
    r'\bshould not\b',
    r'\brevert\b',
    r'\bforget that\b',
    r'\bnot what\b',
]


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


def analyze_denials(entries):
    """Analyze tool denial patterns."""
    denials = [e for e in entries if e.get("event_type") == "tool_denial"]
    by_tool = Counter(e.get("denied_tool", "unknown") for e in denials)
    interrupts = sum(1 for e in denials if e.get("is_interrupt"))
    explicit = len(denials) - interrupts

    return {
        "total": len(denials),
        "by_tool": dict(by_tool.most_common(20)),
        "interrupts": interrupts,
        "explicit_denials": explicit,
        "examples": [
            {
                "timestamp": e.get("timestamp"),
                "tool": e.get("denied_tool"),
                "reason": e.get("denial_reason", "")[:200],
                "is_interrupt": e.get("is_interrupt", False),
            }
            for e in denials[:20]
        ],
    }


def analyze_negations(entries):
    """Find prompts with negation/correction language."""
    prompts = [e for e in entries if e.get("event_type") == "prompt"]
    negation_hits = []

    for entry in prompts:
        prompt = entry.get("prompt", "")
        matched = []
        for pattern in NEGATION_PATTERNS:
            if re.search(pattern, prompt, re.I):
                matched.append(pattern.strip(r'\b'))
        if matched:
            negation_hits.append({
                "timestamp": entry.get("timestamp"),
                "session_id": entry.get("session_id"),
                "prompt": prompt[:300],
                "matched_patterns": matched,
            })

    pattern_counts = Counter()
    for hit in negation_hits:
        for p in hit["matched_patterns"]:
            pattern_counts[p] += 1

    return {
        "total_negation_prompts": len(negation_hits),
        "pattern_frequency": dict(pattern_counts.most_common()),
        "examples": negation_hits[:15],
    }


def analyze_contradictions(entries):
    """Find sequential contradictions within sessions."""
    by_session = defaultdict(list)
    for e in entries:
        if e.get("event_type") == "prompt":
            by_session[e.get("session_id", "")].append(e)

    contradictions = []
    for session_id, prompts in by_session.items():
        prompts.sort(key=lambda x: x.get("timestamp", ""))
        for i in range(1, len(prompts)):
            prev_prompt = prompts[i - 1].get("prompt", "")
            curr_prompt = prompts[i].get("prompt", "")
            # Check if current prompt contradicts/refines previous
            for pattern in [r'^actually', r'^no[,.]?\s', r'^instead', r'^forget that', r'^not what i']:
                if re.match(pattern, curr_prompt, re.I):
                    contradictions.append({
                        "timestamp": prompts[i].get("timestamp"),
                        "session_id": session_id,
                        "previous_prompt": prev_prompt[:200],
                        "correction_prompt": curr_prompt[:200],
                        "pattern": pattern,
                    })
                    break

    return {
        "total": len(contradictions),
        "examples": contradictions[:15],
    }


def analyze_repeated_clarifications(entries):
    """Find similar AskUserQuestion topics across sessions."""
    asks = [e for e in entries if e.get("event_type") == "ask_response"]

    # Simple similarity: normalize question and group
    question_groups = defaultdict(list)
    for ask in asks:
        q = ask.get("question", "").lower().strip()
        # Normalize: remove punctuation, extra whitespace
        q_norm = re.sub(r'[^\w\s]', '', q)
        q_norm = re.sub(r'\s+', ' ', q_norm).strip()
        # Use first 50 chars as group key (rough similarity)
        key = q_norm[:50]
        question_groups[key].append({
            "timestamp": ask.get("timestamp"),
            "session_id": ask.get("session_id"),
            "question": ask.get("question", "")[:200],
            "answer": ask.get("answer", "")[:200],
        })

    # Only keep groups with 2+ occurrences across different sessions
    repeated = {}
    for key, instances in question_groups.items():
        unique_sessions = set(i["session_id"] for i in instances)
        if len(unique_sessions) >= 2:
            repeated[key] = {
                "count": len(instances),
                "unique_sessions": len(unique_sessions),
                "examples": instances[:5],
            }

    return {
        "total_repeated_topics": len(repeated),
        "topics": dict(sorted(repeated.items(), key=lambda x: -x[1]["count"])[:10]),
    }


def analyze_correction_chains(entries):
    """Find denial → follow-up prompt patterns."""
    by_session = defaultdict(list)
    for e in entries:
        by_session[e.get("session_id", "")].append(e)

    chains = []
    for session_id, events in by_session.items():
        events.sort(key=lambda x: x.get("timestamp", ""))
        for i, event in enumerate(events):
            if event.get("event_type") == "tool_denial":
                # Find next prompt in same session
                for j in range(i + 1, min(i + 3, len(events))):
                    if events[j].get("event_type") == "prompt":
                        chains.append({
                            "timestamp": event.get("timestamp"),
                            "session_id": session_id,
                            "denied_tool": event.get("denied_tool"),
                            "follow_up_prompt": events[j].get("prompt", "")[:200],
                        })
                        break

    # Group by denied tool
    by_tool = defaultdict(list)
    for chain in chains:
        by_tool[chain.get("denied_tool", "unknown")].append(chain)

    return {
        "total_chains": len(chains),
        "by_tool": {
            tool: {"count": len(examples), "examples": examples[:5]}
            for tool, examples in sorted(by_tool.items(), key=lambda x: -len(x[1]))[:10]
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Pre-filter friction signals from claudicate logs")
    parser.add_argument("--logs-dir", default=os.path.expanduser("~/.claudicate/logs/"),
                        help="Logs directory")
    parser.add_argument("--project-logs-dir", help="Additional project-specific logs directory")
    parser.add_argument("--project-filter", help="Only include entries matching this project directory")
    parser.add_argument("--output", default="/tmp/claudicate-friction-data.json",
                        help="Output JSON file")
    parser.add_argument("--exclude-agents", action="store_true",
                        help="Exclude agent sessions from analysis (included by default)")
    args = parser.parse_args()

    # Load logs from all sources
    entries = load_logs(args.logs_dir)
    if args.project_logs_dir:
        entries.extend(load_logs(args.project_logs_dir))

    if args.project_filter:
        filter_path = os.path.normpath(args.project_filter).replace('\\', '/')
        entries = [e for e in entries
                   if os.path.normpath(
                       e.get('project_dir', '') or e.get('cwd', '')
                   ).replace('\\', '/') == filter_path]

    # Filter agent sessions if --exclude-agents
    if args.exclude_agents:
        total_before = len(entries)
        entries = [e for e in entries
                   if not (e.get('session_id', '').startswith('agent-')
                           or 'agent' in e.get('tags', []))]
        agent_excluded = total_before - len(entries)
        if agent_excluded:
            print(f"Excluded {agent_excluded} agent entries")

    if not entries:
        print("No log entries found.", file=sys.stderr)
        result = {"error": "no_data", "message": f"No log entries found in {args.logs_dir}"}
        Path(args.output).write_text(json.dumps(result, indent=2))
        sys.exit(0)

    print(f"Loaded {len(entries)} log entries")

    result = {
        "total_entries": len(entries),
        "date_range": {
            "first": min((e.get("timestamp", "") for e in entries), default=""),
            "last": max((e.get("timestamp", "") for e in entries), default=""),
        },
        "denials": analyze_denials(entries),
        "negations": analyze_negations(entries),
        "contradictions": analyze_contradictions(entries),
        "repeated_clarifications": analyze_repeated_clarifications(entries),
        "correction_chains": analyze_correction_chains(entries),
    }

    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Friction data written to {args.output}")

    # Print summary
    print(f"\nSummary:")
    print(f"  Tool denials: {result['denials']['total']}")
    print(f"  Negation prompts: {result['negations']['total_negation_prompts']}")
    print(f"  Sequential contradictions: {result['contradictions']['total']}")
    print(f"  Repeated clarification topics: {result['repeated_clarifications']['total_repeated_topics']}")
    print(f"  Correction chains: {result['correction_chains']['total_chains']}")


if __name__ == "__main__":
    main()
