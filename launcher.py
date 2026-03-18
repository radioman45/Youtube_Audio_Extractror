from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QThread, Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.services.app_state import get_job_work_dir
from app.services.batch_extractor import BatchExtractionOptions, extract_batch
from app.services.colab_transcription import (
    COLAB_HOME_URL,
    COLAB_NOTEBOOK_FILENAME,
    build_colab_notebook_payload,
    create_colab_job_bundle,
    import_colab_result_package,
)
from app.services.extractor import (
    SUPPORTED_FORMATS,
    SUPPORTED_VIDEO_QUALITIES,
    ExtractionOptions,
    ExtractionResult,
    SongExtractionOptions,
    cleanup_temp_dir,
    extract_audio,
    extract_song_mp3,
)
from app.services.subtitle_extractor import SubtitleOptions, SubtitleTrackNotFoundError, extract_subtitles
from app.services.task_control import PauseController
from app.services.video_extractor import VideoExtractionOptions, extract_video
from app.services.whisper_subtitle_extractor import (
    SUPPORTED_WHISPER_MODELS,
    LocalWhisperSubtitleOptions,
    WhisperSubtitleOptions,
    extract_whisper_subtitles,
    extract_whisper_subtitles_from_file,
    validate_upload_audio_filename,
)

APP_TITLE = "YouTube Multi Extractor Desktop"
TASK_OPTIONS: tuple[tuple[str, str], ...] = (
    ("audio", "오디오 추출"),
    ("song_mp3", "노래 MP3 추출"),
    ("video", "영상 추출"),
    ("subtitle", "자막 추출"),
    ("batch", "배치 다운로드"),
)
BATCH_OPTIONS: tuple[tuple[str, str], ...] = (
    ("audio", "오디오 추출"),
    ("song_mp3", "노래 MP3 추출"),
    ("video", "영상 추출"),
    ("subtitle", "자막 추출"),
)
SUBTITLE_ENGINE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("auto", "자동 선택"),
    ("youtube", "YouTube 자막"),
    ("whisper", "Whisper 로컬 생성"),
)
SUBTITLE_FORMAT_OPTIONS: tuple[tuple[str, str], ...] = (
    ("timestamped", "타임스탬프 포함 (.srt)"),
    ("clean", "텍스트만 (.txt)"),
)
WHISPER_DEVICE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("auto", "Auto (GPU first, else CPU)"),
    ("cpu", "CPU only"),
    ("cuda", "NVIDIA GPU (CUDA)"),
)
WHISPER_RUNTIME_OPTIONS: tuple[tuple[str, str], ...] = (
    ("local", "Local PC"),
    ("colab", "Google Colab handoff"),
)
SUBTITLE_SOURCE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("youtube_url", "YouTube 링크"),
    ("audio_file", "오디오 파일 업로드"),
)
DEFAULT_OUTPUT_DIR = Path.home() / "Downloads"
MODE_DONE_LABELS = {
    "audio": "오디오 추출이 완료되었습니다.",
    "song_mp3": "노래 MP3 추출이 완료되었습니다.",
    "video": "영상 추출이 완료되었습니다.",
    "subtitle": "자막 추출이 완료되었습니다.",
    "batch": "배치 다운로드가 완료되었습니다.",
}
ROW_LABEL_MIN_WIDTH = 170
COMPACT_LAYOUT_BREAKPOINT = 940
STACKED_BUTTON_BREAKPOINT = 1180
STACKED_TOPBAR_BREAKPOINT = 780


def build_colab_help_message(bundle_name: str | None = None) -> str:
    exported_bundle_name = bundle_name or "저장한 Colab 번들 ZIP"
    return "\n".join(
        [
            "Colab handoff 사용 순서",
            "",
            "1. '번들 내보내기'를 눌러 Colab 번들 ZIP을 저장합니다.",
            f"   번들 파일: {exported_bundle_name}",
            "2. '노트북 저장'을 눌러 whisper_transcribe.ipynb 파일을 저장합니다.",
            "3. 'Colab 열기'를 눌러 Google Colab을 엽니다.",
            "4. Colab에서 whisper_transcribe.ipynb 파일을 업로드해서 엽니다.",
            "5. Colab 메뉴에서 '런타임 -> 런타임 유형 변경 -> GPU'를 선택합니다.",
            "6. 첫 번째 설치 셀을 실행합니다.",
            "7. 선택 방식:",
            "   - 일반 방식: 설정 셀은 그대로 두고 실행 셀에서 번들 ZIP을 업로드합니다.",
            "   - Drive 방식: 설정 셀에서 USE_GOOGLE_DRIVE = True 로 바꾸고 DRIVE_BUNDLE_PATH, DRIVE_OUTPUT_DIR 를 지정합니다.",
            "8. 실행 셀을 돌리면 전사가 진행되고 colab-result.zip 이 생성됩니다.",
            "9. Drive 방식을 쓰면 결과 ZIP과 자막 파일이 Google Drive에도 저장됩니다.",
            "10. 앱으로 돌아와 '결과 ZIP 가져오기'를 눌러 colab-result.zip 또는 Drive에 저장된 결과 ZIP을 선택합니다.",
            "11. 완료되면 출력 폴더에 자막 파일이 저장됩니다.",
            "",
            "주의: 번들 ZIP은 압축을 풀지 말고 그대로 업로드하세요.",
        ]
    )

THEME_SWITCH_LABELS = {
    "dark": "라이트 모드",
    "light": "다크 모드",
}
THEME_BADGE_LABELS = {
    "dark": "Dark theme",
    "light": "Light theme",
}
THEME_TOKENS: dict[str, dict[str, str]] = {
    "dark": {
        "background": "#09090b",
        "card": "#111114",
        "panel": "#18181b",
        "border": "#27272a",
        "foreground": "#fafafa",
        "muted": "#a1a1aa",
        "input": "#111114",
        "secondary": "#18181b",
        "secondary_hover": "#242428",
        "primary": "#fafafa",
        "primary_text": "#09090b",
        "ring": "#38bdf8",
        "accent_soft": "#082f49",
        "accent_text": "#bae6fd",
        "accent_border": "#0c4a6e",
        "progress_bg": "#111114",
        "progress_chunk": "#38bdf8",
        "header_start": "#111827",
        "header_end": "#09090b",
    },
    "light": {
        "background": "#fafafa",
        "card": "#ffffff",
        "panel": "#ffffff",
        "border": "#e4e4e7",
        "foreground": "#09090b",
        "muted": "#71717a",
        "input": "#ffffff",
        "secondary": "#f4f4f5",
        "secondary_hover": "#e4e4e7",
        "primary": "#18181b",
        "primary_text": "#fafafa",
        "ring": "#06b6d4",
        "accent_soft": "#ecfeff",
        "accent_text": "#155e75",
        "accent_border": "#a5f3fc",
        "progress_bg": "#f4f4f5",
        "progress_chunk": "#06b6d4",
        "header_start": "#ffffff",
        "header_end": "#f4f4f5",
    },
}


@dataclass(slots=True)
class TaskConfig:
    task_type: str
    url: str | None
    start_time: str | None
    end_time: str | None
    audio_format: str
    video_quality: str
    subtitle_engine: str
    subtitle_source: str
    subtitle_language: str
    subtitle_format: str
    whisper_model: str
    whisper_device: str
    whisper_runtime: str
    vad_filter: bool
    batch_mode: str
    audio_file_path: str | None
    output_dir: Path


@dataclass(slots=True)
class ColabHandoffState:
    job_id: str
    work_dir: Path
    bundle_path: Path
    bundle_download_name: str
    output_dir: Path
    expected_details: dict[str, object]
    completed: bool = False


def normalize_optional_text(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def ensure_output_dir(path_text: str) -> Path:
    path = Path(path_text).expanduser() if path_text.strip() else DEFAULT_OUTPUT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    index = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def persist_result(result: ExtractionResult, output_dir: Path) -> Path:
    destination = ensure_unique_path(output_dir / result.download_name)
    try:
        shutil.move(str(result.file_path), destination)
    finally:
        cleanup_temp_dir(result.temp_dir)
    return destination


def export_file_copy(source_path: Path, output_dir: Path, target_name: str | None = None) -> Path:
    if not source_path.exists():
        raise ValueError(f"파일을 찾을 수 없습니다: {source_path}")

    destination = ensure_unique_path(output_dir / (target_name or source_path.name))
    shutil.copy2(source_path, destination)
    return destination


def save_notebook_to_output(output_dir: Path, target_name: str | None = None) -> Path:
    destination = ensure_unique_path(output_dir / (target_name or COLAB_NOTEBOOK_FILENAME))
    destination.write_bytes(build_colab_notebook_payload())
    return destination


def should_use_compact_layout(window_width: int) -> bool:
    return window_width < COMPACT_LAYOUT_BREAKPOINT


def should_stack_action_buttons(window_width: int) -> bool:
    return window_width < STACKED_BUTTON_BREAKPOINT


def should_stack_topbar(window_width: int) -> bool:
    return window_width < STACKED_TOPBAR_BREAKPOINT


def create_colab_handoff_state(config: TaskConfig) -> ColabHandoffState:
    if config.task_type != "subtitle" or config.subtitle_engine != "whisper" or config.subtitle_source != "audio_file":
        raise ValueError("Colab handoff는 업로드 Whisper 자막 작업에서만 사용할 수 있습니다.")

    audio_path = Path(config.audio_file_path or "")
    if not audio_path.exists():
        raise ValueError("Whisper 전사용 오디오 파일을 선택해 주세요.")

    source_name = validate_upload_audio_filename(audio_path.name)
    options = LocalWhisperSubtitleOptions(
        model=config.whisper_model,
        language=config.subtitle_language,
        subtitle_format=config.subtitle_format,
        device=config.whisper_device,
        vad_filter=config.vad_filter,
        start_time=config.start_time,
        end_time=config.end_time,
    )

    job_id = uuid4().hex
    work_dir = get_job_work_dir(job_id)
    bundle_info = create_colab_job_bundle(
        job_id=job_id,
        source_path=audio_path,
        source_name=source_name,
        options=options,
        work_dir=work_dir,
    )

    expected_details: dict[str, object] = {
        "sourceSha256": bundle_info.source_sha256,
        "colabResultName": bundle_info.expected_output_name,
        "subtitleFormat": config.subtitle_format,
        "whisperDevice": config.whisper_device,
        "whisperRuntime": "colab",
        "bundleFilename": bundle_info.bundle_download_name,
        "sourceName": source_name,
    }
    return ColabHandoffState(
        job_id=job_id,
        work_dir=work_dir,
        bundle_path=bundle_info.bundle_path,
        bundle_download_name=bundle_info.bundle_download_name,
        output_dir=config.output_dir,
        expected_details=expected_details,
    )


def compute_visibility(
    task_type: str,
    batch_mode: str,
    subtitle_engine: str,
    subtitle_source: str,
    whisper_runtime: str = "local",
) -> dict[str, bool]:
    is_batch = task_type == "batch"
    effective_task = batch_mode if is_batch else task_type
    subtitle_mode = task_type == "subtitle"
    batch_subtitle_mode = is_batch and batch_mode == "subtitle"
    whisper_mode = subtitle_mode and subtitle_engine == "whisper"
    upload_mode = whisper_mode and subtitle_source == "audio_file"

    return {
        "url": not upload_mode,
        "audio_format": effective_task == "audio",
        "video_quality": effective_task == "video",
        "subtitle_engine": subtitle_mode or batch_subtitle_mode,
        "subtitle_source": whisper_mode,
        "subtitle_language": subtitle_mode or batch_subtitle_mode,
        "subtitle_format": subtitle_mode or batch_subtitle_mode,
        "whisper_model": whisper_mode,
        "whisper_device": whisper_mode,
        "whisper_runtime": upload_mode,
        "vad_filter": whisper_mode,
        "audio_file": upload_mode,
        "batch_mode": is_batch,
        "colab_actions": upload_mode and whisper_runtime == "colab",
    }


def supports_pause_resume(task_type: str, subtitle_engine: str, whisper_runtime: str = "local") -> bool:
    return task_type == "subtitle" and subtitle_engine == "whisper" and whisper_runtime == "local"


def build_stylesheet(theme_mode: str) -> str:
    if theme_mode not in THEME_TOKENS:
        raise ValueError(f"Unsupported theme mode: {theme_mode}")

    theme = THEME_TOKENS[theme_mode]
    return f"""
    QMainWindow, QWidget#root {{
        background: {theme["background"]};
        color: {theme["foreground"]};
        font-family: "Segoe UI";
    }}
    #headerCard {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 {theme["header_start"]},
            stop: 1 {theme["header_end"]}
        );
        border: 1px solid {theme["border"]};
        border-radius: 28px;
    }}
    #panel {{
        background: {theme["panel"]};
        border: 1px solid {theme["border"]};
        border-radius: 24px;
    }}
    QLabel {{
        color: {theme["foreground"]};
    }}
    #eyebrow {{
        color: {theme["muted"]};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.1px;
    }}
    #heroTitle {{
        color: {theme["foreground"]};
    }}
    #subtitle, #helperLabel, #batchLabel, #sectionHint {{
        color: {theme["muted"]};
    }}
    #desktopPill, #themeBadge {{
        padding: 6px 12px;
        border-radius: 999px;
        font-weight: 700;
    }}
    #desktopPill {{
        background: {theme["accent_soft"]};
        color: {theme["accent_text"]};
        border: 1px solid {theme["accent_border"]};
    }}
    #themeBadge {{
        background: {theme["secondary"]};
        color: {theme["foreground"]};
        border: 1px solid {theme["border"]};
    }}
    #sectionTitle {{
        color: {theme["foreground"]};
        font-size: 16px;
        font-weight: 700;
    }}
    #rowLabel {{
        color: {theme["muted"]};
        font-weight: 700;
    }}
    #statusLabel {{
        color: {theme["foreground"]};
        font-weight: 700;
    }}
    QLineEdit, QComboBox {{
        min-height: 40px;
        padding: 6px 12px;
        background: {theme["input"]};
        color: {theme["foreground"]};
        border: 1px solid {theme["border"]};
        border-radius: 14px;
        selection-background-color: {theme["ring"]};
    }}
    QLineEdit:focus, QComboBox:focus, QPushButton:focus {{
        border: 1px solid {theme["ring"]};
        outline: none;
    }}
    QLineEdit:disabled, QComboBox:disabled {{
        color: {theme["muted"]};
        background: {theme["secondary"]};
    }}
    QComboBox::drop-down {{
        border: 0;
        width: 28px;
    }}
    QComboBox QAbstractItemView {{
        background: {theme["panel"]};
        color: {theme["foreground"]};
        border: 1px solid {theme["border"]};
        selection-background-color: {theme["secondary_hover"]};
    }}
    QPushButton {{
        min-height: 40px;
        padding: 6px 14px;
        border-radius: 14px;
        border: 1px solid {theme["border"]};
        background: {theme["secondary"]};
        color: {theme["foreground"]};
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: {theme["secondary_hover"]};
    }}
    QPushButton:disabled {{
        color: {theme["muted"]};
        background: {theme["secondary"]};
    }}
    QPushButton#primaryButton {{
        background: {theme["primary"]};
        color: {theme["primary_text"]};
        border: 1px solid {theme["primary"]};
        font-weight: 700;
    }}
    QPushButton#themeButton {{
        min-width: 132px;
    }}
    QPushButton#helpButton {{
        min-width: 40px;
        max-width: 40px;
        border-radius: 999px;
        font-weight: 700;
        padding: 0;
    }}
    QCheckBox {{
        color: {theme["foreground"]};
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 6px;
        border: 1px solid {theme["border"]};
        background: {theme["input"]};
    }}
    QCheckBox::indicator:checked {{
        background: {theme["ring"]};
        border: 1px solid {theme["ring"]};
    }}
    QProgressBar {{
        min-height: 24px;
        border-radius: 999px;
        border: 1px solid {theme["border"]};
        background: {theme["progress_bg"]};
        color: {theme["foreground"]};
        text-align: center;
    }}
    QProgressBar::chunk {{
        border-radius: 999px;
        background: {theme["progress_chunk"]};
    }}
    QMessageBox {{
        background: {theme["panel"]};
    }}
    """


def open_path(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def execute_task(
    config: TaskConfig,
    progress_callback,
    batch_status_callback,
    pause_controller: PauseController | None = None,
) -> tuple[Path, str]:
    task_type = config.task_type
    progress_callback(2, "작업을 준비하는 중입니다.")

    if (
        task_type == "subtitle"
        and config.subtitle_engine == "whisper"
        and config.subtitle_source == "audio_file"
        and config.whisper_runtime == "colab"
    ):
        raise ValueError("Colab handoff 작업은 데스크톱 Colab 액션으로 만들어 주세요.")

    if task_type == "audio":
        result = extract_audio(
            ExtractionOptions(
                url=config.url or "",
                audio_format=config.audio_format,  # type: ignore[arg-type]
                start_time=config.start_time,
                end_time=config.end_time,
            ),
            progress_callback=progress_callback,
        )
    elif task_type == "song_mp3":
        result = extract_song_mp3(
            SongExtractionOptions(
                url=config.url or "",
                start_time=config.start_time,
                end_time=config.end_time,
            ),
            progress_callback=progress_callback,
        )
    elif task_type == "video":
        result = extract_video(
            VideoExtractionOptions(
                url=config.url or "",
                video_quality=config.video_quality,
                start_time=config.start_time,
                end_time=config.end_time,
            ),
            progress_callback=progress_callback,
        )
    elif task_type == "subtitle":
        if config.subtitle_engine == "whisper" and config.subtitle_source == "audio_file":
            progress_callback(6, "업로드한 오디오 파일을 준비하는 중입니다.")
            audio_path = Path(config.audio_file_path or "")
            if not audio_path.exists():
                raise ValueError("자막 생성에 사용할 오디오 파일을 선택해 주세요.")
            result = extract_whisper_subtitles_from_file(
                audio_path,
                audio_path.name,
                LocalWhisperSubtitleOptions(
                    model=config.whisper_model,
                    language=config.subtitle_language,
                    subtitle_format=config.subtitle_format,
                    device=config.whisper_device,
                    vad_filter=config.vad_filter,
                    start_time=config.start_time,
                    end_time=config.end_time,
                ),
                progress_callback=progress_callback,
                pause_controller=pause_controller,
            )
        elif config.subtitle_engine == "whisper":
            result = extract_whisper_subtitles(
                WhisperSubtitleOptions(
                    url=config.url or "",
                    model=config.whisper_model,
                    language=config.subtitle_language,
                    subtitle_format=config.subtitle_format,
                    device=config.whisper_device,
                    vad_filter=config.vad_filter,
                    start_time=config.start_time,
                    end_time=config.end_time,
                ),
                progress_callback=progress_callback,
                pause_controller=pause_controller,
            )
        elif config.subtitle_engine == "auto":
            progress_callback(8, "YouTube 자막을 먼저 확인하는 중입니다.")
            try:
                result = extract_subtitles(
                    SubtitleOptions(
                        url=config.url or "",
                        subtitle_language=config.subtitle_language,
                        subtitle_format=config.subtitle_format,
                        start_time=config.start_time,
                        end_time=config.end_time,
                    )
                )
                progress_callback(100, "YouTube 자막 추출이 완료되었습니다.")
            except SubtitleTrackNotFoundError:
                progress_callback(12, "YouTube 자막이 없어 Whisper 로컬 생성으로 전환합니다.")
                result = extract_whisper_subtitles(
                    WhisperSubtitleOptions(
                        url=config.url or "",
                        model=config.whisper_model,
                        language=config.subtitle_language,
                        subtitle_format=config.subtitle_format,
                        device=config.whisper_device,
                        vad_filter=config.vad_filter,
                        start_time=config.start_time,
                        end_time=config.end_time,
                    ),
                    progress_callback=progress_callback,
                    pause_controller=pause_controller,
                )
        else:
            progress_callback(8, "YouTube 자막을 다운로드하는 중입니다.")
            result = extract_subtitles(
                SubtitleOptions(
                    url=config.url or "",
                    subtitle_language=config.subtitle_language,
                    subtitle_format=config.subtitle_format,
                    start_time=config.start_time,
                    end_time=config.end_time,
                )
            )
            progress_callback(100, "자막 추출이 완료되었습니다.")
    elif task_type == "batch":
        result = extract_batch(
                BatchExtractionOptions(
                    url=config.url or "",
                    batch_mode=config.batch_mode,
                    audio_format=config.audio_format,
                    video_quality=config.video_quality,
                    subtitle_language=config.subtitle_language,
                    subtitle_format=config.subtitle_format,
                    start_time=config.start_time,
                    end_time=config.end_time,
                ),
            progress_callback=progress_callback,
            status_callback=batch_status_callback,
        )
    else:
        raise ValueError("지원하지 않는 작업 유형입니다.")

    saved_path = persist_result(result, config.output_dir)
    return saved_path, MODE_DONE_LABELS[task_type]


class Row(QWidget):
    def __init__(self, label: str, field: QWidget, extra: QWidget | None = None):
        super().__init__()
        self._title = QLabel(label)
        self._title.setObjectName("rowLabel")
        self._title.setWordWrap(True)
        self._field = field
        self._extra = extra

        self._layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(12)

        self._control_row = QWidget()
        self._control_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self._control_row)
        self._control_layout.setContentsMargins(0, 0, 0, 0)
        self._control_layout.setSpacing(12)

        field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._control_layout.addWidget(field, 1)
        if extra is not None:
            extra.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self._control_layout.addWidget(extra)

        self._layout.addWidget(self._title)
        self._layout.addWidget(self._control_row, 1)
        self.set_compact(False)

    def set_compact(self, compact: bool) -> None:
        self._layout.setDirection(QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight)
        self._layout.setSpacing(8 if compact else 12)
        self._title.setMinimumWidth(0 if compact else ROW_LABEL_MIN_WIDTH)
        self._title.setMaximumWidth(16777215 if compact else ROW_LABEL_MIN_WIDTH)
        self._control_layout.setDirection(
            QBoxLayout.Direction.TopToBottom if compact and self._extra is not None else QBoxLayout.Direction.LeftToRight
        )
        self._control_layout.setSpacing(8 if compact else 12)


class ResponsiveButtonRow(QWidget):
    def __init__(self, *buttons: QPushButton):
        super().__init__()
        self._buttons = list(buttons)
        self._layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        for button in self._buttons:
            self._layout.addWidget(button)

    def set_compact(self, compact: bool) -> None:
        self._layout.setDirection(QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight)
        self._layout.setSpacing(8 if compact else 10)
        for button in self._buttons:
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding if compact else QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Fixed,
            )


class ExtractionWorker(QThread):
    progress = Signal(int, str)
    batch_status = Signal(int, int, int)
    completed = Signal(str, str)
    failed = Signal(str)

    def __init__(self, config: TaskConfig):
        super().__init__()
        self._config = config
        self._pause_controller = (
            PauseController()
            if supports_pause_resume(config.task_type, config.subtitle_engine, config.whisper_runtime)
            else None
        )

    def run(self) -> None:
        try:
            saved_path, message = execute_task(
                self._config,
                self.progress.emit,
                self.batch_status.emit,
                self._pause_controller,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        self.completed.emit(str(saved_path), message)

    def supports_pause_resume(self) -> bool:
        return self._pause_controller is not None

    def is_paused(self) -> bool:
        return self._pause_controller is not None and self._pause_controller.is_paused()

    def pause_work(self) -> None:
        if self._pause_controller is None:
            return
        self._pause_controller.pause()

    def resume_work(self) -> None:
        if self._pause_controller is None:
            return
        self._pause_controller.resume()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker: ExtractionWorker | None = None
        self.colab_state: ColabHandoffState | None = None
        self.last_output_path: Path | None = None
        self.last_output_dir: Path = DEFAULT_OUTPUT_DIR
        self.theme_mode = "dark"
        self._form_rows: list[Row] = []
        self._button_rows: list[ResponsiveButtonRow] = []

        self.setWindowTitle(APP_TITLE)
        self.resize(1160, 920)
        self.setMinimumSize(640, 620)

        self._build_ui()
        self._apply_theme()
        self.refresh_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        topbar = QWidget()
        self.topbar_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, topbar)
        self.topbar_layout.setContentsMargins(0, 0, 0, 0)
        self.topbar_layout.setSpacing(8)

        self.desktop_pill = QLabel("Browser-free")
        self.desktop_pill.setObjectName("desktopPill")
        self.theme_badge = QLabel("")
        self.theme_badge.setObjectName("themeBadge")
        self.theme_button = QPushButton("")
        self.theme_button.setObjectName("themeButton")
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.clicked.connect(self.toggle_theme)

        self.topbar_layout.addWidget(self.desktop_pill)
        self.topbar_layout.addWidget(self.theme_badge)
        self.topbar_layout.addStretch(1)
        self.topbar_layout.addWidget(self.theme_button)
        layout.addWidget(topbar)

        title = QLabel("브라우저 없이 바로 추출")
        title.setObjectName("heroTitle")
        title_font = QFont()
        title_font.setPointSize(22)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        hero_subtitle = QLabel(
            "shadcn UI 감성의 데스크톱 런처입니다. 로컬 웹페이지를 띄우지 않고 추출 서비스를 직접 호출합니다."
        )
        hero_subtitle.setObjectName("subtitle")
        hero_subtitle.setWordWrap(True)
        layout.addWidget(hero_subtitle)

        subtitle = QLabel("브라우저 없이 로컬 추출 서비스를 직접 호출하는 데스크톱 모드입니다.")
        subtitle.hide()
        layout.addWidget(subtitle)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        panel_layout.setSpacing(12)

        self.task_type_combo = self._combo(TASK_OPTIONS)
        self.task_row = Row("작업 유형", self.task_type_combo)
        panel_layout.addWidget(self.task_row)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.url_row = Row("YouTube 링크", self.url_input)
        panel_layout.addWidget(self.url_row)

        self.start_input = QLineEdit()
        self.start_input.setPlaceholderText("예: 01:30")
        self.start_row = Row("시작 시간", self.start_input)
        panel_layout.addWidget(self.start_row)

        self.end_input = QLineEdit()
        self.end_input.setPlaceholderText("예: 02:10")
        self.end_row = Row("종료 시간", self.end_input)
        panel_layout.addWidget(self.end_row)

        self.audio_format_combo = self._combo(tuple((value, value.upper()) for value in SUPPORTED_FORMATS))
        self.audio_format_row = Row("오디오 형식", self.audio_format_combo)
        panel_layout.addWidget(self.audio_format_row)

        self.video_quality_combo = self._combo(tuple((value, value) for value in SUPPORTED_VIDEO_QUALITIES))
        self.video_quality_row = Row("영상 화질", self.video_quality_combo)
        panel_layout.addWidget(self.video_quality_row)

        self.subtitle_engine_combo = self._combo(SUBTITLE_ENGINE_OPTIONS)
        self.subtitle_engine_row = Row("자막 엔진", self.subtitle_engine_combo)
        panel_layout.addWidget(self.subtitle_engine_row)

        self.subtitle_source_combo = self._combo(SUBTITLE_SOURCE_OPTIONS)
        self.subtitle_source_row = Row("Whisper 입력", self.subtitle_source_combo)
        panel_layout.addWidget(self.subtitle_source_row)

        self.subtitle_language_input = QLineEdit("ko")
        self.subtitle_language_input.setPlaceholderText("예: ko, en, ja")
        self.subtitle_language_row = Row("자막 언어", self.subtitle_language_input)
        panel_layout.addWidget(self.subtitle_language_row)

        self.subtitle_format_combo = self._combo(SUBTITLE_FORMAT_OPTIONS)
        self.subtitle_format_row = Row("자막 형식", self.subtitle_format_combo)
        panel_layout.addWidget(self.subtitle_format_row)

        self.whisper_model_combo = self._combo(tuple((value, value) for value in SUPPORTED_WHISPER_MODELS))
        self.whisper_model_row = Row("Whisper 모델", self.whisper_model_combo)
        panel_layout.addWidget(self.whisper_model_row)

        self.whisper_device_combo = self._combo(WHISPER_DEVICE_OPTIONS)
        self.whisper_device_row = Row("Whisper device", self.whisper_device_combo)
        panel_layout.addWidget(self.whisper_device_row)
        self.whisper_runtime_combo = self._combo(WHISPER_RUNTIME_OPTIONS)
        self.colab_help_button = QPushButton("?")
        self.colab_help_button.setObjectName("helpButton")
        self.colab_help_button.setToolTip("Google Colab handoff 사용 순서 보기")
        self.whisper_runtime_row = Row("Whisper runtime", self.whisper_runtime_combo, self.colab_help_button)
        panel_layout.addWidget(self.whisper_runtime_row)

        self.vad_checkbox = QCheckBox("무음 구간 자동 필터링 사용")
        self.vad_checkbox.setChecked(True)
        self.vad_row = Row("Whisper 옵션", self.vad_checkbox)
        panel_layout.addWidget(self.vad_row)

        self.batch_mode_combo = self._combo(BATCH_OPTIONS)
        self.batch_mode_row = Row("배치 작업", self.batch_mode_combo)
        panel_layout.addWidget(self.batch_mode_row)

        self.audio_file_input = QLineEdit()
        self.audio_file_input.setReadOnly(True)
        self.audio_file_button = QPushButton("파일 선택")
        self.audio_file_row = Row("오디오 파일", self.audio_file_input, self.audio_file_button)
        panel_layout.addWidget(self.audio_file_row)

        self.output_dir_input = QLineEdit(str(DEFAULT_OUTPUT_DIR))
        self.output_dir_button = QPushButton("폴더 선택")
        self.output_dir_row = Row("저장 폴더", self.output_dir_input, self.output_dir_button)
        panel_layout.addWidget(self.output_dir_row)

        action_row = QWidget()
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 8, 0, 0)
        action_layout.setSpacing(10)

        self.start_button = QPushButton("작업 시작")
        self.start_button.setObjectName("primaryButton")
        self.pause_button = QPushButton("일시정지")
        self.resume_button = QPushButton("재개")
        self.open_result_button = QPushButton("결과 파일 열기")
        self.open_output_button = QPushButton("저장 폴더 열기")
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.open_result_button.setEnabled(False)
        self.open_output_button.setEnabled(True)
        self.primary_actions_row = ResponsiveButtonRow(
            self.start_button,
            self.pause_button,
            self.resume_button,
            self.open_result_button,
            self.open_output_button,
        )
        action_layout.addWidget(self.primary_actions_row)
        panel_layout.addWidget(action_row)
        self.colab_actions_row = QWidget()
        colab_actions_layout = QHBoxLayout(self.colab_actions_row)
        colab_actions_layout.setContentsMargins(0, 0, 0, 0)
        colab_actions_layout.setSpacing(10)
        self.export_bundle_button = QPushButton("번들 내보내기")
        self.save_notebook_button = QPushButton("노트북 저장")
        self.open_colab_button = QPushButton("Colab 열기")
        self.import_colab_result_button = QPushButton("결과 ZIP 가져오기")
        self.colab_button_row = ResponsiveButtonRow(
            self.export_bundle_button,
            self.save_notebook_button,
            self.open_colab_button,
            self.import_colab_result_button,
        )
        colab_actions_layout.addWidget(self.colab_button_row)
        panel_layout.addWidget(self.colab_actions_row)

        self.status_label = QLabel("준비되었습니다.")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("statusLabel")
        panel_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        panel_layout.addWidget(self.progress_bar)

        self.batch_label = QLabel("")
        self.batch_label.setObjectName("batchLabel")
        self.batch_label.hide()
        panel_layout.addWidget(self.batch_label)

        helper = QLabel(
            "시간 입력은 비워 두면 전체 구간을 처리합니다. 자동 선택은 YouTube 자막을 먼저 찾고, 없으면 Whisper 로컬 생성으로 전환합니다. Whisper 업로드 모드에서는 YouTube 링크 대신 오디오 파일만 사용합니다."
        )
        helper.setWordWrap(True)
        helper.setObjectName("helperLabel")
        panel_layout.addWidget(helper)

        self._form_rows = [
            self.task_row,
            self.url_row,
            self.start_row,
            self.end_row,
            self.audio_format_row,
            self.video_quality_row,
            self.subtitle_engine_row,
            self.subtitle_source_row,
            self.subtitle_language_row,
            self.subtitle_format_row,
            self.whisper_model_row,
            self.whisper_device_row,
            self.whisper_runtime_row,
            self.vad_row,
            self.batch_mode_row,
            self.audio_file_row,
            self.output_dir_row,
        ]
        self._button_rows = [self.primary_actions_row, self.colab_button_row]

        layout.addWidget(panel)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(root)
        self.setCentralWidget(scroll)

        self.task_type_combo.currentIndexChanged.connect(self.refresh_ui)
        self.batch_mode_combo.currentIndexChanged.connect(self.refresh_ui)
        self.subtitle_engine_combo.currentIndexChanged.connect(self.refresh_ui)
        self.subtitle_source_combo.currentIndexChanged.connect(self.refresh_ui)
        self.whisper_runtime_combo.currentIndexChanged.connect(self.handle_whisper_runtime_change)
        self.colab_help_button.clicked.connect(self.show_colab_help)
        self.audio_file_button.clicked.connect(self.pick_audio_file)
        self.output_dir_button.clicked.connect(self.pick_output_dir)
        self.start_button.clicked.connect(self.start_task)
        self.pause_button.clicked.connect(self.pause_task)
        self.resume_button.clicked.connect(self.resume_task)
        self.open_result_button.clicked.connect(self.open_last_result)
        self.open_output_button.clicked.connect(self.open_output_dir)
        self.export_bundle_button.clicked.connect(self.export_colab_bundle)
        self.save_notebook_button.clicked.connect(self.save_colab_notebook)
        self.open_colab_button.clicked.connect(self.open_colab_home)
        self.import_colab_result_button.clicked.connect(self.import_colab_result)

    def _apply_theme(self) -> None:
        self.setStyleSheet(build_stylesheet(self.theme_mode))
        self.theme_badge.setText(THEME_BADGE_LABELS[self.theme_mode])
        self.theme_button.setText(THEME_SWITCH_LABELS[self.theme_mode])

    def toggle_theme(self) -> None:
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        self._apply_theme()

    def _combo(self, items: tuple[tuple[str, str], ...]) -> QComboBox:
        combo = QComboBox()
        for value, label in items:
            combo.addItem(label, value)
        return combo

    def update_responsive_layout(self) -> None:
        window_width = self.width()
        compact_rows = should_use_compact_layout(window_width)
        stacked_buttons = should_stack_action_buttons(window_width)
        stacked_topbar = should_stack_topbar(window_width)

        self.topbar_layout.setDirection(
            QBoxLayout.Direction.TopToBottom if stacked_topbar else QBoxLayout.Direction.LeftToRight
        )
        self.topbar_layout.setSpacing(8 if stacked_topbar else 12)

        for row in self._form_rows:
            row.set_compact(compact_rows)

        for button_row in self._button_rows:
            button_row.set_compact(stacked_buttons)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.update_responsive_layout()

    def refresh_ui(self) -> None:
        task_type = self.current_task_type()
        batch_mode = self.current_batch_mode()
        subtitle_engine = self.current_subtitle_engine()
        subtitle_source = self.current_subtitle_source()
        whisper_runtime = self.current_whisper_runtime()
        visibility = compute_visibility(task_type, batch_mode, subtitle_engine, subtitle_source, whisper_runtime)

        self.url_row.setVisible(visibility["url"])
        self.audio_format_row.setVisible(visibility["audio_format"])
        self.video_quality_row.setVisible(visibility["video_quality"])
        self.subtitle_engine_row.setVisible(visibility["subtitle_engine"])
        self.subtitle_source_row.setVisible(visibility["subtitle_source"])
        self.subtitle_language_row.setVisible(visibility["subtitle_language"])
        self.subtitle_format_row.setVisible(visibility["subtitle_format"])
        self.whisper_model_row.setVisible(visibility["whisper_model"])
        self.whisper_device_row.setVisible(visibility["whisper_device"])
        self.whisper_runtime_row.setVisible(visibility["whisper_runtime"])
        self.colab_help_button.setEnabled(visibility["whisper_runtime"])
        self.vad_row.setVisible(visibility["vad_filter"])
        self.batch_mode_row.setVisible(visibility["batch_mode"])
        self.audio_file_row.setVisible(visibility["audio_file"])
        self.colab_actions_row.setVisible(visibility["colab_actions"])

        batch_subtitle_mode = task_type == "batch" and batch_mode == "subtitle"
        self.subtitle_engine_combo.setEnabled(not batch_subtitle_mode)
        if batch_subtitle_mode:
            index = self.subtitle_engine_combo.findData("youtube")
            if index >= 0:
                self.subtitle_engine_combo.setCurrentIndex(index)

        self.start_button.setText("Colab 패키지 만들기" if visibility["colab_actions"] else "작업 시작")

        pause_visible = supports_pause_resume(task_type, subtitle_engine, whisper_runtime)
        self.pause_button.setVisible(pause_visible)
        self.resume_button.setVisible(pause_visible)
        self.update_responsive_layout()
        self.update_colab_buttons()
        self.update_pause_buttons()

    def current_task_type(self) -> str:
        return str(self.task_type_combo.currentData())

    def current_batch_mode(self) -> str:
        return str(self.batch_mode_combo.currentData())

    def current_subtitle_engine(self) -> str:
        return str(self.subtitle_engine_combo.currentData())

    def current_subtitle_source(self) -> str:
        return str(self.subtitle_source_combo.currentData())

    def current_whisper_runtime(self) -> str:
        return str(self.whisper_runtime_combo.currentData())

    def show_colab_help(self) -> None:
        bundle_name = self.colab_state.bundle_download_name if self.colab_state is not None else None
        QMessageBox.information(self, "Colab handoff 안내", build_colab_help_message(bundle_name))

    def handle_whisper_runtime_change(self) -> None:
        if self.current_whisper_runtime() == "colab":
            model_index = self.whisper_model_combo.findData("large-v3-turbo")
            if str(self.whisper_model_combo.currentData()) == "base" and model_index >= 0:
                self.whisper_model_combo.setCurrentIndex(model_index)

            device_index = self.whisper_device_combo.findData("cuda")
            if str(self.whisper_device_combo.currentData()) == "auto" and device_index >= 0:
                self.whisper_device_combo.setCurrentIndex(device_index)

        self.refresh_ui()

    def pick_audio_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "오디오 파일 선택",
            str(Path.home()),
            "Audio files (*.mp3 *.wav *.m4a *.aac *.opus *.webm *.mp4 *.mkv *.flac *.ogg);;All files (*.*)",
        )
        if path:
            self.audio_file_input.setText(path)

    def pick_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "저장 폴더 선택",
            self.output_dir_input.text() or str(DEFAULT_OUTPUT_DIR),
        )
        if path:
            self.output_dir_input.setText(path)

    def export_colab_bundle(self) -> None:
        if self.colab_state is None or not self.colab_state.bundle_path.exists():
            QMessageBox.information(self, APP_TITLE, "먼저 Colab 패키지를 만들어 주세요.")
            return

        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Colab 번들 저장",
            str(self.colab_state.output_dir / self.colab_state.bundle_download_name),
            "ZIP files (*.zip)",
        )
        if not destination:
            return

        saved_path = export_file_copy(self.colab_state.bundle_path, Path(destination).parent, Path(destination).name)
        self.status_label.setText(f"Colab 번들을 저장했습니다: {saved_path}")

    def save_colab_notebook(self) -> None:
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Colab 노트북 저장",
            str(ensure_output_dir(self.output_dir_input.text()) / COLAB_NOTEBOOK_FILENAME),
            "Jupyter notebooks (*.ipynb)",
        )
        if not destination:
            return

        saved_path = save_notebook_to_output(Path(destination).parent, Path(destination).name)
        self.status_label.setText(f"Colab 노트북을 저장했습니다: {saved_path}")

    def open_colab_home(self) -> None:
        QDesktopServices.openUrl(QUrl(COLAB_HOME_URL))
        self.status_label.setText("Google Colab을 브라우저에서 열었습니다.")

    def import_colab_result(self) -> None:
        if self.colab_state is None or not self.colab_state.bundle_path.exists():
            QMessageBox.information(self, APP_TITLE, "가져올 Colab handoff 정보가 없습니다. 먼저 패키지를 만들어 주세요.")
            return

        package_path, _ = QFileDialog.getOpenFileName(
            self,
            "Colab 결과 ZIP 선택",
            str(self.colab_state.output_dir),
            "ZIP files (*.zip)",
        )
        if not package_path:
            return

        try:
            result, _details = import_colab_result_package(
                package_path=Path(package_path),
                work_dir=self.colab_state.work_dir,
                job_id=self.colab_state.job_id,
                expected_details=self.colab_state.expected_details,
            )
            saved_path = persist_result(result, self.colab_state.output_dir)
        except Exception as exc:
            self.status_label.setText(str(exc))
            QMessageBox.critical(self, APP_TITLE, str(exc))
            return

        self.colab_state.completed = True
        self.last_output_path = saved_path
        self.last_output_dir = self.colab_state.output_dir
        self.progress_bar.setValue(100)
        self.status_label.setText(f"Colab 결과를 가져왔습니다. 저장 위치: {saved_path}")
        self.open_result_button.setEnabled(True)
        self.update_colab_buttons()
        QMessageBox.information(self, APP_TITLE, f"Colab 결과를 가져왔습니다.\n\n{saved_path}")

    def update_pause_buttons(self) -> None:
        worker_running = self.worker is not None and self.worker.isRunning()
        pause_supported = worker_running and self.worker.supports_pause_resume()
        paused = pause_supported and self.worker.is_paused()
        self.pause_button.setEnabled(pause_supported and not paused)
        self.resume_button.setEnabled(pause_supported and paused)

    def update_colab_buttons(self) -> None:
        colab_visible = self.colab_actions_row.isVisible()
        worker_running = self.worker is not None and self.worker.isRunning()
        has_state = self.colab_state is not None and self.colab_state.bundle_path.exists()
        self.export_bundle_button.setEnabled(colab_visible and has_state and not worker_running)
        self.save_notebook_button.setEnabled(colab_visible and not worker_running)
        self.open_colab_button.setEnabled(colab_visible and not worker_running)
        self.import_colab_result_button.setEnabled(
            colab_visible and has_state and not worker_running and not (self.colab_state and self.colab_state.completed)
        )

    def pause_task(self) -> None:
        if self.worker is None or not self.worker.isRunning() or not self.worker.supports_pause_resume():
            return
        self.worker.pause_work()
        self.status_label.setText("Whisper 자막 추출 일시정지를 요청했습니다. 현재 처리 중인 구간이 끝나면 멈춥니다.")
        self.update_pause_buttons()

    def resume_task(self) -> None:
        if self.worker is None or not self.worker.isRunning() or not self.worker.supports_pause_resume():
            return
        self.worker.resume_work()
        self.status_label.setText("Whisper 자막 추출을 다시 시작합니다.")
        self.update_pause_buttons()

    def set_busy(self, busy: bool) -> None:
        controls = (
            self.task_type_combo,
            self.url_input,
            self.start_input,
            self.end_input,
            self.audio_format_combo,
            self.video_quality_combo,
            self.subtitle_engine_combo,
            self.subtitle_source_combo,
            self.subtitle_language_input,
            self.subtitle_format_combo,
            self.whisper_model_combo,
            self.whisper_device_combo,
            self.whisper_runtime_combo,
            self.vad_checkbox,
            self.batch_mode_combo,
            self.audio_file_button,
            self.output_dir_button,
            self.start_button,
        )
        for widget in controls:
            widget.setEnabled(not busy)
        self.update_colab_buttons()
        self.update_pause_buttons()

    def collect_config(self) -> TaskConfig:
        task_type = self.current_task_type()
        subtitle_source = self.current_subtitle_source()
        subtitle_engine = self.current_subtitle_engine()
        batch_mode = self.current_batch_mode()
        whisper_runtime = self.current_whisper_runtime()
        visibility = compute_visibility(task_type, batch_mode, subtitle_engine, subtitle_source, whisper_runtime)

        url = normalize_optional_text(self.url_input.text()) if visibility["url"] else None
        if visibility["url"] and not url:
            raise ValueError("YouTube 링크를 입력해 주세요.")

        audio_file_path = normalize_optional_text(self.audio_file_input.text())
        if visibility["audio_file"] and not audio_file_path:
            raise ValueError("Whisper 전사용 오디오 파일을 선택해 주세요.")

        subtitle_language = normalize_optional_text(self.subtitle_language_input.text()) or "ko"
        return TaskConfig(
            task_type=task_type,
            url=url,
            start_time=normalize_optional_text(self.start_input.text()),
            end_time=normalize_optional_text(self.end_input.text()),
            audio_format=str(self.audio_format_combo.currentData()),
            video_quality=str(self.video_quality_combo.currentData()),
            subtitle_engine=subtitle_engine,
            subtitle_source=subtitle_source,
            subtitle_language=subtitle_language,
            subtitle_format=str(self.subtitle_format_combo.currentData()),
            whisper_model=str(self.whisper_model_combo.currentData()),
            whisper_device=str(self.whisper_device_combo.currentData()),
            whisper_runtime=whisper_runtime,
            vad_filter=self.vad_checkbox.isChecked(),
            batch_mode=batch_mode,
            audio_file_path=audio_file_path,
            output_dir=ensure_output_dir(self.output_dir_input.text()),
        )

    def start_task(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        try:
            config = self.collect_config()
        except Exception as exc:
            QMessageBox.warning(self, APP_TITLE, str(exc))
            return

        if (
            config.task_type == "subtitle"
            and config.subtitle_engine == "whisper"
            and config.subtitle_source == "audio_file"
            and config.whisper_runtime == "colab"
        ):
            try:
                self.start_colab_handoff(config)
            except Exception as exc:
                self.status_label.setText(str(exc))
                QMessageBox.warning(self, APP_TITLE, str(exc))
            return

        self.progress_bar.setValue(0)
        self.status_label.setText("작업을 시작합니다.")
        self.batch_label.hide()
        self.last_output_dir = config.output_dir
        self.last_output_path = None
        self.open_result_button.setEnabled(False)
        self.set_busy(True)

        self.worker = ExtractionWorker(config)
        self.worker.progress.connect(self.handle_progress)
        self.worker.batch_status.connect(self.handle_batch_status)
        self.worker.completed.connect(self.handle_completed)
        self.worker.failed.connect(self.handle_failed)
        self.worker.finished.connect(self.cleanup_worker)
        self.worker.start()
        self.update_pause_buttons()

    def start_colab_handoff(self, config: TaskConfig) -> None:
        if self.colab_state is not None and self.colab_state.bundle_path.exists() and not self.colab_state.completed:
            replace = QMessageBox.question(
                self,
                APP_TITLE,
                "진행 중인 Colab handoff 정보가 있습니다. 새 패키지를 만들면 기존 handoff가 이 창에서 교체됩니다. 계속할까요?",
            )
            if replace != QMessageBox.StandardButton.Yes:
                return
            cleanup_temp_dir(self.colab_state.work_dir)
            self.colab_state = None

        self.colab_state = create_colab_handoff_state(config)
        self.last_output_dir = config.output_dir
        self.last_output_path = None
        self.open_result_button.setEnabled(False)
        self.progress_bar.setValue(15)
        self.status_label.setText("Colab 패키지가 준비되었습니다. 번들을 내보내고 노트북을 실행한 뒤 결과 ZIP을 가져오세요.")
        self.update_colab_buttons()
        QMessageBox.information(
            self,
            APP_TITLE,
            "Colab 패키지를 만들었습니다.\n\n1. 번들 내보내기\n2. 노트북 저장 또는 Colab 열기\n3. 결과 ZIP 가져오기",
        )

    def cleanup_worker(self) -> None:
        self.set_busy(False)
        self.update_pause_buttons()
        self.worker = None

    def handle_progress(self, value: int, message: str) -> None:
        self.progress_bar.setValue(max(0, min(100, value)))
        self.status_label.setText(message)
        self.update_pause_buttons()

    def handle_batch_status(self, total: int, completed: int, failed: int) -> None:
        self.batch_label.setText(f"배치 진행: 총 {total}개, 성공 {completed}개, 실패 {failed}개")
        self.batch_label.show()

    def handle_completed(self, saved_path: str, message: str) -> None:
        self.last_output_path = Path(saved_path)
        self.progress_bar.setValue(100)
        self.status_label.setText(f"{message} 저장 위치: {saved_path}")
        self.open_result_button.setEnabled(True)
        QMessageBox.information(self, APP_TITLE, f"{message}\n\n{saved_path}")

    def handle_failed(self, message: str) -> None:
        self.status_label.setText(message)
        self.update_pause_buttons()
        QMessageBox.critical(self, APP_TITLE, message)

    def open_last_result(self) -> None:
        if self.last_output_path is not None and self.last_output_path.exists():
            open_path(self.last_output_path)

    def open_output_dir(self) -> None:
        open_path(self.last_output_dir)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
