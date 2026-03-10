from pathlib import Path

import pytest

from app.services.extractor import build_output_path, sanitize_filename, validate_requested_range


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
