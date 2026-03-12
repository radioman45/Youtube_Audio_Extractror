from pathlib import Path
import threading
import time
import sys
import types

import pytest

from app.services.extractor import ExtractionInputError, ExtractionRuntimeError, cleanup_temp_dir
from app.services.task_control import PauseController
from app.services.whisper_subtitle_extractor import (
    LocalWhisperSubtitleOptions,
    WhisperSubtitleOptions,
    collect_transcribed_cues,
    ensure_local_whisper_model_directory,
    extract_whisper_subtitles,
    extract_whisper_subtitles_from_file,
    get_whisper_download_endpoints,
    get_whisper_chunk_cues_path,
    get_whisper_resume_state_path,
    load_whisper_model,
    normalize_whisper_model,
    resolve_whisper_device,
    save_whisper_cues,
    has_complete_local_whisper_model,
    validate_upload_audio_filename,
)


class DummySegment:
    def __init__(self, start: float, end: float, text: str):
        self.start = start
        self.end = end
        self.text = text


class DummyWhisperModel:
    def __init__(self):
        self.calls: list[tuple[str, str, bool, bool]] = []

    def transcribe(self, audio_path, *, language, vad_filter, condition_on_previous_text):
        self.calls.append((Path(audio_path).name, language, vad_filter, condition_on_previous_text))
        segment_index = len(self.calls)
        return [DummySegment(0.0, 1.0, f"segment {segment_index}")], {"language": language}


class FakeWhisperModelLoader:
    def __init__(self):
        self.calls: list[tuple[str, str, bool | None]] = []

    def __call__(self, model_name, device="auto", local_files_only=None):
        self.calls.append((model_name, device, local_files_only))
        if local_files_only:
            raise RuntimeError("missing local cache")
        return {"model": model_name}


class FakeWhisperModelFallbackLoader:
    def __init__(self):
        self.calls: list[tuple[str, str, bool | None]] = []

    def __call__(self, model_name, device="auto", local_files_only=None):
        self.calls.append((model_name, device, local_files_only))
        if local_files_only:
            raise RuntimeError("missing local cache")
        if model_name == "base":
            raise RuntimeError("hub download failed")
        return {"model": model_name}


class FakeWhisperCudaFallbackLoader:
    def __init__(self):
        self.calls: list[tuple[str, str, bool | None]] = []

    def __call__(self, model_name, device="auto", local_files_only=None):
        self.calls.append((model_name, device, local_files_only))
        if local_files_only:
            raise RuntimeError("missing local cache")
        if device == "cuda":
            raise RuntimeError("CUDA driver is not available")
        return {"model": model_name, "device": device}


class BrokenWhisperModel:
    def transcribe(self, *_args, **_kwargs):
        raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")


class ProgressWhisperModel:
    def transcribe(self, *_args, **_kwargs):
        return [
            DummySegment(0.0, 10.0, "segment 1"),
            DummySegment(10.0, 20.0, "segment 2"),
        ], {"language": "en"}


class AutoFallbackTranscribeModel:
    def __init__(self):
        self.fallback_calls = 0
        self.should_fail_with_cuda = True

    def transcribe(self, *_args, **_kwargs):
        if self.should_fail_with_cuda:
            raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
        return [DummySegment(0.0, 1.0, "cpu segment")], {"language": "en"}

    def fallback_to_cpu_if_auto(self, _progress_callback=None):
        self.fallback_calls += 1
        self.should_fail_with_cuda = False
        return True


def write_complete_whisper_model_dir(model_dir: Path) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
    (model_dir / "vocabulary.txt").write_text("ok", encoding="utf-8")
    (model_dir / "model.bin").write_bytes(b"model")


def test_normalize_whisper_model_rejects_unknown_model():
    with pytest.raises(ExtractionInputError):
        normalize_whisper_model("unknown")


def test_resolve_whisper_device_defaults_to_cpu_without_gpu(monkeypatch):
    monkeypatch.delenv("APP_WHISPER_DEVICE", raising=False)
    monkeypatch.setattr("app.services.whisper_subtitle_extractor.get_whisper_cuda_device_count", lambda: 0)
    assert resolve_whisper_device() == "cpu"


def test_resolve_whisper_device_defaults_to_cuda_when_gpu_exists(monkeypatch):
    monkeypatch.delenv("APP_WHISPER_DEVICE", raising=False)
    monkeypatch.setattr("app.services.whisper_subtitle_extractor.get_whisper_cuda_device_count", lambda: 1)
    assert resolve_whisper_device() == "cuda"


def test_resolve_whisper_device_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("APP_WHISPER_DEVICE", "metal")
    assert resolve_whisper_device() == "cpu"


def test_get_whisper_download_endpoints_defaults(monkeypatch):
    monkeypatch.delenv("APP_WHISPER_HUB_ENDPOINTS", raising=False)
    assert get_whisper_download_endpoints() == ("https://huggingface.co", "https://hf-mirror.com")


def test_get_whisper_download_endpoints_honors_env(monkeypatch):
    monkeypatch.setenv("APP_WHISPER_HUB_ENDPOINTS", " https://mirror-a.example ; https://mirror-b.example,https://mirror-a.example ")
    assert get_whisper_download_endpoints() == ("https://mirror-a.example", "https://mirror-b.example")


def test_validate_upload_audio_filename_rejects_unsupported_extension():
    with pytest.raises(ExtractionInputError):
        validate_upload_audio_filename("notes.txt")


def test_has_complete_local_whisper_model_allows_missing_preprocessor(tmp_path: Path):
    model_dir = tmp_path / "base"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
    (model_dir / "vocabulary.txt").write_text("ok", encoding="utf-8")
    (model_dir / "model.bin").write_bytes(b"model")

    assert has_complete_local_whisper_model(model_dir) is True


def test_extract_whisper_subtitles_creates_srt(monkeypatch, tmp_path: Path):
    source_path = tmp_path / "source.webm"
    source_path.write_bytes(b"audio")
    dummy_model = DummyWhisperModel()

    def fake_run_ffmpeg(_command, output_path):
        output_path.write_bytes(b"wav")

    monkeypatch.setattr("app.services.whisper_subtitle_extractor.resolve_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.probe_media_info",
        lambda url, ffmpeg_path=None: {"duration": 120, "title": "Sample Video"},
    )
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.download_source_audio",
        lambda url, work_dir, ffmpeg_path, progress_callback=None: (source_path, {"title": "Sample Video"}),
    )
    monkeypatch.setattr("app.services.whisper_subtitle_extractor.run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.load_whisper_model",
        lambda model, progress_callback=None, pause_controller=None, device=None: dummy_model,
    )

    result = extract_whisper_subtitles(
        WhisperSubtitleOptions(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            model="base",
            language="ko",
            vad_filter=True,
        )
    )

    try:
        content = result.file_path.read_text(encoding="utf-8")
        assert "00:00:00,000 --> 00:00:01,000" in content
        assert "segment 1" in content
        assert "whisper_base_ko.srt" in result.download_name
        assert dummy_model.calls == [("whisper-input.wav", "ko", True, False)]
    finally:
        cleanup_temp_dir(result.temp_dir)


def test_extract_whisper_subtitles_creates_clean_text(monkeypatch, tmp_path: Path):
    source_path = tmp_path / "source.webm"
    source_path.write_bytes(b"audio")
    dummy_model = DummyWhisperModel()

    def fake_run_ffmpeg(_command, output_path):
        output_path.write_bytes(b"wav")

    monkeypatch.setattr("app.services.whisper_subtitle_extractor.resolve_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.probe_media_info",
        lambda url, ffmpeg_path=None: {"duration": 120, "title": "Sample Video"},
    )
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.download_source_audio",
        lambda url, work_dir, ffmpeg_path, progress_callback=None: (source_path, {"title": "Sample Video"}),
    )
    monkeypatch.setattr("app.services.whisper_subtitle_extractor.run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.load_whisper_model",
        lambda model, progress_callback=None, pause_controller=None, device=None: dummy_model,
    )

    result = extract_whisper_subtitles(
        WhisperSubtitleOptions(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            model="base",
            language="ko",
            subtitle_format="clean",
        )
    )

    try:
        content = result.file_path.read_text(encoding="utf-8")
        assert content == "segment 1\n"
        assert result.download_name == "Sample Video_whisper_base_ko_clean.txt"
        assert result.media_type == "text/plain; charset=utf-8"
    finally:
        cleanup_temp_dir(result.temp_dir)


def test_extract_whisper_subtitles_chunks_long_audio(monkeypatch, tmp_path: Path):
    source_path = tmp_path / "source.webm"
    source_path.write_bytes(b"audio")
    dummy_model = DummyWhisperModel()

    def fake_run_ffmpeg(_command, output_path):
        output_path.write_bytes(b"wav")

    monkeypatch.setattr("app.services.whisper_subtitle_extractor.resolve_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.probe_media_info",
        lambda url, ffmpeg_path=None: {"duration": 3700, "title": "Long Video"},
    )
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.download_source_audio",
        lambda url, work_dir, ffmpeg_path, progress_callback=None: (source_path, {"title": "Long Video"}),
    )
    monkeypatch.setattr("app.services.whisper_subtitle_extractor.run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.load_whisper_model",
        lambda model, progress_callback=None, pause_controller=None, device=None: dummy_model,
    )

    result = extract_whisper_subtitles(
        WhisperSubtitleOptions(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            model="base",
            language="ko",
        )
    )

    try:
        content = result.file_path.read_text(encoding="utf-8")
        assert len(dummy_model.calls) == 3
        assert "segment 3" in content
        assert "00:30:00,000 --> 00:30:01,000" in content
    finally:
        cleanup_temp_dir(result.temp_dir)


def test_extract_whisper_subtitles_resumes_saved_chunks(monkeypatch, tmp_path: Path):
    source_path = tmp_path / "source.webm"
    source_path.write_bytes(b"audio")
    dummy_model = DummyWhisperModel()

    def fake_run_ffmpeg(_command, output_path):
        output_path.write_bytes(b"wav")

    monkeypatch.setattr("app.services.whisper_subtitle_extractor.resolve_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.probe_media_info",
        lambda url, ffmpeg_path=None: {"duration": 3700, "title": "Resume Video"},
    )
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.download_source_audio",
        lambda url, work_dir, ffmpeg_path, progress_callback=None: (source_path, {"title": "Resume Video"}),
    )
    monkeypatch.setattr("app.services.whisper_subtitle_extractor.run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.load_whisper_model",
        lambda model, progress_callback=None, pause_controller=None, device=None: dummy_model,
    )

    work_dir = tmp_path / "resume-work"
    work_dir.mkdir()
    (work_dir / "whisper-input.wav").write_bytes(b"wav")
    save_whisper_cues(
        get_whisper_chunk_cues_path(work_dir, 1),
        [DummySegment(0.0, 1.0, "restored segment 1")],
    )
    get_whisper_resume_state_path(work_dir).write_text(
        '{"completedChunks": [1], "sourceTitle": "Resume Video", "sourcePath": "'
        + str(source_path).replace("\\", "\\\\")
        + '", "sourceDurationSeconds": 3700}',
        encoding="utf-8",
    )

    result = extract_whisper_subtitles(
        WhisperSubtitleOptions(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            model="base",
            language="ko",
        ),
        temp_dir=work_dir,
    )

    content = result.file_path.read_text(encoding="utf-8")

    assert len(dummy_model.calls) == 2
    assert "restored segment 1" in content
    assert "segment 2" in content


def test_extract_whisper_subtitles_from_uploaded_file(monkeypatch, tmp_path: Path):
    source_path = tmp_path / "sample.mp3"
    source_path.write_bytes(b"audio")
    temp_dir = tmp_path / "work"
    temp_dir.mkdir()
    dummy_model = DummyWhisperModel()

    def fake_run_ffmpeg(_command, output_path):
        output_path.write_bytes(b"wav")

    monkeypatch.setattr("app.services.whisper_subtitle_extractor.resolve_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr("app.services.whisper_subtitle_extractor.run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.load_whisper_model",
        lambda model, progress_callback=None, pause_controller=None, device=None: dummy_model,
    )

    result = extract_whisper_subtitles_from_file(
        source_path,
        "sample.mp3",
        LocalWhisperSubtitleOptions(
            model="base",
            language="ko",
        ),
        temp_dir=temp_dir,
    )

    content = result.file_path.read_text(encoding="utf-8")

    assert "segment 1" in content
    assert result.download_name == "sample_whisper_base_ko.srt"
    assert dummy_model.calls == [("whisper-input.wav", "ko", True, False)]


def test_load_whisper_model_downloads_when_cache_is_missing(monkeypatch, tmp_path: Path):
    fake_loader = FakeWhisperModelLoader()
    progress_updates: list[tuple[int, str]] = []
    manual_dir = tmp_path / "manual-base"
    write_complete_whisper_model_dir(manual_dir)

    monkeypatch.delenv("APP_WHISPER_LOCAL_ONLY", raising=False)
    monkeypatch.setattr("app.services.whisper_subtitle_extractor.get_whisper_cuda_device_count", lambda: 0)
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        types.SimpleNamespace(WhisperModel=fake_loader),
    )
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.ensure_local_whisper_model_directory",
        lambda model, progress_callback=None, pause_controller=None: manual_dir,
    )

    model = load_whisper_model("base", progress_callback=lambda progress, message: progress_updates.append((progress, message)))

    assert model.inner == {"model": str(manual_dir)}
    assert model.requested_device == "auto"
    assert model.active_device == "cpu"
    assert fake_loader.calls == [("base", "cpu", True), (str(manual_dir), "cpu", None)]
    assert progress_updates[0] == (
        88,
        "Whisper device set to Auto. No compatible NVIDIA GPU detected, using CPU.",
    )
    assert progress_updates[-1] == (93, "Whisper model 'base' is ready.")


def test_load_whisper_model_respects_local_only_env(monkeypatch):
    fake_loader = FakeWhisperModelLoader()

    monkeypatch.setenv("APP_WHISPER_LOCAL_ONLY", "1")
    monkeypatch.setattr("app.services.whisper_subtitle_extractor.get_whisper_cuda_device_count", lambda: 0)
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        types.SimpleNamespace(WhisperModel=fake_loader),
    )

    with pytest.raises(ExtractionRuntimeError, match="not available locally"):
        load_whisper_model("base")

    assert fake_loader.calls == [("base", "cpu", True)]


def test_load_whisper_model_retries_with_direct_download(monkeypatch, tmp_path: Path):
    fake_loader = FakeWhisperModelFallbackLoader()
    manual_dir = tmp_path / "manual-base"
    write_complete_whisper_model_dir(manual_dir)
    progress_updates: list[tuple[int, str]] = []

    monkeypatch.delenv("APP_WHISPER_LOCAL_ONLY", raising=False)
    monkeypatch.setattr("app.services.whisper_subtitle_extractor.get_whisper_cuda_device_count", lambda: 0)
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        types.SimpleNamespace(WhisperModel=fake_loader),
    )
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.ensure_local_whisper_model_directory",
        lambda model, progress_callback=None, pause_controller=None: manual_dir,
    )

    model = load_whisper_model("base", progress_callback=lambda progress, message: progress_updates.append((progress, message)))

    assert model.inner == {"model": str(manual_dir)}
    assert model.active_device == "cpu"
    assert fake_loader.calls == [("base", "cpu", True), (str(manual_dir), "cpu", None)]
    assert any("Opening Whisper model 'base' from the local cache." in message for _, message in progress_updates)


def test_load_whisper_model_auto_falls_back_to_cpu_when_cuda_init_fails(monkeypatch, tmp_path: Path):
    fake_loader = FakeWhisperCudaFallbackLoader()
    manual_dir = tmp_path / "manual-base"
    write_complete_whisper_model_dir(manual_dir)
    progress_updates: list[tuple[int, str]] = []

    monkeypatch.delenv("APP_WHISPER_LOCAL_ONLY", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        types.SimpleNamespace(WhisperModel=fake_loader),
    )
    monkeypatch.setattr("app.services.whisper_subtitle_extractor.get_whisper_cuda_device_count", lambda: 1)
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.ensure_local_whisper_model_directory",
        lambda model, progress_callback=None, pause_controller=None: manual_dir,
    )

    model = load_whisper_model("base", progress_callback=lambda progress, message: progress_updates.append((progress, message)))

    assert model.inner == {"model": str(manual_dir), "device": "cpu"}
    assert model.requested_device == "auto"
    assert model.active_device == "cpu"
    assert fake_loader.calls == [
        ("base", "cuda", True),
        (str(manual_dir), "cuda", None),
        (str(manual_dir), "cpu", None),
    ]
    assert any("Falling back to CPU automatically." in message for _, message in progress_updates)


def test_ensure_local_whisper_model_directory_retries_alternate_endpoint(monkeypatch, tmp_path: Path):
    model_dir = tmp_path / "cache" / "base"
    progress_updates: list[tuple[int, str]] = []

    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.get_whisper_model_cache_dir",
        lambda _model: model_dir,
    )
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.get_whisper_download_endpoints",
        lambda: ("https://huggingface.co", "https://hf-mirror.com"),
    )

    def fake_support_files(
        repo_id: str,
        target_dir: Path,
        endpoint: str,
        model: str,
        progress_callback=None,
        pause_controller=None,
    ):
        assert repo_id == "Systran/faster-whisper-base"
        assert model == "base"
        if endpoint == "https://huggingface.co":
            raise ExtractionRuntimeError("Website Blocking")
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in ("config.json", "preprocessor_config.json", "tokenizer.json", "vocabulary.txt"):
            (target_dir / name).write_text("ok", encoding="utf-8")

    def fake_model_binary(*, endpoint: str, target_path: Path, pause_controller=None, **_kwargs):
        if endpoint == "https://huggingface.co":
            raise ExtractionRuntimeError("Website Blocking")
        target_path.write_bytes(b"model")

    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.download_whisper_support_files",
        fake_support_files,
    )
    monkeypatch.setattr(
        "app.services.whisper_subtitle_extractor.download_whisper_model_binary",
        fake_model_binary,
    )

    resolved_dir = ensure_local_whisper_model_directory(
        "base",
        progress_callback=lambda progress, message: progress_updates.append((progress, message)),
    )

    assert resolved_dir == model_dir
    assert (model_dir / "model.bin").exists()
    assert any("alternate Whisper mirror" in message for _, message in progress_updates)


def test_collect_transcribed_cues_wraps_cuda_runtime_error(tmp_path: Path):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"wav")

    with pytest.raises(ExtractionRuntimeError, match="GPU runtime is not available"):
        collect_transcribed_cues(
            BrokenWhisperModel(),
            audio_path,
            language="en",
            vad_filter=True,
            offset_seconds=0.0,
        )


def test_collect_transcribed_cues_auto_falls_back_to_cpu(tmp_path: Path):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"wav")
    progress_updates: list[tuple[int, str]] = []
    model = AutoFallbackTranscribeModel()

    cues = collect_transcribed_cues(
        model,
        audio_path,
        language="en",
        vad_filter=True,
        offset_seconds=0.0,
        progress_callback=lambda progress, message: progress_updates.append((progress, message)),
    )

    assert [cue.text for cue in cues] == ["cpu segment"]
    assert model.fallback_calls == 1
    assert any("Falling back to CPU automatically." in message for _, message in progress_updates)


def test_collect_transcribed_cues_reports_chunk_progress(tmp_path: Path):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"wav")
    progress_updates: list[tuple[int, str]] = []

    cues = collect_transcribed_cues(
        ProgressWhisperModel(),
        audio_path,
        language="en",
        vad_filter=True,
        offset_seconds=0.0,
        progress_callback=lambda progress, message: progress_updates.append((progress, message)),
        progress_start=91,
        progress_end=92,
        expected_duration_seconds=20.0,
        progress_message_prefix="Transcribing Whisper audio chunk 1/8",
    )

    assert [cue.text for cue in cues] == ["segment 1", "segment 2"]
    assert progress_updates == [
        (91, "Transcribing Whisper audio chunk 1/8 (50%)."),
        (92, "Transcribing Whisper audio chunk 1/8 (100%)."),
    ]


def test_collect_transcribed_cues_waits_for_resume_when_paused(tmp_path: Path):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"wav")
    progress_updates: list[tuple[int, str]] = []
    results: dict[str, object] = {}
    pause_controller = PauseController()
    pause_controller.pause()

    def run() -> None:
        results["cues"] = collect_transcribed_cues(
            ProgressWhisperModel(),
            audio_path,
            language="en",
            vad_filter=True,
            offset_seconds=0.0,
            progress_callback=lambda progress, message: progress_updates.append((progress, message)),
            progress_start=91,
            progress_end=92,
            expected_duration_seconds=20.0,
            progress_message_prefix="Transcribing Whisper audio chunk 1/8",
            pause_controller=pause_controller,
        )

    worker = threading.Thread(target=run, daemon=True)
    worker.start()

    deadline = time.time() + 1.0
    while not progress_updates and time.time() < deadline:
        time.sleep(0.02)

    assert worker.is_alive()
    assert progress_updates[0] == (91, "Whisper subtitle extraction is paused. Click resume to continue.")

    pause_controller.resume()
    worker.join(timeout=1.0)

    assert worker.is_alive() is False
    assert [cue.text for cue in results["cues"]] == ["segment 1", "segment 2"]
