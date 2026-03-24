from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import urlparse

import imageio_ffmpeg
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.services.time_utils import parse_timestamp, seconds_to_ffmpeg_timestamp


AudioFormat = Literal["mp3", "m4a", "wav", "opus", "aac"]
ProgressCallback = Callable[[int, str], None]
SUPPORTED_FORMATS: tuple[AudioFormat, ...] = ("mp3", "m4a", "wav", "opus", "aac")
SUPPORTED_MP3_BITRATES: tuple[str, ...] = ("320k", "256k", "192k", "128k", "96k", "64k")
SUPPORTED_SPLIT_SIZES_MB: tuple[int, ...] = (100, 50, 25, 10, 5)
DEFAULT_SPLIT_MP3_BITRATE = "192k"
SPLIT_SIZE_SAFETY_RATIO = 0.96
SPLIT_SIZE_OVERHEAD_BYTES = 64 * 1024
VIDEO_QUALITY_HEIGHTS: dict[str, int] = {
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
    "1440p": 1440,
    "2160p": 2160,
    "4320p": 4320,
}
SUPPORTED_VIDEO_QUALITIES: tuple[str, ...] = tuple(VIDEO_QUALITY_HEIGHTS.keys())
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
    mp3_bitrate: str | None = None
    split_size_mb: int | None = None


@dataclass(slots=True)
class SongExtractionOptions:
    url: str
    start_time: str | None = None
    end_time: str | None = None


@dataclass(slots=True)
class ExtractionResult:
    file_path: Path
    download_name: str
    temp_dir: Path
    media_type: str = "application/octet-stream"


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
        raise ExtractionInputError("유효한 YouTube URL을 입력해 주세요.")

    if parsed.netloc.lower() not in YOUTUBE_HOSTS:
        raise ExtractionInputError("YouTube 링크만 지원합니다.")

    return cleaned


def parse_time_to_seconds(value: str | None) -> int | None:
    try:
        parsed = parse_timestamp(value)
    except ValueError as exc:
        raise ExtractionInputError(str(exc)) from exc

    if parsed is None:
        return None
    return int(parsed)


def normalize_mp3_bitrate(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip().lower()
    if not normalized:
        return None

    if normalized not in SUPPORTED_MP3_BITRATES:
        raise ExtractionInputError("Unsupported MP3 bitrate.")
    return normalized


def normalize_split_size_mb(value: int | None) -> int | None:
    if value is None:
        return None

    if value not in SUPPORTED_SPLIT_SIZES_MB:
        raise ExtractionInputError("Unsupported split size.")
    return value


def resolve_mp3_bitrate(audio_format: str, mp3_bitrate: str | None, split_size_mb: int | None) -> str | None:
    if audio_format != "mp3":
        return None

    normalized = normalize_mp3_bitrate(mp3_bitrate)
    if normalized is not None:
        return normalized

    if split_size_mb is not None:
        return DEFAULT_SPLIT_MP3_BITRATE
    return None


def validate_time_range(
    start_seconds: int | None,
    end_seconds: int | None,
    duration_seconds: int | None,
) -> None:
    if start_seconds is not None and start_seconds < 0:
        raise ExtractionInputError("시작 시간은 0 이상이어야 합니다.")

    if end_seconds is not None and end_seconds <= 0:
        raise ExtractionInputError("종료 시간은 0보다 커야 합니다.")

    if start_seconds is not None and end_seconds is not None and end_seconds <= start_seconds:
        raise ExtractionInputError("종료 시간은 시작 시간보다 뒤여야 합니다.")

    if duration_seconds is None:
        return

    if start_seconds is not None and start_seconds >= duration_seconds:
        raise ExtractionInputError("시작 시간이 영상 길이를 벗어났습니다.")

    if end_seconds is not None and end_seconds > duration_seconds:
        raise ExtractionInputError("종료 시간이 영상 길이를 벗어났습니다.")


def validate_requested_range(
    start_seconds: float | None,
    end_seconds: float | None,
    duration_seconds: float | None,
) -> None:
    if duration_seconds is None:
        return

    if start_seconds is not None and start_seconds >= duration_seconds:
        raise ValueError("시작 시간이 영상 길이를 벗어났습니다.")

    if end_seconds is not None and end_seconds > duration_seconds:
        raise ValueError("종료 시간이 영상 길이를 벗어났습니다.")


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
    return re.sub(r"\s+", " ", cleaned)[:120] or "youtube-media"


def build_output_path(temp_dir: Path, title: str, output_format: str) -> Path:
    return temp_dir / f"{sanitize_filename(title)}.{output_format.lower()}"


def build_download_name(
    title: str,
    output_format: str,
    start_seconds: int | None,
    end_seconds: int | None,
) -> str:
    safe_title = sanitize_filename(title)
    if start_seconds is None and end_seconds is None:
        return f"{safe_title}.{output_format}"

    return (
        f"{safe_title}_{seconds_to_label(start_seconds)}"
        f"_to_{seconds_to_label(end_seconds)}.{output_format}"
    )


def cleanup_temp_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def notify_progress(progress_callback: ProgressCallback | None, progress: int, message: str) -> None:
    if progress_callback is None:
        return

    progress_callback(max(0, min(100, int(progress))), message)


def resolve_ffmpeg_path() -> str:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def ydl_base_options(ffmpeg_path: str, *, noplaylist: bool = True) -> dict[str, object]:
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": noplaylist,
        "ffmpeg_location": ffmpeg_path,
    }


def normalize_info(info: dict[str, object]) -> dict[str, object]:
    if "entries" not in info:
        return info

    entries = info.get("entries") or []
    for entry in entries:
        if isinstance(entry, dict):
            return entry
    raise ExtractionRuntimeError("영상 메타데이터를 읽지 못했습니다.")


def probe_media_info(url: str, ffmpeg_path: str | None = None, *, noplaylist: bool = True) -> dict[str, object]:
    resolved_ffmpeg = ffmpeg_path or resolve_ffmpeg_path()
    with YoutubeDL(ydl_base_options(resolved_ffmpeg, noplaylist=noplaylist)) as ydl:
        info = ydl.extract_info(url, download=False)

    if not isinstance(info, dict):
        raise ExtractionRuntimeError("영상 메타데이터를 읽지 못했습니다.")

    return normalize_info(info) if noplaylist else info


def build_download_progress_hook(
    progress_callback: ProgressCallback | None,
    *,
    download_message: str,
    finished_message: str,
    start_progress: int = 15,
    end_progress: int = 80,
) -> Callable[[dict[str, object]], None]:
    def handle_progress(progress_data: dict[str, object]) -> None:
        status = progress_data.get("status")
        if status == "finished":
            notify_progress(progress_callback, end_progress, finished_message)
            return

        if status != "downloading":
            return

        downloaded_bytes = progress_data.get("downloaded_bytes")
        total_bytes = progress_data.get("total_bytes") or progress_data.get("total_bytes_estimate")
        if not isinstance(downloaded_bytes, (int, float)) or not isinstance(total_bytes, (int, float)) or total_bytes <= 0:
            notify_progress(progress_callback, start_progress, download_message)
            return

        ratio = max(0.0, min(float(downloaded_bytes) / float(total_bytes), 1.0))
        notify_progress(progress_callback, start_progress + int(ratio * (end_progress - start_progress)), download_message)

    return handle_progress


def collect_downloaded_file(work_dir: Path, expected_path: Path | None = None) -> Path:
    if expected_path is not None and expected_path.exists():
        return expected_path

    candidates = sorted(
        [entry for entry in work_dir.iterdir() if entry.is_file()],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise ExtractionRuntimeError("다운로드된 파일을 찾지 못했습니다.")
    return candidates[0]


def download_source_audio(
    url: str,
    work_dir: Path,
    ffmpeg_path: str,
    progress_callback: ProgressCallback | None = None,
) -> tuple[Path, dict[str, object]]:
    ydl_options = ydl_base_options(ffmpeg_path) | {
        "format": "bestaudio/best",
        "outtmpl": str(work_dir / "%(title)s.%(ext)s"),
        "progress_hooks": [
            build_download_progress_hook(
                progress_callback,
                download_message="원본 오디오를 다운로드하는 중입니다.",
                finished_message="다운로드가 끝났습니다. 변환을 시작합니다.",
            )
        ],
    }

    with YoutubeDL(ydl_options) as ydl:
        info = normalize_info(ydl.extract_info(url, download=True))
        expected_path = Path(ydl.prepare_filename(info))

    return collect_downloaded_file(work_dir, expected_path), info


def build_video_format_selector(quality: str) -> str:
    max_height = VIDEO_QUALITY_HEIGHTS[quality]
    return (
        f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={max_height}]+bestaudio/"
        f"best[height<={max_height}][ext=mp4]/"
        f"best[height<={max_height}]/best"
    )


def download_source_video(
    url: str,
    work_dir: Path,
    ffmpeg_path: str,
    quality: str,
    progress_callback: ProgressCallback | None = None,
) -> tuple[Path, dict[str, object]]:
    ydl_options = ydl_base_options(ffmpeg_path) | {
        "format": build_video_format_selector(quality),
        "merge_output_format": "mp4",
        "outtmpl": str(work_dir / "%(title)s.%(ext)s"),
        "progress_hooks": [
            build_download_progress_hook(
                progress_callback,
                download_message="원본 영상을 다운로드하는 중입니다.",
                finished_message="다운로드가 끝났습니다. 후처리를 시작합니다.",
                start_progress=12,
                end_progress=78,
            )
        ],
    }

    with YoutubeDL(ydl_options) as ydl:
        info = normalize_info(ydl.extract_info(url, download=True))
        expected_path = Path(ydl.prepare_filename(info))
        merged_path = expected_path.with_suffix(".mp4")

    expected = merged_path if merged_path.exists() else expected_path
    return collect_downloaded_file(work_dir, expected), info


def get_best_thumbnail_url(info: dict[str, object]) -> str | None:
    thumbnails = info.get("thumbnails")
    if isinstance(thumbnails, list):
        for thumbnail in reversed(thumbnails):
            if isinstance(thumbnail, dict) and thumbnail.get("url"):
                return str(thumbnail["url"])

    thumbnail = info.get("thumbnail")
    if isinstance(thumbnail, str) and thumbnail:
        return thumbnail
    return None


def download_thumbnail(info: dict[str, object], work_dir: Path) -> Path | None:
    thumbnail_url = get_best_thumbnail_url(info)
    if not thumbnail_url:
        return None

    parsed = urlparse(thumbnail_url)
    suffix = Path(parsed.path).suffix or ".jpg"
    output_path = work_dir / f"{sanitize_filename(str(info.get('title') or 'cover'))}_cover{suffix}"

    try:
        urllib.request.urlretrieve(thumbnail_url, output_path)
    except Exception:
        return None

    return output_path if output_path.exists() else None


def build_metadata_map(info: dict[str, object]) -> dict[str, str]:
    title = str(info.get("track") or info.get("title") or "YouTube Audio")
    artist = str(info.get("artist") or info.get("uploader") or info.get("channel") or "")
    album = str(info.get("album") or info.get("playlist_title") or info.get("channel") or "")
    album_artist = str(info.get("album_artist") or info.get("channel") or info.get("uploader") or "")
    date = str(info.get("release_date") or info.get("upload_date") or "")

    metadata = {
        "title": title,
        "artist": artist,
        "album": album,
        "album_artist": album_artist,
        "date": date,
        "comment": "Extracted with YouTube Multi Extractor",
    }
    return {key: value for key, value in metadata.items() if value}


def build_metadata_args(metadata: dict[str, str]) -> list[str]:
    args: list[str] = []
    for key, value in metadata.items():
        args.extend(["-metadata", f"{key}={value}"])
    return args


def decode_subprocess_output(payload: bytes) -> str:
    if not payload:
        return ""

    for encoding in ("utf-8", "cp949"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue

    return payload.decode("utf-8", errors="replace")


def run_ffmpeg(command: list[str], output_path: Path) -> None:
    completed = subprocess.run(command, capture_output=True, text=False, check=False)
    if completed.returncode != 0 or not output_path.exists():
        stderr_text = decode_subprocess_output(completed.stderr)
        error_lines = stderr_text.strip().splitlines()
        message = error_lines[-1] if error_lines else "ffmpeg 처리에 실패했습니다."
        raise ExtractionRuntimeError(message)


def build_audio_ffmpeg_command(
    ffmpeg_path: str,
    input_path: Path,
    output_path: Path,
    audio_format: AudioFormat,
    start_seconds: float | None,
    end_seconds: float | None,
    mp3_bitrate: str | None = None,
) -> list[str]:
    command = [ffmpeg_path, "-y", "-i", str(input_path)]

    if start_seconds is not None:
        command.extend(["-ss", seconds_to_ffmpeg_timestamp(float(start_seconds)) or "00:00:00.000"])

    if end_seconds is not None:
        if start_seconds is not None:
            command.extend(["-t", f"{max(end_seconds - start_seconds, 0.001):.3f}"])
        else:
            command.extend(["-to", seconds_to_ffmpeg_timestamp(float(end_seconds)) or "00:00:00.000"])

    match audio_format:
        case "mp3":
            resolved_mp3_bitrate = normalize_mp3_bitrate(mp3_bitrate)
            if resolved_mp3_bitrate is not None:
                command.extend(["-vn", "-c:a", "libmp3lame", "-b:a", resolved_mp3_bitrate])
            else:
                command.extend(["-vn", "-c:a", "libmp3lame", "-q:a", "2"])
        case "m4a":
            command.extend(["-vn", "-c:a", "aac", "-b:a", "192k", "-f", "ipod"])
        case "aac":
            command.extend(["-vn", "-c:a", "aac", "-b:a", "192k"])
        case "wav":
            command.extend(["-vn", "-c:a", "pcm_s16le"])
        case "opus":
            command.extend(["-vn", "-c:a", "libopus", "-b:a", "160k"])

    command.append(str(output_path))
    return command


def estimate_mp3_bytes_per_second(mp3_bitrate: str) -> float:
    normalized = normalize_mp3_bitrate(mp3_bitrate)
    if normalized is None:
        raise ExtractionInputError("MP3 bitrate is required.")
    return (int(normalized.rstrip("k")) * 1000) / 8


def build_split_chunk_plan(
    effective_duration_seconds: float,
    split_size_mb: int,
    mp3_bitrate: str,
) -> list[tuple[float, float]]:
    if effective_duration_seconds <= 0:
        return []

    normalized_split_size_mb = normalize_split_size_mb(split_size_mb)
    if normalized_split_size_mb is None:
        raise ExtractionInputError("Split size is required.")

    bytes_per_second = estimate_mp3_bytes_per_second(mp3_bitrate)
    safe_budget_bytes = max(
        1,
        int((normalized_split_size_mb * 1024 * 1024 * SPLIT_SIZE_SAFETY_RATIO) - SPLIT_SIZE_OVERHEAD_BYTES),
    )
    chunk_duration_seconds = max(1.0, safe_budget_bytes / bytes_per_second)

    plan: list[tuple[float, float]] = []
    chunk_start_seconds = 0.0
    while chunk_start_seconds < effective_duration_seconds:
        remaining_seconds = effective_duration_seconds - chunk_start_seconds
        chunk_length_seconds = min(chunk_duration_seconds, remaining_seconds)
        plan.append((chunk_start_seconds, chunk_length_seconds))
        chunk_start_seconds += chunk_length_seconds
    return plan


def build_split_part_name(download_name: str, part_index: int, part_count: int) -> str:
    stem = Path(download_name).stem
    width = max(2, len(str(part_count)))
    return f"{stem}_part{part_index:0{width}d}.mp3"


def build_split_archive_name(download_name: str, split_size_mb: int) -> str:
    stem = Path(download_name).stem
    return f"{stem}_split_{split_size_mb}mb.zip"


def package_split_outputs(archive_path: Path, part_paths: list[Path]) -> None:
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for part_path in part_paths:
            archive.write(part_path, arcname=part_path.name)


def extract_audio(
    options: ExtractionOptions,
    progress_callback: ProgressCallback | None = None,
) -> ExtractionResult:
    normalized_url = validate_youtube_url(options.url)
    if options.audio_format not in SUPPORTED_FORMATS:
        raise ExtractionInputError("지원하지 않는 오디오 형식입니다.")

    start_seconds = parse_time_to_seconds(options.start_time)
    end_seconds = parse_time_to_seconds(options.end_time)
    split_size_mb = normalize_split_size_mb(options.split_size_mb)
    resolved_mp3_bitrate = resolve_mp3_bitrate(options.audio_format, options.mp3_bitrate, split_size_mb)

    if options.audio_format != "mp3":
        if options.mp3_bitrate is not None:
            raise ExtractionInputError("MP3 bitrate is only available for MP3 output.")
        if split_size_mb is not None:
            raise ExtractionInputError("File splitting is only available for MP3 output.")

    temp_dir = Path(tempfile.mkdtemp(prefix="youtube-audio-"))
    ffmpeg_path = resolve_ffmpeg_path()

    try:
        notify_progress(progress_callback, 5, "영상 메타데이터를 확인하는 중입니다.")
        metadata = probe_media_info(normalized_url, ffmpeg_path)
        duration = metadata.get("duration")
        duration_seconds = float(duration) if isinstance(duration, (int, float)) else None
        validate_time_range(
            start_seconds,
            end_seconds,
            int(duration_seconds) if duration_seconds is not None else None,
        )
        validate_requested_range(start_seconds, end_seconds, duration_seconds)
        notify_progress(progress_callback, 15, "원본 오디오를 다운로드하는 중입니다.")

        source_path, downloaded_info = download_source_audio(
            normalized_url,
            temp_dir,
            ffmpeg_path,
            progress_callback=progress_callback,
        )
        title = str(downloaded_info.get("title") or metadata.get("title") or "youtube-audio")
        download_name = build_download_name(title, options.audio_format, start_seconds, end_seconds)
        output_path = temp_dir / download_name
        clip_start_seconds = float(start_seconds or 0)
        clip_end_seconds = float(end_seconds) if end_seconds is not None else duration_seconds
        effective_duration_seconds = (
            max(0.0, clip_end_seconds - clip_start_seconds) if clip_end_seconds is not None else None
        )
        if split_size_mb is not None:
            if effective_duration_seconds is None:
                raise ExtractionInputError("Audio duration is required when file splitting is enabled.")

            chunk_plan = build_split_chunk_plan(
                effective_duration_seconds,
                split_size_mb,
                resolved_mp3_bitrate or DEFAULT_SPLIT_MP3_BITRATE,
            )
            if len(chunk_plan) > 1:
                notify_progress(progress_callback, 84, "Splitting MP3 output into multiple files.")
                part_paths: list[Path] = []
                for index, (relative_start_seconds, chunk_duration_seconds) in enumerate(chunk_plan, start=1):
                    absolute_start_seconds = clip_start_seconds + relative_start_seconds
                    absolute_end_seconds = absolute_start_seconds + chunk_duration_seconds
                    part_path = temp_dir / build_split_part_name(download_name, index, len(chunk_plan))
                    command = build_audio_ffmpeg_command(
                        ffmpeg_path=ffmpeg_path,
                        input_path=source_path,
                        output_path=part_path,
                        audio_format=options.audio_format,
                        start_seconds=absolute_start_seconds,
                        end_seconds=absolute_end_seconds,
                        mp3_bitrate=resolved_mp3_bitrate,
                    )
                    run_ffmpeg(command, part_path)
                    part_paths.append(part_path)
                    notify_progress(
                        progress_callback,
                        84 + int((index / len(chunk_plan)) * 14),
                        f"Encoding split MP3 part {index}/{len(chunk_plan)}.",
                    )

                archive_name = build_split_archive_name(download_name, split_size_mb)
                archive_path = temp_dir / archive_name
                package_split_outputs(archive_path, part_paths)
                notify_progress(progress_callback, 100, "?ㅻ뵒??異붿텧???꾨즺?섏뿀?듬땲??")
                return ExtractionResult(
                    file_path=archive_path,
                    download_name=archive_name,
                    temp_dir=temp_dir,
                    media_type="application/zip",
                )

        notify_progress(progress_callback, 85, "오디오를 변환하는 중입니다.")
        command = build_audio_ffmpeg_command(
            ffmpeg_path=ffmpeg_path,
            input_path=source_path,
            output_path=output_path,
            audio_format=options.audio_format,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            mp3_bitrate=resolved_mp3_bitrate,
        )
        run_ffmpeg(command, output_path)

        notify_progress(progress_callback, 100, "오디오 추출이 완료되었습니다.")
        return ExtractionResult(
            file_path=output_path,
            download_name=download_name,
            temp_dir=temp_dir,
        )
    except (DownloadError, OSError) as exc:
        cleanup_temp_dir(temp_dir)
        raise ExtractionRuntimeError("YouTube 오디오 다운로드에 실패했습니다.") from exc
    except Exception:
        cleanup_temp_dir(temp_dir)
        raise


def build_song_ffmpeg_command(
    ffmpeg_path: str,
    input_path: Path,
    output_path: Path,
    metadata: dict[str, str],
    thumbnail_path: Path | None,
    start_seconds: int | None,
    end_seconds: int | None,
) -> list[str]:
    command = [ffmpeg_path, "-y", "-i", str(input_path)]

    if thumbnail_path is not None:
        command.extend(["-i", str(thumbnail_path)])

    if start_seconds is not None:
        command.extend(["-ss", seconds_to_ffmpeg_timestamp(float(start_seconds)) or "00:00:00.000"])

    if end_seconds is not None:
        if start_seconds is not None:
            command.extend(["-t", str(end_seconds - start_seconds)])
        else:
            command.extend(["-to", seconds_to_ffmpeg_timestamp(float(end_seconds)) or "00:00:00.000"])

    command.extend(["-map", "0:a:0"])

    if thumbnail_path is not None:
        command.extend(
            [
                "-map",
                "1:v:0",
                "-c:v",
                "mjpeg",
                "-disposition:v:0",
                "attached_pic",
                "-metadata:s:v",
                "title=Album cover",
                "-metadata:s:v",
                "comment=Cover (front)",
            ]
        )

    command.extend(["-c:a", "libmp3lame", "-q:a", "0", "-id3v2_version", "3"])
    command.extend(build_metadata_args(metadata))
    command.append(str(output_path))
    return command


def extract_song_mp3(
    options: SongExtractionOptions,
    progress_callback: ProgressCallback | None = None,
) -> ExtractionResult:
    normalized_url = validate_youtube_url(options.url)
    start_seconds = parse_time_to_seconds(options.start_time)
    end_seconds = parse_time_to_seconds(options.end_time)

    temp_dir = Path(tempfile.mkdtemp(prefix="youtube-song-"))
    ffmpeg_path = resolve_ffmpeg_path()

    try:
        notify_progress(progress_callback, 5, "음원 메타데이터를 확인하는 중입니다.")
        metadata = probe_media_info(normalized_url, ffmpeg_path)
        duration = metadata.get("duration")
        duration_seconds = float(duration) if isinstance(duration, (int, float)) else None
        validate_time_range(
            start_seconds,
            end_seconds,
            int(duration_seconds) if duration_seconds is not None else None,
        )
        validate_requested_range(start_seconds, end_seconds, duration_seconds)
        notify_progress(progress_callback, 12, "최고 음질 오디오를 다운로드하는 중입니다.")

        source_path, downloaded_info = download_source_audio(
            normalized_url,
            temp_dir,
            ffmpeg_path,
            progress_callback=progress_callback,
        )
        merged_info = metadata | downloaded_info
        title = str(merged_info.get("track") or merged_info.get("title") or "youtube-song")
        output_name = build_download_name(title, "mp3", start_seconds, end_seconds)
        output_path = temp_dir / output_name
        thumbnail_path = download_thumbnail(merged_info, temp_dir)
        ffmpeg_metadata = build_metadata_map(merged_info)

        notify_progress(progress_callback, 84, "MP3에 메타데이터와 앨범아트를 적용하는 중입니다.")
        command = build_song_ffmpeg_command(
            ffmpeg_path=ffmpeg_path,
            input_path=source_path,
            output_path=output_path,
            metadata=ffmpeg_metadata,
            thumbnail_path=thumbnail_path,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        )
        run_ffmpeg(command, output_path)

        notify_progress(progress_callback, 100, "노래 MP3 추출이 완료되었습니다.")
        return ExtractionResult(
            file_path=output_path,
            download_name=output_name,
            temp_dir=temp_dir,
        )
    except (DownloadError, OSError) as exc:
        cleanup_temp_dir(temp_dir)
        raise ExtractionRuntimeError("노래 MP3 추출 중 다운로드에 실패했습니다.") from exc
    except Exception:
        cleanup_temp_dir(temp_dir)
        raise
