from __future__ import annotations


def parse_timestamp(value: str | None) -> float | None:
    if value is None:
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    parts = cleaned.split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError("Time format must be seconds, MM:SS, or HH:MM:SS.")

    try:
        numbers = [float(part) for part in parts]
    except ValueError as exc:
        raise ValueError("Time values must be numeric.") from exc

    if any(number < 0 for number in numbers):
        raise ValueError("Time values must be non-negative.")

    if len(numbers) >= 2 and any(number >= 60 for number in numbers[1:]):
        raise ValueError("Minutes and seconds must be below 60.")

    total = 0.0
    for number in numbers:
        total = (total * 60) + number
    return total


def validate_time_range(start_time: str | None, end_time: str | None) -> tuple[float | None, float | None]:
    start_seconds = parse_timestamp(start_time)
    end_seconds = parse_timestamp(end_time)

    if start_seconds is not None and end_seconds is not None and start_seconds >= end_seconds:
        raise ValueError("End time must be after start time.")

    return start_seconds, end_seconds


def seconds_to_ffmpeg_timestamp(seconds: float | None) -> str | None:
    if seconds is None:
        return None

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole_seconds = int(seconds % 60)
    milliseconds = int(round((seconds - int(seconds)) * 1000))

    if milliseconds == 1000:
        whole_seconds += 1
        milliseconds = 0

    if whole_seconds == 60:
        minutes += 1
        whole_seconds = 0

    if minutes == 60:
        hours += 1
        minutes = 0

    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
