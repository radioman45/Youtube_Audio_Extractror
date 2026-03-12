from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.services.extractor import (
    ExtractionInputError,
    ExtractionResult,
    ExtractionRuntimeError,
    build_download_name,
    cleanup_temp_dir,
    parse_time_to_seconds,
    probe_media_info,
    sanitize_filename,
    validate_requested_range,
    validate_time_range,
    validate_youtube_url,
)


SubtitleLanguage = str
SubtitleFormat = str
SUPPORTED_SUBTITLE_FORMATS: tuple[SubtitleFormat, ...] = ("timestamped", "clean")
TIMING_LINE_PATTERN = re.compile(
    r"^(?P<start>(\d{2}:)?\d{2}:\d{2}\.\d{3})\s+-->\s+(?P<end>(\d{2}:)?\d{2}:\d{2}\.\d{3})(?:\s+.*)?$"
)


@dataclass(slots=True)
class SubtitleCue:
    start: float
    end: float
    lines: list[str]


@dataclass(slots=True)
class SubtitleOptions:
    url: str
    subtitle_language: SubtitleLanguage
    subtitle_format: SubtitleFormat = "timestamped"
    start_time: str | None = None
    end_time: str | None = None


def normalize_language_code(language: str) -> str:
    normalized = language.strip().lower()
    if not normalized:
        raise ExtractionInputError("자막 언어 코드를 입력해 주세요.")
    return normalized


def normalize_subtitle_format(subtitle_format: str) -> str:
    normalized = subtitle_format.strip().lower()
    if normalized not in SUPPORTED_SUBTITLE_FORMATS:
        raise ExtractionInputError("Unsupported subtitle format.")
    return normalized


def find_matching_language(subtitles: dict[str, object], language: SubtitleLanguage) -> str | None:
    normalized_language = normalize_language_code(language)
    exact_match = next((key for key in subtitles if key.lower() == normalized_language), None)
    if exact_match is not None:
        return exact_match

    prefixed_match = next((key for key in subtitles if key.lower().startswith(f"{normalized_language}-")), None)
    if prefixed_match is not None:
        return prefixed_match

    return next((key for key in subtitles if key.lower().startswith(normalized_language)), None)


def resolve_subtitle_track(info: dict[str, object], language: SubtitleLanguage) -> tuple[str, bool]:
    subtitles = info.get("subtitles")
    if isinstance(subtitles, dict):
        matched = find_matching_language(subtitles, language)
        if matched is not None:
            return matched, False

    automatic_captions = info.get("automatic_captions")
    if isinstance(automatic_captions, dict):
        matched = find_matching_language(automatic_captions, language)
        if matched is not None:
            return matched, True

    raise ExtractionInputError("선택한 언어의 자막을 찾지 못했습니다.")


def download_subtitle_file(
    url: str,
    work_dir: Path,
    subtitle_key: str,
    use_automatic_captions: bool,
) -> tuple[Path, dict[str, object]]:
    ydl_options: dict[str, object] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "outtmpl": str(work_dir / "%(title)s"),
        "subtitleslangs": [subtitle_key],
        "subtitlesformat": "vtt",
        "writesubtitles": not use_automatic_captions,
        "writeautomaticsub": use_automatic_captions,
    }

    with YoutubeDL(ydl_options) as ydl:
        info = ydl.extract_info(url, download=True)

    if not isinstance(info, dict):
        raise ExtractionRuntimeError("자막 메타데이터를 읽지 못했습니다.")

    candidates = sorted(work_dir.glob(f"*.{subtitle_key}.vtt"))
    if candidates:
        return candidates[0], info

    fallback_candidates = sorted(work_dir.glob("*.vtt"))
    if not fallback_candidates:
        raise ExtractionRuntimeError("다운로드된 자막 파일을 찾지 못했습니다.")

    return fallback_candidates[0], info


def parse_vtt_timestamp(value: str) -> float:
    parts = value.split(":")
    if len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise ValueError("잘못된 자막 타임스탬프입니다.")

    return (int(hours) * 3600) + (int(minutes) * 60) + float(seconds)


def parse_vtt_cues(content: str) -> list[SubtitleCue]:
    normalized = content.replace("\r\n", "\n").strip()
    if not normalized:
        raise ExtractionRuntimeError("자막 파일이 비어 있습니다.")

    blocks = re.split(r"\n\s*\n", normalized)
    cues: list[SubtitleCue] = []

    for block in blocks:
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines or lines[0] == "WEBVTT" or lines[0].startswith("NOTE") or lines[0].startswith("STYLE"):
            continue

        timing_index = 0
        if "-->" not in lines[0]:
            if len(lines) < 2 or "-->" not in lines[1]:
                continue
            timing_index = 1

        match = TIMING_LINE_PATTERN.match(lines[timing_index])
        if match is None:
            continue

        text_lines = lines[timing_index + 1 :]
        if not text_lines:
            continue

        cues.append(
            SubtitleCue(
                start=parse_vtt_timestamp(match.group("start")),
                end=parse_vtt_timestamp(match.group("end")),
                lines=text_lines,
            )
        )

    if not cues:
        raise ExtractionRuntimeError("유효한 자막 큐를 찾지 못했습니다.")

    return cues


def filter_cues(cues: list[SubtitleCue], start_seconds: float | None, end_seconds: float | None) -> list[SubtitleCue]:
    filtered: list[SubtitleCue] = []
    for cue in cues:
        if start_seconds is not None and cue.end <= start_seconds:
            continue
        if end_seconds is not None and cue.start >= end_seconds:
            continue
        filtered.append(cue)

    if not filtered:
        raise ExtractionInputError("선택한 구간에는 자막이 없습니다.")
    return filtered


def format_srt_timestamp(seconds: float) -> str:
    whole_seconds = int(seconds)
    milliseconds = int(round((seconds - whole_seconds) * 1000))
    if milliseconds == 1000:
        whole_seconds += 1
        milliseconds = 0

    hours = whole_seconds // 3600
    minutes = (whole_seconds % 3600) // 60
    remaining_seconds = whole_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d},{milliseconds:03d}"


def format_vtt_timestamp(seconds: float) -> str:
    return format_srt_timestamp(seconds).replace(",", ".")


def render_srt(cues: list[SubtitleCue]) -> str:
    blocks: list[str] = []
    for index, cue in enumerate(cues, start=1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_srt_timestamp(cue.start)} --> {format_srt_timestamp(cue.end)}",
                    *cue.lines,
                ]
            )
        )
    return "\n\n".join(blocks).strip() + "\n"


def render_clean_text_entries(entries: list[str]) -> str:
    cleaned_entries: list[str] = []
    for entry in entries:
        cleaned = re.sub(r"\s+", " ", entry).strip()
        if not cleaned:
            continue
        if cleaned_entries and cleaned_entries[-1] == cleaned:
            continue
        cleaned_entries.append(cleaned)

    if not cleaned_entries:
        raise ExtractionRuntimeError("?좏슚???먮쭑 ?띿뒪?몃? 李얠? 紐삵뻽?듬땲??")

    return "\n".join(cleaned_entries).strip() + "\n"


def render_clean_subtitle_text(cues: list[SubtitleCue]) -> str:
    return render_clean_text_entries([" ".join(cue.lines) for cue in cues])


def filter_webvtt(content: str, start_seconds: float | None, end_seconds: float | None) -> str:
    cues = filter_cues(parse_vtt_cues(content), start_seconds, end_seconds)
    blocks = ["WEBVTT"]
    for cue in cues:
        blocks.append(
            "\n".join(
                [
                    f"{format_vtt_timestamp(cue.start)} --> {format_vtt_timestamp(cue.end)}",
                    *cue.lines,
                ]
            )
        )
    return "\n\n".join(blocks).strip() + "\n"


def build_subtitle_download_name(
    title: str,
    subtitle_language: SubtitleLanguage,
    start_seconds: int | None,
    end_seconds: int | None,
    subtitle_format: SubtitleFormat = "timestamped",
) -> str:
    normalized_format = normalize_subtitle_format(subtitle_format)
    safe_title = sanitize_filename(title)
    file_extension = "srt" if normalized_format == "timestamped" else "txt"
    base_name = build_download_name(safe_title, file_extension, start_seconds, end_seconds).rsplit(".", 1)[0]
    language_suffix = normalize_language_code(subtitle_language)
    if normalized_format == "clean":
        return f"{base_name}_{language_suffix}_clean.txt"
    return f"{base_name}_{language_suffix}.srt"


def resolve_subtitle_media_type(subtitle_format: SubtitleFormat) -> str:
    normalized_format = normalize_subtitle_format(subtitle_format)
    if normalized_format == "clean":
        return "text/plain; charset=utf-8"
    return "application/x-subrip; charset=utf-8"


def extract_subtitles(options: SubtitleOptions) -> ExtractionResult:
    normalized_url = validate_youtube_url(options.url)
    start_seconds = parse_time_to_seconds(options.start_time)
    end_seconds = parse_time_to_seconds(options.end_time)
    subtitle_format = normalize_subtitle_format(options.subtitle_format)
    temp_dir = Path(tempfile.mkdtemp(prefix="youtube-subtitles-"))

    try:
        metadata = probe_media_info(normalized_url)
        duration = metadata.get("duration")
        duration_seconds = float(duration) if isinstance(duration, (int, float)) else None
        validate_time_range(
            start_seconds,
            end_seconds,
            int(duration_seconds) if duration_seconds is not None else None,
        )
        validate_requested_range(start_seconds, end_seconds, duration_seconds)

        subtitle_key, use_automatic_captions = resolve_subtitle_track(metadata, options.subtitle_language)
        downloaded_path, downloaded_info = download_subtitle_file(
            normalized_url,
            temp_dir,
            subtitle_key,
            use_automatic_captions,
        )

        subtitle_content = downloaded_path.read_text(encoding="utf-8-sig")
        cues = parse_vtt_cues(subtitle_content)
        filtered_cues = filter_cues(cues, start_seconds, end_seconds)
        rendered_subtitles = (
            render_srt(filtered_cues)
            if subtitle_format == "timestamped"
            else render_clean_subtitle_text(filtered_cues)
        )

        title = str(downloaded_info.get("title") or metadata.get("title") or "youtube-subtitles")
        output_name = build_subtitle_download_name(
            title,
            options.subtitle_language,
            start_seconds,
            end_seconds,
            subtitle_format=subtitle_format,
        )
        output_path = temp_dir / output_name
        output_path.write_text(rendered_subtitles, encoding="utf-8")

        return ExtractionResult(
            file_path=output_path,
            download_name=output_name,
            temp_dir=temp_dir,
            media_type=resolve_subtitle_media_type(subtitle_format),
        )
    except (DownloadError, OSError) as exc:
        cleanup_temp_dir(temp_dir)
        raise ExtractionRuntimeError("자막 다운로드에 실패했습니다.") from exc
    except Exception:
        cleanup_temp_dir(temp_dir)
        raise
