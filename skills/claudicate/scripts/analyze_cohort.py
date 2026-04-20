#!/usr/bin/env python3
"""
Claudicate: analyze_cohort.py
Cohort analysis — usage breakdown for a named agent/skill group (BMAD, a slash-command,
a skill family) or auto-discovery of candidate groups from logs.

Two modes:
- Discovery (--list): scan logs, detect candidate groups, emit a ranked table.
- Targeted (--target <selector>): deep analysis for one cohort.
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


# ---------- common helpers (duplicated from analyze_usage.py / analyze_agents.py on purpose) ----------

def load_logs(dirs, since_date=None):
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


def is_agent_session(session_id):
    return (session_id or '').startswith('agent-')


# ---------- target parsing & matching ----------

NEGATION_PATTERNS = [
    r'\bno\b', r'\bnot that\b', r'\bstop\b', r'\bundo\b', r'\bwrong\b',
    r'\binstead\b', r'\bactually\b', r'\brather\b', r"\bdon't\b",
    r'\bshould not\b', r'\brevert\b', r'\bforget that\b', r'\bnot what\b',
]


def parse_target(s):
    """Parse a target selector string into a dict.

    Forms:
      bmad                → {type:'tag_family', prefix:'bmad'}
      bmad:dev            → {type:'tag_exact', tag:'bmad:dev'}
      tag:<x>             → {type:'tag_exact', tag:'<x>'}
      tag_family:<x>      → {type:'tag_family', prefix:'<x>'}
      slash:/<x>          → {type:'slash', prefix:'/<x>'}
      /<x>                → {type:'slash', prefix:'/<x>'}
      skill:<name>        → {type:'skill', name:'<name>'}
      skills              → {type:'skill_family'}
    """
    if not s:
        return None
    s = s.strip()
    if s == 'skills':
        return {'type': 'skill_family'}
    if s.startswith('slash:'):
        rest = s[len('slash:'):]
        if not rest.startswith('/'):
            rest = '/' + rest
        return {'type': 'slash', 'prefix': rest}
    if s.startswith('/'):
        return {'type': 'slash', 'prefix': s}
    if s.startswith('tag_family:'):
        return {'type': 'tag_family', 'prefix': s[len('tag_family:'):]}
    if s.startswith('tag:'):
        return {'type': 'tag_exact', 'tag': s[len('tag:'):]}
    if s.startswith('skill:'):
        return {'type': 'skill', 'name': s[len('skill:'):]}
    if ':' in s:
        return {'type': 'tag_exact', 'tag': s}
    return {'type': 'tag_family', 'prefix': s}


def target_label(t):
    if not t:
        return "?"
    k = t['type']
    if k == 'tag_family':
        return f"{t['prefix']} (tag family)"
    if k == 'tag_exact':
        return f"tag:{t['tag']}"
    if k == 'slash':
        return f"slash:{t['prefix']}"
    if k == 'skill':
        return f"skill:{t['name']}"
    if k == 'skill_family':
        return "skills (family)"
    return "?"


def matches_invocation(record, target):
    """Does this prompt record count as an invocation of the cohort?"""
    if record.get('event_type') != 'prompt':
        return False
    tags = record.get('tags', []) or []
    prompt = record.get('prompt', '') or ''
    k = target['type']
    if k == 'tag_exact':
        return target['tag'] in tags
    if k == 'tag_family':
        pref = target['prefix']
        for t in tags:
            if t == pref:
                return True
            if t.startswith(pref + ':') or t.startswith(pref + '_'):
                return True
        return False
    if k == 'slash':
        return prompt.startswith(target['prefix'])
    if k == 'skill':
        name = re.escape(target['name'])
        if re.match(rf'^/{name}(\b|$)', prompt):
            return True
        if re.search(rf'<command-message>[^<]*{name}', prompt):
            return True
        return False
    if k == 'skill_family':
        # Any slash command that invokes a skill under .claude/skills/ — heuristic: starts with '/'
        # and first token not matching BMAD pattern. Not very useful alone; callers rarely use this.
        return prompt.startswith('/') and not prompt.startswith('/BMad:')
    return False


def extract_member(record, target):
    """For an invocation record, return the sub-identifier within the cohort (e.g., 'dev' for bmad:dev)."""
    tags = record.get('tags', []) or []
    prompt = record.get('prompt', '') or ''
    k = target['type']
    if k == 'tag_family':
        pref = target['prefix']
        for t in tags:
            if t.startswith(pref + ':'):
                return t[len(pref) + 1:]
            if t.startswith(pref + '_'):
                return t
        return '(none)'
    if k == 'slash':
        # Extract full first-line slash token
        first = prompt.splitlines()[0] if prompt else ''
        m = re.match(r'^(/\S+)', first)
        return m.group(1) if m else target['prefix']
    if k == 'tag_exact':
        return target['tag']
    if k == 'skill':
        return target['name']
    return ''


# ---------- declared-set loaders (for "unused members" detection) ----------

def candidate_project_dirs(explicit_filter):
    dirs = []
    if explicit_filter:
        dirs.append(explicit_filter)
    cwd = os.getcwd()
    if cwd not in dirs:
        dirs.append(cwd)
    cpd = os.environ.get("CLAUDE_PROJECT_DIR")
    if cpd and cpd not in dirs:
        dirs.append(cpd)
    return dirs


def load_declared_bmad(search_roots, override=None):
    """Return a set of declared BMAD role names, or None if nothing found."""
    roots = [override] if override else search_roots
    for root in roots:
        if not root:
            continue
        candidate = os.path.join(root, '.bmad-core', 'agents')
        if os.path.isdir(candidate):
            return set(
                Path(f).stem
                for f in glob.glob(os.path.join(candidate, '*.md'))
            )
        # Also check override pointing directly at the agents dir
        if override and os.path.isdir(override):
            return set(Path(f).stem for f in glob.glob(os.path.join(override, '*.md')))
    return None


def load_declared_skills(search_roots, override=None):
    """Return a set of declared skill directory names, or None if nothing found."""
    roots = [override] if override else search_roots
    for root in roots:
        if not root:
            continue
        candidate = os.path.join(root, '.claude', 'skills')
        if os.path.isdir(candidate):
            names = set()
            for entry in os.listdir(candidate):
                if os.path.isfile(os.path.join(candidate, entry, 'SKILL.md')):
                    names.add(entry)
            if names:
                return names
    return None


def load_declared_for_target(target, search_roots, override=None):
    if not target:
        return None
    if target['type'] == 'tag_family' and target['prefix'] == 'bmad':
        return load_declared_bmad(search_roots, override)
    if target['type'] == 'skill_family':
        return load_declared_skills(search_roots, override)
    return None


# ---------- discovery ----------

SLASH_FAMILY_RULES = [
    (re.compile(r'^/BMad:agents:([A-Za-z_-]+)'), 'bmad', 'tag_family'),
    (re.compile(r'^/BMad:tasks:([A-Za-z_-]+)'), 'bmad_task', 'tag_family'),
]


def discover_candidate_groups(user_records, min_count=5):
    """Scan user prompt records, return list of candidate cohort groups."""
    prompts = [r for r in user_records if r.get('event_type') == 'prompt']
    candidates = {}  # key -> {label, target_str, invocations (set of rec ids), sessions (set)}

    def bump(key, label, target_str, rec):
        if key not in candidates:
            candidates[key] = {
                'label': label,
                'target': target_str,
                'records': [],
                'sessions': set(),
            }
        candidates[key]['records'].append(rec)
        candidates[key]['sessions'].add(rec.get('session_id', ''))

    # 1) Tag-family clusters
    tag_prefixes = Counter()
    for r in prompts:
        for t in r.get('tags', []) or []:
            if ':' in t:
                pref = t.split(':', 1)[0]
                tag_prefixes[pref] += 1
    for pref, n in tag_prefixes.items():
        if n < min_count:
            continue
        for r in prompts:
            for t in r.get('tags', []) or []:
                if t == pref or t.startswith(pref + ':'):
                    bump(f"tag_family:{pref}", pref, pref, r)
                    break

    # 2) Slash-command first-token clusters (normalized via SLASH_FAMILY_RULES for BMAD)
    slash_first = Counter()
    for r in prompts:
        p = (r.get('prompt') or '').splitlines()[0] if r.get('prompt') else ''
        if p.startswith('/'):
            # Normalize BMAD variants to a single family already captured by tags — skip
            if any(rule[0].match(p) for rule in SLASH_FAMILY_RULES):
                continue
            m = re.match(r'^(/[^\s]+)', p)
            if m:
                slash_first[m.group(1)] += 1
    for tok, n in slash_first.items():
        if n < min_count:
            continue
        for r in prompts:
            p = (r.get('prompt') or '').splitlines()[0] if r.get('prompt') else ''
            if p.startswith(tok + ' ') or p == tok or p.startswith(tok + '\n') or p.startswith(tok + '\t'):
                bump(f"slash:{tok}", tok, f"slash:{tok}", r)

    # 3) <command-message>...</command-message> invocations (skills not already covered)
    slash_tokens_stripped = {tok.lstrip('/') for tok in slash_first}
    cmdmsg = Counter()
    cmdmsg_pat = re.compile(r'<command-message>([^<]+?)</command-message>')
    for r in prompts:
        m = cmdmsg_pat.search(r.get('prompt') or '')
        if m:
            cmdmsg[m.group(1).strip()] += 1
    for name, n in cmdmsg.items():
        if n < min_count:
            continue
        key_token = (name.split()[0] if name else name).strip()
        # Skip duplicates: BMAD is already covered via tag family; slash tokens via slash cluster
        if key_token.startswith('BMad:') or key_token in slash_tokens_stripped:
            continue
        key = f"skill:{key_token}"
        for r in prompts:
            m = cmdmsg_pat.search(r.get('prompt') or '')
            if m and m.group(1).strip().startswith(key_token):
                bump(key, key_token, f"skill:{key_token}", r)

    # Flatten
    out = []
    for key, d in candidates.items():
        out.append({
            'key': key,
            'label': d['label'],
            'target': d['target'],
            'invocations': len(d['records']),
            'sessions': len(d['sessions']),
            'denial_sessions': d['sessions'],  # reused below
        })
    out.sort(key=lambda x: -x['invocations'])
    return out


# ---------- cohort analysis ----------

def correlate_cohort_fanout(agent_records, user_records, target):
    """Count agent-* sessions whose closest preceding user prompt lives in a cohort-activated user session.

    Attribution is session-level: an agent is counted for the cohort when the *parent* user session
    contains at least one cohort invocation anywhere in its history. This matches how multi-turn
    slash commands work (one `/analyze-evaluation` invocation spawns many subagents across subsequent turns).
    """
    user_prompts = sorted(
        [r for r in user_records if r.get('event_type') == 'prompt' and r.get('_dt')],
        key=lambda r: r['_dt']
    )
    # Pre-compute: which user sessions are cohort-activated (contain ≥1 invocation)
    cohort_sessions = set()
    for r in user_records:
        if matches_invocation(r, target):
            cohort_sessions.add(r.get('session_id', ''))

    agent_sessions = defaultdict(list)
    for r in agent_records:
        agent_sessions[r.get('session_id', '')].append(r)

    cohort_spawns = 0
    total_correlated = 0
    for sid, events in agent_sessions.items():
        starts = [e['_dt'] for e in events if e.get('_dt')]
        if not starts:
            continue
        start = min(starts)
        best = None
        for up in reversed(user_prompts):
            if up['_dt'] < start:
                best = up
                break
        if best is None:
            continue
        total_correlated += 1
        if best.get('session_id', '') in cohort_sessions:
            cohort_spawns += 1
    return cohort_spawns, total_correlated


def analyze_cohort(records, target, declared=None, include_agents=False):
    """Run the full cohort analysis. Returns a dict of metrics."""
    all_records = records
    user_records = [r for r in all_records if not is_agent_session(r.get('session_id', ''))]
    agent_records = [r for r in all_records if is_agent_session(r.get('session_id', ''))]

    if include_agents:
        analysis_records = all_records
    else:
        analysis_records = user_records

    prompts = [r for r in analysis_records if r.get('event_type') == 'prompt']
    invocations = [r for r in prompts if matches_invocation(r, target)]

    # Member breakdown
    members = Counter(extract_member(r, target) for r in invocations)

    # Session-level adoption
    all_sessions = defaultdict(list)
    for r in analysis_records:
        all_sessions[r.get('session_id', '')].append(r)

    cohort_sessions = set()
    for sid, events in all_sessions.items():
        if any(matches_invocation(e, target) for e in events):
            cohort_sessions.add(sid)

    # Prompts per session
    prompts_per_session = defaultdict(int)
    for r in prompts:
        prompts_per_session[r.get('session_id', '')] += 1

    cohort_session_prompts = sum(prompts_per_session[sid] for sid in cohort_sessions)
    non_cohort_sessions = set(all_sessions.keys()) - cohort_sessions
    non_cohort_session_prompts = sum(prompts_per_session[sid] for sid in non_cohort_sessions)

    def session_length_stats(session_ids):
        lens = [prompts_per_session[sid] for sid in session_ids if prompts_per_session[sid] > 0]
        if not lens:
            return None
        lens.sort()
        return {
            'count': len(lens),
            'avg': sum(lens) / len(lens),
            'median': lens[len(lens) // 2],
            'max': max(lens),
        }

    cohort_len = session_length_stats(cohort_sessions)
    non_cohort_len = session_length_stats(non_cohort_sessions)

    # Member combinations per session (only meaningful for family targets)
    combos = Counter()
    for sid in cohort_sessions:
        members_here = set()
        for e in all_sessions[sid]:
            if matches_invocation(e, target):
                members_here.add(extract_member(e, target))
        if members_here:
            combos[tuple(sorted(members_here))] += 1

    # Daily volume
    daily = Counter(r['_dt'].date() for r in invocations if r.get('_dt'))

    # Friction: denials & negations within cohort sessions
    cohort_denials = [
        r for r in analysis_records
        if r.get('event_type') == 'tool_denial' and r.get('session_id', '') in cohort_sessions
    ]
    denied_tools = Counter(r.get('denied_tool', 'unknown') for r in cohort_denials)

    negation_hits = 0
    for r in prompts:
        if r.get('session_id', '') not in cohort_sessions:
            continue
        pt = r.get('prompt') or ''
        if any(re.search(pat, pt, re.I) for pat in NEGATION_PATTERNS):
            negation_hits += 1

    # Subagent fanout
    fanout_cohort, fanout_total = correlate_cohort_fanout(agent_records, user_records, target)

    # Unused members
    unused = None
    if declared:
        observed = set(members.keys()) - {'(none)'}
        unused = sorted(declared - observed)

    total_user_prompts = len(prompts)
    total_user_sessions = len(all_sessions)

    return {
        'target_label': target_label(target),
        'invocations': len(invocations),
        'members': members,
        'total_user_prompts': total_user_prompts,
        'total_user_sessions': total_user_sessions,
        'cohort_sessions': len(cohort_sessions),
        'cohort_session_prompts': cohort_session_prompts,
        'non_cohort_sessions': len(non_cohort_sessions),
        'non_cohort_session_prompts': non_cohort_session_prompts,
        'cohort_len_stats': cohort_len,
        'non_cohort_len_stats': non_cohort_len,
        'combos': combos,
        'daily': daily,
        'denials': len(cohort_denials),
        'denied_tools': denied_tools,
        'negation_hits': negation_hits,
        'fanout_cohort': fanout_cohort,
        'fanout_total': fanout_total,
        'declared': declared,
        'unused': unused,
    }


# ---------- formatting ----------

def pct(n, d):
    return f"{(n / d * 100):.1f}%" if d else "–"


def format_cohort_report(m, fmt="markdown"):
    out = []

    def p(s=""):
        out.append(s)

    p(section(f"COHORT — {m['target_label']}", fmt))

    if fmt == "markdown":
        p("| Metric | Value |")
        p("|--------|-------|")
        p(f"| Direct invocations | {m['invocations']} |")
        p(f"| Cohort sessions | {m['cohort_sessions']} / {m['total_user_sessions']} ({pct(m['cohort_sessions'], m['total_user_sessions'])}) |")
        p(f"| Prompts in cohort sessions | {m['cohort_session_prompts']} / {m['total_user_prompts']} ({pct(m['cohort_session_prompts'], m['total_user_prompts'])}) |")
        p(f"| Prompts outside cohort sessions | {m['non_cohort_session_prompts']} ({pct(m['non_cohort_session_prompts'], m['total_user_prompts'])}) |")
        p(f"| Cohort denials | {m['denials']} |")
        p(f"| Negation language in cohort sessions | {m['negation_hits']} prompts |")
        if m['fanout_total']:
            p(f"| Subagent fanout | {m['fanout_cohort']} / {m['fanout_total']} correlated agent sessions ({pct(m['fanout_cohort'], m['fanout_total'])}) |")
    else:
        p(f"Direct invocations: {m['invocations']}")
        p(f"Cohort sessions: {m['cohort_sessions']} / {m['total_user_sessions']} ({pct(m['cohort_sessions'], m['total_user_sessions'])})")
        p(f"Prompts in cohort sessions: {m['cohort_session_prompts']} / {m['total_user_prompts']} ({pct(m['cohort_session_prompts'], m['total_user_prompts'])})")
        p(f"Prompts outside cohort sessions: {m['non_cohort_session_prompts']}")
        p(f"Cohort denials: {m['denials']}")
        p(f"Negation language in cohort sessions: {m['negation_hits']}")
        if m['fanout_total']:
            p(f"Subagent fanout: {m['fanout_cohort']} / {m['fanout_total']}")

    # Member breakdown
    if m['members']:
        p(section("MEMBER BREAKDOWN", fmt))
        total_inv = m['invocations']
        total_prompts = m['total_user_prompts']
        if fmt == "markdown":
            p("| Member | Invocations | % of cohort | % of all user prompts |")
            p("|--------|-------------|-------------|----------------------|")
            for member, c in m['members'].most_common():
                p(f"| `{member}` | {c} | {pct(c, total_inv)} | {pct(c, total_prompts)} |")
        else:
            for member, c in m['members'].most_common():
                p(f"  {member:30s}: {c:5d}  ({pct(c, total_inv)} of cohort)")

    # Session length comparison
    if m['cohort_len_stats'] and m['non_cohort_len_stats']:
        p(section("SESSION LENGTH", fmt))
        c = m['cohort_len_stats']
        nc = m['non_cohort_len_stats']
        if fmt == "markdown":
            p("| Group | Sessions | Avg prompts | Median | Max |")
            p("|-------|----------|-------------|--------|-----|")
            p(f"| Cohort | {c['count']} | {c['avg']:.1f} | {c['median']} | {c['max']} |")
            p(f"| Non-cohort | {nc['count']} | {nc['avg']:.1f} | {nc['median']} | {nc['max']} |")
        else:
            p(f"Cohort    : n={c['count']} avg={c['avg']:.1f} median={c['median']} max={c['max']}")
            p(f"Non-cohort: n={nc['count']} avg={nc['avg']:.1f} median={nc['median']} max={nc['max']}")

    # Combinations (only interesting for multi-member targets)
    if len(m['combos']) > 1 or (m['combos'] and len(next(iter(m['combos'].keys()))) > 1):
        p(section("MEMBER COMBINATIONS PER SESSION", fmt))
        if fmt == "markdown":
            p("| Combination | Sessions |")
            p("|-------------|----------|")
            for combo, n in m['combos'].most_common(15):
                label = " + ".join(combo) if len(combo) > 1 else f"{combo[0]} only"
                p(f"| `{label}` | {n} |")
        else:
            for combo, n in m['combos'].most_common(15):
                label = " + ".join(combo) if len(combo) > 1 else f"{combo[0]} only"
                p(f"  {label:40s}: {n}")

    # Daily volume
    if m['daily']:
        p(section("DAILY INVOCATIONS", fmt))
        dates = sorted(m['daily'].keys())
        if fmt == "markdown":
            p("| Date | Invocations | |")
            p("|------|-------------|-|")
            for d in dates:
                bar = '#' * m['daily'][d]
                p(f"| {d} | {m['daily'][d]} | `{bar}` |")
        else:
            for d in dates:
                p(f"  {d}  {m['daily'][d]:4d}")

    # Friction detail
    if m['denied_tools']:
        p(section("FRICTION — DENIED TOOLS", fmt))
        if fmt == "markdown":
            p("| Tool | Count |")
            p("|------|-------|")
            for tool, c in m['denied_tools'].most_common():
                p(f"| {tool} | {c} |")
        else:
            for tool, c in m['denied_tools'].most_common():
                p(f"  {tool:30s}: {c}")

    # Unused members
    if m['declared']:
        p(section("DECLARED vs OBSERVED", fmt))
        observed = set(m['members'].keys()) - {'(none)'}
        if fmt == "markdown":
            p(f"Declared members ({len(m['declared'])}): {', '.join(f'`{x}`' for x in sorted(m['declared']))}")
            p(f"\nObserved members ({len(observed)}): {', '.join(f'`{x}`' for x in sorted(observed)) or '–'}")
            if m['unused']:
                p(f"\n**Unused** ({len(m['unused'])}): {', '.join(f'`{x}`' for x in m['unused'])}")
            else:
                p("\n**Unused**: none — every declared member was observed.")
        else:
            p(f"Declared: {sorted(m['declared'])}")
            p(f"Observed: {sorted(observed)}")
            p(f"Unused:   {m['unused']}")

    return "\n".join(out)


def format_discovery(groups, fmt="markdown", all_records=None):
    """Render the discovery overview table with basic per-group metrics."""
    out = []

    def p(s=""):
        out.append(s)

    p(section("DISCOVERED COHORTS", fmt))

    if not groups:
        p("No candidate groups found (threshold: ≥5 invocations).")
        return "\n".join(out)

    total_sessions = 0
    if all_records is not None:
        total_sessions = len(set(
            r.get('session_id', '') for r in all_records
            if not is_agent_session(r.get('session_id', ''))
        ))

    if fmt == "markdown":
        p("| Target | Invocations | Sessions | % of user sessions |")
        p("|--------|-------------|----------|--------------------|")
        for g in groups:
            sp = pct(g['sessions'], total_sessions) if total_sessions else "–"
            p(f"| `{g['target']}` | {g['invocations']} | {g['sessions']} | {sp} |")
        p("\nRun `/claudicate cohort <target>` for a full breakdown of any group above.")
    else:
        for g in groups:
            sp = pct(g['sessions'], total_sessions) if total_sessions else "–"
            p(f"  {g['target']:30s}  inv={g['invocations']:5d}  sess={g['sessions']:4d}  {sp}")

    return "\n".join(out)


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser(description="Cohort analysis of claudicate logs")
    parser.add_argument("--logs-dir", action="append", help="Log directory (can be repeated)")
    parser.add_argument("--since", help="Only analyze after this date (YYYY-MM-DD)")
    parser.add_argument("--project-filter", help="Only include entries matching this project directory")
    parser.add_argument("--format", choices=["text", "markdown"], default="text", help="Output format")
    parser.add_argument("--output", help="Write report to file instead of stdout")
    parser.add_argument("--target", help="Cohort selector (e.g. 'bmad', 'bmad:dev', 'slash:/x', 'skill:x', 'tag:x')")
    parser.add_argument("--list", action="store_true", help="Discovery mode: list candidate groups")
    parser.add_argument("--declared-from", help="Override path for declared-set detection")
    parser.add_argument("--include-agents", action="store_true",
                        help="Include agent (subagent) sessions in the primary analysis")
    parser.add_argument("--min-discovery", type=int, default=5,
                        help="Minimum invocation count for a group to appear in discovery (default 5)")
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
        print("No log directories found.", file=sys.stderr)
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
        print("No log entries found.", file=sys.stderr)
        sys.exit(1)

    user_records = [r for r in records if not is_agent_session(r.get('session_id', ''))]

    report = ""

    if args.list or not args.target:
        groups = discover_candidate_groups(user_records, min_count=args.min_discovery)
        report = format_discovery(groups, fmt=args.format, all_records=user_records)
        if not args.list and not args.target:
            # No target and not explicit --list: still emit discovery (workflow uses this).
            pass
    else:
        target = parse_target(args.target)
        if not target:
            print(f"Error: could not parse target '{args.target}'", file=sys.stderr)
            sys.exit(1)
        search_roots = candidate_project_dirs(args.project_filter)
        declared = load_declared_for_target(target, search_roots, override=args.declared_from)
        metrics = analyze_cohort(records, target, declared=declared, include_agents=args.include_agents)
        report = format_cohort_report(metrics, fmt=args.format)

    if args.output:
        Path(args.output).write_text(report + "\n")
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
