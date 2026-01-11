---
name: backup
description: This skill backs up Claude Code conversation history to organized Markdown files. Use this skill when users want to backup their conversations, save chat history, export sessions, or preserve their dialogue with Claude. Responds to /backup command and phrases like "backup my conversations", "save chat history", "export sessions", etc.
---

# Backup

## Overview

This skill converts Claude Code session history from `.claude/projects/` into readable Markdown files, organized by project and session date. It preserves the complete conversation including tool calls, timestamps, and message flow.

## First Run Setup

On first use, check if configuration exists at the skill's base directory (`config.json`). If not, ask the user:

1. **Output path**: "Where should backup files be saved? (default: ~/claude-backup)"
2. **Language**: "Which language for output? (English / 한국어)"

Save configuration to `{skill_base_dir}/config.json`:
```json
{
  "output_path": "~/claude-backup",
  "language": "en"
}
```

## Workflow

### Step 1: Check Configuration

```
Read {skill_base_dir}/config.json
If not exists → Run First Run Setup
```

### Step 2: Execute Backup

Based on user request, run the appropriate command:

| User Request | Command |
|-------------|---------|
| `/backup` | Incremental backup (new sessions only) |
| `/backup --full` | Full backup (regenerate all) |
| `/backup -i` | Same as `/backup` |
| `/backup --output <path>` | Custom output path |

**Execution:**
```bash
# Windows (if encoding issues occur)
PYTHONIOENCODING=utf-8 python "{skill_base_dir}/scripts/backup.py" --incremental --output "{output_path}"

# Mac/Linux
python "{skill_base_dir}/scripts/backup.py" --incremental --output "{output_path}"
```

### Step 3: Report Results

After execution, report to user:

**English:**
```
✅ Backup complete!
   Processed: {n} sessions
   Skipped: {n} (already exist)
   Projects: {n}
📁 Output: {output_path}
```

**한국어:**
```
✅ 백업 완료!
   처리: {n}개 세션
   스킵: {n}개 (이미 존재)
   프로젝트: {n}개
📁 결과: {output_path}
```

## Output Structure

```
claude-backup/
├── _SUMMARY.md                        # Overview of all projects
├── my-project/
│   ├── _INDEX.md                      # Project session list (Obsidian wikilinks)
│   ├── 2025-01-10_Implement login.md  # Session file (title from first message)
│   └── 2025-01-11_Fix bug in API.md
└── another-project/
    └── ...
```

### Filename Format

Session filenames are auto-generated from the first user message:

| First Message | Filename |
|---------------|----------|
| "Implement login feature" | `2025-01-10_Implement login feature.md` |
| `https://github.com/user/repo` | `2025-01-10_GitHub repo.md` |
| `C:\path\to\file.py` | `2025-01-10_file.md` |
| (command only) | `2025-01-10_a1b2c3d4.md` (fallback to session ID) |

## Session File Format

Each session is saved in this format:

```markdown
# Project Name

> Session: `a1b2c3d4...`
> Started: 2025-01-10 14:30

---

## 🧑 User (14:30)

> User message here

---

## 🤖 Claude (14:31)

Claude's response here

`📁 Read: src/main.py`
`🔧 npm install`

---
```

### Tool Icons

| Icon | Tools |
|------|-------|
| 📁 | Read, Write, Edit, Glob, Grep |
| 🔧 | Bash |
| 🌐 | WebSearch, WebFetch |
| 📝 | TodoWrite |
| 🤖 | Task Agent |
| ⚙️ | Other tools |

## Automation Options

When users ask about automation, suggest:

### Option 1: Task Scheduler / cron

**Windows:**
```powershell
schtasks /create /tn "Claude Backup" /tr "python {script_path} -i" /sc daily /st 00:00
```

**Mac/Linux:**
```bash
# crontab -e
0 0 * * * python3 {script_path} -i
```

### Option 2: Pre-clear Hook

Add to `~/.claude/settings.json`:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "clear",
        "command": "python {script_path} -i --silent"
      }
    ]
  }
}
```

## Troubleshooting

### "Projects folder not found"
Claude Code must have been used at least once. Check:
```bash
ls ~/.claude/projects/
```

### Windows encoding error
Use UTF-8 encoding:
```bash
set PYTHONIOENCODING=utf-8 && python {script_path} -i
```

### Permission error
Check write permissions on output folder.

## Resources

### scripts/backup.py

The main backup script that:
- Reads session files from `~/.claude/projects/`
- Converts JSONL to Markdown
- Groups consecutive Claude responses
- Generates project indexes with Obsidian wikilinks
- Supports incremental backup mode
