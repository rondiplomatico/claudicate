#!/usr/bin/env python3
"""
Claudicate: analyze-usage.py
Comprehensive usage analysis of Claudicate interaction logs.
Based on analyze.py from bordnetzgpt, extended with CLI, log discovery, and markdown output.
"""

import argparse
import json
import glob
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, date
from pathlib import Path


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

    # Parse timestamps
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


def main():
    parser = argparse.ArgumentParser(description="Analyze Claudicate interaction logs")
    parser.add_argument("--logs-dir", action="append", help="Log directory (can be repeated)")
    parser.add_argument("--since", help="Only analyze after this date (YYYY-MM-DD)")
    parser.add_argument("--project-filter", help="Only include entries matching this project directory")
    parser.add_argument("--format", choices=["text", "markdown"], default="text", help="Output format")
    parser.add_argument("--output", help="Write report to file instead of stdout")
    parser.add_argument("--include-agents", action="store_true",
                        help="Include agent sessions (excluded by default)")
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
        print("No log directories found. Checked:")
        print(f"  ~/.claudicate/logs/")
        print(f"  $CLAUDE_PROJECT_DIR/.claudicate/logs/")
        print("\nRun the Claudicate installer or use extract-sessions.py for backfill.")
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

    # Filter agent sessions unless --include-agents
    if not args.include_agents:
        total_before = len(records)
        records = [r for r in records
                   if not (r.get('session_id', '').startswith('agent-')
                           or 'agent' in r.get('tags', []))]
        agent_excluded = total_before - len(records)
    else:
        agent_excluded = 0

    if not records:
        print("No log entries found in:", ", ".join(log_dirs))
        if since_date:
            print(f"(filtered: since {since_date})")
        sys.exit(1)

    fmt = args.format
    out = []

    def p(text=""):
        out.append(text)

    prompts = [r for r in records if r.get('event_type') == 'prompt']
    asks = [r for r in records if r.get('event_type') == 'ask_response']
    denials = [r for r in records if r.get('event_type') == 'tool_denial']
    turn_ends = [r for r in records if r.get('event_type') == 'turn_end']

    if agent_excluded > 0:
        p(f"*Agent sessions excluded: {agent_excluded} entries (use --include-agents to include)*\n")

    # ============ VOLUME ============
    p(section("VOLUME", fmt))
    dates = sorted(set(r['_dt'].date() for r in records))
    sessions = defaultdict(list)
    for r in records:
        sessions[r.get('session_id', 'unknown')].append(r)

    sessions_per_day = defaultdict(set)
    for r in records:
        sessions_per_day[r['_dt'].date()].add(r.get('session_id'))
    spd = [len(v) for v in sessions_per_day.values()]

    pps = defaultdict(int)
    for r in prompts:
        pps[r.get('session_id', 'unknown')] += 1
    pps_vals = list(pps.values()) if pps else [0]

    if fmt == "markdown":
        p(f"| Metric | Value |")
        p(f"|--------|-------|")
        p(f"| Total interactions | {len(records)} |")
        p(f"| Prompts | {len(prompts)} |")
        p(f"| Ask responses | {len(asks)} |")
        p(f"| Tool denials | {len(denials)} |")
        p(f"| Turn ends | {len(turn_ends)} |")
        p(f"| Date range | {dates[0]} to {dates[-1]} ({(dates[-1]-dates[0]).days + 1} days) |")
        p(f"| Active days | {len(dates)} |")
        p(f"| Total sessions | {len(sessions)} |")
        p(f"| Sessions/active day | avg {sum(spd)/len(spd):.1f}, min {min(spd)}, max {max(spd)} |")
        p(f"| Prompts/session | avg {sum(pps_vals)/len(pps_vals):.1f}, min {min(pps_vals)}, max {max(pps_vals)}, median {sorted(pps_vals)[len(pps_vals)//2]} |")
    else:
        p(f"Total interactions: {len(records)}")
        p(f"  Prompts: {len(prompts)}")
        p(f"  Ask responses: {len(asks)}")
        p(f"  Tool denials: {len(denials)}")
        p(f"  Turn ends: {len(turn_ends)}")
        p(f"Date range: {dates[0]} to {dates[-1]} ({(dates[-1]-dates[0]).days + 1} calendar days)")
        p(f"Active days: {len(dates)}")
        p(f"Total sessions: {len(sessions)}")
        p(f"Sessions per active day: avg={sum(spd)/len(spd):.1f}, min={min(spd)}, max={max(spd)}")
        p(f"Prompts per session: avg={sum(pps_vals)/len(pps_vals):.1f}, min={min(pps_vals)}, max={max(pps_vals)}, median={sorted(pps_vals)[len(pps_vals)//2]}")

    # ============ ACTIVITY DISTRIBUTION ============
    p(section("ACTIVITY DISTRIBUTION", fmt))
    tag_categories = ['planning', 'testing', 'git_ops', 'bmad', 'slash_command', 'clarification', 'correction']
    all_tags = Counter()
    for r in prompts:
        for t in r.get('tags', []):
            all_tags[t] += 1

    if fmt == "markdown":
        p(f"| Category | Count | % of prompts |")
        p(f"|----------|-------|-------------|")
        for cat in tag_categories:
            count = sum(v for k, v in all_tags.items() if cat in k.lower())
            pct = count / len(prompts) * 100 if prompts else 0
            p(f"| {cat} | {count} | {pct:.1f}% |")
        p(f"\n### All tags (top 30)\n")
        p(f"| Tag | Count | % |")
        p(f"|-----|-------|---|")
        for tag, count in all_tags.most_common(30):
            pct = count / len(prompts) * 100
            p(f"| {tag} | {count} | {pct:.1f}% |")
    else:
        for cat in tag_categories:
            count = sum(v for k, v in all_tags.items() if cat in k.lower())
            pct = count / len(prompts) * 100 if prompts else 0
            p(f"  {cat:20s}: {count:5d} ({pct:5.1f}%)")
        p(f"\nAll tags (top 30):")
        for tag, count in all_tags.most_common(30):
            pct = count / len(prompts) * 100
            p(f"  {tag:40s}: {count:5d} ({pct:5.1f}%)")

    # ============ BMAD AGENT USAGE ============
    p(section("BMAD AGENT & TASK USAGE", fmt))
    bmad_tags = {k: v for k, v in all_tags.items() if 'bmad' in k.lower()}
    if bmad_tags:
        if fmt == "markdown":
            p(f"| Tag | Count |")
            p(f"|-----|-------|")
            for tag, count in sorted(bmad_tags.items(), key=lambda x: -x[1]):
                p(f"| {tag} | {count} |")
        else:
            for tag, count in sorted(bmad_tags.items(), key=lambda x: -x[1]):
                p(f"  {tag:40s}: {count:5d}")

        bmad_sessions = set()
        for r in prompts:
            if any('bmad' in t.lower() for t in r.get('tags', [])):
                bmad_sessions.add(r.get('session_id'))
        if bmad_sessions:
            bmad_lens = [pps.get(sid, 0) for sid in bmad_sessions]
            p(f"\nAvg session length (BMAD): {sum(bmad_lens)/len(bmad_lens):.1f} prompts")
    else:
        p("No BMAD tags found")

    # ============ INTERACTION PATTERNS ============
    p(section("INTERACTION PATTERNS", fmt))
    p(f"Ask response rate: {len(asks)/len(records)*100:.1f}% of all events")
    p(f"Tool denial rate: {len(denials)/len(records)*100:.1f}% of all events")

    # Avg prompts between denials
    if denials:
        gaps = []
        for sid, events in sessions.items():
            sorted_events = sorted(events, key=lambda x: x.get('timestamp', ''))
            prompt_count = 0
            for e in sorted_events:
                if e.get('event_type') == 'prompt':
                    prompt_count += 1
                elif e.get('event_type') == 'tool_denial':
                    gaps.append(prompt_count)
                    prompt_count = 0
        if gaps:
            p(f"Avg prompts between denials: {sum(gaps)/len(gaps):.1f}")

    denied_tools = Counter(r.get('denied_tool', 'unknown') for r in denials)
    if denied_tools:
        if fmt == "markdown":
            p(f"\n### Most denied tools\n")
            p(f"| Tool | Count |")
            p(f"|------|-------|")
            for tool, count in denied_tools.most_common(10):
                p(f"| {tool} | {count} |")
        else:
            p(f"Most denied tools:")
            for tool, count in denied_tools.most_common(10):
                p(f"  {tool:40s}: {count:3d}")

    # ============ TIME PATTERNS ============
    p(section("TIME PATTERNS", fmt))
    hours = Counter(r['_dt'].hour for r in records)
    if fmt == "markdown":
        p("### Hour (UTC) distribution\n")
        p("| Hour | Count | |")
        p("|------|-------|-|")
        for h in range(24):
            count = hours.get(h, 0)
            bar = '#' * (count // 5)
            if count > 0:
                p(f"| {h:02d}:00 | {count} | `{bar}` |")
    else:
        p("Hour (UTC) distribution:")
        for h in range(24):
            count = hours.get(h, 0)
            bar = '#' * (count // 5)
            if count > 0:
                p(f"  {h:02d}:00  {count:4d}  {bar}")

    dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    dows = Counter(r['_dt'].weekday() for r in records)
    if fmt == "markdown":
        p("\n### Day of week\n")
        p("| Day | Count |")
        p("|-----|-------|")
        for d in range(7):
            p(f"| {dow_names[d]} | {dows.get(d, 0)} |")
    else:
        p("\nDay of week distribution:")
        for d in range(7):
            p(f"  {dow_names[d]:3s}  {dows.get(d, 0):4d}")

    # ============ TOKEN USAGE ============
    p(section("TOKEN USAGE", fmt))
    token_records = [r for r in records if r.get('token_usage')]
    if token_records:
        inp = [r['token_usage'].get('input_tokens', 0) for r in token_records]
        out_tok = [r['token_usage'].get('output_tokens', 0) for r in token_records]
        cache_read = [r['token_usage'].get('cache_read_input_tokens', 0) for r in token_records]
        cache_create = [r['token_usage'].get('cache_creation_input_tokens', 0) for r in token_records]

        total_inp = sum(inp)
        total_out = sum(out_tok)
        total_cache = sum(cache_read)

        if fmt == "markdown":
            p(f"| Metric | Value |")
            p(f"|--------|-------|")
            p(f"| Records with token data | {len(token_records)} |")
            p(f"| Avg input tokens/turn | {total_inp/len(inp):,.0f} |")
            p(f"| Avg output tokens/turn | {total_out/len(out_tok):,.0f} |")
            p(f"| Cache hit rate | {total_cache/total_inp*100:.1f}% |" if total_inp else "| Cache hit rate | N/A |")
            p(f"| Total input tokens | {total_inp:,} |")
            p(f"| Total output tokens | {total_out:,} |")
            p(f"| Total cache read | {total_cache:,} |")
            p(f"| Total cache creation | {sum(cache_create):,} |")
        else:
            p(f"Records with token data: {len(token_records)}")
            p(f"Avg input tokens/turn: {total_inp/len(inp):,.0f}")
            p(f"Avg output tokens/turn: {total_out/len(out_tok):,.0f}")
            p(f"Cache hit rate: {total_cache/total_inp*100:.1f}%" if total_inp else "Cache hit rate: N/A")
            p(f"Total input tokens: {total_inp:,}")
            p(f"Total output tokens: {total_out:,}")
            p(f"Total cache read: {total_cache:,}")
            p(f"Total cache creation: {sum(cache_create):,}")
    else:
        p("No token usage data available in logs.")

    # ============ PROMPT CHARACTERISTICS ============
    p(section("PROMPT CHARACTERISTICS", fmt))
    prompt_texts = [r.get('prompt', '') for r in prompts if r.get('prompt')]
    if prompt_texts:
        lengths = [len(pt) for pt in prompt_texts]
        slash = [pt for pt in prompt_texts if pt.startswith('/')]
        prefixes = Counter(pt[:30] for pt in prompt_texts)

        if fmt == "markdown":
            p(f"| Metric | Value |")
            p(f"|--------|-------|")
            p(f"| Average prompt length | {sum(lengths)/len(lengths):.0f} chars |")
            p(f"| Median prompt length | {sorted(lengths)[len(lengths)//2]} chars |")
            p(f"| Max prompt length | {max(lengths)} chars |")
            p(f"| Slash commands | {len(slash)} ({len(slash)/len(prompt_texts)*100:.1f}%) |")
            p(f"| Free text | {len(prompt_texts)-len(slash)} ({(len(prompt_texts)-len(slash))/len(prompt_texts)*100:.1f}%) |")
            p(f"\n### Top 15 prompt prefixes (first 30 chars)\n")
            p(f"| Count | Prefix |")
            p(f"|-------|--------|")
            for prefix, count in prefixes.most_common(15):
                p(f"| {count} | `{prefix}` |")
        else:
            p(f"Average prompt length: {sum(lengths)/len(lengths):.0f} chars")
            p(f"Median prompt length: {sorted(lengths)[len(lengths)//2]} chars")
            p(f"Max prompt length: {max(lengths)} chars")
            p(f"Slash commands: {len(slash)} ({len(slash)/len(prompt_texts)*100:.1f}%)")
            p(f"Free text: {len(prompt_texts)-len(slash)} ({(len(prompt_texts)-len(slash))/len(prompt_texts)*100:.1f}%)")
            p(f"\nTop 15 prompt prefixes (first 30 chars):")
            for prefix, count in prefixes.most_common(15):
                p(f"  {count:4d}x  {prefix!r}")
    else:
        p("No prompt texts found.")

    # ============ PROJECT DISTRIBUTION ============
    p(section("PROJECT DISTRIBUTION", fmt))
    projects = Counter(r.get('project_dir', '') or r.get('cwd', 'unknown') for r in records)
    if fmt == "markdown":
        p(f"| Count | Project |")
        p(f"|-------|---------|")
        for proj, count in projects.most_common(10):
            p(f"| {count} | {proj} |")
    else:
        for proj, count in projects.most_common(10):
            p(f"  {count:5d}  {proj}")

    # ============ DAILY VOLUME ============
    p(section("DAILY VOLUME (prompts per day)", fmt))
    daily = Counter(r['_dt'].date() for r in prompts)
    if fmt == "markdown":
        p(f"| Date | Prompts | |")
        p(f"|------|---------|-|")
        for d in sorted(daily.keys()):
            bar = '#' * (daily[d] // 3)
            p(f"| {d} | {daily[d]} | `{bar}` |")
    else:
        for d in sorted(daily.keys()):
            bar = '#' * (daily[d] // 3)
            p(f"  {d}  {daily[d]:4d}  {bar}")

    # ============ MODEL USAGE ============
    models = Counter(r.get('model', '') for r in turn_ends if r.get('model'))
    if models:
        p(section("MODEL USAGE", fmt))
        if fmt == "markdown":
            p(f"| Model | Turns |")
            p(f"|-------|-------|")
            for model, count in models.most_common():
                p(f"| {model} | {count} |")
        else:
            for model, count in models.most_common():
                p(f"  {model:40s}: {count:5d}")

    # Output
    report = "\n".join(out)
    if args.output:
        Path(args.output).write_text(report + "\n")
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
