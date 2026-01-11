# claude-backup-skill

Claude Code 대화 기록을 마크다운으로 백업하는 스킬입니다.

A Claude Code skill that backs up your conversation history to organized Markdown files.

## Features

- **Project-based organization**: Auto-categorizes by working directory
- **Session files**: `YYYY-MM-DD_sessionID.md` format
- **Merged responses**: Consecutive Claude responses combined into one block
- **Tool call display**: Inline backticks with icons (📁 🔧 🌐)
- **Incremental backup**: Only new sessions option
- **Obsidian compatible**: Wikilinks and index files
- **Bilingual**: English / 한국어

## Installation

```bash
# Clone to Claude Code skills folder
git clone https://github.com/Kyoungsoo2314/claude-backup-skill.git ~/.claude/skills/backup

# Or download and copy
cp -r backup ~/.claude/skills/
```

## Usage

In Claude Code:

```bash
/backup              # Incremental backup (new sessions only)
/backup --full       # Full backup (regenerate all)
/backup --output ~/my-backup   # Custom output path
```

## First Run

On first use, Claude will ask:

1. **Output path**: Where to save backup files (default: `~/claude-backup`)
2. **Language**: English or 한국어

Settings are saved to `config.json`.

## Output Structure

```
claude-backup/
├── _SUMMARY.md                 # Overview
├── my-project/
│   ├── _INDEX.md               # Session list (Obsidian wikilinks)
│   ├── 2025-01-10_a1b2c3d4.md
│   └── 2025-01-11_e5f6g7h8.md
└── another-project/
    └── ...
```

## Output Format

```markdown
# Project Name

> Session: `a1b2c3d4...`
> Started: 2025-01-10 14:30

---

## 🧑 User (14:30)

> User message

---

## 🤖 Claude (14:31)

Claude's response

`📁 Read: src/main.py`
`🔧 npm install`

---
```

## Tool Icons

| Icon | Tools |
|------|-------|
| 📁 | Read, Write, Edit, Glob, Grep |
| 🔧 | Bash |
| 🌐 | WebSearch, WebFetch |
| 📝 | TodoWrite |
| 🤖 | Task Agent |
| ⚙️ | Other tools |

## Automation

### Daily backup (Task Scheduler / cron)

**Windows:**
```powershell
schtasks /create /tn "Claude Backup" /tr "python ~/.claude/skills/backup/scripts/backup.py -i" /sc daily /st 00:00
```

**Mac/Linux:**
```bash
0 0 * * * python3 ~/.claude/skills/backup/scripts/backup.py -i
```

### Pre-clear hook

Add to `~/.claude/settings.json`:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "clear",
        "command": "python ~/.claude/skills/backup/scripts/backup.py -i --silent"
      }
    ]
  }
}
```

## Requirements

- Python 3.8+
- Claude Code with usage history

## Troubleshooting

### Windows encoding error
```bash
set PYTHONIOENCODING=utf-8 && python backup.py -i
```

### Projects folder not found
```bash
ls ~/.claude/projects/
```

## License

MIT License

## Contributing

Issues and PRs welcome!
