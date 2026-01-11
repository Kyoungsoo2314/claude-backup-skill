#!/usr/bin/env python3
"""
Claude Code 대화 백업 스크립트 (범용 버전)

사용법:
    python backup_claude_conversations.py
    python backup_claude_conversations.py --output ./backup
    python backup_claude_conversations.py --projects ~/.claude/projects --output ~/claude-backup
"""

import json
import os
import re
import sys
import argparse
from datetime import datetime
from collections import defaultdict
from pathlib import Path


def safe_print(msg):
    """Windows cp949 인코딩에서도 안전하게 출력"""
    try:
        print(msg)
    except UnicodeEncodeError:
        # 이모지를 ASCII로 대체
        safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
        print(safe_msg)

# ============ 기본 설정 ============
DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
DEFAULT_OUTPUT_DIR = Path.home() / "claude-backup"
# ==================================


def get_project_name(messages):
    """세션에서 프로젝트명 추출"""
    for msg in messages:
        cwd = msg.get('cwd', '')
        if not cwd:
            continue

        parts = Path(cwd).parts

        # 숫자로 시작하는 폴더 찾기 (예: "017 - 연차장부")
        for part in reversed(parts):
            if re.match(r'^\d{2,3}\s*[-]', part):
                return part

        # 홈 디렉토리가 아닌 마지막 유의미한 폴더
        home_name = Path.home().name
        skip_names = {'Users', 'home', home_name, 'Documents', 'Desktop', ''}
        for part in reversed(parts):
            if part and part not in skip_names:
                return part

    return "00-기타"


def sanitize_name(name):
    """폴더명에서 특수문자 제거"""
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()[:60]


def clean_title_text(text):
    """텍스트를 깨끗한 제목으로 변환"""
    if not text:
        return None

    # 0. 먼저 줄바꿈을 공백으로 변환 (모든 처리 전에)
    text = text.replace('\n', ' ').replace('\r', ' ')

    # 1. URL 처리 - 도메인만 추출
    url_match = re.match(r'https?://(?:www\.)?([^/\s]+)', text)
    if url_match and text.strip().startswith('http'):
        domain = url_match.group(1)
        # github.com/user/repo 형태면 repo명 추출
        repo_match = re.search(r'github\.com/[^/]+/([^/\s]+)', text)
        if repo_match:
            return f"GitHub {repo_match.group(1)[:20]}"
        return f"웹 {domain[:20]}"

    # 2. 파일 경로 처리 - 파일명만 추출
    first_line = text.split()[0] if text.split() else text
    if re.match(r'^[A-Za-z]:[/\\]|^[/\\]|^~[/\\]', first_line) or '\\' in first_line[:30]:
        # 파일명 추출 (첫 번째 단어만 사용)
        path_parts = re.split(r'[/\\]', first_line)
        filename = next((p for p in reversed(path_parts) if p and not p.endswith(':')), None)
        if filename:
            # 확장자 제거하고 파일명만
            name = re.sub(r'\.[^.]+$', '', filename)
            # 파일명 안전 문자만
            name = re.sub(r'[<>:"/\\|?*\n\r]', '', name)
            if len(name) >= 3:
                return name[:25]

    # 3. 명령어/시스템 텍스트 제거
    text = re.sub(r'<[^>]+>[^<]*</[^>]+>', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'^(Base directory|Skill instructions|You are).*', '', text, flags=re.IGNORECASE)

    # 4. 공백 정리
    text = ' '.join(text.split())

    if not text.strip() or len(text.strip()) < 3:
        return None

    # 5. 특수문자 제거 및 길이 제한 (파일명에 사용 불가능한 모든 문자)
    title = re.sub(r'[<>:"/\\|?*\n\r\t]', '', text)[:30].strip()

    # 6. 마침표로 끝나면 제거
    title = title.rstrip('.')

    return title if len(title) >= 3 else None


def get_session_title(messages):
    """사용자 메시지에서 세션 제목 추출 (여러 메시지 시도)"""
    user_texts = []

    for msg in messages:
        if msg.get('type') == 'user' or msg.get('message', {}).get('role') == 'user':
            content = msg.get('message', {}).get('content', '')

            # 텍스트 추출
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = ' '.join(
                    item.get('text', '')
                    for item in content
                    if isinstance(item, dict) and item.get('type') == 'text'
                )
            else:
                continue

            if text.strip():
                user_texts.append(text.strip())

            # 최대 3개 메시지까지만 수집
            if len(user_texts) >= 3:
                break

    # 각 메시지에서 제목 추출 시도
    for text in user_texts:
        title = clean_title_text(text)
        if title:
            return title

    return None


def load_session(filepath):
    """세션 파일 로드"""
    messages = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                messages.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    return messages


def extract_text(content):
    """메시지에서 텍스트 추출"""
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

                    # 도구별 아이콘
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
    """메시지 역할 판별"""
    if msg.get('type') == 'user' or msg.get('message', {}).get('role') == 'user':
        return 'user'
    if msg.get('type') == 'assistant' or msg.get('message', {}).get('role') == 'assistant':
        return 'assistant'
    return None


def format_conversation(messages, project_name):
    """대화를 마크다운으로 변환"""
    md = f"# {project_name}\n\n"

    # 세션 정보
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
        md += f"> 세션: `{session_id[:8]}...`\n"
    if first_ts:
        md += f"> 시작: {first_ts.strftime('%Y-%m-%d %H:%M')}\n"
    md += "\n---\n\n"

    # 메시지 그룹화 (연속 응답 합치기)
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

        # 스킵할 내용
        if not text or text.startswith(('<local-command', '<command-name>')):
            continue

        # 타임스탬프
        time_str = ""
        if ts := msg.get('timestamp'):
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                time_str = dt.strftime("%H:%M")
            except:
                pass

        # 역할 변경시 저장
        if role != current['role'] and current['texts']:
            groups.append(current.copy())
            current = {'role': None, 'time': None, 'texts': []}

        current['role'] = role
        if not current['time']:
            current['time'] = time_str
        if text.strip():
            current['texts'].append(text.strip())

        # User 후 리셋
        if role == 'user' and current['texts']:
            groups.append(current.copy())
            current = {'role': None, 'time': None, 'texts': []}

    if current['texts']:
        groups.append(current)

    # 마크다운 생성
    for g in groups:
        text = '\n\n'.join(g['texts'])
        if len(text) > 10000:
            text = text[:10000] + "\n\n> [길이 초과로 생략됨]"

        if g['role'] == 'user':
            md += f"## 🧑 User ({g['time']})\n\n"
            for line in text.split('\n'):
                md += f"> {line}\n"
            md += "\n---\n\n"
        else:
            md += f"## 🤖 Claude ({g['time']})\n\n{text}\n\n---\n\n"

    return md


def process_sessions(projects_dir, output_dir, incremental=False):
    """모든 세션 처리"""
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

                # 첫 타임스탬프
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

                # 출력 경로
                project_out = output_dir / project_name
                project_out.mkdir(parents=True, exist_ok=True)

                # 세션 제목 추출 (없으면 세션ID 사용)
                session_title = get_session_title(messages)
                if session_title:
                    filename = f"{first_ts.strftime('%Y-%m-%d')}_{session_title}.md"
                else:
                    filename = f"{first_ts.strftime('%Y-%m-%d')}_{session_file.stem[:8]}.md"

                out_file = project_out / filename

                # 증분 모드: 같은 날짜+제목 또는 같은 세션ID 파일이 있으면 스킵
                if incremental:
                    # 같은 파일이 있으면 스킵
                    if out_file.exists():
                        skipped += 1
                        continue
                    # 같은 세션ID로 된 기존 파일이 있으면 스킵
                    old_style = project_out / f"{first_ts.strftime('%Y-%m-%d')}_{session_file.stem[:8]}.md"
                    if old_style.exists():
                        skipped += 1
                        continue

                out_file.write_text(format_conversation(messages, project_name), encoding='utf-8')

                stats[project_name]['sessions'] += 1
                stats[project_name]['messages'] += len(messages)
                stats[project_name]['files'].append(filename)
                processed += 1

            except Exception as e:
                safe_print(f"[X] {session_file.name}: {e}")

    # 인덱스 생성
    for name, s in stats.items():
        if s['sessions'] == 0:
            continue
        project_out = output_dir / name
        index_file = project_out / "_INDEX.md"

        # 기존 파일 목록 로드 (증분 모드)
        existing_files = []
        if incremental and index_file.exists():
            content = index_file.read_text(encoding='utf-8')
            existing_files = re.findall(r'\[\[(.+?)\]\]', content)

        all_files = list(set(existing_files + s['files']))

        content = f"# {name}\n\n"
        content += f"**세션:** {len(all_files)}개\n\n"
        content += "## 세션 목록\n\n"
        for f in sorted(all_files, reverse=True):
            f_clean = f.replace('.md', '')
            content += f"- [[{f_clean}]]\n"
        index_file.write_text(content, encoding='utf-8')

    # 전체 요약
    summary_file = output_dir / "_전체요약.md"

    # 모든 프로젝트 폴더 스캔
    all_projects = {}
    for proj_dir in output_dir.iterdir():
        if proj_dir.is_dir() and not proj_dir.name.startswith('_'):
            session_count = len(list(proj_dir.glob("*.md"))) - 1  # _INDEX.md 제외
            if session_count > 0:
                all_projects[proj_dir.name] = session_count

    content = "# Claude Code 대화 백업\n\n"
    content += f"**생성일:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    content += f"**프로젝트:** {len(all_projects)}개 | **세션:** {sum(all_projects.values())}개\n\n"
    content += "| 프로젝트 | 세션 |\n|---|---|\n"
    for name, count in sorted(all_projects.items(), key=lambda x: -x[1]):
        content += f"| [[{name}/_INDEX\\|{name}]] | {count} |\n"
    summary_file.write_text(content, encoding='utf-8')

    return processed, skipped, len(all_projects)


def main():
    parser = argparse.ArgumentParser(
        description='Claude Code 대화를 마크다운으로 백업',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python backup_claude_conversations.py
  python backup_claude_conversations.py --output ./my-backup
  python backup_claude_conversations.py --incremental
        """
    )
    parser.add_argument(
        '--projects', type=Path, default=DEFAULT_PROJECTS_DIR,
        help=f'Claude 프로젝트 폴더 (기본값: {DEFAULT_PROJECTS_DIR})'
    )
    parser.add_argument(
        '--output', type=Path, default=DEFAULT_OUTPUT_DIR,
        help=f'출력 폴더 (기본값: {DEFAULT_OUTPUT_DIR})'
    )
    parser.add_argument(
        '--incremental', '-i', action='store_true',
        help='증분 백업 (새 세션만 추가)'
    )

    args = parser.parse_args()

    if not args.projects.exists():
        safe_print(f"[X] 프로젝트 폴더를 찾을 수 없습니다: {args.projects}")
        return 1

    mode = "증분" if args.incremental else "전체"
    safe_print(f"[*] {mode} 백업 시작...")
    safe_print(f"    소스: {args.projects}")
    safe_print(f"    대상: {args.output}")

    processed, skipped, total_projects = process_sessions(
        args.projects, args.output, args.incremental
    )

    safe_print(f"\n[OK] 완료!")
    safe_print(f"     처리: {processed}개 세션")
    if skipped:
        safe_print(f"     스킵: {skipped}개 (이미 존재)")
    safe_print(f"     프로젝트: {total_projects}개")
    safe_print(f"[->] 결과: {args.output}")

    return 0


if __name__ == "__main__":
    exit(main())
