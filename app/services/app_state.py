from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


APP_STATE_ENV_VAR = "APP_STATE_DIR"
APP_STATE_FOLDER_NAME = "YouTubeAudioExtractor"


def get_app_state_root() -> Path:
    configured = os.environ.get(APP_STATE_ENV_VAR)
    if configured:
        root = Path(configured).expanduser()
    elif "pytest" in sys.modules:
        root = Path(tempfile.gettempdir()) / "youtube-audio-extractor-test-state"
    else:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            root = Path(local_app_data) / APP_STATE_FOLDER_NAME
        else:
            root = Path.home() / ".cache" / APP_STATE_FOLDER_NAME

    root.mkdir(parents=True, exist_ok=True)
    return root


def get_jobs_state_dir() -> Path:
    jobs_dir = get_app_state_root() / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    return jobs_dir


def get_job_state_dir(job_id: str) -> Path:
    job_dir = get_jobs_state_dir() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def get_job_work_dir(job_id: str) -> Path:
    work_dir = get_job_state_dir(job_id) / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def get_job_state_file(job_id: str) -> Path:
    return get_job_state_dir(job_id) / "job.json"
