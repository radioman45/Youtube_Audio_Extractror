import pytest

from app.services.time_utils import parse_timestamp, seconds_to_ffmpeg_timestamp, validate_time_range


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("90", 90.0),
        ("01:30", 90.0),
        ("01:02:03", 3723.0),
        ("1:02:03.5", 3723.5),
        ("", None),
        (None, None),
    ],
)
def test_parse_timestamp(value, expected):
    assert parse_timestamp(value) == expected


def test_validate_time_range_rejects_invalid_order():
    with pytest.raises(ValueError):
        validate_time_range("10", "5")


def test_seconds_to_ffmpeg_timestamp_formats_output():
    assert seconds_to_ffmpeg_timestamp(3723.25) == "01:02:03.250"
