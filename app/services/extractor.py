from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import imageio_ffmpeg
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.services.time_utils import parse_timestamp, seconds_to_ffmpeg_timestamp


AudioFormat = Literal["mp3", "m4a", "wav", "opus"]
SUPPORTED_FORMATS: tuple[AudioFormat, ...] = ("mp3", "m4a", "wav", "opus")
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


class ExtractionInputError(ValueError):
    """Raised when the request payload is invalid."""


class ExtractionRuntimeError(RuntimeError):
    """Raised when yt-dlp or ffmpeg processing fails."""


@dataclass(slots=True)
class ExtractionOptions:
    url: str
    audio_format: AudioFormat
    start_time: str | None = None
    end_time: str | None = None


@dataclass(slots=True)
class ExtractionResult:
    file_path: Path
    download_name: str
    temp_dir: Path


def is_supported_youtube_url(url: str) -> bool:
    try:
        validate_youtube_url(url)
    except ExtractionInputError:
        return False
    return True


def validate_youtube_url(url: str) -> str:
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        raise ExtractionInputError("Enter a valid YouTube URL.")

    if parsed.netloc.lower() not in YOUTUBE_HOSTS:
        raise ExtractionInputError("Only YouTube links are supported.")

    return cleaned


def parse_time_to_seconds(value: str | None) -> int | None:
    try:
        parsed = parse_timestamp(value)
    except ValueError as exc:
        raise ExtractionInputError(str(exc)) from exc

    if parsed is None:
        return None
    return int(parsed)


def validate_time_range(
    start_seconds: int | None,
    end_seconds: int | None,
    duration_seconds: int | None,
) -> None:
    if start_seconds is not None and start_seconds < 0:
        raise ExtractionInputError("Start time must be 0 or greater.")

    if end_seconds is not None and end_seconds <= 0:
        raise ExtractionInputError("End time must be greater than 0.")

    if start_seconds is not None and end_seconds is not None and end_seconds <= start_seconds:
        raise ExtractionInputError("End time must be after start time.")

    if duration_seconds is None:
        return

    if start_seconds is not None and start_seconds >= duration_seconds:
        raise ExtractionInputError("Start time is outside the video duration.")

    if end_seconds is not None and end_seconds > duration_seconds:
        raise ExtractionInputError("End time is outside the video duration.")


def validate_requested_range(
    start_seconds: float | None,
    end_seconds: float | None,
    duration_seconds: float | None,
) -> None:
    if duration_seconds is None:
        return

    if start_seconds is not None and start_seconds >= duration_seconds:
        raise ValueError("Start time is outside the video duration.")

    if end_seconds is not None and end_seconds > duration_seconds:
        raise ValueError("End time is outside the video duration.")


def seconds_to_label(value: int | None) -> str:
    if value is None:
        return "full"

    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}-{minutes:02d}-{seconds:02d}"
    return f"{minutes:02d}-{seconds:02d}"


def sanitize_filename(name: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("", name).strip().rstrip(".")
    return re.sub(r"\s+", " ", cleaned)[:120] or "youtube-audio"


def build_output_path(temp_dir: Path, title: str, output_format: str) -> Path:
    return temp_dir / f"{sanitize_filename(title)}.{output_format.lower()}"


def build_download_name(
    title: str,
    audio_format: AudioFormat,
    start_seconds: int | None,
    end_seconds: int | None,
) -> str:
    if start_seconds is None and end_seconds is None:
        return build_output_path(Path("."), title, audio_format).name

    safe_title = sanitize_filename(title)
    return (
        f"{safe_title}_{seconds_to_label(start_seconds)}"
        f"_to_{seconds_to_label(end_seconds)}.{audio_format}"
    )


def cleanup_temp_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def resolve_ffmpeg_path() -> str:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _ydl_base_options(ffmpeg_path: str) -> dict[str, object]:
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "ffmpeg_location": ffmpeg_path,
    }


def _normalize_info(info: dict[str, object]) -> dict[str, object]:
    if "entries" not in info:
        return info

    entries = info.get("entries") or []
    for entry in entries:
        if isinstance(entry, dict):
            return entry
    raise ExtractionRuntimeError("Failed to read video metadata.")


def _probe_video(url: str, ffmpeg_path: str) -> dict[str, object]:
    with YoutubeDL(_ydl_base_options(ffmpeg_path)) as ydl:
        info = ydl.extract_info(url, download=False)

    if not isinstance(info, dict):
        raise ExtractionRuntimeError("Failed to read video metadata.")

    return _normalize_info(info)


def _download_source_audio(url: str, work_dir: Path, ffmpeg_path: str) -> tuple[Path, dict[str, object]]:
    ydl_options = _ydl_base_options(ffmpeg_path) | {
        "format": "bestaudio/best",
        "outtmpl": str(work_dir / "%(title)s.%(ext)s"),
    }

    with YoutubeDL(ydl_options) as ydl:
        info = _normalize_info(ydl.extract_info(url, download=True))
        expected_path = Path(ydl.prepare_filename(info))

    if expected_path.exists():
        return expected_path, info

    candidates = sorted(
        [entry for entry in work_dir.iterdir() if entry.is_file()],
        key=lambda item: item.stat().st_size,
        reverse=True,
    )
    if not candidates:
        raise ExtractionRuntimeError("Downloaded source audio file was not found.")
    return candidates[0], info


def _build_ffmpeg_command(
    ffmpeg_path: str,
    input_path: Path,
    output_path: Path,
    audio_format: AudioFormat,
    start_seconds: int | None,
    end_seconds: int | None,
) -> list[str]:
    command = [ffmpeg_path, "-y", "-i", str(input_path)]

    if start_seconds is not None:
        command.extend(["-ss", seconds_to_ffmpeg_timestamp(float(start_seconds)) or "00:00:00.000"])

    if end_seconds is not None:
        if start_seconds is not None:
            command.extend(["-t", str(end_seconds - start_seconds)])
        else:
            command.extend(["-to", seconds_to_ffmpeg_timestamp(float(end_seconds)) or "00:00:00.000"])

    match audio_format:
        case "mp3":
            command.extend(["-vn", "-c:a", "libmp3lame", "-q:a", "2"])
        case "m4a":
            command.extend(["-vn", "-c:a", "aac", "-b:a", "192k"])
        case "wav":
            command.extend(["-vn", "-c:a", "pcm_s16le"])
        case "opus":
            command.extend(["-vn", "-c:a", "libopus", "-b:a", "160k"])

    command.append(str(output_path))
    return command


def extract_audio(options: ExtractionOptions) -> ExtractionResult:
    normalized_url = validate_youtube_url(options.url)
    if options.audio_format not in SUPPORTED_FORMATS:
        raise ExtractionInputError("Unsupported audio format.")

    start_seconds = parse_time_to_seconds(options.start_time)
    end_seconds = parse_time_to_seconds(options.end_time)

    temp_dir = Path(tempfile.mkdtemp(prefix="youtube-audio-"))
    ffmpeg_path = resolve_ffmpeg_path()

    try:
        metadata = _probe_video(normalized_url, ffmpeg_path)
        duration = metadata.get("duration")
        duration_seconds = float(duration) if isinstance(duration, (int, float)) else None
        validate_time_range(
            start_seconds,
            end_seconds,
            int(duration_seconds) if duration_seconds is not None else None,
        )
        validate_requested_range(start_seconds, end_seconds, duration_seconds)

        source_path, downloaded_info = _download_source_audio(normalized_url, temp_dir, ffmpeg_path)
        title = str(downloaded_info.get("title") or metadata.get("title") or "youtube-audio")
        download_name = build_download_name(title, options.audio_format, start_seconds, end_seconds)
        output_path = temp_dir / download_name

        command = _build_ffmpeg_command(
            ffmpeg_path=ffmpeg_path,
            input_path=source_path,
            output_path=output_path,
            audio_format=options.audio_format,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        )

        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0 or not output_path.exists():
            error_lines = completed.stderr.strip().splitlines()
            message = error_lines[-1] if error_lines else "ffmpeg conversion failed."
            raise ExtractionRuntimeError(message)

        return ExtractionResult(file_path=output_path, download_name=download_name, temp_dir=temp_dir)
    except (DownloadError, OSError) as exc:
        cleanup_temp_dir(temp_dir)
        raise ExtractionRuntimeError("Failed while downloading YouTube audio.") from exc
    except Exception:
        cleanup_temp_dir(temp_dir)
        raise
