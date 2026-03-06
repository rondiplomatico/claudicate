#!/usr/bin/env python3
"""
promptforge: extract-sessions.py
Retroactive extraction of user interactions from Claude Code session JSONL files
and old text-format prompt logs into promptforge JSONL format.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


def auto_tag(text):
    """Apply auto-tagging rules to a prompt text."""
    tags = []
    if not text:
        return tags

    # BMAD agent invocation
    m = re.match(r'^/BMad:agents:([a-zA-Z_-]+)', text)
    if m:
        tags.extend(["bmad", f"bmad:{m.group(1)}"])
    m = re.match(r'^/BMad:tasks:([a-zA-Z_-]+)', text)
    if m:
        tags.extend(["bmad", f"bmad_task:{m.group(1)}"])

    if text.startswith("/"):
        tags.append("slash_command")

    if re.search(r'(plan\s+mode|planning|/plan|enter\s+plan)', text, re.I):
        tags.append("planning")

    if re.search(r'(test|pytest|verify|spec\s)', text, re.I):
        tags.append("testing")

    if re.search(r'(commit|push|pull\s+request|merge|pr\s)', text, re.I):
        tags.append("git_ops")

    return tags


def parse_session_jsonl(filepath, since_date=None, project_filter=None):
    """Parse a Claude Code session JSONL file and extract user interactions."""
    entries = []
    session_id = filepath.stem  # filename without extension
    prev_tool_use = None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                record_type = record.get("type")

                # Extract metadata
                cwd = record.get("cwd", "")
                project_dir = record.get("cwd", "")  # best guess
                timestamp = record.get("timestamp")

                if timestamp and since_date:
                    try:
                        rec_date = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date()
                        if rec_date < since_date:
                            continue
                    except (ValueError, AttributeError):
                        pass

                if project_filter and project_filter not in str(filepath):
                    continue

                # Track tool_use blocks for correlating denials
                if record_type == "assistant":
                    msg = record.get("message", {})
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                prev_tool_use = block

                # Process user messages
                if record_type == "user":
                    msg = record.get("message", {})
                    content = msg.get("content", "")

                    # Simple string content = user prompt
                    if isinstance(content, str) and content.strip():
                        entry = {
                            "timestamp": timestamp or datetime.utcnow().isoformat() + "Z",
                            "event_type": "prompt",
                            "session_id": session_id,
                            "project_dir": project_dir,
                            "cwd": cwd,
                            "prompt": content.strip(),
                            "tags": auto_tag(content.strip()),
                        }
                        entries.append(entry)
                        continue

                    # Array content - check for tool_result blocks
                    if isinstance(content, list):
                        for block in content:
                            if not isinstance(block, dict):
                                continue

                            if block.get("type") == "tool_result":
                                result_content = block.get("content", "")
                                if isinstance(result_content, list):
                                    result_content = " ".join(
                                        b.get("text", "") for b in result_content
                                        if isinstance(b, dict)
                                    )

                                # AskUserQuestion answer
                                if "User has answered your questions:" in str(result_content):
                                    question = ""
                                    answer = ""
                                    q_match = re.search(r'Question:\s*(.*?)(?:\nAnswer:)', str(result_content), re.S)
                                    a_match = re.search(r'Answer:\s*(.*?)$', str(result_content), re.S)
                                    if q_match:
                                        question = q_match.group(1).strip()
                                    if a_match:
                                        answer = a_match.group(1).strip()
                                    entry = {
                                        "timestamp": timestamp or datetime.utcnow().isoformat() + "Z",
                                        "event_type": "ask_response",
                                        "session_id": session_id,
                                        "project_dir": project_dir,
                                        "cwd": cwd,
                                        "question": question,
                                        "answer": answer,
                                        "tags": ["clarification"],
                                    }
                                    entries.append(entry)

                                # Tool denial
                                elif "doesn't want to proceed" in str(result_content) or "user doesn't want" in str(result_content):
                                    denied_tool = ""
                                    denied_input = {}
                                    if prev_tool_use:
                                        denied_tool = prev_tool_use.get("name", "")
                                        inp = prev_tool_use.get("input", {})
                                        if inp:
                                            serialized = json.dumps(inp)
                                            if len(serialized) > 500:
                                                denied_input = {"_truncated": serialized[:500]}
                                            else:
                                                denied_input = inp
                                        else:
                                            denied_input = {}
                                    entry = {
                                        "timestamp": timestamp or datetime.utcnow().isoformat() + "Z",
                                        "event_type": "tool_denial",
                                        "session_id": session_id,
                                        "project_dir": project_dir,
                                        "cwd": cwd,
                                        "denied_tool": denied_tool,
                                        "denied_input": denied_input,
                                        "denial_reason": str(result_content)[:200],
                                        "is_interrupt": False,
                                        "tags": ["correction"],
                                    }
                                    entries.append(entry)

                                # User interrupt
                                elif "Request interrupted by user" in str(result_content):
                                    entry = {
                                        "timestamp": timestamp or datetime.utcnow().isoformat() + "Z",
                                        "event_type": "tool_denial",
                                        "session_id": session_id,
                                        "project_dir": project_dir,
                                        "cwd": cwd,
                                        "denied_tool": prev_tool_use.get("name", "") if prev_tool_use else "",
                                        "denied_input": {},
                                        "denial_reason": "User interrupted",
                                        "is_interrupt": True,
                                        "tags": ["correction"],
                                    }
                                    entries.append(entry)

                            elif block.get("type") == "text":
                                text = block.get("text", "").strip()
                                if text:
                                    entry = {
                                        "timestamp": timestamp or datetime.utcnow().isoformat() + "Z",
                                        "event_type": "prompt",
                                        "session_id": session_id,
                                        "project_dir": project_dir,
                                        "cwd": cwd,
                                        "prompt": text,
                                        "tags": auto_tag(text),
                                    }
                                    entries.append(entry)

    except Exception as e:
        print(f"  Warning: Error parsing {filepath}: {e}", file=sys.stderr)

    return entries


def parse_old_text_logs(logs_dir):
    """Parse old text-format prompt logs from ~/.claude/prompt-logs/."""
    entries = []
    logs_path = Path(logs_dir)
    if not logs_path.exists():
        return entries

    for log_file in sorted(logs_path.glob("*.log")):
        try:
            content = log_file.read_text(encoding='utf-8')
            # Split on --- separator
            blocks = content.split("---")
            for block in blocks:
                block = block.strip()
                if not block:
                    continue

                timestamp = ""
                session_id = ""
                workspace = ""
                cwd = ""
                prompt_lines = []
                in_prompt = False

                for line in block.split("\n"):
                    if line.startswith("Timestamp:"):
                        timestamp = line.split(":", 1)[1].strip()
                    elif line.startswith("Session:"):
                        session_id = line.split(":", 1)[1].strip()
                    elif line.startswith("Workspace:"):
                        workspace = line.split(":", 1)[1].strip()
                    elif line.startswith("Working Directory:"):
                        cwd = line.split(":", 1)[1].strip()
                    elif line.startswith("Prompt:"):
                        in_prompt = True
                        rest = line.split(":", 1)[1].strip()
                        if rest:
                            prompt_lines.append(rest)
                    elif in_prompt:
                        prompt_lines.append(line)

                prompt_text = "\n".join(prompt_lines).strip()
                if prompt_text:
                    entry = {
                        "timestamp": timestamp or datetime.utcnow().isoformat() + "Z",
                        "event_type": "prompt",
                        "session_id": session_id,
                        "project_dir": workspace,
                        "cwd": cwd or workspace,
                        "prompt": prompt_text,
                        "tags": auto_tag(prompt_text),
                    }
                    entries.append(entry)

        except Exception as e:
            print(f"  Warning: Error parsing {log_file}: {e}", file=sys.stderr)

    return entries


def deduplicate(entries):
    """Remove duplicate entries by timestamp+session_id+event_type."""
    seen = set()
    unique = []
    for entry in entries:
        key = (entry.get("timestamp", ""), entry.get("session_id", ""), entry.get("event_type", ""),
               entry.get("prompt", entry.get("question", entry.get("denied_tool", ""))))
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


def write_entries(entries, output_dir):
    """Write entries to date-partitioned JSONL files."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Group by date
    by_date = {}
    for entry in entries:
        ts = entry.get("timestamp", "")
        try:
            date_str = ts[:10]  # YYYY-MM-DD
            if not re.match(r'\d{4}-\d{2}-\d{2}', date_str):
                date_str = datetime.utcnow().strftime("%Y-%m-%d")
        except (IndexError, ValueError):
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
        by_date.setdefault(date_str, []).append(entry)

    total = 0
    for date_str, date_entries in sorted(by_date.items()):
        filepath = output_path / f"{date_str}.jsonl"

        # Load existing entries for deduplication
        existing = []
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            existing.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

        all_entries = existing + date_entries
        unique = deduplicate(all_entries)

        with open(filepath, 'w', encoding='utf-8') as f:
            for entry in sorted(unique, key=lambda e: e.get("timestamp", "")):
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        new_count = len(unique) - len(existing)
        if new_count > 0:
            total += new_count
            print(f"  {date_str}: {new_count} new entries (total: {len(unique)})")

    return total


def main():
    parser = argparse.ArgumentParser(description="Extract user interactions from Claude Code sessions")
    parser.add_argument("--since", help="Only process sessions after this date (YYYY-MM-DD)")
    parser.add_argument("--project", help="Filter by project directory name substring")
    parser.add_argument("--include-old-logs", action="store_true", help="Also convert ~/.claude/prompt-logs/*.log")
    parser.add_argument("--output", default=os.path.expanduser("~/.promptforge/logs/"),
                        help="Output directory (default: ~/.promptforge/logs/)")
    args = parser.parse_args()

    since_date = None
    if args.since:
        try:
            since_date = datetime.strptime(args.since, "%Y-%m-%d").date()
        except ValueError:
            print(f"Error: Invalid date format '{args.since}'. Use YYYY-MM-DD.", file=sys.stderr)
            sys.exit(1)

    all_entries = []

    # Parse session JSONL files
    projects_dir = Path.home() / ".claude" / "projects"
    if projects_dir.exists():
        session_files = list(projects_dir.rglob("*.jsonl"))
        print(f"Found {len(session_files)} session files")
        for i, sf in enumerate(session_files, 1):
            if args.project and args.project not in str(sf):
                continue
            entries = parse_session_jsonl(sf, since_date, args.project)
            if entries:
                print(f"  [{i}/{len(session_files)}] {sf.name}: {len(entries)} interactions")
            all_entries.extend(entries)
    else:
        print("No session files found at ~/.claude/projects/")

    # Parse old text logs
    if args.include_old_logs:
        old_logs_dir = Path.home() / ".claude" / "prompt-logs"
        if old_logs_dir.exists():
            print(f"\nParsing old text logs from {old_logs_dir}")
            old_entries = parse_old_text_logs(old_logs_dir)
            print(f"  Found {len(old_entries)} entries from old logs")
            all_entries.extend(old_entries)
        else:
            print("\nNo old text logs found at ~/.claude/prompt-logs/")

    # Deduplicate and write
    print(f"\nTotal raw entries: {len(all_entries)}")
    unique = deduplicate(all_entries)
    print(f"After deduplication: {len(unique)}")

    print(f"\nWriting to {args.output}")
    new_count = write_entries(unique, args.output)
    print(f"\nDone! {new_count} new entries written.")


if __name__ == "__main__":
    main()
