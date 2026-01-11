#!/usr/bin/env python3
"""
Claude Code Conversation Backup Script

Converts Claude Code session history to readable Markdown files.

Usage:
    python backup.py                    # Full backup
    python backup.py -i                 # Incremental (new sessions only)
    python backup.py --output ~/backup  # Custom output directory
"""

import json
import re
import argparse
import sys
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# Default paths
DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
DEFAULT_OUTPUT_DIR = Path.home() / "claude-backup"


def get_project_name(messages):
    """Extract project name from session messages"""
    for msg in messages:
        cwd = msg.get('cwd', '')
        if not cwd:
            continue

        parts = Path(cwd).parts

        # Find numbered folders (e.g., "017 - my-project")
        for part in reversed(parts):
            if re.match(r'^\d{2,3}\s*[-]', part):
                return part

        # Skip common system folders
        home_name = Path.home().name
        skip_names = {'Users', 'home', home_name, 'Documents', 'Desktop', ''}
        for part in reversed(parts):
            if part and part not in skip_names:
                return part

    return "00-misc"


def sanitize_name(name):
    """Remove special characters from folder name"""
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()[:60]


def extract_session_title(messages, max_length=30):
    """Extract meaningful title from first user message"""
    for msg in messages:
        # Find first user message
        if msg.get('type') == 'user' or msg.get('message', {}).get('role') == 'user':
            content = msg.get('message', {}).get('content', '')

            # Extract text from content
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = ' '.join(
                    item.get('text', '') for item in content
                    if isinstance(item, dict) and item.get('type') == 'text'
                )
            else:
                continue

            # Skip command messages
            if text.startswith(('<', '/')):
                continue

            # Clean up the text
            text = text.strip()
            if not text:
                continue

            # Remove special characters for filename
            text = re.sub(r'[<>:"/\\|?*\n\r\t]', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()

            # Extract meaningful part (first line or sentence)
            text = text.split('.')[0].split('?')[0].split('!')[0]
            text = text.strip()

            # Truncate to max length
            if len(text) > max_length:
                # Try to cut at word boundary
                text = text[:max_length].rsplit(' ', 1)[0]
                if len(text) < 10:  # If too short, just truncate
                    text = text[:max_length]

            if len(text) >= 3:  # Minimum 3 characters
                return text

    return None


def load_session(filepath):
    """Load session file"""
    messages = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                messages.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    return messages


def extract_text(content):
    """Extract text from message content"""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    texts.append(item.get('text', ''))
                elif item.get('type') == 'tool_use':
                    tool = item.get('name', 'Tool')
                    inp = item.get('input', {})

                    # Tool icons
                    if tool in ['Read', 'Write', 'Edit', 'Glob', 'Grep']:
                        path = inp.get('file_path') or inp.get('path') or inp.get('pattern', '')
                        texts.append(f"`📁 {tool}: {path[-50:]}`")
                    elif tool == 'Bash':
                        cmd = inp.get('command', '')[:80]
                        texts.append(f"`🔧 {cmd}`")
                    elif tool == 'TodoWrite':
                        texts.append("`📝 Todo`")
                    elif tool in ['WebSearch', 'WebFetch']:
                        texts.append(f"`🌐 {tool}`")
                    elif tool == 'Task':
                        texts.append("`🤖 Task Agent`")
                    else:
                        texts.append(f"`⚙️ {tool}`")
        return '\n'.join(texts)

    return str(content)


def get_role(msg):
    """Determine message role"""
    if msg.get('type') == 'user' or msg.get('message', {}).get('role') == 'user':
        return 'user'
    if msg.get('type') == 'assistant' or msg.get('message', {}).get('role') == 'assistant':
        return 'assistant'
    return None


def format_conversation(messages, project_name):
    """Convert conversation to Markdown"""
    md = f"# {project_name}\n\n"

    # Session info
    session_id = next((m.get('sessionId') for m in messages if m.get('sessionId')), None)
    first_ts = None
    for msg in messages:
        if ts := msg.get('timestamp'):
            try:
                first_ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                break
            except:
                pass

    if session_id:
        md += f"> Session: `{session_id[:8]}...`\n"
    if first_ts:
        md += f"> Started: {first_ts.strftime('%Y-%m-%d %H:%M')}\n"
    md += "\n---\n\n"

    # Group messages (merge consecutive responses)
    groups = []
    current = {'role': None, 'time': None, 'texts': []}

    for msg in messages:
        if msg.get('isMeta'):
            continue

        role = get_role(msg)
        if not role:
            continue

        content = msg.get('message', {}).get('content', '')
        text = extract_text(content)

        # Skip internal content
        if not text or text.startswith(('<local-command', '<command-name>')):
            continue

        # Timestamp
        time_str = ""
        if ts := msg.get('timestamp'):
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                time_str = dt.strftime("%H:%M")
            except:
                pass

        # Save on role change
        if role != current['role'] and current['texts']:
            groups.append(current.copy())
            current = {'role': None, 'time': None, 'texts': []}

        current['role'] = role
        if not current['time']:
            current['time'] = time_str
        if text.strip():
            current['texts'].append(text.strip())

        # Reset after user message
        if role == 'user' and current['texts']:
            groups.append(current.copy())
            current = {'role': None, 'time': None, 'texts': []}

    if current['texts']:
        groups.append(current)

    # Generate Markdown
    for g in groups:
        text = '\n\n'.join(g['texts'])
        if len(text) > 10000:
            text = text[:10000] + "\n\n> [Truncated due to length]"

        if g['role'] == 'user':
            md += f"## 🧑 User ({g['time']})\n\n"
            for line in text.split('\n'):
                md += f"> {line}\n"
            md += "\n---\n\n"
        else:
            md += f"## 🤖 Claude ({g['time']})\n\n{text}\n\n---\n\n"

    return md


def process_sessions(projects_dir, output_dir, incremental=False, silent=False):
    """Process all sessions"""
    import shutil

    if not incremental and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stats = defaultdict(lambda: {'sessions': 0, 'messages': 0, 'files': []})
    processed = 0
    skipped = 0

    for project_folder in projects_dir.iterdir():
        if not project_folder.is_dir():
            continue

        for session_file in project_folder.glob("*.jsonl"):
            if session_file.stat().st_size < 1000:
                continue

            try:
                messages = load_session(session_file)
                if not messages:
                    continue

                project_name = sanitize_name(get_project_name(messages))

                # First timestamp
                first_ts = None
                for msg in messages:
                    if ts := msg.get('timestamp'):
                        try:
                            first_ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            break
                        except:
                            pass

                if not first_ts:
                    continue

                # Output path
                project_out = output_dir / project_name
                project_out.mkdir(parents=True, exist_ok=True)

                # Generate filename with title
                date_str = first_ts.strftime('%Y-%m-%d')
                title = extract_session_title(messages)
                if title:
                    filename = f"{date_str}_{title}.md"
                else:
                    filename = f"{date_str}_{session_file.stem[:8]}.md"
                out_file = project_out / filename

                # Skip existing in incremental mode
                if incremental and out_file.exists():
                    skipped += 1
                    continue

                out_file.write_text(format_conversation(messages, project_name), encoding='utf-8')

                stats[project_name]['sessions'] += 1
                stats[project_name]['messages'] += len(messages)
                stats[project_name]['files'].append(filename)
                processed += 1

            except Exception as e:
                if not silent:
                    print(f"Error: {session_file.name}: {e}", file=sys.stderr)

    # Generate index files
    for name, s in stats.items():
        if s['sessions'] == 0:
            continue
        project_out = output_dir / name
        index_file = project_out / "_INDEX.md"

        # Load existing files in incremental mode
        existing_files = []
        if incremental and index_file.exists():
            content = index_file.read_text(encoding='utf-8')
            existing_files = re.findall(r'\[\[(.+?)\]\]', content)

        all_files = list(set(existing_files + s['files']))

        content = f"# {name}\n\n"
        content += f"**Sessions:** {len(all_files)}\n\n"
        content += "## Session List\n\n"
        for f in sorted(all_files, reverse=True):
            f_clean = f.replace('.md', '')
            content += f"- [[{f_clean}]]\n"
        index_file.write_text(content, encoding='utf-8')

    # Generate summary
    summary_file = output_dir / "_SUMMARY.md"

    all_projects = {}
    for proj_dir in output_dir.iterdir():
        if proj_dir.is_dir() and not proj_dir.name.startswith('_'):
            session_count = len(list(proj_dir.glob("*.md"))) - 1
            if session_count > 0:
                all_projects[proj_dir.name] = session_count

    content = "# Claude Code Backup\n\n"
    content += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    content += f"**Projects:** {len(all_projects)} | **Sessions:** {sum(all_projects.values())}\n\n"
    content += "| Project | Sessions |\n|---|---|\n"
    for name, count in sorted(all_projects.items(), key=lambda x: -x[1]):
        content += f"| [[{name}/_INDEX\\|{name}]] | {count} |\n"
    summary_file.write_text(content, encoding='utf-8')

    return processed, skipped, len(all_projects)


def main():
    parser = argparse.ArgumentParser(
        description='Backup Claude Code conversations to Markdown',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backup.py                    # Full backup
  python backup.py -i                 # Incremental backup
  python backup.py --output ~/backup  # Custom output
        """
    )
    parser.add_argument(
        '--projects', type=Path, default=DEFAULT_PROJECTS_DIR,
        help=f'Claude projects folder (default: {DEFAULT_PROJECTS_DIR})'
    )
    parser.add_argument(
        '--output', type=Path, default=DEFAULT_OUTPUT_DIR,
        help=f'Output folder (default: {DEFAULT_OUTPUT_DIR})'
    )
    parser.add_argument(
        '--incremental', '-i', action='store_true',
        help='Incremental backup (new sessions only)'
    )
    parser.add_argument(
        '--silent', '-s', action='store_true',
        help='Suppress output messages'
    )

    args = parser.parse_args()

    if not args.projects.exists():
        if not args.silent:
            print(f"Error: Projects folder not found: {args.projects}", file=sys.stderr)
        return 1

    mode = "Incremental" if args.incremental else "Full"
    if not args.silent:
        print(f"Starting {mode.lower()} backup...")
        print(f"  Source: {args.projects}")
        print(f"  Output: {args.output}")

    processed, skipped, total_projects = process_sessions(
        args.projects, args.output, args.incremental, args.silent
    )

    if not args.silent:
        print(f"\nDone!")
        print(f"  Processed: {processed} sessions")
        if skipped:
            print(f"  Skipped: {skipped} (already exist)")
        print(f"  Projects: {total_projects}")
        print(f"  Output: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
