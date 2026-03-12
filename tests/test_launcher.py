from pathlib import Path

from app.services.extractor import ExtractionResult
from launcher import build_stylesheet, compute_visibility, ensure_unique_path, persist_result, supports_pause_resume


def test_compute_visibility_for_audio_task():
    visibility = compute_visibility("audio", "audio", "youtube", "youtube_url")

    assert visibility["url"] is True
    assert visibility["audio_format"] is True
    assert visibility["video_quality"] is False
    assert visibility["subtitle_format"] is False
    assert visibility["whisper_device"] is False
    assert visibility["audio_file"] is False


def test_compute_visibility_for_uploaded_whisper_subtitles():
    visibility = compute_visibility("subtitle", "audio", "whisper", "audio_file")

    assert visibility["url"] is False
    assert visibility["subtitle_source"] is True
    assert visibility["subtitle_format"] is True
    assert visibility["whisper_model"] is True
    assert visibility["whisper_device"] is True
    assert visibility["audio_file"] is True


def test_supports_pause_resume_only_for_whisper_subtitles():
    assert supports_pause_resume("subtitle", "whisper") is True
    assert supports_pause_resume("subtitle", "youtube") is False
    assert supports_pause_resume("audio", "whisper") is False


def test_ensure_unique_path_appends_suffix(tmp_path: Path):
    first = tmp_path / "track.mp3"
    second = tmp_path / "track_1.mp3"
    first.write_bytes(b"a")
    second.write_bytes(b"b")

    candidate = ensure_unique_path(first)

    assert candidate == tmp_path / "track_2.mp3"


def test_persist_result_moves_file_and_cleans_temp_dir(tmp_path: Path):
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    source = temp_dir / "track.mp3"
    source.write_bytes(b"audio")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    saved_path = persist_result(
        ExtractionResult(
            file_path=source,
            download_name="track.mp3",
            temp_dir=temp_dir,
        ),
        output_dir,
    )

    assert saved_path == output_dir / "track.mp3"
    assert saved_path.exists()
    assert not temp_dir.exists()


def test_build_stylesheet_has_dark_mode_tokens():
    stylesheet = build_stylesheet("dark")

    assert "#09090b" in stylesheet
    assert "#38bdf8" in stylesheet
    assert "QPushButton#themeButton" in stylesheet


def test_build_stylesheet_has_light_mode_tokens():
    stylesheet = build_stylesheet("light")

    assert "#fafafa" in stylesheet
    assert "#06b6d4" in stylesheet
    assert "#18181b" in stylesheet
