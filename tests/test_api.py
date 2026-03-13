import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.extraction_jobs import ExtractionJobStore
from app.services.extractor import ExtractionResult


class InlineThread:
    def __init__(self, target, args=(), daemon=None):
        self._target = target
        self._args = args
        self.daemon = daemon

    def start(self):
        self._target(*self._args)


def normalize_newlines(payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n")


def make_colab_result_zip(
    *,
    job_id: str,
    source_sha256: str,
    download_name: str,
    subtitle_format: str,
    content: str,
    whisper_model: str = "large-v3-turbo",
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(download_name, content.encode("utf-8"))
        archive.writestr(
            "result.json",
            json.dumps(
                {
                    "jobId": job_id,
                    "sourceSha256": source_sha256,
                    "subtitleFormat": subtitle_format,
                    "downloadName": download_name,
                    "resultFile": download_name,
                    "whisperModel": whisper_model,
                    "device": "cuda",
                    "language": "ko",
                    "segmentCount": 3,
                    "durationSeconds": 42.5,
                    "generator": "pytest-colab",
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    return buffer.getvalue()


def test_healthcheck_exposes_supported_options():
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["name"] == "YouTube Multi Extractor"
    assert "aac" in payload["formats"]
    assert "1080p" in payload["videoQualities"]
    assert "batch" in payload["taskTypes"]
    assert "whisper" in payload["subtitleEngines"]
    assert "clean" in payload["subtitleFormats"]
    assert "large-v3-turbo" in payload["whisperModels"]
    assert "auto" in payload["whisperDevices"]
    assert "colab" in payload["whisperRuntimes"]
    assert "audio_file" in payload["subtitleSources"]
    assert payload["colab"]["enabled"] is True


def test_extract_endpoint_accepts_frontend_camel_case_fields(monkeypatch, tmp_path: Path):
    captured = {}
    work_dir = tmp_path / "job"
    work_dir.mkdir()
    output_file = work_dir / "track.mp3"
    output_file.write_bytes(b"audio")

    def fake_extract_audio(options):
        captured["options"] = options
        return ExtractionResult(
            file_path=output_file,
            download_name="track.mp3",
            temp_dir=work_dir,
        )

    monkeypatch.setattr("app.main.extract_audio", fake_extract_audio)
    client = TestClient(app)

    response = client.post(
        "/api/extract",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "audioFormat": "mp3",
            "startTime": "00:10",
            "endTime": "00:20",
        },
    )

    assert response.status_code == 200
    assert captured["options"].audio_format == "mp3"
    assert captured["options"].start_time == "00:10"
    assert captured["options"].end_time == "00:20"


def test_extract_job_endpoint_tracks_progress_and_download(monkeypatch, tmp_path: Path):
    captured = {}
    store = ExtractionJobStore()
    work_dir = tmp_path / "job"
    work_dir.mkdir()
    output_file = work_dir / "track.mp3"
    output_file.write_bytes(b"audio")

    def fake_extract_audio(options, progress_callback=None):
        captured["options"] = options
        assert progress_callback is not None
        progress_callback(45, "원본 오디오를 다운로드하는 중입니다.")
        return ExtractionResult(
            file_path=output_file,
            download_name="track.mp3",
            temp_dir=work_dir,
        )

    monkeypatch.setattr("app.main.job_store", store)
    monkeypatch.setattr("app.main.extract_audio", fake_extract_audio)
    monkeypatch.setattr("app.main.threading.Thread", InlineThread)
    client = TestClient(app)

    create_response = client.post(
        "/api/extract/jobs",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "audioFormat": "mp3",
            "startTime": "00:10",
            "endTime": "00:20",
        },
    )

    assert create_response.status_code == 202
    job_id = create_response.json()["jobId"]
    assert captured["options"].audio_format == "mp3"

    status_response = client.get(f"/api/extract/jobs/{job_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "completed"
    assert status_payload["progress"] == 100
    assert status_payload["downloadUrl"].endswith(f"/api/extract/jobs/{job_id}/download")

    download_response = client.get(status_payload["downloadUrl"])
    assert download_response.status_code == 200
    assert download_response.content == b"audio"


def test_subtitle_endpoint_accepts_frontend_camel_case_fields(monkeypatch, tmp_path: Path):
    captured = {}
    work_dir = tmp_path / "job"
    work_dir.mkdir()
    output_file = work_dir / "track_en_clean.txt"
    output_file.write_text("Hello\n", encoding="utf-8")

    def fake_extract_subtitles(options):
        captured["options"] = options
        return ExtractionResult(
            file_path=output_file,
            download_name="track_en_clean.txt",
            temp_dir=work_dir,
            media_type="text/plain; charset=utf-8",
        )

    monkeypatch.setattr("app.main.extract_subtitles", fake_extract_subtitles)
    client = TestClient(app)

    response = client.post(
        "/api/subtitles",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "subtitleLanguage": "en",
            "subtitleFormat": "clean",
            "startTime": "00:10",
            "endTime": "00:20",
        },
    )

    assert response.status_code == 200
    assert captured["options"].subtitle_language == "en"
    assert captured["options"].subtitle_format == "clean"
    assert captured["options"].start_time == "00:10"
    assert captured["options"].end_time == "00:20"
    assert normalize_newlines(response.content) == b"Hello\n"


def test_whisper_subtitle_endpoint_accepts_frontend_camel_case_fields(monkeypatch, tmp_path: Path):
    captured = {}
    work_dir = tmp_path / "job"
    work_dir.mkdir()
    output_file = work_dir / "track_whisper_ko_clean.txt"
    output_file.write_text("안녕하세요\n", encoding="utf-8")

    def fake_extract_whisper_subtitles(options):
        captured["options"] = options
        return ExtractionResult(
            file_path=output_file,
            download_name="track_whisper_ko_clean.txt",
            temp_dir=work_dir,
            media_type="text/plain; charset=utf-8",
        )

    monkeypatch.setattr("app.main.extract_whisper_subtitles", fake_extract_whisper_subtitles)
    client = TestClient(app)

    response = client.post(
        "/api/subtitles",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "subtitleEngine": "whisper",
            "subtitleFormat": "clean",
            "whisperModel": "base",
            "whisperDevice": "cpu",
            "subtitleLanguage": "ko",
            "vadFilter": False,
        },
    )

    assert response.status_code == 200
    assert captured["options"].model == "base"
    assert captured["options"].language == "ko"
    assert captured["options"].subtitle_format == "clean"
    assert captured["options"].device == "cpu"
    assert captured["options"].vad_filter is False
    assert normalize_newlines(response.content) == "안녕하세요\n".encode("utf-8")


def test_generic_video_job_dispatches_and_downloads(monkeypatch, tmp_path: Path):
    store = ExtractionJobStore()
    work_dir = tmp_path / "job"
    work_dir.mkdir()
    output_file = work_dir / "clip.mp4"
    output_file.write_bytes(b"video")

    def fake_extract_video(options, progress_callback=None):
        assert options.video_quality == "720p"
        assert progress_callback is not None
        progress_callback(60, "영상 후처리를 진행하는 중입니다.")
        return ExtractionResult(
            file_path=output_file,
            download_name="clip.mp4",
            temp_dir=work_dir,
            media_type="video/mp4",
        )

    monkeypatch.setattr("app.main.job_store", store)
    monkeypatch.setattr("app.main.extract_video", fake_extract_video)
    monkeypatch.setattr("app.main.threading.Thread", InlineThread)
    client = TestClient(app)

    create_response = client.post(
        "/api/jobs",
        json={
            "taskType": "video",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "videoQuality": "720p",
        },
    )

    assert create_response.status_code == 202
    job_id = create_response.json()["jobId"]

    status_response = client.get(f"/api/jobs/{job_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "completed"
    assert status_payload["filename"] == "clip.mp4"
    assert status_payload["details"]["taskType"] == "video"

    download_response = client.get(status_payload["downloadUrl"])
    assert download_response.status_code == 200
    assert download_response.content == b"video"


def test_generic_batch_job_reports_details(monkeypatch, tmp_path: Path):
    store = ExtractionJobStore()
    work_dir = tmp_path / "job"
    work_dir.mkdir()
    output_file = work_dir / "batch.zip"
    output_file.write_bytes(b"zip")

    def fake_extract_batch(options, progress_callback=None, status_callback=None):
        assert options.batch_mode == "subtitle"
        assert options.subtitle_format == "clean"
        assert status_callback is not None
        assert progress_callback is not None
        status_callback(3, 0, 0)
        progress_callback(35, "1/3 항목을 처리하는 중입니다.")
        status_callback(3, 2, 1)
        return ExtractionResult(
            file_path=output_file,
            download_name="batch.zip",
            temp_dir=work_dir,
            media_type="application/zip",
        )

    monkeypatch.setattr("app.main.job_store", store)
    monkeypatch.setattr("app.main.extract_batch", fake_extract_batch)
    monkeypatch.setattr("app.main.threading.Thread", InlineThread)
    client = TestClient(app)

    create_response = client.post(
        "/api/jobs",
        json={
            "taskType": "batch",
            "batchMode": "subtitle",
            "url": "https://www.youtube.com/playlist?list=PL1234567890",
            "subtitleLanguage": "ko",
            "subtitleFormat": "clean",
        },
    )

    assert create_response.status_code == 202
    job_id = create_response.json()["jobId"]

    status_response = client.get(f"/api/jobs/{job_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "completed"
    assert status_payload["details"]["total"] == 3
    assert status_payload["details"]["completed"] == 2
    assert status_payload["details"]["failed"] == 1
    assert status_payload["downloadUrl"].endswith(f"/api/jobs/{job_id}/download")


def test_whisper_subtitle_job_dispatches_and_downloads(monkeypatch, tmp_path: Path):
    store = ExtractionJobStore()
    work_dir = tmp_path / "job"
    work_dir.mkdir()
    output_file = work_dir / "track_whisper_base_ko_clean.txt"
    output_file.write_text("Hello\n", encoding="utf-8")

    def fake_extract_whisper_subtitles(options, progress_callback=None, temp_dir=None, resume_state_callback=None):
        assert options.model == "base"
        assert options.language == "ko"
        assert options.subtitle_format == "clean"
        assert options.device == "cpu"
        assert options.vad_filter is True
        assert progress_callback is not None
        assert temp_dir is not None
        if resume_state_callback is not None:
            resume_state_callback({"completedChunks": 0, "chunkCount": 1})
        progress_callback(65, "Transcribing audio with faster-whisper.")
        return ExtractionResult(
            file_path=output_file,
            download_name="track_whisper_base_ko_clean.txt",
            temp_dir=temp_dir,
            media_type="text/plain; charset=utf-8",
        )

    monkeypatch.setattr("app.main.job_store", store)
    monkeypatch.setattr("app.main.extract_whisper_subtitles", fake_extract_whisper_subtitles)
    monkeypatch.setattr("app.main.threading.Thread", InlineThread)
    client = TestClient(app)

    create_response = client.post(
        "/api/jobs",
        json={
            "taskType": "subtitle",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "subtitleEngine": "whisper",
            "subtitleFormat": "clean",
            "whisperModel": "base",
            "whisperDevice": "cpu",
            "subtitleLanguage": "ko",
            "vadFilter": True,
        },
    )

    assert create_response.status_code == 202
    job_id = create_response.json()["jobId"]

    status_response = client.get(f"/api/jobs/{job_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "completed"
    assert status_payload["details"]["subtitleEngine"] == "whisper"
    assert status_payload["details"]["subtitleFormat"] == "clean"
    assert status_payload["details"]["whisperDevice"] == "cpu"
    assert status_payload["filename"] == "track_whisper_base_ko_clean.txt"

    download_response = client.get(status_payload["downloadUrl"])
    assert download_response.status_code == 200
    assert normalize_newlines(download_response.content) == b"Hello\n"


def test_uploaded_whisper_subtitle_job_dispatches_and_downloads(monkeypatch, tmp_path: Path):
    store = ExtractionJobStore()
    captured = {}

    def fake_extract_whisper_subtitles_from_file(
        source_path,
        source_name,
        options,
        temp_dir=None,
        progress_callback=None,
        resume_state_callback=None,
    ):
        captured["source_name"] = source_name
        captured["options"] = options
        captured["source_exists"] = source_path.exists()
        assert temp_dir is not None
        assert progress_callback is not None
        if resume_state_callback is not None:
            resume_state_callback({"completedChunks": 0, "chunkCount": 1})
        progress_callback(72, "Transcribing uploaded audio with faster-whisper.")
        output_file = temp_dir / "uploaded_whisper_base_ko_clean.txt"
        output_file.write_text("Uploaded\n", encoding="utf-8")
        return ExtractionResult(
            file_path=output_file,
            download_name="uploaded_whisper_base_ko_clean.txt",
            temp_dir=temp_dir,
            media_type="text/plain; charset=utf-8",
        )

    monkeypatch.setattr("app.main.job_store", store)
    monkeypatch.setattr("app.main.extract_whisper_subtitles_from_file", fake_extract_whisper_subtitles_from_file)
    monkeypatch.setattr("app.main.threading.Thread", InlineThread)
    client = TestClient(app)

    create_response = client.post(
        "/api/subtitles/upload/jobs",
        data={
            "whisperModel": "base",
            "whisperDevice": "cuda",
            "subtitleLanguage": "ko",
            "subtitleFormat": "clean",
            "vadFilter": "true",
        },
        files={
            "file": ("sample.mp3", b"audio-bytes", "audio/mpeg"),
        },
    )

    assert create_response.status_code == 202
    job_id = create_response.json()["jobId"]
    assert captured["source_name"] == "sample.mp3"
    assert captured["source_exists"] is True
    assert captured["options"].model == "base"
    assert captured["options"].language == "ko"
    assert captured["options"].subtitle_format == "clean"
    assert captured["options"].device == "cuda"

    status_response = client.get(f"/api/jobs/{job_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "completed"
    assert status_payload["details"]["subtitleSource"] == "upload"
    assert status_payload["details"]["subtitleFormat"] == "clean"
    assert status_payload["details"]["whisperDevice"] == "cuda"

    download_response = client.get(status_payload["downloadUrl"])
    assert download_response.status_code == 200
    assert normalize_newlines(download_response.content) == b"Uploaded\n"


def test_uploaded_colab_job_creates_bundle_and_notebook(monkeypatch, tmp_path: Path):
    store = ExtractionJobStore(state_dir=tmp_path / "state")

    def fake_get_job_work_dir(job_id: str) -> Path:
        work_dir = tmp_path / job_id / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir

    monkeypatch.setattr("app.main.job_store", store)
    monkeypatch.setattr("app.main.get_job_work_dir", fake_get_job_work_dir)
    client = TestClient(app)

    create_response = client.post(
        "/api/subtitles/upload/colab/jobs",
        data={
            "whisperModel": "large-v3-turbo",
            "whisperDevice": "cuda",
            "subtitleLanguage": "ko",
            "subtitleFormat": "timestamped",
            "vadFilter": "true",
        },
        files={
            "file": ("sample.mp3", b"audio-bytes", "audio/mpeg"),
        },
    )

    assert create_response.status_code == 202
    payload = create_response.json()
    assert payload["status"] == "waiting_for_colab"
    assert payload["details"]["whisperRuntime"] == "colab"
    assert payload["details"]["bundleDownloadUrl"].endswith("/bundle")
    assert payload["details"]["resultUploadUrl"].endswith("/complete")

    bundle_response = client.get(payload["details"]["bundleDownloadUrl"])
    assert bundle_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle_response.content)) as archive:
        assert "manifest.json" in archive.namelist()
        assert "result-schema.json" in archive.namelist()
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["jobId"] == payload["jobId"]
    assert manifest["sourceSha256"] == payload["details"]["sourceSha256"]

    notebook_response = client.get(payload["details"]["notebookDownloadUrl"])
    assert notebook_response.status_code == 200
    assert b"WhisperModel" in notebook_response.content
    assert b"drive.mount" in notebook_response.content
    assert b"USE_GOOGLE_DRIVE = False" in notebook_response.content
    assert b"DRIVE_BUNDLE_PATH" in notebook_response.content


def test_uploaded_colab_job_imports_result_zip(monkeypatch, tmp_path: Path):
    store = ExtractionJobStore(state_dir=tmp_path / "state")

    def fake_get_job_work_dir(job_id: str) -> Path:
        work_dir = tmp_path / job_id / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir

    monkeypatch.setattr("app.main.job_store", store)
    monkeypatch.setattr("app.main.get_job_work_dir", fake_get_job_work_dir)
    client = TestClient(app)

    create_response = client.post(
        "/api/subtitles/upload/colab/jobs",
        data={
            "whisperModel": "large-v3-turbo",
            "whisperDevice": "cuda",
            "subtitleLanguage": "ko",
            "subtitleFormat": "clean",
            "vadFilter": "true",
        },
        files={
            "file": ("sample.mp3", b"audio-bytes", "audio/mpeg"),
        },
    )

    assert create_response.status_code == 202
    created = create_response.json()
    result_zip = make_colab_result_zip(
        job_id=created["jobId"],
        source_sha256=created["details"]["sourceSha256"],
        download_name=created["details"]["colabResultName"],
        subtitle_format="clean",
        content="Imported from Colab\n",
    )

    complete_response = client.post(
        created["details"]["resultUploadUrl"],
        files={
            "file": ("colab-result.zip", result_zip, "application/zip"),
        },
    )

    assert complete_response.status_code == 200
    completed = complete_response.json()
    assert completed["status"] == "completed"
    assert completed["details"]["whisperRuntime"] == "colab"
    assert completed["details"]["resultModel"] == "large-v3-turbo"
    assert completed["filename"] == created["details"]["colabResultName"]

    download_response = client.get(completed["downloadUrl"])
    assert download_response.status_code == 200
    assert normalize_newlines(download_response.content) == b"Imported from Colab\n"


def test_uploaded_colab_job_rejects_mismatched_result_zip(monkeypatch, tmp_path: Path):
    store = ExtractionJobStore(state_dir=tmp_path / "state")

    def fake_get_job_work_dir(job_id: str) -> Path:
        work_dir = tmp_path / job_id / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir

    monkeypatch.setattr("app.main.job_store", store)
    monkeypatch.setattr("app.main.get_job_work_dir", fake_get_job_work_dir)
    client = TestClient(app)

    create_response = client.post(
        "/api/subtitles/upload/colab/jobs",
        data={
            "whisperModel": "large-v3-turbo",
            "whisperDevice": "cuda",
            "subtitleLanguage": "ko",
            "subtitleFormat": "timestamped",
        },
        files={
            "file": ("sample.mp3", b"audio-bytes", "audio/mpeg"),
        },
    )

    assert create_response.status_code == 202
    created = create_response.json()
    result_zip = make_colab_result_zip(
        job_id=created["jobId"],
        source_sha256="not-the-right-sha",
        download_name=created["details"]["colabResultName"],
        subtitle_format="timestamped",
        content="1\n00:00:00,000 --> 00:00:01,000\nMismatch\n",
    )

    complete_response = client.post(
        created["details"]["resultUploadUrl"],
        files={
            "file": ("colab-result.zip", result_zip, "application/zip"),
        },
    )

    assert complete_response.status_code == 400
    assert "different source file" in complete_response.json()["detail"]

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "waiting_for_colab"
    assert "lastImportError" in status_payload["details"]


def test_job_endpoint_rejects_batch_without_mode():
    client = TestClient(app)

    response = client.post(
        "/api/jobs",
        json={
            "taskType": "batch",
            "url": "https://www.youtube.com/playlist?list=PL1234567890",
        },
    )

    assert response.status_code == 422


def test_job_endpoint_rejects_batch_whisper_subtitle():
    client = TestClient(app)

    response = client.post(
        "/api/jobs",
        json={
            "taskType": "batch",
            "batchMode": "subtitle",
            "url": "https://www.youtube.com/playlist?list=PL1234567890",
            "subtitleEngine": "whisper",
            "whisperModel": "base",
        },
    )

    assert response.status_code == 422


def test_job_endpoint_rejects_colab_runtime_for_url_whisper():
    client = TestClient(app)

    response = client.post(
        "/api/jobs",
        json={
            "taskType": "subtitle",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "subtitleEngine": "whisper",
            "whisperRuntime": "colab",
            "whisperModel": "large-v3-turbo",
        },
    )

    assert response.status_code == 422


def test_extract_endpoint_rejects_invalid_time_format():
    client = TestClient(app)

    response = client.post(
        "/api/extract",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "audioFormat": "mp3",
            "startTime": "bad",
        },
    )

    assert response.status_code == 422
    messages = " ".join(item["msg"] for item in response.json()["detail"])
    assert "Time values must be numeric." in messages


def test_extract_endpoint_rejects_invalid_time_order():
    client = TestClient(app)

    response = client.post(
        "/api/extract",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "audioFormat": "mp3",
            "startTime": "20",
            "endTime": "10",
        },
    )

    assert response.status_code == 422
    messages = " ".join(item["msg"] for item in response.json()["detail"])
    assert "End time must be after start time." in messages


def test_subtitle_endpoint_rejects_invalid_time_order():
    client = TestClient(app)

    response = client.post(
        "/api/subtitles",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "subtitleLanguage": "ko",
            "startTime": "20",
            "endTime": "10",
        },
    )

    assert response.status_code == 422
    messages = " ".join(item["msg"] for item in response.json()["detail"])
    assert "End time must be after start time." in messages


def test_resume_pending_jobs_restarts_whisper_url_job(monkeypatch, tmp_path: Path):
    store = ExtractionJobStore(state_dir=tmp_path / "state")
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    created = store.create_job(
        message="Recover me",
        details={
            "taskType": "subtitle",
            "subtitleEngine": "whisper",
            "subtitleSource": "youtube_url",
            "resumeSupported": True,
            "workDir": str(work_dir),
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "whisperModel": "base",
            "whisperDevice": "cpu",
            "subtitleLanguage": "ko",
            "vadFilter": True,
            "startTime": None,
            "endTime": None,
        },
    )
    job_id = str(created["jobId"])
    store.update_progress(job_id, 91, "Running")
    started = []

    monkeypatch.setattr("app.main.job_store", store)
    monkeypatch.setattr("app.main.start_background_job", lambda target, *args: started.append((target.__name__, args)))

    from app.main import resume_pending_jobs

    resume_pending_jobs()

    assert started
    assert started[0][0] == "run_whisper_url_job"
    assert started[0][1][0] == job_id
    assert started[0][1][1].device == "cpu"
