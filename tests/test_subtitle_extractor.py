import pytest

from app.services.extractor import ExtractionInputError
from app.services.subtitle_extractor import (
    build_subtitle_download_name,
    filter_webvtt,
    parse_vtt_cues,
    render_srt,
)


SAMPLE_VTT = """WEBVTT

00:00:01.000 --> 00:00:05.000
First line

00:00:10.000 --> 00:00:15.000
Second line

00:00:20.000 --> 00:00:25.000
Third line
"""


def test_filter_webvtt_keeps_only_selected_range():
    filtered = filter_webvtt(SAMPLE_VTT, 9, 20)

    assert "Second line" in filtered
    assert "First line" not in filtered
    assert "Third line" not in filtered
    assert "WEBVTT" in filtered


def test_parse_vtt_and_render_srt():
    cues = parse_vtt_cues(SAMPLE_VTT)
    rendered = render_srt(cues[:1])

    assert "1" in rendered
    assert "00:00:01,000 --> 00:00:05,000" in rendered
    assert "First line" in rendered


def test_filter_webvtt_raises_when_no_cues_match():
    with pytest.raises(ExtractionInputError):
        filter_webvtt(SAMPLE_VTT, 30, 40)


def test_build_subtitle_download_name_includes_language_and_range():
    name = build_subtitle_download_name("Sample Video", "en", 10, 30)

    assert name == "Sample Video_00-10_to_00-30_en.srt"
