#!/usr/bin/env python3
"""
Claudicate: analyze-agents.py
Analysis of Claude Code agent session patterns from Claudicate interaction logs.
"""

import argparse
import json
import glob
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def is_agent_session(session_id):
    """Check if session_id matches agent-XXXXXXX pattern."""
    return session_id.startswith('agent-')


def load_logs(dirs, since_date=None):
    """Load all JSONL entries from multiple log directories."""
    records = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except Exception:
                            pass

    for r in records:
        try:
            r['_dt'] = datetime.fromisoformat(r['timestamp'].replace('Z', '+00:00'))
        except Exception:
            r['_dt'] = None

    records = [r for r in records if r['_dt']]

    if since_date:
        records = [r for r in records if r['_dt'].date() >= since_date]

    return records


def discover_log_dirs():
    """Auto-discover claudicate log directories."""
    dirs = []
    global_dir = os.path.expanduser("~/.claudicate/logs")
    if os.path.isdir(global_dir):
        dirs.append(global_dir)
    proj_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj_dir:
        project_logs = os.path.join(proj_dir, ".claudicate", "logs")
        if os.path.isdir(project_logs):
            dirs.append(project_logs)
    return dirs


def section(title, fmt="text"):
    if fmt == "markdown":
        return f"\n## {title}\n"
    return f"\n{'=' * 60}\n{title}\n{'=' * 60}"


def correlate_parent_sessions(agent_sessions, user_sessions):
    """For each agent session, find the user session with the closest preceding prompt.

    Returns dict: agent_session_id -> {user_session_id, user_prompt, time_delta_seconds}
    """
    # Build timeline of user prompts (last prompt per session before each agent start)
    user_prompts = []
    for sid, events in user_sessions.items():
        prompts = [e for e in events if e.get('event_type') == 'prompt']
        for p in prompts:
            user_prompts.append((p['_dt'], sid, p.get('prompt', '')))
    user_prompts.sort(key=lambda x: x[0])

    correlations = {}
    for agent_sid, events in agent_sessions.items():
        agent_start = min(e['_dt'] for e in events)
        # Find the user prompt closest before (and within same project if possible)
        best = None
        agent_project = events[0].get('project_dir', '') or events[0].get('cwd', '')
        for dt, user_sid, prompt in reversed(user_prompts):
            if dt < agent_start:
                best = (user_sid, prompt, (agent_start - dt).total_seconds())
                break
        if best:
            correlations[agent_sid] = {
                'user_session_id': best[0],
                'user_prompt': best[1][:200],
                'time_delta_seconds': best[2],
            }

    return correlations


def main():
    parser = argparse.ArgumentParser(description="Analyze Claude Code agent session patterns")
    parser.add_argument("--logs-dir", action="append", help="Log directory (can be repeated)")
    parser.add_argument("--since", help="Only analyze after this date (YYYY-MM-DD)")
    parser.add_argument("--project-filter", help="Only include entries matching this project directory")
    parser.add_argument("--format", choices=["text", "markdown"], default="text", help="Output format")
    parser.add_argument("--output", help="Write report to file instead of stdout")
    args = parser.parse_args()

    since_date = None
    if args.since:
        try:
            since_date = datetime.strptime(args.since, "%Y-%m-%d").date()
        except ValueError:
            print(f"Error: Invalid date '{args.since}'. Use YYYY-MM-DD.", file=sys.stderr)
            sys.exit(1)

    log_dirs = args.logs_dir if args.logs_dir else discover_log_dirs()
    if not log_dirs:
        print("No log directories found.")
        sys.exit(1)

    records = load_logs(log_dirs, since_date)

    if args.project_filter:
        filter_path = os.path.normpath(args.project_filter).replace('\\', '/')

        def matches_project(entry):
            pd = os.path.normpath(entry.get('project_dir', '')).replace('\\', '/')
            if pd == filter_path:
                return True
            cwd = os.path.normpath(entry.get('cwd', '')).replace('\\', '/')
            return cwd == filter_path or cwd.startswith(filter_path + '/')

        records = [r for r in records if matches_project(r)]

    if not records:
        print("No log entries found.")
        sys.exit(1)

    fmt = args.format
    out = []

    def p(text=""):
        out.append(text)

    # Split into agent vs user
    agent_records = [r for r in records if is_agent_session(r.get('session_id', ''))]
    user_records = [r for r in records if not is_agent_session(r.get('session_id', ''))]

    agent_sessions = defaultdict(list)
    for r in agent_records:
        agent_sessions[r.get('session_id', '')].append(r)

    user_sessions = defaultdict(list)
    for r in user_records:
        user_sessions[r.get('session_id', '')].append(r)

    # ============ OVERVIEW ============
    p(section("AGENT vs USER OVERVIEW", fmt))

    agent_prompts = [r for r in agent_records if r.get('event_type') == 'prompt']
    user_prompts = [r for r in user_records if r.get('event_type') == 'prompt']
    agent_denials = [r for r in agent_records if r.get('event_type') == 'tool_denial']

    dates = sorted(set(r['_dt'].date() for r in records))

    if fmt == "markdown":
        p("| Metric | Agent | User | Total |")
        p("|--------|-------|------|-------|")
        p(f"| Sessions | {len(agent_sessions)} | {len(user_sessions)} | {len(agent_sessions) + len(user_sessions)} |")
        p(f"| Prompts | {len(agent_prompts)} | {len(user_prompts)} | {len(agent_prompts) + len(user_prompts)} |")
        p(f"| Tool denials | {len(agent_denials)} | {len([r for r in user_records if r.get('event_type') == 'tool_denial'])} | {len([r for r in records if r.get('event_type') == 'tool_denial'])} |")
        pct = len(agent_sessions) / (len(agent_sessions) + len(user_sessions)) * 100 if agent_sessions or user_sessions else 0
        p(f"| Agent session % | {pct:.1f}% | | |")
        p(f"| Date range | {dates[0]} to {dates[-1]} ({(dates[-1]-dates[0]).days + 1} days) | | |")
    else:
        p(f"Total records: {len(records)}")
        p(f"Agent sessions: {len(agent_sessions)}  |  User sessions: {len(user_sessions)}")
        pct = len(agent_sessions) / (len(agent_sessions) + len(user_sessions)) * 100 if agent_sessions or user_sessions else 0
        p(f"Agent session ratio: {pct:.1f}%")
        p(f"Agent prompts: {len(agent_prompts)}  |  User prompts: {len(user_prompts)}")
        p(f"Agent tool denials: {len(agent_denials)}")
        p(f"Date range: {dates[0]} to {dates[-1]}")

    # Daily trend
    agent_daily = Counter(r['_dt'].date() for r in agent_records)
    user_daily = Counter(r['_dt'].date() for r in user_records)
    if fmt == "markdown":
        p("\n### Daily agent vs user events\n")
        p("| Date | Agent | User |")
        p("|------|-------|------|")
        for d in sorted(set(list(agent_daily.keys()) + list(user_daily.keys()))):
            p(f"| {d} | {agent_daily.get(d, 0)} | {user_daily.get(d, 0)} |")
    else:
        p("\nDaily agent vs user events:")
        for d in sorted(set(list(agent_daily.keys()) + list(user_daily.keys()))):
            p(f"  {d}  agent={agent_daily.get(d, 0):4d}  user={user_daily.get(d, 0):4d}")

    # ============ AGENT PROMPT CHARACTERISTICS ============
    p(section("AGENT PROMPT CHARACTERISTICS", fmt))

    prompt_texts = [r.get('prompt', '') for r in agent_prompts if r.get('prompt')]
    if prompt_texts:
        lengths = [len(pt) for pt in prompt_texts]
        warmup_count = sum(1 for pt in prompt_texts if pt.strip().lower() == 'warmup')

        if fmt == "markdown":
            p("| Metric | Value |")
            p("|--------|-------|")
            p(f"| Total agent prompts | {len(prompt_texts)} |")
            p(f"| Warmup prompts | {warmup_count} ({warmup_count/len(prompt_texts)*100:.1f}%) |")
            p(f"| Non-warmup prompts | {len(prompt_texts) - warmup_count} |")
            p(f"| Avg prompt length | {sum(lengths)/len(lengths):.0f} chars |")
            p(f"| Median prompt length | {sorted(lengths)[len(lengths)//2]} chars |")
            p(f"| Max prompt length | {max(lengths)} chars |")
        else:
            p(f"Total agent prompts: {len(prompt_texts)}")
            p(f"Warmup prompts: {warmup_count} ({warmup_count/len(prompt_texts)*100:.1f}%)")
            p(f"Non-warmup prompts: {len(prompt_texts) - warmup_count}")
            p(f"Avg prompt length: {sum(lengths)/len(lengths):.0f} chars")
            p(f"Median: {sorted(lengths)[len(lengths)//2]} chars, Max: {max(lengths)} chars")

        # Top prefixes (excluding warmup)
        non_warmup = [pt for pt in prompt_texts if pt.strip().lower() != 'warmup']
        if non_warmup:
            prefixes = Counter(pt[:60] for pt in non_warmup)
            if fmt == "markdown":
                p(f"\n### Top agent prompt prefixes (first 60 chars)\n")
                p("| Count | Prefix |")
                p("|-------|--------|")
                for prefix, count in prefixes.most_common(15):
                    p(f"| {count} | `{prefix}` |")
            else:
                p("\nTop agent prompt prefixes (first 60 chars):")
                for prefix, count in prefixes.most_common(15):
                    p(f"  {count:4d}x  {prefix!r}")
    else:
        p("No agent prompts found.")

    # ============ AGENT FRICTION ============
    p(section("AGENT FRICTION", fmt))

    if agent_denials:
        denied_tools = Counter(r.get('denied_tool', 'unknown') for r in agent_denials)
        if fmt == "markdown":
            p(f"Total agent tool denials: {len(agent_denials)}\n")
            p("| Tool | Count |")
            p("|------|-------|")
            for tool, count in denied_tools.most_common(10):
                p(f"| {tool} | {count} |")
        else:
            p(f"Total agent tool denials: {len(agent_denials)}")
            for tool, count in denied_tools.most_common(10):
                p(f"  {tool:30s}: {count:3d}")
    else:
        p("No tool denials in agent sessions.")

    # Negation patterns in agent sessions
    negation_patterns = [
        r'\bno\b', r'\bnot that\b', r'\bstop\b', r'\bundo\b', r'\bwrong\b',
        r'\binstead\b', r'\bactually\b', r'\brather\b', r"\bdon't\b",
        r'\bshould not\b', r'\brevert\b', r'\bforget that\b', r'\bnot what\b',
    ]
    negation_count = 0
    for r in agent_prompts:
        prompt = r.get('prompt', '')
        if any(re.search(pat, prompt, re.I) for pat in negation_patterns):
            negation_count += 1
    p(f"\nAgent prompts with negation language: {negation_count}")

    # ============ PARENT-CHILD CORRELATION ============
    p(section("PARENT-CHILD CORRELATION", fmt))

    correlations = correlate_parent_sessions(agent_sessions, user_sessions)

    if correlations:
        # Which user sessions spawn the most agents
        user_agent_count = Counter(c['user_session_id'] for c in correlations.values())

        if fmt == "markdown":
            p(f"Agent sessions correlated to a parent: {len(correlations)} / {len(agent_sessions)}\n")
            p("### User sessions spawning the most agents\n")
            p("| User Session | Agents Spawned | First User Prompt |")
            p("|-------------|----------------|-------------------|")
            for user_sid, count in user_agent_count.most_common(15):
                # Find first prompt in that user session
                first_prompt = ""
                user_events = user_sessions.get(user_sid, [])
                for e in sorted(user_events, key=lambda x: x.get('timestamp', '')):
                    if e.get('event_type') == 'prompt':
                        first_prompt = e.get('prompt', '')[:80]
                        break
                p(f"| `{user_sid[:12]}...` | {count} | `{first_prompt}` |")
        else:
            p(f"Agent sessions correlated to a parent: {len(correlations)} / {len(agent_sessions)}")
            p("\nUser sessions spawning the most agents:")
            for user_sid, count in user_agent_count.most_common(15):
                first_prompt = ""
                user_events = user_sessions.get(user_sid, [])
                for e in sorted(user_events, key=lambda x: x.get('timestamp', '')):
                    if e.get('event_type') == 'prompt':
                        first_prompt = e.get('prompt', '')[:80]
                        break
                p(f"  {count:3d} agents  {user_sid[:12]}...  {first_prompt!r}")

        # Agent sessions with friction and their parent context
        friction_agents = [sid for sid in agent_sessions
                          if any(e.get('event_type') == 'tool_denial' for e in agent_sessions[sid])]
        if friction_agents:
            if fmt == "markdown":
                p("\n### Agent sessions with friction (denials) and parent context\n")
                p("| Agent Session | Denied Tool | Parent Prompt |")
                p("|-------------|-------------|---------------|")
                for agent_sid in friction_agents[:20]:
                    denied = [e for e in agent_sessions[agent_sid] if e.get('event_type') == 'tool_denial']
                    tools = ', '.join(set(e.get('denied_tool', '?') for e in denied))
                    parent_prompt = correlations.get(agent_sid, {}).get('user_prompt', 'unknown')[:80]
                    p(f"| `{agent_sid}` | {tools} | `{parent_prompt}` |")
            else:
                p("\nAgent sessions with friction (denials) and parent context:")
                for agent_sid in friction_agents[:20]:
                    denied = [e for e in agent_sessions[agent_sid] if e.get('event_type') == 'tool_denial']
                    tools = ', '.join(set(e.get('denied_tool', '?') for e in denied))
                    parent_prompt = correlations.get(agent_sid, {}).get('user_prompt', 'unknown')[:80]
                    p(f"  {agent_sid}  denied=[{tools}]  parent={parent_prompt!r}")
    else:
        p("No parent-child correlations found.")

    # ============ AGENT SESSION COMPLEXITY ============
    p(section("AGENT SESSION COMPLEXITY", fmt))

    prompts_per_session = []
    for sid, events in agent_sessions.items():
        n_prompts = sum(1 for e in events if e.get('event_type') == 'prompt')
        prompts_per_session.append(n_prompts)

    if prompts_per_session:
        prompts_per_session.sort()
        if fmt == "markdown":
            p("| Metric | Value |")
            p("|--------|-------|")
            p(f"| Agent sessions | {len(prompts_per_session)} |")
            p(f"| Avg prompts/session | {sum(prompts_per_session)/len(prompts_per_session):.1f} |")
            p(f"| Median prompts/session | {prompts_per_session[len(prompts_per_session)//2]} |")
            p(f"| Max prompts/session | {max(prompts_per_session)} |")
            p(f"| Single-prompt sessions | {sum(1 for n in prompts_per_session if n == 1)} ({sum(1 for n in prompts_per_session if n == 1)/len(prompts_per_session)*100:.0f}%) |")
        else:
            p(f"Agent sessions: {len(prompts_per_session)}")
            p(f"Avg prompts/session: {sum(prompts_per_session)/len(prompts_per_session):.1f}")
            p(f"Median: {prompts_per_session[len(prompts_per_session)//2]}, Max: {max(prompts_per_session)}")
            single = sum(1 for n in prompts_per_session if n == 1)
            p(f"Single-prompt sessions: {single} ({single/len(prompts_per_session)*100:.0f}%)")

        # Distribution
        dist = Counter(prompts_per_session)
        if fmt == "markdown":
            p("\n### Prompts-per-session distribution\n")
            p("| Prompts | Sessions |")
            p("|---------|----------|")
            for n in sorted(dist.keys()):
                p(f"| {n} | {dist[n]} |")
        else:
            p("\nPrompts-per-session distribution:")
            for n in sorted(dist.keys()):
                p(f"  {n:3d} prompts: {dist[n]:5d} sessions")

    # Output
    report = "\n".join(out)
    if args.output:
        Path(args.output).write_text(report + "\n")
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
