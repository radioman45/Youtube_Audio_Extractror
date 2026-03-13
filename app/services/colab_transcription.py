from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.extractor import ExtractionInputError, ExtractionResult, sanitize_filename
from app.services.subtitle_extractor import normalize_subtitle_format, resolve_subtitle_media_type
from app.services.whisper_subtitle_extractor import (
    LocalWhisperSubtitleOptions,
    build_whisper_download_name,
    normalize_local_whisper_options,
)


COLAB_HOME_URL = "https://colab.research.google.com/"
COLAB_NOTEBOOK_FILENAME = "whisper_transcribe.ipynb"
COLAB_BUNDLE_FILENAME = "colab-job.zip"
COLAB_RESULT_FILENAME = "colab-result.zip"


@dataclass(slots=True)
class ColabBundleInfo:
    bundle_path: Path
    bundle_download_name: str
    manifest_path: Path
    source_sha256: str
    archive_source_name: str
    expected_output_name: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_colab_bundle_download_name(source_name: str) -> str:
    stem = sanitize_filename(Path(source_name).stem or "uploaded-audio")
    return f"{stem}_colab_bundle.zip"


def build_colab_manifest(
    *,
    job_id: str,
    source_name: str,
    archive_source_name: str,
    source_sha256: str,
    options: LocalWhisperSubtitleOptions,
    expected_output_name: str,
) -> dict[str, object]:
    subtitle_format = normalize_subtitle_format(options.subtitle_format)
    return {
        "version": 1,
        "jobId": job_id,
        "sourceName": source_name,
        "sourceArchiveName": archive_source_name,
        "sourceSha256": source_sha256,
        "language": options.language,
        "subtitleFormat": subtitle_format,
        "whisperModel": options.model,
        "whisperDevice": options.device,
        "vadFilter": options.vad_filter,
        "startTime": options.start_time,
        "endTime": options.end_time,
        "expectedOutputName": expected_output_name,
    }


def build_result_schema() -> dict[str, object]:
    return {
        "required": [
            "jobId",
            "sourceSha256",
            "subtitleFormat",
            "downloadName",
            "resultFile",
        ],
        "optional": [
            "whisperModel",
            "device",
            "language",
            "segmentCount",
            "durationSeconds",
            "generator",
        ],
    }


def build_bundle_readme() -> str:
    return "\n".join(
        [
            "Colab job bundle",
            "",
            "1. Open Google Colab.",
            "2. Upload the notebook template and run its setup cell.",
            "3. Either upload this ZIP bundle when prompted or mount Google Drive and point the notebook at the bundle path.",
            "4. Download the generated result ZIP or save it into Google Drive.",
            "5. Import the result ZIP back into the app.",
            "",
            "Do not rename manifest.json or result.json files.",
        ]
    )


def create_colab_job_bundle(
    *,
    job_id: str,
    source_path: Path,
    source_name: str,
    options: LocalWhisperSubtitleOptions,
    work_dir: Path,
) -> ColabBundleInfo:
    if not source_path.exists():
        raise ExtractionInputError("The uploaded source audio file was not found.")

    (
        normalized_model,
        normalized_language,
        _normalized_output_format,
        normalized_subtitle_format,
        normalized_device,
        start_seconds,
        end_seconds,
    ) = normalize_local_whisper_options(options)
    source_sha256 = sha256_file(source_path)
    archive_source_name = sanitize_filename(source_name) or "uploaded-audio"
    expected_output_name = build_whisper_download_name(
        title=Path(source_name).stem or "uploaded-audio",
        model=normalized_model,
        language=normalized_language,
        output_format="srt",
        subtitle_format=normalized_subtitle_format,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
    )
    normalized_options = LocalWhisperSubtitleOptions(
        model=normalized_model,
        language=normalized_language,
        subtitle_format=normalized_subtitle_format,
        device=normalized_device,
        vad_filter=options.vad_filter,
        start_time=options.start_time,
        end_time=options.end_time,
    )
    manifest = build_colab_manifest(
        job_id=job_id,
        source_name=source_name,
        archive_source_name=archive_source_name,
        source_sha256=source_sha256,
        options=normalized_options,
        expected_output_name=expected_output_name,
    )

    bundle_path = work_dir / COLAB_BUNDLE_FILENAME
    manifest_path = work_dir / "colab-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(source_path, arcname=f"source/{archive_source_name}")
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("result-schema.json", json.dumps(build_result_schema(), ensure_ascii=False, indent=2))
        archive.writestr("README.txt", build_bundle_readme())

    return ColabBundleInfo(
        bundle_path=bundle_path,
        bundle_download_name=build_colab_bundle_download_name(source_name),
        manifest_path=manifest_path,
        source_sha256=source_sha256,
        archive_source_name=archive_source_name,
        expected_output_name=expected_output_name,
    )


def _find_archive_member(archive: zipfile.ZipFile, *candidate_names: str) -> str | None:
    members = archive.namelist()
    for candidate in candidate_names:
        if candidate in members:
            return candidate
    basenames = {Path(name).name: name for name in members}
    for candidate in candidate_names:
        basename = Path(candidate).name
        if basename in basenames:
            return basenames[basename]
    return None


def import_colab_result_package(
    *,
    package_path: Path,
    work_dir: Path,
    job_id: str,
    expected_details: dict[str, Any],
) -> tuple[ExtractionResult, dict[str, object]]:
    if not package_path.exists():
        raise ExtractionInputError("The uploaded Colab result package was not found.")

    expected_source_sha256 = str(expected_details.get("sourceSha256") or "").strip()
    expected_download_name = str(expected_details.get("colabResultName") or "").strip()
    expected_subtitle_format = normalize_subtitle_format(str(expected_details.get("subtitleFormat") or "timestamped"))
    if not expected_source_sha256 or not expected_download_name:
        raise ExtractionInputError("The Colab job is missing required validation metadata.")

    try:
        with zipfile.ZipFile(package_path) as archive:
            manifest_member = _find_archive_member(archive, "result.json")
            if manifest_member is None:
                raise ExtractionInputError("The Colab result package is missing result.json.")

            result_manifest = json.loads(archive.read(manifest_member).decode("utf-8"))
            if not isinstance(result_manifest, dict):
                raise ExtractionInputError("The Colab result manifest is invalid.")

            if str(result_manifest.get("jobId") or "") != job_id:
                raise ExtractionInputError("The Colab result job ID does not match this request.")

            if str(result_manifest.get("sourceSha256") or "") != expected_source_sha256:
                raise ExtractionInputError("The Colab result package was generated for a different source file.")

            result_subtitle_format = normalize_subtitle_format(str(result_manifest.get("subtitleFormat") or expected_subtitle_format))
            if result_subtitle_format != expected_subtitle_format:
                raise ExtractionInputError("The Colab result subtitle format does not match the requested format.")

            result_file_name = str(result_manifest.get("resultFile") or "").strip()
            if not result_file_name:
                raise ExtractionInputError("The Colab result manifest is missing resultFile.")

            result_member = _find_archive_member(archive, result_file_name)
            if result_member is None:
                raise ExtractionInputError("The Colab result output file is missing from the ZIP package.")

            result_bytes = archive.read(result_member)
    except zipfile.BadZipFile as exc:
        raise ExtractionInputError("The uploaded Colab result file is not a valid ZIP archive.") from exc

    if not result_bytes:
        raise ExtractionInputError("The uploaded Colab result output is empty.")

    expected_suffix = ".txt" if expected_subtitle_format == "clean" else ".srt"
    output_path = work_dir / expected_download_name
    if output_path.suffix.lower() != expected_suffix:
        output_path = output_path.with_suffix(expected_suffix)

    output_path.write_bytes(result_bytes)
    media_type = resolve_subtitle_media_type(expected_subtitle_format)

    details = {
        "resultModel": str(result_manifest.get("whisperModel") or result_manifest.get("model") or ""),
        "resultDevice": str(result_manifest.get("device") or ""),
        "resultLanguage": str(result_manifest.get("language") or ""),
        "resultSegments": int(result_manifest.get("segmentCount") or 0),
        "resultDurationSeconds": float(result_manifest.get("durationSeconds") or 0.0),
        "resultGenerator": str(result_manifest.get("generator") or "google-colab"),
    }
    return (
        ExtractionResult(
            file_path=output_path,
            download_name=output_path.name,
            temp_dir=work_dir,
            media_type=media_type,
        ),
        details,
    )


def build_colab_notebook_payload() -> bytes:
    markdown_cell = [
        "# GPU Whisper transcription notebook",
        "",
        "1. Run the install cell.",
        "2. Choose one input path:",
        "   - upload the Colab job bundle ZIP from the app, or",
        "   - mount Google Drive and point the notebook to the bundle ZIP path.",
        "3. Wait for transcription to finish.",
        "4. Download the generated `colab-result.zip` file or save it into Google Drive.",
        "5. Import the ZIP back into the app.",
    ]
    setup_cell = """!pip -q install faster-whisper\n!apt -qq update && apt -qq install -y ffmpeg"""
    config_cell = """USE_GOOGLE_DRIVE = False
DRIVE_BUNDLE_PATH = "/content/drive/MyDrive/ColabHandoff/your_bundle.zip"
DRIVE_OUTPUT_DIR = "/content/drive/MyDrive/ColabHandoff/results"
DOWNLOAD_RESULT_TO_BROWSER = True

# If USE_GOOGLE_DRIVE is True:
# 1. Put the exported bundle ZIP somewhere in Google Drive.
# 2. Set DRIVE_BUNDLE_PATH to that ZIP file.
# 3. Set DRIVE_OUTPUT_DIR to where you want the subtitle file and result ZIP saved.
# 4. Set DOWNLOAD_RESULT_TO_BROWSER to False if Drive saving is enough."""
    run_cell = """import json
import shutil
import zipfile
from pathlib import Path

from google.colab import drive, files
from faster_whisper import WhisperModel


WORK_DIR = Path("/content/colab-whisper-job")
WORK_DIR.mkdir(parents=True, exist_ok=True)

if USE_GOOGLE_DRIVE:
    drive.mount("/content/drive", force_remount=False)

    drive_bundle_path = Path(DRIVE_BUNDLE_PATH.strip())
    if not DRIVE_BUNDLE_PATH.strip():
        raise RuntimeError("Set DRIVE_BUNDLE_PATH before running the notebook.")
    if not drive_bundle_path.exists():
        raise FileNotFoundError(f"Bundle ZIP not found in Google Drive: {drive_bundle_path}")

    bundle_path = WORK_DIR / drive_bundle_path.name
    shutil.copy2(drive_bundle_path, bundle_path)
    print(f"Loaded bundle ZIP from Google Drive: {drive_bundle_path}")
else:
    uploaded = files.upload()
    if not uploaded:
        raise RuntimeError("Upload the Colab job bundle ZIP file.")

    bundle_name = next(iter(uploaded))
    bundle_path = WORK_DIR / bundle_name
    bundle_path.write_bytes(uploaded[bundle_name])

with zipfile.ZipFile(bundle_path) as archive:
    archive.extractall(WORK_DIR)

manifest_path = WORK_DIR / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

source_path = WORK_DIR / "source" / manifest["sourceArchiveName"]
subtitle_format = manifest.get("subtitleFormat", "timestamped")
result_name = manifest.get("expectedOutputName") or ("result.txt" if subtitle_format == "clean" else "result.srt")

device = "cuda"
try:
    model = WhisperModel(manifest.get("whisperModel", "large-v3-turbo"), device=device)
except Exception:
    device = "cpu"
    model = WhisperModel(manifest.get("whisperModel", "large-v3-turbo"), device=device)

segments, _ = model.transcribe(
    str(source_path),
    language=manifest.get("language") or "ko",
    vad_filter=bool(manifest.get("vadFilter", True)),
    condition_on_previous_text=False,
)

segment_list = list(segments)

def format_srt_timestamp(value: float) -> str:
    whole_seconds = int(value)
    milliseconds = int(round((value - whole_seconds) * 1000))
    if milliseconds == 1000:
        whole_seconds += 1
        milliseconds = 0
    hours = whole_seconds // 3600
    minutes = (whole_seconds % 3600) // 60
    seconds = whole_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def render_output() -> str:
    if subtitle_format == "clean":
        lines = []
        last_line = None
        for segment in segment_list:
            text = str(getattr(segment, "text", "") or "").strip()
            if not text:
                continue
            if text == last_line:
                continue
            lines.append(text)
            last_line = text
        return "\\n".join(lines).strip() + "\\n"

    blocks = []
    for index, segment in enumerate(segment_list, start=1):
        text = str(getattr(segment, "text", "") or "").strip()
        if not text:
            continue
        start = float(getattr(segment, "start", 0.0) or 0.0)
        end = float(getattr(segment, "end", 0.0) or 0.0)
        blocks.append(
            "\\n".join(
                [
                    str(index),
                    f"{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}",
                    text,
                ]
            )
        )
    return "\\n\\n".join(blocks).strip() + "\\n"

output_path = WORK_DIR / result_name
output_path.write_text(render_output(), encoding="utf-8")

result_manifest = {
    "jobId": manifest["jobId"],
    "sourceSha256": manifest["sourceSha256"],
    "subtitleFormat": subtitle_format,
    "downloadName": output_path.name,
    "resultFile": output_path.name,
    "whisperModel": manifest.get("whisperModel"),
    "device": device,
    "language": manifest.get("language"),
    "segmentCount": len(segment_list),
    "durationSeconds": float(getattr(segment_list[-1], "end", 0.0) or 0.0) if segment_list else 0.0,
    "generator": "google-colab-faster-whisper",
}

result_zip_path = WORK_DIR / "colab-result.zip"
with zipfile.ZipFile(result_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    archive.write(output_path, arcname=output_path.name)
    archive.writestr("result.json", json.dumps(result_manifest, ensure_ascii=False, indent=2))

if USE_GOOGLE_DRIVE:
    drive_output_dir = Path(DRIVE_OUTPUT_DIR.strip() or "/content/drive/MyDrive/ColabHandoff/results")
    drive_output_dir.mkdir(parents=True, exist_ok=True)

    drive_subtitle_path = drive_output_dir / output_path.name
    drive_result_zip_path = drive_output_dir / f"{manifest['jobId']}_colab-result.zip"
    shutil.copy2(output_path, drive_subtitle_path)
    shutil.copy2(result_zip_path, drive_result_zip_path)
    print(f"Saved subtitle file to Google Drive: {drive_subtitle_path}")
    print(f"Saved result ZIP to Google Drive: {drive_result_zip_path}")

if DOWNLOAD_RESULT_TO_BROWSER:
    files.download(str(result_zip_path))
else:
    print(f"Browser download skipped. Local result ZIP: {result_zip_path}")
"""
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [line + "\n" for line in markdown_cell],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [line + "\n" for line in setup_cell.splitlines()],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [line + "\n" for line in config_cell.splitlines()],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [line + "\n" for line in run_cell.splitlines()],
            },
        ],
        "metadata": {
            "accelerator": "GPU",
            "colab": {
                "name": COLAB_NOTEBOOK_FILENAME,
                "provenance": [],
                "gpuType": "T4",
                "machine_shape": "hm",
            },
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(notebook, ensure_ascii=False, indent=2).encode("utf-8")
