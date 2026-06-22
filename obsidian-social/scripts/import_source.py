#!/usr/bin/env python3
"""Import XHS, Douyin, and WeChat links into Obsidian source notes."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


DEFAULT_VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", "~/Documents/Obsidian Vault")).expanduser()
DEFAULT_SOURCE_DIR = Path(os.environ.get("OBSIDIAN_SOURCE_DIR", "02-Sources"))
PLATFORM_FOLDERS = {
    "xiaohongshu": "XHS",
    "douyin": "Douyin",
    "wechat": "WeChat",
}
VIDEO_PLATFORMS = {"xiaohongshu", "douyin"}


@dataclass
class ImportRecord:
    platform: str
    source_url: str
    canonical_url: str = ""
    title: str = ""
    author: str = ""
    published: str = ""
    description: str = ""
    text: str = ""
    video_url: str = ""
    image_urls: list[str] = field(default_factory=list)
    original_tags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class MarkdownTextExtractor(HTMLParser):
    """Small HTML to text/Markdown converter for article bodies."""

    BLOCK_TAGS = {
        "article",
        "blockquote",
        "div",
        "figcaption",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "section",
        "table",
        "tbody",
        "td",
        "th",
        "tr",
        "ul",
        "ol",
    }
    SKIP_TAGS = {"script", "style", "svg", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.link_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self._new_block()
            self.parts.append("- ")
        elif tag in self.BLOCK_TAGS:
            self._new_block()
        elif tag == "a":
            href = ""
            for key, value in attrs:
                if key.lower() == "href" and value:
                    href = value
                    break
            self.link_stack.append(href)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag == "a":
            if self.link_stack:
                self.link_stack.pop()
        elif tag in self.BLOCK_TAGS:
            self._new_block()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = normalize_inline(data)
        if text:
            self.parts.append(text)

    def _new_block(self) -> None:
        if self.parts and not self.parts[-1].endswith("\n\n"):
            self.parts.append("\n\n")

    def get_markdown(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()


def normalize_inline(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\u00a0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", value).strip()


def normalize_block(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\u00a0", " ").replace("\u200b", "")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def fetch_url(url: str) -> tuple[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read()
        final_url = response.geturl()
        charset = response.headers.get_content_charset() or "utf-8"
    try:
        return final_url, raw.decode(charset, errors="replace")
    except LookupError:
        return final_url, raw.decode("utf-8", errors="replace")


def read_html_source(url: str, html_file: str | None) -> tuple[str, str]:
    if html_file:
        return url, Path(html_file).read_text(encoding="utf-8", errors="replace")
    return fetch_url(url)


def detect_platform(url: str, requested: str) -> str:
    if requested != "auto":
        return requested
    host = urllib.parse.urlparse(url).netloc.lower()
    if "mp.weixin.qq.com" in host:
        return "wechat"
    if "xiaohongshu.com" in host or "xhslink.com" in host:
        return "xiaohongshu"
    if "douyin.com" in host or "iesdouyin.com" in host:
        return "douyin"
    raise ValueError(f"Unsupported URL host: {host}")


def extract_meta(markup: str, *names: str) -> str:
    for name in names:
        escaped = re.escape(name)
        patterns = [
            rf"<meta\b(?=[^>]*(?:property|name)=['\"]{escaped}['\"])[^>]*content=['\"]([^'\"]*)['\"][^>]*>",
            rf"<meta\b(?=[^>]*content=['\"]([^'\"]*)['\"])[^>]*(?:property|name)=['\"]{escaped}['\"][^>]*>",
        ]
        for pattern in patterns:
            match = re.search(pattern, markup, flags=re.I | re.S)
            if match:
                return normalize_inline(match.group(1))
    return ""


def extract_title_tag(markup: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", markup, flags=re.I | re.S)
    if not match:
        return ""
    title = normalize_inline(re.sub(r"<[^>]+>", "", match.group(1)))
    title = re.sub(r"\s*[-_]\s*(小红书|抖音|微信公众平台|微信)\s*$", "", title)
    return title.strip()


def extract_js_var(markup: str, *names: str) -> str:
    for name in names:
        pattern = rf"(?:var\s+)?{re.escape(name)}\s*=\s*(['\"])(.*?)\1"
        match = re.search(pattern, markup, flags=re.S)
        if not match:
            continue
        raw = match.group(2)
        try:
            return normalize_inline(json.loads(f'"{raw}"'))
        except Exception:
            return normalize_inline(raw.encode("utf-8").decode("unicode_escape", errors="ignore"))
    return ""


def extract_balanced_object(markup: str, marker: str) -> str:
    start = markup.find(marker)
    if start < 0:
        return ""
    brace = markup.find("{", start)
    if brace < 0:
        return ""
    depth = 0
    quote = ""
    escaped = False
    for index in range(brace, len(markup)):
        char = markup[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return markup[brace : index + 1]
    return ""


def parse_jsonish(raw: str) -> Any:
    if not raw:
        return None
    text = html.unescape(raw).strip()
    text = text.replace("\\u002F", "/").replace("\\/", "/")
    text = re.sub(r"\bundefined\b", "null", text)
    text = re.sub(r"\bNaN\b", "null", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def deep_values(obj: Any) -> list[Any]:
    values: list[Any] = []
    if isinstance(obj, dict):
        values.append(obj)
        for value in obj.values():
            values.extend(deep_values(value))
    elif isinstance(obj, list):
        for value in obj:
            values.extend(deep_values(value))
    return values


def get_nested(obj: dict[str, Any], path: list[str]) -> Any:
    current: Any = obj
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def parse_wechat(url: str, final_url: str, markup: str) -> ImportRecord:
    title = (
        extract_js_var(markup, "msg_title")
        or extract_meta(markup, "og:title", "twitter:title")
        or extract_title_tag(markup)
    )
    description = (
        extract_js_var(markup, "msg_desc")
        or extract_meta(markup, "description", "og:description")
    )
    author = (
        extract_js_var(markup, "nickname", "author", "user_name")
        or extract_meta(markup, "author")
    )
    published = timestamp_to_date(extract_js_var(markup, "ct", "create_time"))
    article_html = extract_wechat_article_html(markup)
    text = html_to_markdown(article_html) if article_html else ""
    warnings: list[str] = []
    if not text:
        warnings.append("Could not find the WeChat article body in js_content.")
    return ImportRecord(
        platform="wechat",
        source_url=url,
        canonical_url=final_url,
        title=title or "Untitled WeChat article",
        author=author,
        published=published,
        description=description,
        text=text or description,
        warnings=warnings,
    )


def extract_wechat_article_html(markup: str) -> str:
    match = re.search(
        r"<div\b[^>]*id=['\"]js_content['\"][^>]*>(.*?)(?:<script\b|</body>)",
        markup,
        flags=re.I | re.S,
    )
    if not match:
        return ""
    content = match.group(1)
    content = re.sub(r"<script\b.*?</script>", "", content, flags=re.I | re.S)
    content = re.sub(r"<style\b.*?</style>", "", content, flags=re.I | re.S)
    return content


def html_to_markdown(fragment: str) -> str:
    parser = MarkdownTextExtractor()
    parser.feed(fragment)
    return parser.get_markdown()


def parse_xiaohongshu(url: str, final_url: str, markup: str) -> ImportRecord:
    state = None
    for marker in ("window.__INITIAL_STATE__", "__INITIAL_STATE__"):
        state = parse_jsonish(extract_balanced_object(markup, marker))
        if state:
            break
    note = find_xhs_note(state) if state else None
    title = extract_meta(markup, "og:title", "twitter:title") or extract_title_tag(markup)
    description = extract_meta(markup, "description", "og:description")
    author = ""
    published = ""
    text = description
    video_url = ""
    image_urls: list[str] = []
    original_tags: list[str] = []
    warnings: list[str] = []
    if note:
        title = as_text(note.get("title")) or title
        text = as_text(note.get("desc") or note.get("description")) or text
        description = text[:260] if text else description
        author = as_text(get_nested(note, ["user", "nickname"]) or get_nested(note, ["userInfo", "nickname"]))
        published = timestamp_to_date(note.get("time") or note.get("lastUpdateTime"))
        image_urls = extract_xhs_images(note)
        video_url = pick_video_url(note.get("video"))
        original_tags = sorted(set(re.findall(r"#([\w\u4e00-\u9fff-]+)", text or "")))
    else:
        warnings.append("Could not parse Xiaohongshu initial state from the fetched page.")
    if video_url and "xhscdn.com" in video_url:
        warnings.append("Xiaohongshu CDN video URL may expire; keep the clean source URL as the durable reference.")
    if not video_url:
        warnings.append("No stable Xiaohongshu video URL was found. Keep the source URL and add transcript later if needed.")
    return ImportRecord(
        platform="xiaohongshu",
        source_url=url,
        canonical_url=final_url,
        title=title or "Untitled Xiaohongshu note",
        author=author,
        published=published,
        description=description,
        text=text,
        video_url=video_url,
        image_urls=image_urls,
        original_tags=original_tags,
        warnings=warnings,
    )


def find_xhs_note(state: Any) -> dict[str, Any] | None:
    if not state:
        return None
    explicit = get_nested(state, ["note", "noteDetailMap"])
    if isinstance(explicit, dict):
        for value in explicit.values():
            if isinstance(value, dict):
                note = value.get("note") if isinstance(value.get("note"), dict) else value
                if looks_like_xhs_note(note):
                    return note
    for value in deep_values(state):
        if looks_like_xhs_note(value):
            return value
    return None


def looks_like_xhs_note(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return bool(
        ("desc" in value or "title" in value)
        and ("imageList" in value or "video" in value or "type" in value or "interactInfo" in value)
    )


def extract_xhs_images(note: dict[str, Any]) -> list[str]:
    images: list[str] = []
    for image in note.get("imageList") or []:
        if not isinstance(image, dict):
            continue
        candidates = [
            image.get("urlDefault"),
            image.get("url"),
            image.get("originalUrl"),
            image.get("thumbnail"),
        ]
        for candidate in candidates:
            if candidate:
                images.append(str(candidate))
                break
    return dedupe(images)


def pick_video_url(video: Any) -> str:
    if not isinstance(video, dict):
        return ""
    stream = get_nested(video, ["media", "stream"]) or video.get("stream") or {}
    candidates: list[str] = []
    if isinstance(stream, dict):
        for codec in ("h264", "h265", "av1"):
            values = stream.get(codec) or []
            if isinstance(values, dict):
                values = [values]
            for value in values:
                if not isinstance(value, dict):
                    continue
                candidates.extend(url for url in [
                    value.get("masterUrl"),
                    value.get("backupUrl"),
                    first(value.get("backupUrls")),
                    value.get("url"),
                ] if url)
    candidates.extend(collect_urls(video))
    for candidate in dedupe(candidates):
        if looks_like_video_url(candidate):
            return normalize_url_string(candidate)
    return normalize_url_string(first(dedupe(candidates)) or "")


def parse_douyin(url: str, final_url: str, markup: str) -> ImportRecord:
    description = extract_meta(markup, "description", "og:description")
    title = extract_meta(markup, "og:title", "twitter:title") or extract_title_tag(markup)
    author = extract_meta(markup, "author")
    json_blobs = extract_douyin_json(markup)
    candidates: list[str] = []
    text_candidates: list[str] = []
    author_candidates: list[str] = []
    for blob in json_blobs:
        candidates.extend(collect_urls(blob))
        text_candidates.extend(collect_text_candidates(blob))
        author_candidates.extend(collect_author_candidates(blob))
    video_url = choose_video_candidate(candidates)
    text = description
    if text_candidates:
        text = max(text_candidates, key=len)
    if not author and author_candidates:
        author = author_candidates[0]
    warnings: list[str] = []
    if not video_url:
        warnings.append("No reliable Douyin video URL was found. Douyin often requires browser-context capture.")
    return ImportRecord(
        platform="douyin",
        source_url=url,
        canonical_url=final_url,
        title=clean_douyin_title(title) or "Untitled Douyin video",
        author=author,
        description=text[:260] if text else description,
        text=text,
        video_url=video_url,
        warnings=warnings,
    )


def extract_douyin_json(markup: str) -> list[Any]:
    blobs: list[Any] = []
    for script_id in ("RENDER_DATA", "__UNIVERSAL_DATA_FOR_REHYDRATION__"):
        pattern = rf"<script\b[^>]*id=['\"]{script_id}['\"][^>]*>(.*?)</script>"
        match = re.search(pattern, markup, flags=re.I | re.S)
        if match:
            raw = html.unescape(match.group(1)).strip()
            decoded = urllib.parse.unquote(raw)
            parsed = parse_jsonish(decoded) or parse_jsonish(raw)
            if parsed:
                blobs.append(parsed)
    for marker in ("window._ROUTER_DATA", "window.__INIT_PROPS__", "window.__INITIAL_STATE__"):
        parsed = parse_jsonish(extract_balanced_object(markup, marker))
        if parsed:
            blobs.append(parsed)
    if not blobs:
        blobs.append({"html": markup[:2_000_000]})
    return blobs


def collect_urls(obj: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(obj, dict):
        for value in obj.values():
            urls.extend(collect_urls(value))
    elif isinstance(obj, list):
        for value in obj:
            urls.extend(collect_urls(value))
    elif isinstance(obj, str):
        text = normalize_url_string(obj)
        urls.extend(re.findall(r"https?://[^\s\"'<>]+", text))
    return dedupe(urls)


def collect_text_candidates(obj: Any) -> list[str]:
    candidates: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            lower = str(key).lower()
            if lower in {"desc", "description", "caption", "title", "content"} and isinstance(value, str):
                text = normalize_block(value)
                if len(text) >= 4:
                    candidates.append(text)
            else:
                candidates.extend(collect_text_candidates(value))
    elif isinstance(obj, list):
        for value in obj:
            candidates.extend(collect_text_candidates(value))
    return dedupe(candidates)


def collect_author_candidates(obj: Any) -> list[str]:
    candidates: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            lower = str(key).lower()
            if lower in {"nickname", "author", "name", "accountname"} and isinstance(value, str):
                text = normalize_inline(value)
                if 1 < len(text) < 80:
                    candidates.append(text)
            else:
                candidates.extend(collect_author_candidates(value))
    elif isinstance(obj, list):
        for value in obj:
            candidates.extend(collect_author_candidates(value))
    return dedupe(candidates)


def choose_video_candidate(urls: list[str]) -> str:
    scored: list[tuple[int, str]] = []
    for raw in dedupe(urls):
        url = normalize_url_string(raw)
        lower = url.lower()
        score = 0
        for marker in ("mp4", "playwm", "playaddr", "douyinvod", "byteimg", "aweme", "video"):
            if marker in lower:
                score += 10
        if "http" in lower and score:
            scored.append((score, url))
    if not scored:
        return ""
    scored.sort(key=lambda item: (-item[0], len(item[1])))
    return scored[0][1]


def clean_douyin_title(title: str) -> str:
    title = re.sub(r"\s*[-_]\s*抖音.*$", "", title or "")
    title = title.replace(" - 抖音", "").strip()
    return title


def looks_like_video_url(value: str) -> bool:
    lower = value.lower()
    return any(marker in lower for marker in ("mp4", "video", "stream", "h264", "play"))


def normalize_url_string(value: Any) -> str:
    text = str(value or "")
    text = html.unescape(text)
    text = text.replace("\\u002F", "/").replace("\\/", "/")
    text = text.replace("\\u0026", "&")
    text = text.strip()
    return text


def timestamp_to_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        number = int(str(value).strip())
    except ValueError:
        return ""
    if number > 10_000_000_000:
        number = number // 1000
    try:
        return dt.datetime.fromtimestamp(number).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return normalize_block(str(value))


def first(value: Any) -> Any:
    if isinstance(value, list) and value:
        return value[0]
    return value


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def apply_overrides(record: ImportRecord, args: argparse.Namespace) -> ImportRecord:
    if args.title:
        record.title = args.title
    if args.author:
        record.author = args.author
    if args.video_url:
        record.video_url = args.video_url
    return record


def build_markdown(record: ImportRecord, transcript: str) -> str:
    created = dt.date.today().isoformat()
    canonical = record.canonical_url or record.source_url
    tags = ["clippings", "source/social", f"platform/{record.platform}"]
    frontmatter = [
        "---",
        f"title: {yaml_quote(record.title)}",
        f"source: {yaml_quote(record.source_url)}",
        f"canonical: {yaml_quote(canonical)}",
        f"platform: {yaml_quote(record.platform)}",
        "author:",
    ]
    if record.author:
        frontmatter.append(f"  - {yaml_quote(record.author)}")
    else:
        frontmatter.append("  - \"\"")
    frontmatter.extend(
        [
            f"published: {yaml_quote(record.published)}",
            f"created: {yaml_quote(created)}",
            f"description: {yaml_quote(record.description)}",
            "tags:",
        ]
    )
    for tag in tags:
        frontmatter.append(f"  - {yaml_quote(tag)}")
    if record.original_tags:
        frontmatter.append("original_tags:")
        for tag in record.original_tags:
            frontmatter.append(f"  - {yaml_quote(tag)}")
    if record.video_url:
        frontmatter.append(f"video_url: {yaml_quote(record.video_url)}")
    frontmatter.append(f"transcription_status: {yaml_quote(transcription_status(record, transcript))}")
    frontmatter.append("---")

    body: list[str] = ["\n".join(frontmatter), "", f"[Open original]({record.source_url})"]
    if canonical and canonical != record.source_url:
        body.append(f"\n[Canonical URL]({canonical})")
    if record.text:
        body.extend(["", "## Text", "", normalize_block(record.text)])
    body.extend(["", "## Media", "", f"- Source: {record.source_url}"])
    if record.video_url:
        body.append(f"- Video: {record.video_url}")
    if record.image_urls:
        body.append("- Images:")
        for image_url in record.image_urls[:12]:
            body.append(f"  - {image_url}")
    if record.platform in VIDEO_PLATFORMS or transcript:
        body.extend(["", "## Transcript", ""])
        if transcript:
            body.append(normalize_block(transcript))
        else:
            body.append("_Transcript pending. Add a verified ASR transcript or pass `--transcript-file` when available._")
    if record.warnings:
        body.extend(["", "## Import Notes", ""])
        for warning in record.warnings:
            body.append(f"- {warning}")
    return "\n".join(body).rstrip() + "\n"


def transcription_status(record: ImportRecord, transcript: str) -> str:
    if transcript:
        return "provided"
    if record.platform in VIDEO_PLATFORMS:
        return "pending"
    return "not_applicable"


def yaml_quote(value: Any) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def target_path(record: ImportRecord, vault: Path, output_dir: str | None) -> Path:
    source_root = vault / (output_dir or DEFAULT_SOURCE_DIR)
    folder = PLATFORM_FOLDERS.get(record.platform, record.platform)
    directory = source_root / folder
    directory.mkdir(parents=True, exist_ok=True)
    title = safe_filename(record.title or f"{record.platform}-{dt.date.today().isoformat()}")
    path = directory / f"{title}.md"
    counter = 2
    while path.exists():
        path = directory / f"{title}-{counter}.md"
        counter += 1
    return path


def safe_filename(title: str) -> str:
    title = normalize_inline(title)
    title = re.sub(r"[\\/:*?\"<>|#\[\]^]", " ", title)
    title = re.sub(r"\s+", " ", title).strip(". ")
    if not title:
        title = f"source-{dt.date.today().isoformat()}"
    return title[:90]


def import_record(args: argparse.Namespace) -> tuple[ImportRecord, str, Path | None]:
    platform = detect_platform(args.url, args.platform)
    final_url, markup = read_html_source(args.url, args.html_file)
    if platform == "wechat":
        record = parse_wechat(args.url, final_url, markup)
    elif platform == "xiaohongshu":
        record = parse_xiaohongshu(args.url, final_url, markup)
    elif platform == "douyin":
        record = parse_douyin(args.url, final_url, markup)
    else:
        raise ValueError(f"Unsupported platform: {platform}")
    record = apply_overrides(record, args)
    record.source_url = clean_public_url(record.source_url, record.platform)
    record.canonical_url = clean_public_url(record.canonical_url, record.platform)
    transcript = ""
    if args.transcript_file:
        transcript = Path(args.transcript_file).read_text(encoding="utf-8", errors="replace")
    markdown = build_markdown(record, transcript)
    if args.dry_run:
        return record, markdown, None
    vault = Path(args.vault).expanduser()
    path = target_path(record, vault, args.output_dir)
    path.write_text(markdown, encoding="utf-8")
    return record, markdown, path


def clean_public_url(url: str, platform: str) -> str:
    """Strip share tracking from URLs before writing permanent vault notes."""
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if platform == "xiaohongshu":
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
    return url


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a 小红书, 抖音, or 微信公众号 source into Obsidian.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              import_source.py "https://www.xiaohongshu.com/explore/..."
              import_source.py "https://mp.weixin.qq.com/s/..." --output-dir "02-Sources"
              import_source.py "https://v.douyin.com/..." --transcript-file transcript.txt
              import_source.py "https://www.xiaohongshu.com/..." --html-file saved-page.html
            """
        ),
    )
    parser.add_argument("url", help="Source URL from 小红书, 抖音, or 微信公众号.")
    parser.add_argument("--platform", choices=["auto", "xiaohongshu", "douyin", "wechat"], default="auto")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT), help="Obsidian vault path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_SOURCE_DIR), help="Vault-relative output directory.")
    parser.add_argument("--html-file", help="Use saved page HTML instead of fetching the URL.")
    parser.add_argument("--transcript-file", help="Text transcript to place under ## Transcript.")
    parser.add_argument("--video-url", help="Known video URL to include in the note.")
    parser.add_argument("--title", help="Override detected title.")
    parser.add_argument("--author", help="Override detected author.")
    parser.add_argument("--dry-run", action="store_true", help="Print Markdown instead of writing a note.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        record, markdown, path = import_record(args)
    except (OSError, urllib.error.URLError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    if args.dry_run:
        print(markdown)
    result = {
        "status": "ok",
        "platform": record.platform,
        "title": record.title,
        "path": str(path) if path else None,
        "source": record.source_url,
        "canonical": record.canonical_url or record.source_url,
        "video_url": record.video_url,
        "warnings": record.warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
