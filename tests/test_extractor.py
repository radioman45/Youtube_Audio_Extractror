from pathlib import Path

import pytest

from app.services.extractor import (
    DEFAULT_SPLIT_MP3_BITRATE,
    build_audio_ffmpeg_command,
    build_output_path,
    build_split_archive_name,
    build_split_chunk_plan,
    build_split_part_name,
    resolve_mp3_bitrate,
    sanitize_filename,
    validate_requested_range,
)
from app.services.video_extractor import build_video_download_name


def test_sanitize_filename_removes_invalid_characters():
    assert sanitize_filename('Sample:/\\\\Video*?"<>|') == "SampleVideo"


def test_build_output_path_uses_selected_extension():
    output_path = build_output_path(Path("C:/tmp"), "sample-track", "mp3")
    assert output_path == Path("C:/tmp/sample-track.mp3")


def test_validate_requested_range_rejects_start_past_duration():
    with pytest.raises(ValueError):
        validate_requested_range(300, None, 120)


def test_validate_requested_range_rejects_end_past_duration():
    with pytest.raises(ValueError):
        validate_requested_range(30, 150, 120)


def test_build_video_download_name_sanitizes_range_filename():
    name = build_video_download_name("Video:? Title*", "1080p", 0, 30)
    assert name == "Video Title_1080p_00-00_to_00-30.mp4"


def test_resolve_mp3_bitrate_defaults_for_split_mode():
    assert resolve_mp3_bitrate("mp3", None, 25) == DEFAULT_SPLIT_MP3_BITRATE


def test_build_audio_ffmpeg_command_uses_selected_mp3_bitrate():
    command = build_audio_ffmpeg_command(
        ffmpeg_path="ffmpeg",
        input_path=Path("C:/tmp/source.webm"),
        output_path=Path("C:/tmp/output.mp3"),
        audio_format="mp3",
        start_seconds=0,
        end_seconds=60,
        mp3_bitrate="128k",
    )

    assert "-b:a" in command
    assert "128k" in command
    assert "-q:a" not in command


def test_build_split_chunk_plan_splits_long_audio_into_multiple_parts():
    chunk_plan = build_split_chunk_plan(900, 5, "128k")

    assert len(chunk_plan) > 1
    assert round(sum(duration for _, duration in chunk_plan), 3) == 900
    assert all(duration > 0 for _, duration in chunk_plan)


def test_build_split_names_are_stable():
    assert build_split_part_name("sample-track.mp3", 1, 12) == "sample-track_part01.mp3"
    assert build_split_archive_name("sample-track.mp3", 25) == "sample-track_split_25mb.zip"
