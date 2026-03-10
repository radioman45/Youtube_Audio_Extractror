from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

from app.services.extractor import ExtractionResult, cleanup_temp_dir


JobStatus = Literal["queued", "processing", "completed", "failed"]


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
    def __init__(self, retention_seconds: int = 3600) -> None:
        self._jobs: dict[str, ExtractionJob] = {}
        self._lock = threading.Lock()
        self._retention_seconds = retention_seconds

    def create_job(
        self,
        *,
        message: str = "작업을 준비하는 중입니다.",
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
            return job.to_response(download_path_template)

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

    def complete_job(
        self,
        job_id: str,
        result: ExtractionResult,
        *,
        message: str = "작업이 완료되었습니다.",
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

    def delete_job(self, job_id: str) -> None:
        result: ExtractionResult | None = None

        with self._lock:
            job = self._jobs.pop(job_id, None)
            if job is not None:
                result = job.result

        if result is not None:
            cleanup_temp_dir(result.temp_dir)

    def cleanup_expired_jobs(self) -> None:
        expired_results: list[ExtractionResult] = []
        now = time.time()

        with self._lock:
            expired_job_ids = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in {"completed", "failed"} and (now - job.updated_at) > self._retention_seconds
            ]

            for job_id in expired_job_ids:
                job = self._jobs.pop(job_id)
                if job.result is not None:
                    expired_results.append(job.result)

        for result in expired_results:
            cleanup_temp_dir(result.temp_dir)
