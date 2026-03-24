from __future__ import annotations

import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.services.extractor import (
    ExtractionInputError,
    ExtractionOptions,
    ExtractionResult,
    ExtractionRuntimeError,
    SongExtractionOptions,
    SUPPORTED_VIDEO_QUALITIES,
    SUPPORTED_FORMATS,
    ProgressCallback,
    cleanup_temp_dir,
    notify_progress,
    resolve_ffmpeg_path,
    sanitize_filename,
    validate_youtube_url,
    ydl_base_options,
    extract_audio,
    extract_song_mp3,
)
from app.services.subtitle_extractor import SubtitleOptions, extract_subtitles
from app.services.video_extractor import VideoExtractionOptions, extract_video


BatchOperation = str
BatchStatusCallback = Callable[[int, int, int], None]


@dataclass(slots=True)
class BatchExtractionOptions:
    url: str
    batch_mode: BatchOperation
    audio_format: str = "mp3"
    mp3_bitrate: str | None = None
    split_size_mb: int | None = None
    video_quality: str = "1080p"
    subtitle_language: str = "ko"
    subtitle_format: str = "timestamped"
    start_time: str | None = None
    end_time: str | None = None


def resolve_entry_url(entry: dict[str, object]) -> str | None:
    webpage_url = entry.get("webpage_url")
    if isinstance(webpage_url, str) and webpage_url.startswith("http"):
        return webpage_url

    raw_url = entry.get("url")
    if isinstance(raw_url, str) and raw_url.startswith("http"):
        return raw_url

    if isinstance(raw_url, str) and raw_url:
        return f"https://www.youtube.com/watch?v={raw_url}"

    entry_id = entry.get("id")
    if isinstance(entry_id, str) and entry_id:
        return f"https://www.youtube.com/watch?v={entry_id}"

    return None


def list_collection_entries(url: str) -> tuple[str, list[dict[str, object]]]:
    ffmpeg_path = resolve_ffmpeg_path()
    options = ydl_base_options(ffmpeg_path, noplaylist=False) | {
        "extract_flat": "in_playlist",
        "skip_download": True,
    }

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if not isinstance(info, dict):
        raise ExtractionRuntimeError("재생목록 또는 채널 정보를 읽지 못했습니다.")

    raw_entries = info.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ExtractionInputError("재생목록 또는 채널 URL을 입력해 주세요.")

    entries = [entry for entry in raw_entries if isinstance(entry, dict) and resolve_entry_url(entry)]
    if not entries:
        raise ExtractionInputError("처리할 항목을 찾지 못했습니다.")

    title = str(info.get("title") or info.get("uploader") or info.get("channel") or "youtube-batch")
    return title, entries


def ensure_unique_path(directory: Path, filename: str) -> Path:
    base = Path(filename)
    candidate = directory / base.name
    index = 1
    while candidate.exists():
        candidate = directory / f"{base.stem}_{index}{base.suffix}"
        index += 1
    return candidate


def write_batch_report(report_path: Path, total: int, completed: int, failed_items: list[str]) -> None:
    lines = [
        "YouTube Multi Extractor 배치 작업 보고서",
        f"총 항목: {total}",
        f"성공: {completed}",
        f"실패: {len(failed_items)}",
        "",
    ]
    if failed_items:
        lines.append("실패 항목")
        lines.extend(failed_items)
    else:
        lines.append("실패 항목 없음")

    report_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def extract_batch(
    options: BatchExtractionOptions,
    progress_callback: ProgressCallback | None = None,
    status_callback: BatchStatusCallback | None = None,
) -> ExtractionResult:
    normalized_url = validate_youtube_url(options.url)
    if options.batch_mode == "audio" and options.audio_format not in SUPPORTED_FORMATS:
        raise ExtractionInputError("지원하지 않는 오디오 형식입니다.")
    if options.batch_mode == "video" and options.video_quality not in SUPPORTED_VIDEO_QUALITIES:
        raise ExtractionInputError("지원하지 않는 화질입니다.")

    temp_dir = Path(tempfile.mkdtemp(prefix="youtube-batch-"))
    output_dir = temp_dir / "files"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        notify_progress(progress_callback, 2, "재생목록 또는 채널 목록을 불러오는 중입니다.")
        collection_title, entries = list_collection_entries(normalized_url)
        total = len(entries)
        completed = 0
        failed = 0
        failed_items: list[str] = []

        if status_callback is not None:
            status_callback(total, completed, failed)

        for index, entry in enumerate(entries, start=1):
            entry_url = resolve_entry_url(entry)
            if entry_url is None:
                failed += 1
                failed_items.append(f"{index}. URL 확인 실패")
                if status_callback is not None:
                    status_callback(total, completed, failed)
                continue

            entry_title = str(entry.get("title") or f"항목 {index}")
            start_progress = 5 + int(((index - 1) / total) * 88)
            end_progress = 5 + int((index / total) * 88)

            def item_progress(progress: int, message: str) -> None:
                scaled = start_progress + int((max(0, min(100, progress)) / 100) * (end_progress - start_progress))
                notify_progress(progress_callback, scaled, f"[{index}/{total}] {entry_title}: {message}")

            try:
                if options.batch_mode == "audio":
                    result = extract_audio(
                        ExtractionOptions(
                            url=entry_url,
                            audio_format=options.audio_format,  # type: ignore[arg-type]
                            start_time=options.start_time,
                            end_time=options.end_time,
                            mp3_bitrate=options.mp3_bitrate,
                            split_size_mb=options.split_size_mb,
                        ),
                        progress_callback=item_progress,
                    )
                elif options.batch_mode == "song_mp3":
                    result = extract_song_mp3(
                        SongExtractionOptions(
                            url=entry_url,
                            start_time=options.start_time,
                            end_time=options.end_time,
                        ),
                        progress_callback=item_progress,
                    )
                elif options.batch_mode == "video":
                    result = extract_video(
                        VideoExtractionOptions(
                            url=entry_url,
                            video_quality=options.video_quality,
                            start_time=options.start_time,
                            end_time=options.end_time,
                        ),
                        progress_callback=item_progress,
                    )
                elif options.batch_mode == "subtitle":
                    result = extract_subtitles(
                        SubtitleOptions(
                            url=entry_url,
                            subtitle_language=options.subtitle_language,
                            subtitle_format=options.subtitle_format,
                            start_time=options.start_time,
                            end_time=options.end_time,
                        )
                    )
                else:
                    raise ExtractionInputError("지원하지 않는 배치 작업 유형입니다.")

                destination = ensure_unique_path(output_dir, result.download_name)
                shutil.move(str(result.file_path), destination)
                cleanup_temp_dir(result.temp_dir)
                completed += 1
            except Exception as exc:
                failed += 1
                failed_items.append(f"{index}. {entry_title}: {exc}")
            finally:
                if status_callback is not None:
                    status_callback(total, completed, failed)

        if completed == 0:
            raise ExtractionRuntimeError("모든 항목 처리에 실패했습니다.")

        report_path = temp_dir / "batch-report.txt"
        write_batch_report(report_path, total, completed, failed_items)

        zip_name = f"{sanitize_filename(collection_title)}_{options.batch_mode}.zip"
        zip_path = temp_dir / zip_name
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in sorted(output_dir.iterdir()):
                archive.write(file_path, arcname=file_path.name)
            archive.write(report_path, arcname=report_path.name)

        notify_progress(progress_callback, 100, "배치 다운로드가 완료되었습니다.")
        return ExtractionResult(
            file_path=zip_path,
            download_name=zip_name,
            temp_dir=temp_dir,
            media_type="application/zip",
        )
    except (DownloadError, OSError) as exc:
        cleanup_temp_dir(temp_dir)
        raise ExtractionRuntimeError("배치 다운로드 중 목록 조회에 실패했습니다.") from exc
    except Exception:
        cleanup_temp_dir(temp_dir)
        raise
