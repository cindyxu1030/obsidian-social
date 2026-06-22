#!/usr/bin/env python3
"""Download source-note video media, transcribe it locally, and update the note."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_CACHE_DIR = Path(os.environ.get("OBSIDIAN_SOCIAL_CACHE_DIR", "~/.cache/obsidian-social")).expanduser()
ALLOWED_COMMANDS = {"ffmpeg", "whisper"}
ALLOWED_MODELS = {"auto", "tiny", "base", "small", "medium", "large", "turbo"}
DEFAULT_INITIAL_PROMPT = (
    "以下是中文短视频口播转写，主题常涉及 AI Agent、Claude、OpenAI、Sora、a16z、"
    "Yupp.ai、Jasper、Chegg、GTC、workflow、prompt、SaaS、iOS、Google Cloud、"
    "Gemini、GPT-5、合规、私有数据、工作流、护城河。请尽量使用简体中文和正确技术名词。"
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a video URL from an Obsidian source note, transcribe it, and update the rough ASR transcript section.",
    )
    parser.add_argument("--note", help="Obsidian source note to read and update.")
    parser.add_argument("--video-url", help="Direct video URL when not using --note.")
    parser.add_argument("--source-url", help="Original page URL for Referer headers.")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR), help="Local cache directory for media and ASR output.")
    parser.add_argument("--model", default="auto", help="Whisper model name. Use auto, tiny, base, small, medium, large, or turbo.")
    parser.add_argument("--language", default="zh", help="Whisper language code. Use zh for Mandarin/Chinese.")
    parser.add_argument("--initial-prompt", default=DEFAULT_INITIAL_PROMPT, help="Whisper initial prompt for domain terms.")
    parser.add_argument("--force", action="store_true", help="Re-download and re-transcribe even if cached files exist.")
    parser.add_argument("--no-update-note", action="store_true", help="Print transcript path without editing the note.")
    parser.add_argument("--print-model-decision", action="store_true", help="Print the auto-selected model and exit without transcribing.")
    parser.add_argument("--delete-media-after-transcribe", action="store_true", help="Delete cached video/audio after successful transcription. Transcript cache remains.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    resolved_model, model_reason, resources = resolve_model(args.model)
    if args.print_model_decision:
        print(
            json.dumps(
                {
                    "status": "ok",
                    "requested_model": args.model,
                    "model": resolved_model,
                    "model_reason": model_reason,
                    "resources": resources,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    note_path = Path(args.note).expanduser() if args.note else None
    note_text = note_path.read_text(encoding="utf-8") if note_path else ""
    video_url = args.video_url or extract_note_field(note_text, "video_url") or extract_media_video(note_text)
    source_url = args.source_url or extract_note_field(note_text, "source") or extract_media_source(note_text)

    if not video_url:
        print_json_error("No video URL found. Pass --video-url or use a note with video_url / '- Video:'.")
        return 1
    validate_video_url(video_url)
    validate_language(args.language)
    require_command("ffmpeg")
    require_command("whisper")

    work_dir = make_work_dir(args.cache_dir, note_path, video_url)
    work_dir.mkdir(parents=True, exist_ok=True)
    video_path = work_dir / f"video{guess_extension(video_url)}"
    audio_path = work_dir / "audio.wav"
    transcript_dir = work_dir / f"transcript-{resolved_model}"
    transcript_path = transcript_dir / "audio.txt"

    try:
        if args.force or not video_path.exists():
            download_video(video_url, video_path, source_url)
        if args.force or not audio_path.exists():
            extract_audio(video_path, audio_path)
        if args.force or not transcript_path.exists():
            run_whisper(audio_path, transcript_dir, resolved_model, args.language, args.initial_prompt)
        transcript = sanitize_transcript(transcript_path.read_text(encoding="utf-8", errors="replace"))
        if not transcript:
            raise RuntimeError("Whisper completed but produced an empty transcript.")
        if note_path and not args.no_update_note:
            updated = update_note_transcript(note_text, transcript, resolved_model, model_reason)
            note_path.write_text(updated, encoding="utf-8")
        deleted_media = []
        if args.delete_media_after_transcribe:
            deleted_media = delete_media_files(video_path, audio_path)
    except Exception as exc:
        print_json_error(safe_message(str(exc)))
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "note": str(note_path) if note_path else None,
                "video_url": video_url,
                "cache_dir": str(work_dir),
                "video_path": str(video_path),
                "audio_path": str(audio_path),
                "transcript_path": str(transcript_path),
                "updated_note": bool(note_path and not args.no_update_note),
                "requested_model": args.model,
                "model": resolved_model,
                "model_reason": model_reason,
                "resources": resources,
                "deleted_media": deleted_media,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def extract_note_field(markdown: str, field: str) -> str:
    match = re.search(rf"^{re.escape(field)}:\s*(.+?)\s*$", markdown, flags=re.M)
    if not match:
        return ""
    raw = match.group(1).strip()
    try:
        value = json.loads(raw)
        return str(value)
    except Exception:
        return raw.strip("'\"")


def extract_media_video(markdown: str) -> str:
    match = re.search(r"^\s*-\s*Video:\s*(\S+)\s*$", markdown, flags=re.M)
    return match.group(1).strip() if match else ""


def extract_media_source(markdown: str) -> str:
    match = re.search(r"^\s*-\s*Source:\s*(\S+)\s*$", markdown, flags=re.M)
    return match.group(1).strip() if match else ""


def require_command(command: str) -> None:
    if not shutil.which(command):
        raise RuntimeError(f"Required command not found: {command}")


def validate_video_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("Video URL must be an http or https URL.")


def validate_model(model: str) -> None:
    if model not in ALLOWED_MODELS:
        allowed = ", ".join(sorted(ALLOWED_MODELS))
        raise RuntimeError(f"Unsupported Whisper model. Use one of: {allowed}.")


def resolve_model(requested_model: str) -> tuple[str, str, dict[str, float | int | str]]:
    model = requested_model
    validate_model(model)
    resources = inspect_resources()
    if model != "auto":
        reason = f"explicit model `{model}` selected"
        return model, reason, resources

    cpu_threads = int(resources["cpu_threads"])
    memory_gb = float(resources["memory_gb"])
    load_ratio = float(resources["load_ratio"])

    if cpu_threads >= 12 and memory_gb >= 24 and load_ratio <= 0.45:
        selected = "small"
    elif load_ratio >= 0.85 or memory_gb < 8:
        selected = "tiny"
    else:
        selected = "base"

    reason = (
        f"auto selected `{selected}` from {cpu_threads} CPU threads, "
        f"{memory_gb:.1f} GB RAM, 1m load {float(resources['load_1m']):.2f} "
        f"({load_ratio:.0%} of CPU threads)"
    )
    return selected, reason, resources


def inspect_resources() -> dict[str, float | int | str]:
    cpu_threads = os.cpu_count() or 1
    try:
        load_1m = os.getloadavg()[0]
    except OSError:
        load_1m = 0.0
    load_ratio = min(load_1m / max(cpu_threads, 1), 9.99)
    memory_gb = total_memory_gb()
    return {
        "cpu_threads": cpu_threads,
        "memory_gb": round(memory_gb, 2),
        "load_1m": round(load_1m, 2),
        "load_ratio": round(load_ratio, 4),
        "auto_policy": "small if >=12 CPU threads, >=24GB RAM, and <=45% 1m load; tiny if constrained; otherwise base",
    }


def total_memory_gb() -> float:
    if hasattr(os, "sysconf"):
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            pages = os.sysconf("SC_PHYS_PAGES")
            return float(page_size * pages) / (1024**3)
        except (ValueError, OSError, AttributeError):
            pass
    return 0.0


def validate_language(language: str) -> None:
    if not re.fullmatch(r"[A-Za-z-]{2,20}", language):
        raise RuntimeError("Language must be a short Whisper language code, such as zh or en.")


def make_work_dir(cache_dir: str, note_path: Path | None, video_url: str) -> Path:
    stem = note_path.stem if note_path else "video"
    safe_stem = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", stem, flags=re.U).strip("-")[:80]
    digest = hashlib.sha256(video_url.encode("utf-8")).hexdigest()[:10]
    return Path(cache_dir).expanduser() / f"{safe_stem}-{digest}"


def guess_extension(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix in {".mp4", ".mov", ".m4v", ".webm"}:
        return suffix
    return ".mp4"


def download_video(url: str, output_path: Path, source_url: str) -> None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }
    if source_url:
        headers["Referer"] = source_url
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as file:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                file.write(chunk)
    if output_path.stat().st_size < 1024:
        raise RuntimeError("Downloaded file is too small to be a valid video.")


def extract_audio(video_path: Path, audio_path: Path) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(audio_path),
        ]
    )


def run_whisper(audio_path: Path, output_dir: Path, model: str, language: str, initial_prompt: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "whisper",
        str(audio_path),
        "--language",
        language,
        "--model",
        model,
        "--task",
        "transcribe",
        "--fp16",
        "False",
        "--output_format",
        "txt",
        "--output_dir",
        str(output_dir),
        "--verbose",
        "False",
    ]
    if initial_prompt:
        command.extend(["--initial_prompt", initial_prompt[:800]])
    run(command)


def run(command: list[str]) -> None:
    if not command or command[0] not in ALLOWED_COMMANDS:
        raise RuntimeError("Blocked unexpected external command.")
    try:
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"External command failed: {command[0]} exited with code {exc.returncode}.") from exc


def update_note_transcript(markdown: str, transcript: str, model: str, model_reason: str) -> str:
    today = dt.date.today().isoformat()
    updated = update_frontmatter(markdown, "transcription_status", "generated")
    updated = update_frontmatter(updated, "transcribed", today)
    updated = update_frontmatter(updated, "transcription_model", f"whisper-{model}")
    updated = update_frontmatter(updated, "transcription_quality", "rough_asr_unreviewed")
    updated = replace_rough_transcript_section(updated, transcript.strip() + "\n")
    note = f"Transcript generated locally from downloaded video on {today} using Whisper model `{model}`."
    updated = add_import_note(updated, note)
    updated = add_import_note(updated, "Rough ASR transcript; verify against the video before quoting or publishing.")
    updated = add_import_note(updated, "If rough ASR is hard to read, create a `## Cleaned Transcript` from the post caption plus confirmed ASR context; do not present it as verbatim.")
    updated = add_import_note(updated, f"Whisper model selection: {model_reason}.")
    return updated.rstrip() + "\n"


def sanitize_transcript(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(char for char in text if char == "\n" or char == "\t" or ord(char) >= 32)
    safe_lines: list[str] = []
    for line in text.split("\n"):
        line = line.rstrip()
        if re.match(r"^#{1,6}\s", line):
            line = "\\" + line
        if line.strip() == "---":
            line = "\\---"
        safe_lines.append(line)
    text = "\n".join(safe_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def update_frontmatter(markdown: str, key: str, value: str) -> str:
    quoted = json.dumps(value, ensure_ascii=False)
    frontmatter = re.match(r"\A---\n(.*?)\n---\n", markdown, flags=re.S)
    if not frontmatter:
        return markdown
    block = frontmatter.group(1)
    if re.search(rf"^{re.escape(key)}:", block, flags=re.M):
        block = re.sub(rf"^{re.escape(key)}:\s*.*$", f"{key}: {quoted}", block, flags=re.M)
    else:
        block = block.rstrip() + f"\n{key}: {quoted}"
    return "---\n" + block + "\n---\n" + markdown[frontmatter.end() :]


def replace_section(markdown: str, title: str, body: str) -> str:
    pattern = rf"(?ms)^## {re.escape(title)}\n\n.*?(?=^## |\Z)"
    replacement = f"## {title}\n\n{body.rstrip()}\n\n"
    if re.search(pattern, markdown):
        return re.sub(pattern, replacement, markdown)
    return markdown.rstrip() + "\n\n" + replacement


def replace_rough_transcript_section(markdown: str, body: str) -> str:
    rough_title = "Transcript (rough ASR)"
    rough_pattern = rf"(?ms)^## {re.escape(rough_title)}\n\n.*?(?=^## |\Z)"
    replacement = f"## {rough_title}\n\n{body.rstrip()}\n\n"
    if re.search(rough_pattern, markdown):
        return re.sub(rough_pattern, replacement, markdown)

    transcript_pattern = r"(?ms)^## Transcript\n\n.*?(?=^## |\Z)"
    if re.search(transcript_pattern, markdown):
        return re.sub(transcript_pattern, replacement, markdown)

    return markdown.rstrip() + "\n\n" + replacement


def add_import_note(markdown: str, note: str) -> str:
    markdown = re.sub(r"(?m)^- Transcript generated locally from downloaded video on .*$\n?", "", markdown)
    markdown = re.sub(r"(?m)^- Whisper model selection: .*$\n?", "", markdown)
    markdown = re.sub(rf"(?m)^- {re.escape(note)}\n?", "", markdown)
    if re.search(r"(?m)^## Import Notes\s*$", markdown):
        return re.sub(r"(?m)^## Import Notes\s*\n", f"## Import Notes\n\n- {note}\n", markdown, count=1)
    return markdown.rstrip() + f"\n\n## Import Notes\n\n- {note}\n"


def delete_media_files(video_path: Path, audio_path: Path) -> list[str]:
    deleted: list[str] = []
    for path in (video_path, audio_path):
        if path.exists():
            path.unlink()
            deleted.append(str(path))
    return deleted


def print_json_error(message: str) -> None:
    print(json.dumps({"status": "error", "error": message}, ensure_ascii=False, indent=2), file=sys.stderr)


def safe_message(message: str) -> str:
    message = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", message)
    message = re.sub(r"\s+", " ", message).strip()
    return message[:500] or "Workflow failed."


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
