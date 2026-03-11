from __future__ import annotations

import json
import math
import os
import tempfile
import wave
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from app.services.app_state import get_app_state_root
from app.services.extractor import (
    ExtractionInputError,
    ExtractionResult,
    ExtractionRuntimeError,
    ProgressCallback,
    build_download_name,
    cleanup_temp_dir,
    download_source_audio,
    notify_progress,
    parse_time_to_seconds,
    probe_media_info,
    resolve_ffmpeg_path,
    run_ffmpeg,
    sanitize_filename,
    validate_requested_range,
    validate_time_range,
    validate_youtube_url,
)
from app.services.subtitle_extractor import format_srt_timestamp, normalize_language_code
from app.services.time_utils import seconds_to_ffmpeg_timestamp


SubtitleEngine = str
WhisperModelName = str
WhisperOutputFormat = str

SUPPORTED_SUBTITLE_ENGINES: tuple[SubtitleEngine, ...] = ("youtube", "whisper")
SUPPORTED_WHISPER_MODELS: tuple[WhisperModelName, ...] = (
    "tiny",
    "base",
    "small",
    "medium",
    "large",
    "large-v3",
    "large-v3-turbo",
)
SUPPORTED_WHISPER_OUTPUT_FORMATS: tuple[WhisperOutputFormat, ...] = ("srt",)
SUPPORTED_UPLOAD_AUDIO_EXTENSIONS: tuple[str, ...] = (
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".opus",
    ".webm",
    ".mp4",
    ".mkv",
    ".flac",
    ".ogg",
)
MODEL_NAME_ALIASES: dict[str, str] = {
    "large": "large-v3",
}
WHISPER_MODEL_REPOSITORIES: dict[str, str] = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}
WHISPER_SUPPORT_FILE_PATTERNS: tuple[str, ...] = (
    "config.json",
    "preprocessor_config.json",
    "tokenizer.json",
    "vocabulary.*",
)
LOCAL_ONLY_ENV_VAR = "APP_WHISPER_LOCAL_ONLY"
WHISPER_DEVICE_ENV_VAR = "APP_WHISPER_DEVICE"
SUPPORTED_WHISPER_DEVICES: tuple[str, ...] = ("cpu", "auto", "cuda")
WHISPER_SAMPLE_RATE = 16000
WHISPER_CHANNELS = 1
WHISPER_CHUNK_SECONDS = 30 * 60
WHISPER_CHUNK_FILESIZE_BYTES = 512 * 1024 * 1024
WHISPER_RESUME_STATE_FILENAME = "whisper-resume-state.json"
WHISPER_FULL_CUES_FILENAME = "whisper-full-cues.json"


@dataclass(slots=True)
class WhisperCue:
    start: float
    end: float
    text: str


@dataclass(slots=True)
class WhisperSubtitleOptions:
    url: str
    model: WhisperModelName
    language: str = "ko"
    output_format: WhisperOutputFormat = "srt"
    vad_filter: bool = True
    start_time: str | None = None
    end_time: str | None = None


@dataclass(slots=True)
class LocalWhisperSubtitleOptions:
    model: WhisperModelName
    language: str = "ko"
    output_format: WhisperOutputFormat = "srt"
    vad_filter: bool = True
    start_time: str | None = None
    end_time: str | None = None


ResumeStateCallback = Callable[[dict[str, object]], None]


def normalize_subtitle_engine(engine: str) -> str:
    normalized = engine.strip().lower()
    if normalized not in SUPPORTED_SUBTITLE_ENGINES:
        raise ExtractionInputError("Unsupported subtitle engine.")
    return normalized


def normalize_whisper_model(model: str) -> str:
    normalized = model.strip().lower()
    if normalized not in SUPPORTED_WHISPER_MODELS:
        raise ExtractionInputError("Unsupported Whisper model.")
    return normalized


def normalize_output_format(output_format: str) -> str:
    normalized = output_format.strip().lower()
    if normalized not in SUPPORTED_WHISPER_OUTPUT_FORMATS:
        raise ExtractionInputError("Unsupported subtitle output format.")
    return normalized


def validate_upload_audio_filename(filename: str) -> str:
    cleaned = filename.strip()
    if not cleaned:
        raise ExtractionInputError("No audio file was uploaded.")

    suffix = Path(cleaned).suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_AUDIO_EXTENSIONS:
        raise ExtractionInputError("Unsupported uploaded audio format.")
    return cleaned


def write_json_file(path: Path, payload: dict[str, object] | list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def read_json_file(path: Path) -> dict[str, object] | list[object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_whisper_resume_state_path(temp_dir: Path) -> Path:
    return temp_dir / WHISPER_RESUME_STATE_FILENAME


def get_whisper_chunk_cues_path(temp_dir: Path, chunk_index: int) -> Path:
    return temp_dir / f"whisper-chunk-{chunk_index:03d}.json"


def get_whisper_full_cues_path(temp_dir: Path) -> Path:
    return temp_dir / WHISPER_FULL_CUES_FILENAME


def serialize_whisper_cues(cues: list[WhisperCue]) -> list[dict[str, object]]:
    return [
        {
            "start": cue.start,
            "end": cue.end,
            "text": cue.text,
        }
        for cue in cues
    ]


def deserialize_whisper_cues(payload: object) -> list[WhisperCue]:
    if not isinstance(payload, list):
        return []

    cues: list[WhisperCue] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        cues.append(
            WhisperCue(
                start=float(item.get("start") or 0.0),
                end=float(item.get("end") or 0.0),
                text=str(item.get("text") or ""),
            )
        )
    return cues


def load_whisper_resume_state(temp_dir: Path) -> dict[str, object]:
    payload = read_json_file(get_whisper_resume_state_path(temp_dir))
    if isinstance(payload, dict):
        return payload
    return {}


def save_whisper_resume_state(temp_dir: Path, payload: dict[str, object]) -> None:
    write_json_file(get_whisper_resume_state_path(temp_dir), payload)


def load_saved_whisper_cues(path: Path) -> list[WhisperCue]:
    payload = read_json_file(path)
    return deserialize_whisper_cues(payload)


def save_whisper_cues(path: Path, cues: list[WhisperCue]) -> None:
    write_json_file(path, serialize_whisper_cues(cues))


def build_whisper_download_name(
    title: str,
    model: WhisperModelName,
    language: str,
    output_format: WhisperOutputFormat,
    start_seconds: int | None,
    end_seconds: int | None,
) -> str:
    base_name = build_download_name(title, output_format, start_seconds, end_seconds).rsplit(".", 1)[0]
    safe_model = sanitize_filename(model).replace(" ", "-")
    safe_language = normalize_language_code(language).replace("-", "_")
    return f"{base_name}_whisper_{safe_model}_{safe_language}.{output_format}"


def build_whisper_wav_command(
    ffmpeg_path: str,
    input_path: Path,
    output_path: Path,
    start_seconds: int | None,
    end_seconds: int | None,
) -> list[str]:
    command = [ffmpeg_path, "-y"]

    if start_seconds is not None:
        command.extend(["-ss", seconds_to_ffmpeg_timestamp(float(start_seconds)) or "00:00:00.000"])

    command.extend(["-i", str(input_path)])

    if end_seconds is not None:
        if start_seconds is not None:
            command.extend(["-t", str(end_seconds - start_seconds)])
        else:
            command.extend(["-to", seconds_to_ffmpeg_timestamp(float(end_seconds)) or "00:00:00.000"])

    command.extend(
        [
            "-vn",
            "-ac",
            str(WHISPER_CHANNELS),
            "-ar",
            str(WHISPER_SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return command


def build_chunk_wav_command(
    ffmpeg_path: str,
    input_path: Path,
    output_path: Path,
    chunk_start_seconds: float,
    chunk_duration_seconds: float,
) -> list[str]:
    return [
        ffmpeg_path,
        "-y",
        "-ss",
        seconds_to_ffmpeg_timestamp(chunk_start_seconds) or "00:00:00.000",
        "-i",
        str(input_path),
        "-t",
        str(chunk_duration_seconds),
        "-vn",
        "-ac",
        str(WHISPER_CHANNELS),
        "-ar",
        str(WHISPER_SAMPLE_RATE),
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]


def calculate_effective_duration(
    duration_seconds: float | None,
    start_seconds: int | None,
    end_seconds: int | None,
) -> float | None:
    if duration_seconds is None:
        return None

    trimmed_start = float(start_seconds or 0)
    trimmed_end = float(end_seconds) if end_seconds is not None else float(duration_seconds)
    return max(0.0, trimmed_end - trimmed_start)


def should_chunk_audio(wav_path: Path, effective_duration_seconds: float | None) -> bool:
    if effective_duration_seconds is not None and effective_duration_seconds > WHISPER_CHUNK_SECONDS:
        return True
    return wav_path.stat().st_size >= WHISPER_CHUNK_FILESIZE_BYTES


def build_chunk_plan(effective_duration_seconds: float) -> list[tuple[float, float]]:
    if effective_duration_seconds <= 0:
        return []

    chunk_count = max(1, math.ceil(effective_duration_seconds / WHISPER_CHUNK_SECONDS))
    plan: list[tuple[float, float]] = []
    for chunk_index in range(chunk_count):
        chunk_start = float(chunk_index * WHISPER_CHUNK_SECONDS)
        chunk_end = min(effective_duration_seconds, chunk_start + WHISPER_CHUNK_SECONDS)
        plan.append((chunk_start, max(0.0, chunk_end - chunk_start)))
    return plan


def estimate_wav_duration_seconds(wav_path: Path) -> float | None:
    try:
        with wave.open(str(wav_path), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            if frame_rate <= 0:
                return None
            return float(wav_file.getnframes()) / float(frame_rate)
    except (EOFError, wave.Error, OSError):
        return None


@contextmanager
def offline_model_loading() -> Iterator[None]:
    previous_value = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        yield
    finally:
        if previous_value is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous_value


def resolve_model_name(model: str) -> str:
    normalized = normalize_whisper_model(model)
    return MODEL_NAME_ALIASES.get(normalized, normalized)


def should_use_local_only_whisper_model() -> bool:
    value = os.environ.get(LOCAL_ONLY_ENV_VAR, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def resolve_whisper_device() -> str:
    configured = os.environ.get(WHISPER_DEVICE_ENV_VAR, "cpu").strip().lower()
    if configured not in SUPPORTED_WHISPER_DEVICES:
        return "cpu"
    return configured


def get_whisper_repository_id(model: str) -> str:
    try:
        return WHISPER_MODEL_REPOSITORIES[model]
    except KeyError as exc:
        raise ExtractionRuntimeError(f"Unsupported Whisper repository mapping for model '{model}'.") from exc


def get_whisper_model_cache_root() -> Path:
    return get_app_state_root() / "whisper-models"


def get_whisper_model_cache_dir(model: str) -> Path:
    return get_whisper_model_cache_root() / model


def has_complete_local_whisper_model(model_dir: Path) -> bool:
    if not (model_dir / "config.json").exists():
        return False
    if not (model_dir / "preprocessor_config.json").exists():
        return False
    if not (model_dir / "tokenizer.json").exists():
        return False
    if not (model_dir / "model.bin").exists():
        return False
    return any(model_dir.glob("vocabulary.*"))


def download_whisper_support_files(repo_id: str, model_dir: Path) -> None:
    from huggingface_hub import snapshot_download

    model_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id,
        allow_patterns=list(WHISPER_SUPPORT_FILE_PATTERNS),
        local_dir=str(model_dir),
        local_dir_use_symlinks=False,
    )


def download_whisper_model_binary(
    *,
    repo_id: str,
    model: str,
    target_path: Path,
    progress_callback: ProgressCallback | None = None,
) -> None:
    import httpx
    from huggingface_hub import hf_hub_url

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(".bin.part")
    existing_bytes = temp_path.stat().st_size if temp_path.exists() else 0

    headers: dict[str, str] = {}
    if existing_bytes > 0:
        headers["Range"] = f"bytes={existing_bytes}-"

    with httpx.Client(follow_redirects=True, timeout=None) as client:
        with client.stream("GET", hf_hub_url(repo_id, "model.bin"), headers=headers) as response:
            response.raise_for_status()

            total_bytes = 0
            mode = "wb"
            if response.status_code == 206 and existing_bytes > 0:
                total_bytes = existing_bytes + int(response.headers.get("Content-Length") or 0)
                mode = "ab"
            else:
                existing_bytes = 0
                total_bytes = int(response.headers.get("Content-Length") or 0)
                if temp_path.exists():
                    temp_path.unlink()

            written_bytes = existing_bytes
            last_reported_percent = -1
            with temp_path.open(mode) as handle:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    written_bytes += len(chunk)

                    if total_bytes <= 0:
                        continue

                    percent = int((written_bytes / total_bytes) * 100)
                    if percent == last_reported_percent:
                        continue
                    last_reported_percent = percent
                    mapped_progress = 90 + min(3, int((percent / 100) * 3))
                    notify_progress(
                        progress_callback,
                        mapped_progress,
                        f"Downloading Whisper model '{model}' ({percent}%).",
                    )

    temp_path.replace(target_path)


def ensure_local_whisper_model_directory(
    model: str,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    resolved_name = resolve_model_name(model)
    repo_id = get_whisper_repository_id(resolved_name)
    model_dir = get_whisper_model_cache_dir(resolved_name)

    if has_complete_local_whisper_model(model_dir):
        return model_dir

    notify_progress(
        progress_callback,
        90,
        f"Preparing Whisper model '{model}' for local use.",
    )
    download_whisper_support_files(repo_id, model_dir)
    if not (model_dir / "model.bin").exists():
        download_whisper_model_binary(
            repo_id=repo_id,
            model=model,
            target_path=model_dir / "model.bin",
            progress_callback=progress_callback,
        )

    if not has_complete_local_whisper_model(model_dir):
        raise ExtractionRuntimeError(f"Whisper model '{model}' was downloaded incompletely.")

    return model_dir


def instantiate_whisper_model(whisper_model_class, model_name: str, *, local_files_only: bool, device: str):
    try:
        return whisper_model_class(model_name, device=device, local_files_only=local_files_only)
    except TypeError:
        if local_files_only:
            with offline_model_loading():
                return whisper_model_class(model_name, device=device)
        return whisper_model_class(model_name, device=device)


def load_whisper_model(
    model: WhisperModelName,
    progress_callback: ProgressCallback | None = None,
):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ExtractionRuntimeError(
            "faster-whisper is not installed. Install it with `pip install faster-whisper`."
        ) from exc

    resolved_name = resolve_model_name(model)
    device = resolve_whisper_device()

    try:
        with offline_model_loading():
            return instantiate_whisper_model(WhisperModel, resolved_name, local_files_only=True, device=device)
    except Exception as local_exc:
        manual_model_dir = get_whisper_model_cache_dir(resolved_name)
        if has_complete_local_whisper_model(manual_model_dir):
            return WhisperModel(str(manual_model_dir), device=device)
        if should_use_local_only_whisper_model():
            raise ExtractionRuntimeError(
                f"Whisper model '{model}' is not available locally. Cache the model before running offline."
            ) from local_exc

    notify_progress(
        progress_callback,
        90,
        f"Whisper model '{model}' is not cached locally. Downloading it once for future offline use.",
    )
    try:
        downloaded_model = instantiate_whisper_model(WhisperModel, resolved_name, local_files_only=False, device=device)
    except Exception:
        notify_progress(
            progress_callback,
            90,
            f"Whisper Hub download for model '{model}' failed. Retrying with direct download.",
        )
        try:
            model_dir = ensure_local_whisper_model_directory(model, progress_callback=progress_callback)
            downloaded_model = WhisperModel(str(model_dir), device=device)
        except Exception as download_exc:
            raise ExtractionRuntimeError(
                f"Whisper model '{model}' could not be downloaded. Check internet access, disk space, or choose a smaller model like 'base'."
            ) from download_exc

    notify_progress(progress_callback, 92, f"Whisper model '{model}' is ready.")
    return downloaded_model


def collect_transcribed_cues(
    model,
    audio_path: Path,
    *,
    language: str,
    vad_filter: bool,
    offset_seconds: float,
    progress_callback: ProgressCallback | None = None,
    progress_start: int | None = None,
    progress_end: int | None = None,
    expected_duration_seconds: float | None = None,
    progress_message_prefix: str | None = None,
) -> list[WhisperCue]:
    try:
        segments, _ = model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=vad_filter,
            condition_on_previous_text=False,
        )
    except RuntimeError as exc:
        raw_message = str(exc)
        normalized_message = raw_message.lower()
        if "cublas" in normalized_message or "cudnn" in normalized_message or "cuda" in normalized_message:
            raise ExtractionRuntimeError(
                "Whisper GPU runtime is not available on this PC. The app will run on CPU by default after restart, or set APP_WHISPER_DEVICE=cpu."
            ) from exc
        raise ExtractionRuntimeError(f"Whisper transcription failed: {raw_message}") from exc
    except Exception as exc:
        raise ExtractionRuntimeError(f"Whisper transcription failed: {exc}") from exc

    cues: list[WhisperCue] = []
    last_progress_value: int | None = None
    last_message: str | None = None
    for segment in segments:
        text = str(getattr(segment, "text", "") or "").strip()
        start = float(getattr(segment, "start", 0.0) or 0.0) + offset_seconds
        end = float(getattr(segment, "end", 0.0) or 0.0) + offset_seconds

        if (
            progress_callback is not None
            and progress_start is not None
            and progress_end is not None
            and expected_duration_seconds is not None
            and expected_duration_seconds > 0
        ):
            raw_segment_end = float(getattr(segment, "end", 0.0) or 0.0)
            completion_ratio = max(0.0, min(raw_segment_end / expected_duration_seconds, 1.0))
            progress_value = progress_start + int((progress_end - progress_start) * completion_ratio)
            chunk_percent = int(completion_ratio * 100)
            if progress_message_prefix:
                message = f"{progress_message_prefix} ({chunk_percent}%)."
            else:
                message = f"Transcribing Whisper audio ({chunk_percent}%)."

            if progress_value != last_progress_value or message != last_message:
                notify_progress(progress_callback, progress_value, message)
                last_progress_value = progress_value
                last_message = message

        if not text:
            continue

        cues.append(WhisperCue(start=max(0.0, start), end=max(start, end), text=text))

    return cues


def render_whisper_srt(cues: list[WhisperCue]) -> str:
    blocks: list[str] = []
    for index, cue in enumerate(cues, start=1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_srt_timestamp(cue.start)} --> {format_srt_timestamp(cue.end)}",
                    cue.text,
                ]
            )
        )
    return "\n\n".join(blocks).strip() + "\n"


def normalize_local_whisper_options(options: LocalWhisperSubtitleOptions) -> tuple[str, str, str, int | None, int | None]:
    normalized_model = normalize_whisper_model(options.model)
    normalized_language = normalize_language_code(options.language)
    normalized_output_format = normalize_output_format(options.output_format)
    start_seconds = parse_time_to_seconds(options.start_time)
    end_seconds = parse_time_to_seconds(options.end_time)
    validate_time_range(start_seconds, end_seconds, None)
    return normalized_model, normalized_language, normalized_output_format, start_seconds, end_seconds


def transcribe_whisper_audio_file(
    *,
    source_path: Path,
    source_title: str,
    options: LocalWhisperSubtitleOptions,
    temp_dir: Path,
    progress_callback: ProgressCallback | None = None,
    source_duration_seconds: float | None = None,
    source_url: str | None = None,
    resume_state_callback: ResumeStateCallback | None = None,
) -> ExtractionResult:
    normalized_model, normalized_language, normalized_output_format, start_seconds, end_seconds = normalize_local_whisper_options(options)
    validate_requested_range(start_seconds, end_seconds, source_duration_seconds)

    ffmpeg_path = resolve_ffmpeg_path()
    whisper_input_path = temp_dir / "whisper-input.wav"
    resume_state = load_whisper_resume_state(temp_dir)

    if not source_path.exists() and not whisper_input_path.exists():
        raise ExtractionInputError("The source audio file was not found.")

    if whisper_input_path.exists():
        notify_progress(progress_callback, 84, "Reusing cached Whisper WAV input.")
    else:
        notify_progress(progress_callback, 84, "Converting source audio to Whisper WAV format.")
        run_ffmpeg(
            build_whisper_wav_command(
                ffmpeg_path=ffmpeg_path,
                input_path=source_path,
                output_path=whisper_input_path,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
            ),
            whisper_input_path,
        )

    notify_progress(progress_callback, 88, "Loading Whisper model.")
    model = load_whisper_model(normalized_model, progress_callback=progress_callback)

    effective_duration_seconds = calculate_effective_duration(source_duration_seconds, start_seconds, end_seconds)
    if effective_duration_seconds is None:
        effective_duration_seconds = estimate_wav_duration_seconds(whisper_input_path)

    base_offset_seconds = float(start_seconds or 0)
    chunk_plan = build_chunk_plan(effective_duration_seconds) if should_chunk_audio(whisper_input_path, effective_duration_seconds) and effective_duration_seconds is not None else []
    download_name = build_whisper_download_name(
        title=source_title,
        model=normalized_model,
        language=normalized_language,
        output_format=normalized_output_format,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
    )

    completed_chunks = {
        int(value)
        for value in list(resume_state.get("completedChunks") or [])
        if isinstance(value, (int, float, str)) and str(value).isdigit()
    }
    resume_state.update(
        {
            "sourceTitle": source_title,
            "sourcePath": str(source_path),
            "sourceUrl": source_url,
            "model": normalized_model,
            "language": normalized_language,
            "outputFormat": normalized_output_format,
            "vadFilter": options.vad_filter,
            "startSeconds": start_seconds,
            "endSeconds": end_seconds,
            "effectiveDurationSeconds": effective_duration_seconds,
            "downloadName": download_name,
            "chunkCount": len(chunk_plan) if chunk_plan else 1,
            "completedChunks": sorted(completed_chunks),
        }
    )
    save_whisper_resume_state(temp_dir, resume_state)
    if resume_state_callback is not None:
        resume_state_callback(
            {
                "whisperWorkDir": str(temp_dir),
                "sourceTitle": source_title,
                "sourcePath": str(source_path),
                "subtitleDownloadName": download_name,
                "chunkCount": len(chunk_plan) if chunk_plan else 1,
                "completedChunks": len(completed_chunks),
            }
        )

    cues: list[WhisperCue] = []

    if chunk_plan:
        for index, (chunk_start, chunk_duration) in enumerate(chunk_plan, start=1):
            chunk_cues_path = get_whisper_chunk_cues_path(temp_dir, index)
            if index in completed_chunks and chunk_cues_path.exists():
                cues.extend(load_saved_whisper_cues(chunk_cues_path))
                notify_progress(
                    progress_callback,
                    90 + int((index / len(chunk_plan)) * 9),
                    f"Recovered completed Whisper audio chunk {index}/{len(chunk_plan)}.",
                )
                continue

            chunk_path = temp_dir / f"whisper-chunk-{index:03d}.wav"
            if not chunk_path.exists():
                run_ffmpeg(
                    build_chunk_wav_command(
                        ffmpeg_path=ffmpeg_path,
                        input_path=whisper_input_path,
                        output_path=chunk_path,
                        chunk_start_seconds=chunk_start,
                        chunk_duration_seconds=chunk_duration,
                    ),
                    chunk_path,
                )

            chunk_progress_start = 90 + int(((index - 1) / len(chunk_plan)) * 9)
            chunk_progress_end = 90 + int((index / len(chunk_plan)) * 9)
            notify_progress(
                progress_callback,
                chunk_progress_start,
                f"Transcribing Whisper audio chunk {index}/{len(chunk_plan)} (0%).",
            )
            latest_chunk_cues = collect_transcribed_cues(
                model,
                chunk_path,
                language=normalized_language,
                vad_filter=options.vad_filter,
                offset_seconds=base_offset_seconds + chunk_start,
                progress_callback=progress_callback,
                progress_start=chunk_progress_start,
                progress_end=max(chunk_progress_start, chunk_progress_end),
                expected_duration_seconds=chunk_duration,
                progress_message_prefix=f"Transcribing Whisper audio chunk {index}/{len(chunk_plan)}",
            )
            cues.extend(latest_chunk_cues)
            if latest_chunk_cues:
                save_whisper_cues(chunk_cues_path, latest_chunk_cues)
            completed_chunks.add(index)
            resume_state["completedChunks"] = sorted(completed_chunks)
            save_whisper_resume_state(temp_dir, resume_state)
            if resume_state_callback is not None:
                resume_state_callback({"completedChunks": len(completed_chunks), "chunkCount": len(chunk_plan)})
    else:
        full_cues_path = get_whisper_full_cues_path(temp_dir)
        if full_cues_path.exists():
            notify_progress(progress_callback, 98, "Recovered completed Whisper transcription.")
            cues = load_saved_whisper_cues(full_cues_path)
        else:
            notify_progress(progress_callback, 94, "Transcribing audio with faster-whisper (0%).")
            cues = collect_transcribed_cues(
                model,
                whisper_input_path,
                language=normalized_language,
                vad_filter=options.vad_filter,
                offset_seconds=base_offset_seconds,
                progress_callback=progress_callback,
                progress_start=94,
                progress_end=99,
                expected_duration_seconds=effective_duration_seconds,
                progress_message_prefix="Transcribing audio with faster-whisper",
            )
            save_whisper_cues(full_cues_path, cues)

    if not cues:
        raise ExtractionRuntimeError("No speech was detected in the selected audio range.")

    output_path = temp_dir / download_name
    output_path.write_text(render_whisper_srt(cues), encoding="utf-8")

    notify_progress(progress_callback, 100, "Whisper subtitle extraction completed.")
    resume_state["status"] = "completed"
    save_whisper_resume_state(temp_dir, resume_state)
    return ExtractionResult(
        file_path=output_path,
        download_name=download_name,
        temp_dir=temp_dir,
        media_type="application/x-subrip; charset=utf-8",
    )


def extract_whisper_subtitles(
    options: WhisperSubtitleOptions,
    progress_callback: ProgressCallback | None = None,
    *,
    temp_dir: Path | None = None,
    resume_state_callback: ResumeStateCallback | None = None,
) -> ExtractionResult:
    normalized_url = validate_youtube_url(options.url)
    owns_temp_dir = temp_dir is None
    work_dir = temp_dir or Path(tempfile.mkdtemp(prefix="youtube-whisper-"))
    ffmpeg_path = resolve_ffmpeg_path()
    resume_state = load_whisper_resume_state(work_dir)

    try:
        notify_progress(progress_callback, 5, "Checking video metadata for Whisper subtitle extraction.")
        source_title = str(resume_state.get("sourceTitle") or "youtube-whisper")
        duration_value = resume_state.get("sourceDurationSeconds")
        duration_seconds = float(duration_value) if isinstance(duration_value, (int, float)) else None
        source_path_value = str(resume_state.get("sourcePath") or "")
        source_path = Path(source_path_value) if source_path_value else work_dir / "missing-source"

        if not source_path.exists() and not (work_dir / "whisper-input.wav").exists():
            metadata = probe_media_info(normalized_url, ffmpeg_path)
            raw_duration = metadata.get("duration")
            duration_seconds = float(raw_duration) if isinstance(raw_duration, (int, float)) else None
            start_seconds = parse_time_to_seconds(options.start_time)
            end_seconds = parse_time_to_seconds(options.end_time)
            validate_time_range(
                start_seconds,
                end_seconds,
                int(duration_seconds) if duration_seconds is not None else None,
            )
            validate_requested_range(start_seconds, end_seconds, duration_seconds)

            source_path, downloaded_info = download_source_audio(
                normalized_url,
                work_dir,
                ffmpeg_path,
                progress_callback=progress_callback,
            )
            source_title = str(downloaded_info.get("title") or metadata.get("title") or "youtube-whisper")
            resume_state.update(
                {
                    "sourceTitle": source_title,
                    "sourcePath": str(source_path),
                    "sourceUrl": normalized_url,
                    "sourceDurationSeconds": duration_seconds,
                }
            )
            save_whisper_resume_state(work_dir, resume_state)

        return transcribe_whisper_audio_file(
            source_path=source_path,
            source_title=source_title,
            options=LocalWhisperSubtitleOptions(
                model=options.model,
                language=options.language,
                output_format=options.output_format,
                vad_filter=options.vad_filter,
                start_time=options.start_time,
                end_time=options.end_time,
            ),
            temp_dir=work_dir,
            progress_callback=progress_callback,
            source_duration_seconds=duration_seconds,
            source_url=normalized_url,
            resume_state_callback=resume_state_callback,
        )
    except Exception:
        if owns_temp_dir:
            cleanup_temp_dir(work_dir)
        raise


def extract_whisper_subtitles_from_file(
    source_path: Path,
    source_name: str,
    options: LocalWhisperSubtitleOptions,
    *,
    temp_dir: Path | None = None,
    progress_callback: ProgressCallback | None = None,
    resume_state_callback: ResumeStateCallback | None = None,
) -> ExtractionResult:
    validated_name = validate_upload_audio_filename(source_name)
    owns_temp_dir = temp_dir is None
    working_dir = temp_dir or Path(tempfile.mkdtemp(prefix="uploaded-whisper-"))
    source_title = Path(validated_name).stem or "uploaded-audio"

    try:
        notify_progress(progress_callback, 10, "Preparing uploaded audio file for Whisper subtitle extraction.")
        resume_state = load_whisper_resume_state(working_dir)
        if source_path.exists():
            resume_state.update(
                {
                    "sourceTitle": source_title,
                    "sourcePath": str(source_path),
                    "sourceName": validated_name,
                    "sourceKind": "audio_file",
                }
            )
            save_whisper_resume_state(working_dir, resume_state)
        return transcribe_whisper_audio_file(
            source_path=source_path,
            source_title=source_title,
            options=options,
            temp_dir=working_dir,
            progress_callback=progress_callback,
            source_duration_seconds=None,
            resume_state_callback=resume_state_callback,
        )
    except Exception:
        if owns_temp_dir:
            cleanup_temp_dir(working_dir)
        raise
