---
name: obsidian-social
description: Use when a user gives a 小红书, 抖音, or 微信公众号 URL and wants it captured into Obsidian 02-Sources with title, source link, post copy, video link when discoverable, and a transcript section for local research notes.
allowed-tools:
  - Read
  - Write
  - Bash
permissions:
  - env
  - network
  - Read public web pages or explicit saved HTML files supplied by the user.
  - Read OBSIDIAN_VAULT_PATH, OBSIDIAN_SOURCE_DIR, and OBSIDIAN_SOCIAL_CACHE_DIR environment variables when present.
  - Write Markdown source notes under the configured Obsidian vault.
  - Run bundled Python scripts from this skill.
  - Download discovered media into the configured local cache directory.
  - Invoke only ffmpeg and whisper from the transcription script's command allowlist.
metadata:
  permissions:
    - Use network access for public web pages and explicit user-provided media URLs.
    - Read optional environment variables for vault, source-folder, and cache configuration.
    - Read public web pages or explicit saved HTML files.
    - Write Markdown source notes under the configured Obsidian vault.
    - Run the bundled local importer script.
---

# Obsidian Social

## Overview

Import social-platform source material into an Obsidian vault using a clean source-note shape: frontmatter, original link, text/copy, media links, and transcript when available.

This skill is for source capture, not publishing automation. Never bypass login walls, captchas, rate limits, or platform controls; do not store private browser/account data, caches, or temporary logs in the vault.

GitHub repos for similar tools are review-only references. Do not install, clone, run, or vendor code from a repo into this workflow unless the user explicitly asks for that repo to be installed after a safety review. Borrow patterns by re-implementing the needed idea inside this skill.

## When To Use

Use this skill when the user asks to:

- Save a 小红书, 抖音, or 微信公众号 link into Obsidian sources.
- Import Chinese social content for later script, research, or swipe-file work.
- Convert a WeChat article into a clean source note.
- Preserve video post title, caption, source URL, video URL if available, and transcript text.

## Workflow

1. If the user gave only a URL, run the importer:

   ```bash
   SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/obsidian-social"
   python3 "$SKILL_DIR/scripts/import_source.py" "URL"
   ```

   By default, notes are written to `~/Documents/Obsidian Vault/02-Sources`. To use a different vault, pass `--vault "/path/to/vault"` or set `OBSIDIAN_VAULT_PATH`.

2. If the user already has a transcript, pass it in instead of re-transcribing:

   ```bash
   SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/obsidian-social"
   python3 "$SKILL_DIR/scripts/import_source.py" "URL" --transcript-file /path/to/transcript.txt
   ```

3. If a page needs a browser session and server-side fetching fails, save the page HTML from a logged-in browser session and pass it explicitly:

   ```bash
   SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/obsidian-social"
   python3 "$SKILL_DIR/scripts/import_source.py" "URL" --html-file /path/to/page.html
   ```

4. For video notes where a `video_url` is present, download and transcribe into the same note:

   Video transcription needs `ffmpeg` and OpenAI's local Whisper CLI (`whisper`) installed on the user's machine. Article import and metadata capture still work without these dependencies. To check:

   ```bash
   SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/obsidian-social"
   python3 "$SKILL_DIR/scripts/download_and_transcribe.py" --check-deps
   ```

   ```bash
   SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/obsidian-social"
   python3 "$SKILL_DIR/scripts/download_and_transcribe.py" --note /path/to/source-note.md
   ```

   Default model selection is `--model auto`: it checks CPU threads, total memory, and current 1-minute CPU load. It selects `small` on stronger idle machines, `base` for normal use, and `tiny` when resources are constrained. Use `--model small` to force higher quality, or `--print-model-decision` to see what auto would choose without transcribing. The script includes a default AI-domain prompt; override it with `--initial-prompt` for other topics. Treat local ASR as rough until reviewed.

   Use local Whisper as the default and preferred ASR path. Do not add or configure third-party ASR APIs such as DashScope, Doubao/Volcengine, Tencent, OpenAI Audio, Deepgram, or AssemblyAI unless the user explicitly asks for an API-based transcription path later.

   If the ASR is hard to read, do not silently "fix" it into a fake verbatim transcript. Add a `## Cleaned Transcript` section that is explicitly labeled as a readable, caption/context-based cleanup, and keep the raw output under `## Transcript (rough ASR)` for traceability.

5. If the direct video URL is missing, expires, downloads as `403`, or the page only exposes a `blob:` stream, use Chrome Browser Use before giving up:

   - Ask the user to open the original video in Chrome if it is not already open.
   - Use the Chrome browser skill to claim the existing tab. Keep the inspection read-only.
   - Read page metadata, visible caption text, platform-generated chapter summaries, and any actual subtitle tracks (`<track>`, `video.textTracks`) if present.
   - Inspect the first real video element. If `video.currentSrc` is an `https` URL with `video_mp4`, `mime_type=video_mp4`, `.mp4`, or another clear playable media signal, treat it as a temporary browser-discovered URL and transcribe with:

     ```bash
     SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/obsidian-social"
     python3 "$SKILL_DIR/scripts/download_and_transcribe.py" --note /path/to/source-note.md --video-url "BROWSER_CURRENT_SRC" --source-url "CANONICAL_PAGE_URL"
     ```

   - Browser-discovered media URLs are usually signed and temporary. Use them for cache + ASR only; do not treat them as durable source links.
   - If Chrome exposes real subtitles, write them under `## Transcript` and mark the source. If it only exposes platform AI chapters/summaries, write those under `## Platform AI Summary`, keep `transcription_status: pending`, and say they are not a transcript.
   - Limit Chrome fallback to visible page metadata, subtitle tracks, platform summaries, and media element URLs. Private browser/account data is outside scope.

6. Read the JSON result from the script. Report the created note path, platform, title, transcript status, and any warnings. If the transcript is pending after Chrome fallback too, say that plainly; do not invent one.

## Output Contract

Default vault target:

- 小红书: `02-Sources/XHS/`
- 抖音: `02-Sources/Douyin/`
- 微信公众号: `02-Sources/WeChat/`

Each note should follow this shape:

```markdown
---
title: "..."
source: "..."
platform: "xiaohongshu"
author:
  - "..."
published: "YYYY-MM-DD"
created: "YYYY-MM-DD"
description: "..."
tags:
  - "clippings"
  - "source/social"
---

[Open original](...)

## Text

...

## Media

- Source: ...
- Video: ...

## Cleaned Transcript

> Caption/context-based readable version when ASR is rough. Not a verified verbatim transcript.

...

## Transcript

Verified transcript, user-supplied transcript, or platform-provided transcript.

## Transcript (rough ASR)

...
```

For WeChat articles, the article body belongs under `## Text`; a `## Transcript` section is only needed when the user supplied one.

## Platform Notes

Read `references/platform-notes.md` before changing extraction behavior. Current principles:

- WeChat public articles are usually text-first and can often be captured from page HTML.
- 小红书 exposes useful post metadata in initial page state when the public web page is available. If the page blocks public fetches, use `--html-file` from a browser session rather than storing cookies in the skill or vault.
- 抖音 frequently protects video media URLs. Capture the source link and text first; add `--video-url` or `--transcript-file` when browser extraction or ASR output is available.
- When 抖音 or 小红书 direct transcription fails but the user has the video open in Chrome, use Chrome Browser Use to read `video.currentSrc`, real subtitle tracks, and visible platform summaries before marking the transcript pending.
- Keep platform as a first-class field. Do not merge 小红书 and 抖音 into one vague "short video" bucket.

## Cache Debug Log

A cache debug log is an optional local diagnostic record for failed or confusing imports. It is not a lock file, database, source note, or transcript.

If implemented, keep it under the local media cache directory. It may record non-sensitive facts such as platform, canonical URL, extraction method tried, selected Whisper model, cache file paths, and failure reason. Keep private account/browser data, raw HTML dumps, and secrets out of it. It is safe to delete and should never be copied into Obsidian.

## Safety Rules

- Do not directly install, clone, run, or vendor code from GitHub repos reviewed for inspiration. Treat them as references only unless the user explicitly approves installation after review.
- Prefer the bundled local Whisper workflow for ASR. Do not wire in external ASR providers or API keys by default.
- Whole-browser account-data export is outside this workflow.
- Do not copy private account/browser data, raw page dumps, downloaded video files, or temporary logs into Obsidian.
- Downloaded videos and extracted audio should stay in the local cache directory, not inside the vault, unless the user explicitly asks for media archiving. The script does not delete cache files by default. Use `--delete-media-after-transcribe` only when the local media cache is no longer needed.
- Do not claim a transcript exists unless it came from the page, a transcript file, or a verified ASR run.
- Mark generated ASR as rough/unreviewed unless a human has checked it against the video. Rough ASR belongs under `## Transcript (rough ASR)`, not plain `## Transcript`.
- When rough ASR is unreadable but the post caption is useful, create `## Cleaned Transcript` as a readable working version and state that it is not verbatim.
- Chrome fallback is allowed for the user's already-open video pages, but only as read-only page inspection and temporary media extraction. Never use it to copy credentials or bypass platform controls.
- If extraction fails, create a clean source note only when there is enough title/link/context to be useful; otherwise ask for a saved HTML file or transcript.
