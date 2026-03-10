from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from yt_dlp.utils import DownloadError

from app.services.extractor import (
    ExtractionInputError,
    ExtractionResult,
    ExtractionRuntimeError,
    ProgressCallback,
    SUPPORTED_VIDEO_QUALITIES,
    build_download_name,
    cleanup_temp_dir,
    download_source_video,
    notify_progress,
    parse_time_to_seconds,
    probe_media_info,
    resolve_ffmpeg_path,
    run_ffmpeg,
    sanitize_filename,
    seconds_to_label,
    seconds_to_ffmpeg_timestamp,
    validate_requested_range,
    validate_time_range,
    validate_youtube_url,
)


@dataclass(slots=True)
class VideoExtractionOptions:
    url: str
    video_quality: str = "1080p"
    start_time: str | None = None
    end_time: str | None = None


def build_video_download_name(
    title: str,
    video_quality: str,
    start_seconds: int | None,
    end_seconds: int | None,
) -> str:
    safe_title = sanitize_filename(title)
    if start_seconds is None and end_seconds is None:
        return build_download_name(f"{safe_title}_{video_quality}", "mp4", None, None)

    return (
        f"{safe_title}_{video_quality}_{seconds_to_label(start_seconds)}"
        f"_to_{seconds_to_label(end_seconds)}.mp4"
    )


def build_video_ffmpeg_command(
    ffmpeg_path: str,
    input_path: Path,
    output_path: Path,
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

    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return command


def extract_video(
    options: VideoExtractionOptions,
    progress_callback: ProgressCallback | None = None,
) -> ExtractionResult:
    normalized_url = validate_youtube_url(options.url)
    if options.video_quality not in SUPPORTED_VIDEO_QUALITIES:
        raise ExtractionInputError("지원하지 않는 화질입니다.")

    start_seconds = parse_time_to_seconds(options.start_time)
    end_seconds = parse_time_to_seconds(options.end_time)

    temp_dir = Path(tempfile.mkdtemp(prefix="youtube-video-"))
    ffmpeg_path = resolve_ffmpeg_path()

    try:
        notify_progress(progress_callback, 4, "영상 메타데이터를 확인하는 중입니다.")
        metadata = probe_media_info(normalized_url, ffmpeg_path)
        duration = metadata.get("duration")
        duration_seconds = float(duration) if isinstance(duration, (int, float)) else None
        validate_time_range(
            start_seconds,
            end_seconds,
            int(duration_seconds) if duration_seconds is not None else None,
        )
        validate_requested_range(start_seconds, end_seconds, duration_seconds)
        notify_progress(progress_callback, 12, "선택한 화질로 영상을 다운로드하는 중입니다.")

        source_path, downloaded_info = download_source_video(
            normalized_url,
            temp_dir,
            ffmpeg_path,
            options.video_quality,
            progress_callback=progress_callback,
        )
        title = str(downloaded_info.get("title") or metadata.get("title") or "youtube-video")
        output_name = build_video_download_name(title, options.video_quality, start_seconds, end_seconds)
        output_path = temp_dir / output_name

        if start_seconds is None and end_seconds is None and source_path.suffix.lower() == ".mp4":
            if source_path != output_path:
                shutil.move(str(source_path), output_path)
            notify_progress(progress_callback, 100, "영상 추출이 완료되었습니다.")
            return ExtractionResult(
                file_path=output_path,
                download_name=output_name,
                temp_dir=temp_dir,
                media_type="video/mp4",
            )

        notify_progress(progress_callback, 84, "영상 후처리를 진행하는 중입니다.")
        command = build_video_ffmpeg_command(
            ffmpeg_path=ffmpeg_path,
            input_path=source_path,
            output_path=output_path,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        )
        run_ffmpeg(command, output_path)

        notify_progress(progress_callback, 100, "영상 추출이 완료되었습니다.")
        return ExtractionResult(
            file_path=output_path,
            download_name=output_name,
            temp_dir=temp_dir,
            media_type="video/mp4",
        )
    except (DownloadError, OSError) as exc:
        cleanup_temp_dir(temp_dir)
        raise ExtractionRuntimeError("영상 다운로드에 실패했습니다.") from exc
    except Exception:
        cleanup_temp_dir(temp_dir)
        raise
