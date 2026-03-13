from pathlib import Path

from app.services.extractor import ExtractionResult
from launcher import (
    build_colab_help_message,
    build_stylesheet,
    compute_visibility,
    ensure_unique_path,
    persist_result,
    save_notebook_to_output,
    should_stack_action_buttons,
    should_stack_topbar,
    should_use_compact_layout,
    supports_pause_resume,
)


def test_compute_visibility_for_audio_task():
    visibility = compute_visibility("audio", "audio", "youtube", "youtube_url")

    assert visibility["url"] is True
    assert visibility["audio_format"] is True
    assert visibility["video_quality"] is False
    assert visibility["subtitle_format"] is False
    assert visibility["whisper_device"] is False
    assert visibility["whisper_runtime"] is False
    assert visibility["audio_file"] is False


def test_compute_visibility_for_uploaded_whisper_subtitles():
    visibility = compute_visibility("subtitle", "audio", "whisper", "audio_file", "local")

    assert visibility["url"] is False
    assert visibility["subtitle_source"] is True
    assert visibility["subtitle_format"] is True
    assert visibility["whisper_model"] is True
    assert visibility["whisper_device"] is True
    assert visibility["whisper_runtime"] is True
    assert visibility["audio_file"] is True
    assert visibility["colab_actions"] is False


def test_compute_visibility_for_colab_uploaded_whisper_subtitles():
    visibility = compute_visibility("subtitle", "audio", "whisper", "audio_file", "colab")

    assert visibility["audio_file"] is True
    assert visibility["whisper_runtime"] is True
    assert visibility["colab_actions"] is True


def test_supports_pause_resume_only_for_whisper_subtitles():
    assert supports_pause_resume("subtitle", "whisper", "local") is True
    assert supports_pause_resume("subtitle", "whisper", "colab") is False
    assert supports_pause_resume("subtitle", "youtube", "local") is False
    assert supports_pause_resume("audio", "whisper", "local") is False


def test_responsive_breakpoints():
    assert should_use_compact_layout(939) is True
    assert should_use_compact_layout(940) is False
    assert should_stack_action_buttons(1179) is True
    assert should_stack_action_buttons(1180) is False
    assert should_stack_topbar(779) is True
    assert should_stack_topbar(780) is False


def test_build_colab_help_message_mentions_required_files():
    message = build_colab_help_message("sample_colab_bundle.zip")

    assert "sample_colab_bundle.zip" in message
    assert "whisper_transcribe.ipynb" in message
    assert "colab-result.zip" in message
    assert "GPU" in message
    assert "USE_GOOGLE_DRIVE = True" in message
    assert "DRIVE_BUNDLE_PATH" in message


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


def test_save_notebook_to_output_uses_requested_name(tmp_path: Path):
    saved_path = save_notebook_to_output(tmp_path, "custom-colab.ipynb")

    assert saved_path == tmp_path / "custom-colab.ipynb"
    assert saved_path.exists()
    assert '"nbformat": 4' in saved_path.read_text(encoding="utf-8")


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
