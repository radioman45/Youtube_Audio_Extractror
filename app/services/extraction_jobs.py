from __future__ import annotations

import json
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from app.services.app_state import get_jobs_state_dir
from app.services.extractor import ExtractionResult, cleanup_temp_dir


JobStatus = Literal["queued", "processing", "waiting_for_colab", "importing_result", "completed", "failed"]


@dataclass(slots=True)
class ExtractionJob:
    job_id: str
    status: JobStatus
    progress: int
    message: str
    created_at: float
    updated_at: float
    result: ExtractionResult | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_response(self, download_path_template: str = "/api/jobs/{job_id}/download") -> dict[str, object]:
        payload: dict[str, object] = {
            "jobId": self.job_id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "details": self.details,
        }

        if self.error:
            payload["error"] = self.error

        if self.status == "completed" and self.result is not None:
            payload["filename"] = self.result.download_name
            payload["downloadUrl"] = download_path_template.format(job_id=self.job_id)

        return payload


class ExtractionJobStore:
    def __init__(self, retention_seconds: int = 3600, state_dir: Path | None = None) -> None:
        self._jobs: dict[str, ExtractionJob] = {}
        self._lock = threading.Lock()
        self._retention_seconds = retention_seconds
        self._state_dir = state_dir or get_jobs_state_dir()
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._load_existing_jobs()

    def _job_state_path(self, job_id: str) -> Path:
        return self._state_dir / job_id / "job.json"

    def _serialize_result(self, result: ExtractionResult | None) -> dict[str, str] | None:
        if result is None:
            return None
        return {
            "filePath": str(result.file_path),
            "downloadName": result.download_name,
            "tempDir": str(result.temp_dir),
            "mediaType": result.media_type,
        }

    def _deserialize_result(self, payload: dict[str, Any] | None) -> ExtractionResult | None:
        if not payload:
            return None
        return ExtractionResult(
            file_path=Path(str(payload["filePath"])),
            download_name=str(payload["downloadName"]),
            temp_dir=Path(str(payload["tempDir"])),
            media_type=str(payload.get("mediaType") or "application/octet-stream"),
        )

    def _serialize_job(self, job: ExtractionJob) -> dict[str, Any]:
        return {
            "jobId": job.job_id,
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "createdAt": job.created_at,
            "updatedAt": job.updated_at,
            "error": job.error,
            "details": job.details,
            "result": self._serialize_result(job.result),
        }

    def _persist_job_locked(self, job: ExtractionJob) -> None:
        state_path = self._job_state_path(job.job_id)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = state_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(self._serialize_job(job), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(state_path)

    def _delete_job_state(self, job_id: str) -> None:
        shutil.rmtree(self._state_dir / job_id, ignore_errors=True)

    def _load_existing_jobs(self) -> None:
        for state_path in self._state_dir.glob("*/job.json"):
            try:
                payload = json.loads(state_path.read_text(encoding="utf-8"))
                job = ExtractionJob(
                    job_id=str(payload["jobId"]),
                    status=str(payload["status"]),
                    progress=int(payload["progress"]),
                    message=str(payload["message"]),
                    created_at=float(payload["createdAt"]),
                    updated_at=float(payload["updatedAt"]),
                    result=self._deserialize_result(payload.get("result")),
                    error=str(payload["error"]) if payload.get("error") else None,
                    details=dict(payload.get("details") or {}),
                )
            except Exception:
                continue
            self._jobs[job.job_id] = job

        self.cleanup_expired_jobs()

    def create_job(
        self,
        *,
        message: str = "Job is being prepared.",
        details: dict[str, Any] | None = None,
        download_path_template: str = "/api/jobs/{job_id}/download",
    ) -> dict[str, object]:
        self.cleanup_expired_jobs()

        now = time.time()
        job = ExtractionJob(
            job_id=uuid4().hex,
            status="queued",
            progress=0,
            message=message,
            created_at=now,
            updated_at=now,
            details=details or {},
        )

        with self._lock:
            self._jobs[job.job_id] = job
            self._persist_job_locked(job)
            return job.to_response(download_path_template)

    def list_jobs(self, statuses: set[JobStatus] | None = None) -> list[ExtractionJob]:
        self.cleanup_expired_jobs()
        with self._lock:
            jobs = list(self._jobs.values())
        if statuses is None:
            return jobs
        return [job for job in jobs if job.status in statuses]

    def merge_details(self, job_id: str, details: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.details.update(details)
            job.updated_at = time.time()
            self._persist_job_locked(job)

    def get_response(
        self,
        job_id: str,
        *,
        download_path_template: str = "/api/jobs/{job_id}/download",
    ) -> dict[str, object] | None:
        self.cleanup_expired_jobs()

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return job.to_response(download_path_template)

    def get_result(self, job_id: str) -> ExtractionResult | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "completed":
                return None
            return job.result

    def update_progress(
        self,
        job_id: str,
        progress: int,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        normalized_progress = max(0, min(99, int(progress)))

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in {"completed", "failed"}:
                return

            job.status = "processing"
            job.progress = max(job.progress, normalized_progress)
            job.message = message
            if details:
                job.details.update(details)
            job.updated_at = time.time()
            self._persist_job_locked(job)

    def set_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        progress: int,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        normalized_progress = max(0, min(100, int(progress)))

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in {"completed", "failed"}:
                return

            job.status = status
            job.progress = normalized_progress
            job.message = message
            if details:
                job.details.update(details)
            job.updated_at = time.time()
            self._persist_job_locked(job)

    def complete_job(
        self,
        job_id: str,
        result: ExtractionResult,
        *,
        message: str = "Job completed.",
        details: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                cleanup_temp_dir(result.temp_dir)
                return

            job.status = "completed"
            job.progress = 100
            job.message = message
            job.updated_at = time.time()
            job.result = result
            job.error = None
            if details:
                job.details.update(details)
            self._persist_job_locked(job)

    def fail_job(self, job_id: str, message: str, details: dict[str, Any] | None = None) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return

            job.status = "failed"
            job.message = message
            job.error = message
            job.updated_at = time.time()
            if details:
                job.details.update(details)
            self._persist_job_locked(job)

    def delete_job(self, job_id: str) -> None:
        result: ExtractionResult | None = None

        with self._lock:
            job = self._jobs.pop(job_id, None)
            if job is not None:
                result = job.result

        if result is not None:
            cleanup_temp_dir(result.temp_dir)
        self._delete_job_state(job_id)

    def cleanup_expired_jobs(self) -> None:
        expired_results: list[ExtractionResult] = []
        expired_job_ids: list[str] = []
        now = time.time()

        with self._lock:
            for job_id, job in list(self._jobs.items()):
                if job.status not in {"completed", "failed"}:
                    continue
                if (now - job.updated_at) <= self._retention_seconds:
                    continue
                expired_job_ids.append(job_id)
                if job.result is not None:
                    expired_results.append(job.result)
                self._jobs.pop(job_id, None)

        for result in expired_results:
            cleanup_temp_dir(result.temp_dir)
        for job_id in expired_job_ids:
            self._delete_job_state(job_id)
