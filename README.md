# obsidian-social

Codex skill for saving Xiaohongshu, Douyin, and WeChat public links into Obsidian source notes.

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

## Defaults

- Vault: `~/Documents/Obsidian Vault`
- Output folder: `02-Sources`
- Media cache: `~/.cache/obsidian-social`
- ASR: local Whisper only

Useful overrides:

```bash
export OBSIDIAN_VAULT_PATH="/path/to/your/vault"
export OBSIDIAN_SOURCE_DIR="02-Sources"
export OBSIDIAN_SOCIAL_CACHE_DIR="$HOME/.cache/obsidian-social"
```

## Scope

This skill captures public/social source material for research notes. It does not publish, automate engagement, bypass login walls, export browser credentials, or use third-party ASR APIs by default.
