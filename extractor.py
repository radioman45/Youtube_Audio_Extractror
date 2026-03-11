# Install example: pip install yt-dlp faster-whisper ffmpeg
# Example:
# python extractor.py --url https://youtube.com/watch?v=example --model large-v3-turbo

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Sequence

from app.services.extractor import ExtractionInputError, ExtractionRuntimeError, cleanup_temp_dir
from app.services.whisper_subtitle_extractor import (
    SUPPORTED_WHISPER_MODELS,
    WhisperSubtitleOptions,
    extract_whisper_subtitles,
)


def ensure_unique_output_path(directory: Path, filename: str) -> Path:
    base = Path(filename)
    candidate = directory / base.name
    index = 1
    while candidate.exists():
        candidate = directory / f"{base.stem}_{index}{base.suffix}"
        index += 1
    return candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download YouTube audio locally and generate SRT subtitles with faster-whisper.",
    )
    parser.add_argument("--url", required=True, help="YouTube video URL")
    parser.add_argument(
        "--model",
        required=True,
        choices=SUPPORTED_WHISPER_MODELS,
        help="Whisper model. Use tiny/base for low-spec PCs, large-v3-turbo for high-spec PCs.",
    )
    parser.add_argument("--language", default="ko", help="Subtitle language code. Default: ko")
    parser.add_argument(
        "--output-format",
        default="srt",
        choices=("srt",),
        help="Subtitle output format. Only srt is currently supported.",
    )
    parser.add_argument(
        "--vad-filter",
        dest="vad_filter",
        action="store_true",
        default=True,
        help="Enable VAD filtering for more accurate subtitle segmentation.",
    )
    parser.add_argument(
        "--no-vad-filter",
        dest="vad_filter",
        action="store_false",
        help="Disable VAD filtering.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        result = extract_whisper_subtitles(
            WhisperSubtitleOptions(
                url=args.url,
                model=args.model,
                language=args.language,
                output_format=args.output_format,
                vad_filter=bool(args.vad_filter),
            )
        )
    except (ExtractionInputError, ExtractionRuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output_dir = Path.cwd()
    destination = ensure_unique_output_path(output_dir, result.download_name)

    try:
        shutil.move(str(result.file_path), destination)
    finally:
        cleanup_temp_dir(result.temp_dir)

    print(f"Success: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
