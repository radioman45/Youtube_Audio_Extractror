from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from app.models import ExtractRequest
from app.services.extractor import (
    SUPPORTED_FORMATS,
    ExtractionInputError,
    ExtractionOptions,
    ExtractionRuntimeError,
    cleanup_temp_dir,
    extract_audio,
)


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="YouTube Audio Extractor",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def healthcheck() -> dict[str, object]:
    return {"ok": True, "formats": SUPPORTED_FORMATS}


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
        media_type="application/octet-stream",
        filename=result.download_name,
        background=BackgroundTask(cleanup_temp_dir, result.temp_dir),
    )


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
