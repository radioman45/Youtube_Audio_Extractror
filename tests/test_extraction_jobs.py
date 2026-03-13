from pathlib import Path

from app.services.extraction_jobs import ExtractionJobStore
from app.services.extractor import ExtractionResult


def test_job_store_persists_completed_job(tmp_path: Path):
    state_dir = tmp_path / "state"
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    output_file = work_dir / "result.srt"
    output_file.write_text("ok", encoding="utf-8")

    store = ExtractionJobStore(state_dir=state_dir)
    created = store.create_job(message="Preparing", details={"taskType": "subtitle"})
    job_id = str(created["jobId"])
    store.merge_details(job_id, {"subtitleEngine": "whisper"})
    store.complete_job(
        job_id,
        ExtractionResult(
            file_path=output_file,
            download_name="result.srt",
            temp_dir=work_dir,
            media_type="application/x-subrip; charset=utf-8",
        ),
        message="Done",
    )

    reloaded_store = ExtractionJobStore(state_dir=state_dir)
    payload = reloaded_store.get_response(job_id)

    assert payload is not None
    assert payload["status"] == "completed"
    assert payload["filename"] == "result.srt"
    assert payload["details"]["subtitleEngine"] == "whisper"


def test_job_store_persists_waiting_for_colab_job(tmp_path: Path):
    state_dir = tmp_path / "state"
    store = ExtractionJobStore(state_dir=state_dir)
    created = store.create_job(message="Preparing", details={"taskType": "subtitle"})
    job_id = str(created["jobId"])

    store.set_status(
        job_id,
        "waiting_for_colab",
        progress=15,
        message="Bundle ready",
        details={"whisperRuntime": "colab", "bundleFilename": "sample_bundle.zip"},
    )

    reloaded_store = ExtractionJobStore(state_dir=state_dir)
    payload = reloaded_store.get_response(job_id)

    assert payload is not None
    assert payload["status"] == "waiting_for_colab"
    assert payload["progress"] == 15
    assert payload["details"]["whisperRuntime"] == "colab"
