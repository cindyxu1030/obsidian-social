# Platform notes

These notes capture the useful logic from the reviewed repos without adopting their unsafe defaults.

Reviewed GitHub repos are references only. Do not install, clone, run, or vendor repo code into this workflow unless the user explicitly approves installation after a safety review. Borrow the useful pattern and re-implement it inside this skill.

## Shared output pattern

The target is a clean Obsidian source-note style in `02-Sources`: YAML frontmatter, original source link, readable text, media links, then transcript when available.

The importer writes source notes only. It does not publish, like, comment, bypass login walls, or run account actions.

## 小红书

Useful extraction pattern:

- Resolve share links such as `xhslink.com` to their final `xiaohongshu.com` URL.
- Prefer the public page HTML. When available, parse `window.__INITIAL_STATE__`.
- Note records often contain a `noteDetailMap`; the useful object is commonly under a nested `note` key.
- Useful fields include `title`, `desc`, `type`, `time`, `user.nickname`, `imageList`, and `video.media.stream`.
- For video, prefer h264 stream URLs when present, then h265, then av1.

Safety decision:

- Do not make whole-browser account-data export the default.
- If public fetching fails, use an explicit saved HTML file from the user's browser session, or create a source shell with the real URL and transcript pending.

## 抖音

Useful extraction pattern:

- Resolve short links such as `v.douyin.com`.
- Parse normal metadata first: title, description, author, canonical URL.
- Search hydrated JSON and page text for playable media candidates, but expect anti-hotlinking and expiring URLs.
- If the media URL is not reliable, preserve the real source URL and allow a later `--video-url` or `--transcript-file`.
- If public fetching fails and the user has the video open in Chrome, use Chrome Browser Use as the next step. Claim the existing tab, read `video.currentSrc`, `<track>` / `video.textTracks`, visible captions, and platform AI summaries. A signed `video.currentSrc` can be used immediately with `download_and_transcribe.py --video-url`, but it should not be saved as the durable source URL.

Safety decision:

- Do not promise server-side direct video download. Browser-context capture or user-provided transcript is often more reliable than pretending a crawler can always fetch the video.
- Keep Chrome fallback limited to visible page inspection plus temporary media extraction. Private browser/account data is outside scope.

## 微信公众号

Useful extraction pattern:

- `mp.weixin.qq.com` article pages usually expose enough HTML for title, description, account name, publish timestamp, and article body.
- Prefer the `js_content` article block for body text.
- Convert the body to plain Markdown and keep images out unless the user explicitly wants media archiving.

Safety decision:

- Do not store raw article HTML in the vault unless the user explicitly asks for archival evidence. The source note should stay readable.

## Transcript policy

For video platforms, transcript can come from:

- A transcript file supplied by the user.
- Verified ASR output from a separate tool.
- The bundled local workflow: download the detected video URL to cache, extract audio with ffmpeg, transcribe with Whisper, and write the transcript back to the source note.
- A platform-provided transcript if it is actually present.

If none is available, write a `## Transcript` section with a short pending note. Never generate a fake transcript from title or caption alone.

Downloaded video and audio files belong in local cache, not in `02-Sources`, unless the user explicitly asks to archive media files. The workflow does not delete cached video/audio by default; operating systems may still purge cache directories when storage is tight. Use `--delete-media-after-transcribe` for cleanup after a transcript is safely written.

The default transcription model is `auto`. Auto chooses `small` only when the machine has enough CPU threads, enough memory, and low current load; otherwise it chooses `base`, or `tiny` when constrained. Use `--model small` to force quality on a stronger machine. Local ASR output is rough until reviewed against the actual video.

Local Whisper is the preferred ASR path. Do not add third-party ASR providers or API keys by default, even when a reviewed repo supports DashScope, Doubao/Volcengine, Tencent, OpenAI Audio, Deepgram, AssemblyAI, or a custom API. External ASR should require a separate explicit decision from the user.

If rough ASR is hard to read, keep it under `## Transcript (rough ASR)` and add a separate `## Cleaned Transcript` section for a readable working version. Build that cleaned section from the post caption, visible on-screen text, and ASR phrases that can be confidently resolved. Do not guess unclear names or numbers and then label the result as a transcript.

If Chrome exposes real subtitles, write them as `## Transcript` and record the source. If Chrome exposes only platform AI summaries or chapter outlines, write them as `## Platform AI Summary`, keep transcript status pending until ASR or a real transcript exists, and label the section as non-verbatim.

## Cache debug logs

A cache debug log, if added, should live beside the local media cache. It is only for troubleshooting import/transcription failures.

Allowed contents: platform, canonical URL, extraction method, whether Chrome fallback was used, selected Whisper model, local cache file paths, non-secret warnings, and failure reasons.

Disallowed contents: private browser/account data, raw HTML dumps, full session logs, and anything copied from private accounts. The log is safe to delete and must not be mirrored into Obsidian.
