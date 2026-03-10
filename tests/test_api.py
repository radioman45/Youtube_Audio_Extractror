from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.extractor import ExtractionResult


def test_healthcheck_exposes_supported_formats():
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "formats": ["mp3", "m4a", "wav", "opus"]}


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
