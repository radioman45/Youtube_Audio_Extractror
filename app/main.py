from __future__ import annotations

import threading
from pathlib import Path
import sys

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from app.models import ExtractRequest, JobRequest, SubtitleRequest
from app.services.batch_extractor import BatchExtractionOptions, extract_batch
from app.services.extraction_jobs import ExtractionJobStore
from app.services.extractor import (
    SUPPORTED_FORMATS,
    SUPPORTED_VIDEO_QUALITIES,
    ExtractionInputError,
    ExtractionOptions,
    ExtractionResult,
    ExtractionRuntimeError,
    SongExtractionOptions,
    cleanup_temp_dir,
    extract_audio,
    extract_song_mp3,
)
from app.services.subtitle_extractor import SubtitleOptions, extract_subtitles
from app.services.video_extractor import VideoExtractionOptions, extract_video

def resolve_static_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "app" / "static"
    return Path(__file__).resolve().parent / "static"


STATIC_DIR = resolve_static_dir()
job_store = ExtractionJobStore()

app = FastAPI(
    title="YouTube Multi Extractor",
    version="2.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def build_download_response(result: ExtractionResult, job_id: str) -> FileResponse:
    return FileResponse(
        path=result.file_path,
        media_type=result.media_type,
        filename=result.download_name,
        background=BackgroundTask(job_store.delete_job, job_id),
    )


def get_job_or_404(job_id: str, download_path_template: str) -> dict[str, object]:
    job = job_store.get_response(job_id, download_path_template=download_path_template)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


def dispatch_job(job_id: str, payload: JobRequest) -> None:
    batch_details = {
        "taskType": payload.task_type,
        "batchMode": payload.batch_mode,
        "total": 0,
        "completed": 0,
        "failed": 0,
    }
    latest_batch_message = "배치 작업을 준비하는 중입니다."

    try:
        if payload.task_type == "audio":
            result = extract_audio(
                ExtractionOptions(
                    url=payload.url,
                    audio_format=payload.audio_format,  # type: ignore[arg-type]
                    start_time=payload.start_time,
                    end_time=payload.end_time,
                ),
                progress_callback=lambda progress, message: job_store.update_progress(job_id, progress, message),
            )
            success_message = "오디오 추출이 완료되었습니다."
            details = {"taskType": payload.task_type}
        elif payload.task_type == "song_mp3":
            result = extract_song_mp3(
                SongExtractionOptions(
                    url=payload.url,
                    start_time=payload.start_time,
                    end_time=payload.end_time,
                ),
                progress_callback=lambda progress, message: job_store.update_progress(job_id, progress, message),
            )
            success_message = "노래 MP3 추출이 완료되었습니다."
            details = {"taskType": payload.task_type}
        elif payload.task_type == "video":
            result = extract_video(
                VideoExtractionOptions(
                    url=payload.url,
                    video_quality=payload.video_quality,
                    start_time=payload.start_time,
                    end_time=payload.end_time,
                ),
                progress_callback=lambda progress, message: job_store.update_progress(job_id, progress, message),
            )
            success_message = "영상 추출이 완료되었습니다."
            details = {"taskType": payload.task_type}
        elif payload.task_type == "subtitle":
            job_store.update_progress(job_id, 10, "자막을 준비하는 중입니다.")
            result = extract_subtitles(
                SubtitleOptions(
                    url=payload.url,
                    subtitle_language=payload.subtitle_language,
                    start_time=payload.start_time,
                    end_time=payload.end_time,
                )
            )
            success_message = "자막 추출이 완료되었습니다."
            details = {"taskType": payload.task_type}
        elif payload.task_type == "batch":
            def batch_progress(progress: int, message: str) -> None:
                nonlocal latest_batch_message
                latest_batch_message = message
                job_store.update_progress(job_id, progress, message, batch_details)

            def batch_status(total: int, completed: int, failed: int) -> None:
                batch_details.update({"total": total, "completed": completed, "failed": failed})
                job_store.update_progress(job_id, 1, latest_batch_message, batch_details)

            result = extract_batch(
                BatchExtractionOptions(
                    url=payload.url,
                    batch_mode=payload.batch_mode or "audio",
                    audio_format=payload.audio_format,
                    video_quality=payload.video_quality,
                    subtitle_language=payload.subtitle_language,
                    start_time=payload.start_time,
                    end_time=payload.end_time,
                ),
                progress_callback=batch_progress,
                status_callback=batch_status,
            )
            success_message = "배치 다운로드가 완료되었습니다."
            details = batch_details | {"taskType": payload.task_type}
        else:
            raise ExtractionInputError("지원하지 않는 작업 유형입니다.")
    except ExtractionInputError as exc:
        job_store.fail_job(job_id, str(exc), details=batch_details if payload.task_type == "batch" else None)
    except ExtractionRuntimeError as exc:
        job_store.fail_job(job_id, str(exc), details=batch_details if payload.task_type == "batch" else None)
    except Exception:
        job_store.fail_job(
            job_id,
            "작업 중 예기치 않은 오류가 발생했습니다.",
            details=batch_details if payload.task_type == "batch" else None,
        )
    else:
        job_store.complete_job(job_id, result, message=success_message, details=details)


def run_audio_job(job_id: str, payload: ExtractRequest) -> None:
    try:
        result = extract_audio(
            ExtractionOptions(
                url=payload.url,
                audio_format=payload.audio_format,  # type: ignore[arg-type]
                start_time=payload.start_time,
                end_time=payload.end_time,
            ),
            progress_callback=lambda progress, message: job_store.update_progress(job_id, progress, message),
        )
    except ExtractionInputError as exc:
        job_store.fail_job(job_id, str(exc))
    except ExtractionRuntimeError as exc:
        job_store.fail_job(job_id, str(exc))
    except Exception:
        job_store.fail_job(job_id, "작업 중 예기치 않은 오류가 발생했습니다.")
    else:
        job_store.complete_job(job_id, result, message="오디오 추출이 완료되었습니다.", details={"taskType": "audio"})


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def healthcheck() -> dict[str, object]:
    return {
        "ok": True,
        "name": "YouTube Multi Extractor",
        "formats": list(SUPPORTED_FORMATS),
        "audioFormats": list(SUPPORTED_FORMATS),
        "videoQualities": list(SUPPORTED_VIDEO_QUALITIES),
        "taskTypes": ["audio", "song_mp3", "video", "subtitle", "batch"],
        "batchModes": ["audio", "song_mp3", "video", "subtitle"],
    }


@app.post("/api/jobs", status_code=202)
def create_job(payload: JobRequest) -> dict[str, object]:
    details = {"taskType": payload.task_type}
    if payload.task_type == "batch":
        details.update({"batchMode": payload.batch_mode, "total": 0, "completed": 0, "failed": 0})

    job = job_store.create_job(
        message="작업을 준비하는 중입니다.",
        details=details,
        download_path_template="/api/jobs/{job_id}/download",
    )
    threading.Thread(
        target=dispatch_job,
        args=(str(job["jobId"]), payload),
        daemon=True,
    ).start()
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, object]:
    return get_job_or_404(job_id, "/api/jobs/{job_id}/download")


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str) -> FileResponse:
    result = job_store.get_result(job_id)
    if result is None:
        get_job_or_404(job_id, "/api/jobs/{job_id}/download")
        raise HTTPException(status_code=409, detail="The job is not ready yet.")
    return build_download_response(result, job_id)


@app.post("/api/extract/jobs", status_code=202)
def create_extract_job(payload: ExtractRequest) -> dict[str, object]:
    job = job_store.create_job(
        message="오디오 작업을 준비하는 중입니다.",
        details={"taskType": "audio"},
        download_path_template="/api/extract/jobs/{job_id}/download",
    )
    threading.Thread(
        target=run_audio_job,
        args=(str(job["jobId"]), payload),
        daemon=True,
    ).start()
    return job


@app.get("/api/extract/jobs/{job_id}")
def get_extract_job(job_id: str) -> dict[str, object]:
    return get_job_or_404(job_id, "/api/extract/jobs/{job_id}/download")


@app.get("/api/extract/jobs/{job_id}/download")
def download_extract_job(job_id: str) -> FileResponse:
    result = job_store.get_result(job_id)
    if result is None:
        get_job_or_404(job_id, "/api/extract/jobs/{job_id}/download")
        raise HTTPException(status_code=409, detail="Extraction is not ready yet.")
    return build_download_response(result, job_id)


@app.post("/api/subtitles")
def extract_subtitles_endpoint(payload: SubtitleRequest) -> FileResponse:
    try:
        result = extract_subtitles(
            SubtitleOptions(
                url=payload.url,
                subtitle_language=payload.subtitle_language,
                start_time=payload.start_time,
                end_time=payload.end_time,
            )
        )
    except ExtractionInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExtractionRuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return FileResponse(
        path=result.file_path,
        media_type=result.media_type,
        filename=result.download_name,
        background=BackgroundTask(cleanup_temp_dir, result.temp_dir),
    )


@app.post("/api/extract")
def extract_endpoint(payload: ExtractRequest) -> FileResponse:
    try:
        result = extract_audio(
            ExtractionOptions(
                url=payload.url,
                audio_format=payload.audio_format,  # type: ignore[arg-type]
                start_time=payload.start_time,
                end_time=payload.end_time,
            )
        )
    except ExtractionInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExtractionRuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return FileResponse(
        path=result.file_path,
        media_type=result.media_type,
        filename=result.download_name,
        background=BackgroundTask(cleanup_temp_dir, result.temp_dir),
    )


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
