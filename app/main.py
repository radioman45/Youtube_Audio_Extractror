from __future__ import annotations

import os
import shutil
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from app.models import ExtractRequest, JobRequest, SubtitleRequest
from app.services.app_state import get_job_work_dir
from app.services.batch_extractor import BatchExtractionOptions, extract_batch
from app.services.colab_transcription import (
    COLAB_BUNDLE_FILENAME,
    COLAB_HOME_URL,
    COLAB_NOTEBOOK_FILENAME,
    COLAB_RESULT_FILENAME,
    create_colab_job_bundle,
    build_colab_notebook_payload,
    import_colab_result_package,
)
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
from app.services.subtitle_extractor import SUPPORTED_SUBTITLE_FORMATS, SubtitleOptions, extract_subtitles
from app.services.video_extractor import VideoExtractionOptions, extract_video
from app.services.whisper_subtitle_extractor import (
    LocalWhisperSubtitleOptions,
    SUPPORTED_SUBTITLE_ENGINES,
    SUPPORTED_WHISPER_DEVICES,
    SUPPORTED_WHISPER_MODELS,
    WhisperSubtitleOptions,
    extract_whisper_subtitles,
    extract_whisper_subtitles_from_file,
    normalize_local_whisper_options,
    validate_upload_audio_filename,
)


def resolve_static_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "app" / "static"
    return Path(__file__).resolve().parent / "static"


STATIC_DIR = resolve_static_dir()
job_store = ExtractionJobStore()


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    if should_resume_jobs_on_startup():
        resume_pending_jobs()
    yield


app = FastAPI(
    title="YouTube Multi Extractor",
    version="2.0.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=app_lifespan,
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


def should_resume_jobs_on_startup() -> bool:
    if os.environ.get("APP_ENABLE_JOB_RECOVERY", "1") == "0":
        return False
    if "pytest" in sys.modules:
        return False
    return True


def build_whisper_resume_details(
    *,
    work_dir: Path,
    model: str,
    whisper_device: str,
    language: str,
    subtitle_format: str,
    vad_filter: bool,
    start_time: str | None,
    end_time: str | None,
    subtitle_source: str,
    url: str | None = None,
    source_name: str | None = None,
    source_path: Path | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "taskType": "subtitle",
        "subtitleEngine": "whisper",
        "whisperRuntime": "local",
        "subtitleSource": subtitle_source,
        "resumeSupported": True,
        "workDir": str(work_dir),
        "whisperModel": model,
        "whisperDevice": whisper_device,
        "subtitleLanguage": language,
        "subtitleFormat": subtitle_format,
        "vadFilter": vad_filter,
        "startTime": start_time,
        "endTime": end_time,
    }
    if url:
        payload["url"] = url
    if source_name:
        payload["sourceName"] = source_name
    if source_path is not None:
        payload["sourcePath"] = str(source_path)
    return payload


def build_colab_job_details(
    *,
    job_id: str,
    work_dir: Path,
    source_name: str,
    source_path: Path,
    bundle_download_name: str,
    source_sha256: str,
    result_name: str,
    options: LocalWhisperSubtitleOptions,
) -> dict[str, object]:
    return {
        "taskType": "subtitle",
        "subtitleEngine": "whisper",
        "whisperRuntime": "colab",
        "subtitleSource": "upload",
        "resumeSupported": False,
        "workDir": str(work_dir),
        "sourceName": source_name,
        "sourcePath": str(source_path),
        "whisperModel": options.model,
        "whisperDevice": options.device,
        "subtitleLanguage": options.language,
        "subtitleFormat": options.subtitle_format,
        "vadFilter": options.vad_filter,
        "startTime": options.start_time,
        "endTime": options.end_time,
        "sourceSha256": source_sha256,
        "bundleDownloadUrl": f"/api/subtitles/colab/jobs/{job_id}/bundle",
        "bundleFilename": bundle_download_name,
        "resultUploadUrl": f"/api/subtitles/colab/jobs/{job_id}/complete",
        "notebookDownloadUrl": "/api/subtitles/colab/notebook",
        "colabHomeUrl": COLAB_HOME_URL,
        "colabResultName": result_name,
    }


def store_uploaded_source_file(work_dir: Path, upload: UploadFile, source_name: str) -> Path:
    suffix = Path(source_name).suffix.lower()
    source_path = work_dir / f"uploaded-source{suffix}"
    with source_path.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)
    return source_path


def start_background_job(target, *args) -> None:
    threading.Thread(
        target=target,
        args=args,
        daemon=True,
    ).start()


def dispatch_job(job_id: str, payload: JobRequest) -> None:
    batch_details = {
        "taskType": payload.task_type,
        "batchMode": payload.batch_mode,
        "total": 0,
        "completed": 0,
        "failed": 0,
    }
    latest_batch_message = "Batch job is being prepared."

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
            success_message = "Audio extraction completed."
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
            success_message = "Song MP3 extraction completed."
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
            success_message = "Video extraction completed."
            details = {"taskType": payload.task_type}
        elif payload.task_type == "subtitle":
            job_store.update_progress(job_id, 10, "Preparing subtitle extraction.")
            if payload.subtitle_engine == "whisper":
                result = extract_whisper_subtitles(
                    WhisperSubtitleOptions(
                        url=payload.url,
                        model=payload.whisper_model,
                        language=payload.subtitle_language,
                        subtitle_format=payload.subtitle_format,
                        device=payload.whisper_device,
                        vad_filter=payload.vad_filter,
                        start_time=payload.start_time,
                        end_time=payload.end_time,
                    ),
                    progress_callback=lambda progress, message: job_store.update_progress(job_id, progress, message),
                )
                success_message = "Whisper subtitle extraction completed."
            else:
                result = extract_subtitles(
                    SubtitleOptions(
                        url=payload.url,
                        subtitle_language=payload.subtitle_language,
                        subtitle_format=payload.subtitle_format,
                        start_time=payload.start_time,
                        end_time=payload.end_time,
                    )
                )
                success_message = "Subtitle extraction completed."
            details = {
                "taskType": payload.task_type,
                "subtitleEngine": payload.subtitle_engine,
                "subtitleFormat": payload.subtitle_format,
            }
            if payload.subtitle_engine == "whisper":
                details["whisperDevice"] = payload.whisper_device
                details["whisperRuntime"] = "local"
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
                    subtitle_format=payload.subtitle_format,
                    start_time=payload.start_time,
                    end_time=payload.end_time,
                ),
                progress_callback=batch_progress,
                status_callback=batch_status,
            )
            success_message = "Batch download completed."
            details = batch_details | {"taskType": payload.task_type}
        else:
            raise ExtractionInputError("Unsupported task type.")
    except ExtractionInputError as exc:
        job_store.fail_job(job_id, str(exc), details=batch_details if payload.task_type == "batch" else None)
    except ExtractionRuntimeError as exc:
        job_store.fail_job(job_id, str(exc), details=batch_details if payload.task_type == "batch" else None)
    except Exception:
        job_store.fail_job(
            job_id,
            "An unexpected error occurred while processing the request.",
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
        job_store.fail_job(job_id, "An unexpected error occurred while processing the request.")
    else:
        job_store.complete_job(job_id, result, message="Audio extraction completed.", details={"taskType": "audio"})


def run_whisper_url_job(
    job_id: str,
    options: WhisperSubtitleOptions,
    work_dir: Path,
) -> None:
    try:
        result = extract_whisper_subtitles(
            options,
            progress_callback=lambda progress, message: job_store.update_progress(job_id, progress, message),
            temp_dir=work_dir,
            resume_state_callback=lambda details: job_store.merge_details(job_id, details),
        )
    except ExtractionInputError as exc:
        job_store.fail_job(job_id, str(exc))
    except ExtractionRuntimeError as exc:
        job_store.fail_job(job_id, str(exc))
    except Exception as exc:
        job_store.fail_job(job_id, f"An unexpected error occurred while processing the request: {exc}")
    else:
        job_store.complete_job(
            job_id,
            result,
            message="Whisper subtitle extraction completed.",
            details={
                "taskType": "subtitle",
                "subtitleEngine": "whisper",
                "whisperRuntime": "local",
                "subtitleSource": "youtube_url",
                "subtitleFormat": options.subtitle_format,
                "whisperDevice": options.device,
            },
        )


def run_uploaded_whisper_job(
    job_id: str,
    source_path: Path,
    source_name: str,
    options: LocalWhisperSubtitleOptions,
    temp_dir: Path,
) -> None:
    try:
        result = extract_whisper_subtitles_from_file(
            source_path,
            source_name,
            options,
            temp_dir=temp_dir,
            progress_callback=lambda progress, message: job_store.update_progress(job_id, progress, message),
            resume_state_callback=lambda details: job_store.merge_details(job_id, details),
        )
    except ExtractionInputError as exc:
        job_store.fail_job(job_id, str(exc))
    except ExtractionRuntimeError as exc:
        job_store.fail_job(job_id, str(exc))
    except Exception as exc:
        job_store.fail_job(job_id, f"An unexpected error occurred while processing the uploaded audio: {exc}")
    else:
        job_store.complete_job(
            job_id,
            result,
            message="Whisper subtitle extraction completed.",
            details={
                "taskType": "subtitle",
                "subtitleEngine": "whisper",
                "whisperRuntime": "local",
                "subtitleSource": "upload",
                "subtitleFormat": options.subtitle_format,
                "whisperDevice": options.device,
            },
        )


def resume_pending_jobs() -> None:
    for job in job_store.list_jobs(statuses={"queued", "processing"}):
        details = job.details
        if not details.get("resumeSupported"):
            job_store.fail_job(job.job_id, "This in-progress job cannot be resumed after app restart.")
            continue

        if details.get("taskType") != "subtitle" or details.get("subtitleEngine") != "whisper":
            job_store.fail_job(job.job_id, "This in-progress job cannot be resumed after app restart.")
            continue

        work_dir_value = details.get("workDir")
        if not isinstance(work_dir_value, str) or not work_dir_value:
            job_store.fail_job(job.job_id, "The resumable job is missing its working directory.")
            continue

        work_dir = Path(work_dir_value)
        job_store.update_progress(job.job_id, max(job.progress, 1), "Recovering Whisper job after app restart.", {"recovered": True})

        if details.get("subtitleSource") == "upload":
            source_name = str(details.get("sourceName") or "uploaded-audio")
            source_path_value = details.get("sourcePath")
            source_path = Path(str(source_path_value)) if source_path_value else work_dir / "missing-source"
            start_background_job(
                run_uploaded_whisper_job,
                job.job_id,
                source_path,
                source_name,
                LocalWhisperSubtitleOptions(
                    model=str(details.get("whisperModel") or "base"),
                    language=str(details.get("subtitleLanguage") or "ko"),
                    subtitle_format=str(details.get("subtitleFormat") or "timestamped"),
                    device=str(details.get("whisperDevice") or "auto"),
                    vad_filter=bool(details.get("vadFilter", True)),
                    start_time=str(details.get("startTime")) if details.get("startTime") is not None else None,
                    end_time=str(details.get("endTime")) if details.get("endTime") is not None else None,
                ),
                work_dir,
            )
            continue

        start_background_job(
            run_whisper_url_job,
            job.job_id,
            WhisperSubtitleOptions(
                url=str(details.get("url") or ""),
                model=str(details.get("whisperModel") or "base"),
                language=str(details.get("subtitleLanguage") or "ko"),
                subtitle_format=str(details.get("subtitleFormat") or "timestamped"),
                device=str(details.get("whisperDevice") or "auto"),
                vad_filter=bool(details.get("vadFilter", True)),
                start_time=str(details.get("startTime")) if details.get("startTime") is not None else None,
                end_time=str(details.get("endTime")) if details.get("endTime") is not None else None,
            ),
            work_dir,
        )


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
        "subtitleEngines": list(SUPPORTED_SUBTITLE_ENGINES),
        "subtitleFormats": list(SUPPORTED_SUBTITLE_FORMATS),
        "whisperModels": list(SUPPORTED_WHISPER_MODELS),
        "whisperDevices": list(SUPPORTED_WHISPER_DEVICES),
        "whisperRuntimes": ["local", "colab"],
        "subtitleSources": ["youtube_url", "audio_file"],
        "colab": {
            "enabled": True,
            "homeUrl": COLAB_HOME_URL,
            "notebookFilename": COLAB_NOTEBOOK_FILENAME,
            "uploadOnly": True,
        },
        "recommendedWhisperModels": {
            "default": "base",
            "longVideo": "base",
            "balanced": "small",
            "highSpec": "large-v3-turbo",
        },
    }


@app.post("/api/jobs", status_code=202)
def create_job(payload: JobRequest) -> dict[str, object]:
    details = {"taskType": payload.task_type}
    if payload.task_type == "subtitle":
        details["subtitleEngine"] = payload.subtitle_engine
        details["subtitleFormat"] = payload.subtitle_format
        if payload.subtitle_engine == "whisper":
            details["whisperDevice"] = payload.whisper_device
            details["whisperRuntime"] = "local"
    if payload.task_type == "batch":
        details.update({"batchMode": payload.batch_mode, "total": 0, "completed": 0, "failed": 0})

    job = job_store.create_job(
        message="Job is being prepared.",
        details=details,
        download_path_template="/api/jobs/{job_id}/download",
    )
    job_id = str(job["jobId"])

    if payload.task_type == "subtitle" and payload.subtitle_engine == "whisper":
        work_dir = get_job_work_dir(job_id)
        job_store.merge_details(
            job_id,
            build_whisper_resume_details(
                work_dir=work_dir,
                model=payload.whisper_model,
                whisper_device=payload.whisper_device,
                language=payload.subtitle_language,
                subtitle_format=payload.subtitle_format,
                vad_filter=payload.vad_filter,
                start_time=payload.start_time,
                end_time=payload.end_time,
                subtitle_source="youtube_url",
                url=payload.url,
            ),
        )
        start_background_job(
            run_whisper_url_job,
            job_id,
            WhisperSubtitleOptions(
                url=payload.url,
                model=payload.whisper_model,
                language=payload.subtitle_language,
                subtitle_format=payload.subtitle_format,
                device=payload.whisper_device,
                vad_filter=payload.vad_filter,
                start_time=payload.start_time,
                end_time=payload.end_time,
            ),
            work_dir,
        )
        return job

    start_background_job(dispatch_job, job_id, payload)
    return job


@app.post("/api/subtitles/upload/jobs", status_code=202)
async def create_uploaded_whisper_job(
    file: UploadFile = File(...),
    whisper_model: str = Form("base", alias="whisperModel"),
    whisper_device: str = Form("auto", alias="whisperDevice"),
    subtitle_language: str = Form("ko", alias="subtitleLanguage"),
    subtitle_format: str = Form("timestamped", alias="subtitleFormat"),
    vad_filter: bool = Form(True, alias="vadFilter"),
    start_time: str | None = Form(None, alias="startTime"),
    end_time: str | None = Form(None, alias="endTime"),
) -> dict[str, object]:
    try:
        source_name = validate_upload_audio_filename(file.filename or "")
    except ExtractionInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        options = LocalWhisperSubtitleOptions(
            model=whisper_model,
            language=subtitle_language,
            subtitle_format=subtitle_format,
            device=whisper_device,
            vad_filter=vad_filter,
            start_time=start_time,
            end_time=end_time,
        )
        normalize_local_whisper_options(options)
    except ExtractionInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = job_store.create_job(
        message="Uploaded audio is being prepared.",
        details={
            "taskType": "subtitle",
            "subtitleEngine": "whisper",
            "subtitleSource": "upload",
            "whisperRuntime": "local",
        },
        download_path_template="/api/jobs/{job_id}/download",
    )
    job_id = str(job["jobId"])
    work_dir = get_job_work_dir(job_id)

    try:
        source_path = store_uploaded_source_file(work_dir, file, source_name)
    except Exception as exc:
        job_store.delete_job(job_id)
        raise HTTPException(status_code=400, detail="Failed to store the uploaded audio file.") from exc
    finally:
        await file.close()

    if not source_path.exists() or source_path.stat().st_size == 0:
        job_store.delete_job(job_id)
        raise HTTPException(status_code=400, detail="The uploaded audio file is empty.")

    job_store.merge_details(
        job_id,
        build_whisper_resume_details(
            work_dir=work_dir,
            model=options.model,
            whisper_device=options.device,
            language=options.language,
            subtitle_format=options.subtitle_format,
            vad_filter=options.vad_filter,
            start_time=options.start_time,
            end_time=options.end_time,
            subtitle_source="upload",
            source_name=source_name,
            source_path=source_path,
        ),
    )
    start_background_job(run_uploaded_whisper_job, job_id, source_path, source_name, options, work_dir)
    return job


@app.post("/api/subtitles/upload/colab/jobs", status_code=202)
async def create_uploaded_colab_job(
    file: UploadFile = File(...),
    whisper_model: str = Form("large-v3-turbo", alias="whisperModel"),
    whisper_device: str = Form("cuda", alias="whisperDevice"),
    subtitle_language: str = Form("ko", alias="subtitleLanguage"),
    subtitle_format: str = Form("timestamped", alias="subtitleFormat"),
    vad_filter: bool = Form(True, alias="vadFilter"),
    start_time: str | None = Form(None, alias="startTime"),
    end_time: str | None = Form(None, alias="endTime"),
) -> dict[str, object]:
    try:
        source_name = validate_upload_audio_filename(file.filename or "")
    except ExtractionInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        options = LocalWhisperSubtitleOptions(
            model=whisper_model,
            language=subtitle_language,
            subtitle_format=subtitle_format,
            device=whisper_device,
            vad_filter=vad_filter,
            start_time=start_time,
            end_time=end_time,
        )
        normalize_local_whisper_options(options)
    except ExtractionInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = job_store.create_job(
        message="Preparing Colab package.",
        details={
            "taskType": "subtitle",
            "subtitleEngine": "whisper",
            "subtitleSource": "upload",
            "whisperRuntime": "colab",
        },
        download_path_template="/api/jobs/{job_id}/download",
    )
    job_id = str(job["jobId"])
    work_dir = get_job_work_dir(job_id)

    try:
        source_path = store_uploaded_source_file(work_dir, file, source_name)
        bundle_info = create_colab_job_bundle(
            job_id=job_id,
            source_path=source_path,
            source_name=source_name,
            options=options,
            work_dir=work_dir,
        )
    except ExtractionInputError as exc:
        job_store.delete_job(job_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        job_store.delete_job(job_id)
        raise HTTPException(status_code=400, detail="Failed to prepare the Colab package.") from exc
    finally:
        await file.close()

    if not source_path.exists() or source_path.stat().st_size == 0:
        job_store.delete_job(job_id)
        raise HTTPException(status_code=400, detail="The uploaded audio file is empty.")

    details = build_colab_job_details(
        job_id=job_id,
        work_dir=work_dir,
        source_name=source_name,
        source_path=source_path,
        bundle_download_name=bundle_info.bundle_download_name,
        source_sha256=bundle_info.source_sha256,
        result_name=bundle_info.expected_output_name,
        options=options,
    )
    job_store.set_status(
        job_id,
        "waiting_for_colab",
        progress=15,
        message="Colab package is ready. Download it, run the notebook, and import the result ZIP.",
        details=details,
    )
    payload = job_store.get_response(job_id)
    if payload is None:
        raise HTTPException(status_code=500, detail="The Colab job could not be created.")
    return payload


@app.get("/api/subtitles/colab/notebook")
def download_colab_notebook() -> Response:
    payload = build_colab_notebook_payload()
    headers = {
        "Content-Disposition": f'attachment; filename="{COLAB_NOTEBOOK_FILENAME}"',
    }
    return Response(payload, media_type="application/x-ipynb+json", headers=headers)


@app.get("/api/subtitles/colab/jobs/{job_id}/bundle")
def download_colab_bundle(job_id: str) -> FileResponse:
    job = get_job_or_404(job_id, "/api/jobs/{job_id}/download")
    details = dict(job.get("details") or {})
    if details.get("whisperRuntime") != "colab":
        raise HTTPException(status_code=404, detail="Colab bundle not found for this job.")

    bundle_path = Path(str(details.get("workDir") or "")) / COLAB_BUNDLE_FILENAME
    if not bundle_path.exists():
        raise HTTPException(status_code=404, detail="Colab bundle file not found.")

    return FileResponse(
        path=bundle_path,
        media_type="application/zip",
        filename=str(details.get("bundleFilename") or bundle_path.name),
    )


@app.post("/api/subtitles/colab/jobs/{job_id}/complete")
async def complete_colab_job(job_id: str, file: UploadFile = File(...)) -> dict[str, object]:
    job = get_job_or_404(job_id, "/api/jobs/{job_id}/download")
    details = dict(job.get("details") or {})
    if details.get("whisperRuntime") != "colab":
        raise HTTPException(status_code=404, detail="Colab result import is not available for this job.")

    work_dir_value = details.get("workDir")
    if not isinstance(work_dir_value, str) or not work_dir_value:
        raise HTTPException(status_code=400, detail="The Colab job is missing its working directory.")

    work_dir = Path(work_dir_value)
    upload_path = work_dir / COLAB_RESULT_FILENAME

    try:
        with upload_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Failed to store the Colab result ZIP.") from exc
    finally:
        await file.close()

    if not upload_path.exists() or upload_path.stat().st_size == 0:
        raise HTTPException(status_code=400, detail="The uploaded Colab result ZIP is empty.")

    job_store.set_status(
        job_id,
        "importing_result",
        progress=90,
        message="Importing Colab result package.",
    )

    try:
        result, imported_details = import_colab_result_package(
            package_path=upload_path,
            work_dir=work_dir,
            job_id=job_id,
            expected_details=details,
        )
    except ExtractionInputError as exc:
        job_store.set_status(
            job_id,
            "waiting_for_colab",
            progress=15,
            message="Waiting for a valid Colab result package.",
            details={"lastImportError": str(exc)},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        job_store.set_status(
            job_id,
            "failed",
            progress=max(int(job.get("progress") or 0), 15),
            message="An unexpected error occurred while importing the Colab result package.",
        )
        raise HTTPException(status_code=500, detail="Unexpected Colab result import failure.") from exc

    job_store.complete_job(
        job_id,
        result,
        message="Colab subtitle import completed.",
        details={
            "taskType": "subtitle",
            "subtitleEngine": "whisper",
            "subtitleSource": "upload",
            "whisperRuntime": "colab",
            "subtitleFormat": details.get("subtitleFormat"),
            "whisperDevice": details.get("whisperDevice"),
            **imported_details,
        },
    )
    payload = job_store.get_response(job_id)
    if payload is None:
        raise HTTPException(status_code=500, detail="The Colab job could not be completed.")
    return payload


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
        message="Audio extraction is being prepared.",
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
        if payload.subtitle_engine == "whisper":
            result = extract_whisper_subtitles(
                WhisperSubtitleOptions(
                    url=payload.url,
                    model=payload.whisper_model,
                    language=payload.subtitle_language,
                    subtitle_format=payload.subtitle_format,
                    device=payload.whisper_device,
                    vad_filter=payload.vad_filter,
                    start_time=payload.start_time,
                    end_time=payload.end_time,
                )
            )
        else:
            result = extract_subtitles(
                SubtitleOptions(
                    url=payload.url,
                    subtitle_language=payload.subtitle_language,
                    subtitle_format=payload.subtitle_format,
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
