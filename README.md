# obsidian-social

Codex skill for saving Xiaohongshu, Douyin, and WeChat public links into Obsidian source notes.

[中文说明](README.zh-CN.md)

## Security Scan

Latest public repo scan:

- Tool: SkillSpector `2.2.3`
- Target: `https://github.com/cindyxu1030/obsidian-social`
- Mode: static scan, `--no-llm`
- Result: `SAFE`
- Severity: `LOW`
- Score: `19/100`
- Date: `2026-06-22`

Remaining notes: SkillSpector flags the transcription script's `subprocess.run` call because it invokes external commands. The script uses `shell=False` and a command allowlist limited to `ffmpeg` and `whisper`. SkillSpector also flags standard MIT License wording as a low-risk scope-creep false positive.

## Install

Ask Codex to install:

```text
Install https://github.com/cindyxu1030/obsidian-social/tree/main/obsidian-social
```

Or run the bundled Codex installer directly:

```bash
python3 "$HOME/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo cindyxu1030/obsidian-social \
  --path obsidian-social
```

Then restart Codex so the skill list refreshes.

## What One Install Includes

The skill install includes the importer, note template, platform extraction logic, and local transcription workflow.

It does not install native transcription dependencies. Article import and metadata capture work without them, but video transcription requires:

- `ffmpeg`
- OpenAI Whisper CLI, available as the `whisper` command

Check the current machine:

```bash
python3 "$HOME/.codex/skills/obsidian-social/scripts/download_and_transcribe.py" --check-deps
```

Common macOS setup:

```bash
brew install ffmpeg
python3 -m pip install -U openai-whisper
```

The `whisper` command here means OpenAI's local Whisper CLI, not the Wispr dictation app.

## Defaults

- Vault: `~/Documents/Obsidian Vault`
- Output folder: `02-Sources`
- Media cache: `~/.cache/obsidian-social`
- ASR: local Whisper only, when `ffmpeg` and `whisper` are installed

Useful overrides:

```bash
export OBSIDIAN_VAULT_PATH="/path/to/your/vault"
export OBSIDIAN_SOURCE_DIR="02-Sources"
export OBSIDIAN_SOCIAL_CACHE_DIR="$HOME/.cache/obsidian-social"
```

## Scope

This skill captures public/social source material for research notes. It does not publish, automate engagement, bypass login walls, export browser credentials, or use third-party ASR APIs by default.
