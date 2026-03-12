from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.services.batch_extractor import BatchExtractionOptions, extract_batch
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
from app.services.subtitle_extractor import SubtitleOptions, extract_subtitles
from app.services.task_control import PauseController
from app.services.video_extractor import VideoExtractionOptions, extract_video
from app.services.whisper_subtitle_extractor import (
    SUPPORTED_WHISPER_MODELS,
    LocalWhisperSubtitleOptions,
    WhisperSubtitleOptions,
    extract_whisper_subtitles,
    extract_whisper_subtitles_from_file,
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
    vad_filter: bool
    batch_mode: str
    audio_file_path: str | None
    output_dir: Path


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


def compute_visibility(
    task_type: str,
    batch_mode: str,
    subtitle_engine: str,
    subtitle_source: str,
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
        "vad_filter": whisper_mode,
        "audio_file": upload_mode,
        "batch_mode": is_batch,
    }


def supports_pause_resume(task_type: str, subtitle_engine: str) -> bool:
    return task_type == "subtitle" and subtitle_engine == "whisper"


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
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        title = QLabel(label)
        title.setMinimumWidth(170)
        title.setObjectName("rowLabel")
        layout.addWidget(title)

        field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(field, 1)
        if extra is not None:
            layout.addWidget(extra)


class ExtractionWorker(QThread):
    progress = Signal(int, str)
    batch_status = Signal(int, int, int)
    completed = Signal(str, str)
    failed = Signal(str)

    def __init__(self, config: TaskConfig):
        super().__init__()
        self._config = config
        self._pause_controller = PauseController() if supports_pause_resume(config.task_type, config.subtitle_engine) else None

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
        self.last_output_path: Path | None = None
        self.last_output_dir: Path = DEFAULT_OUTPUT_DIR
        self.theme_mode = "dark"

        self.setWindowTitle(APP_TITLE)
        self.resize(1160, 920)
        self.setMinimumSize(980, 780)

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
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(0, 0, 0, 0)
        topbar_layout.setSpacing(8)

        self.desktop_pill = QLabel("Browser-free")
        self.desktop_pill.setObjectName("desktopPill")
        self.theme_badge = QLabel("")
        self.theme_badge.setObjectName("themeBadge")
        self.theme_button = QPushButton("")
        self.theme_button.setObjectName("themeButton")
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.clicked.connect(self.toggle_theme)

        topbar_layout.addWidget(self.desktop_pill)
        topbar_layout.addWidget(self.theme_badge)
        topbar_layout.addStretch(1)
        topbar_layout.addWidget(self.theme_button)
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
        action_layout.addWidget(self.start_button)
        action_layout.addWidget(self.pause_button)
        action_layout.addWidget(self.resume_button)
        action_layout.addWidget(self.open_result_button)
        action_layout.addWidget(self.open_output_button)
        action_layout.addStretch(1)
        panel_layout.addWidget(action_row)

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
            "시간 입력은 비워 두면 전체 구간을 처리합니다. Whisper 업로드 모드에서는 YouTube 링크 대신 오디오 파일만 사용합니다."
        )
        helper.setWordWrap(True)
        helper.setObjectName("helperLabel")
        panel_layout.addWidget(helper)

        layout.addWidget(panel)
        layout.addStretch(1)
        self.setCentralWidget(root)

        self.task_type_combo.currentIndexChanged.connect(self.refresh_ui)
        self.batch_mode_combo.currentIndexChanged.connect(self.refresh_ui)
        self.subtitle_engine_combo.currentIndexChanged.connect(self.refresh_ui)
        self.subtitle_source_combo.currentIndexChanged.connect(self.refresh_ui)
        self.audio_file_button.clicked.connect(self.pick_audio_file)
        self.output_dir_button.clicked.connect(self.pick_output_dir)
        self.start_button.clicked.connect(self.start_task)
        self.pause_button.clicked.connect(self.pause_task)
        self.resume_button.clicked.connect(self.resume_task)
        self.open_result_button.clicked.connect(self.open_last_result)
        self.open_output_button.clicked.connect(self.open_output_dir)

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

    def refresh_ui(self) -> None:
        task_type = self.current_task_type()
        batch_mode = self.current_batch_mode()
        subtitle_engine = self.current_subtitle_engine()
        subtitle_source = self.current_subtitle_source()
        visibility = compute_visibility(task_type, batch_mode, subtitle_engine, subtitle_source)

        self.url_row.setVisible(visibility["url"])
        self.audio_format_row.setVisible(visibility["audio_format"])
        self.video_quality_row.setVisible(visibility["video_quality"])
        self.subtitle_engine_row.setVisible(visibility["subtitle_engine"])
        self.subtitle_source_row.setVisible(visibility["subtitle_source"])
        self.subtitle_language_row.setVisible(visibility["subtitle_language"])
        self.subtitle_format_row.setVisible(visibility["subtitle_format"])
        self.whisper_model_row.setVisible(visibility["whisper_model"])
        self.whisper_device_row.setVisible(visibility["whisper_device"])
        self.vad_row.setVisible(visibility["vad_filter"])
        self.batch_mode_row.setVisible(visibility["batch_mode"])
        self.audio_file_row.setVisible(visibility["audio_file"])

        batch_subtitle_mode = task_type == "batch" and batch_mode == "subtitle"
        self.subtitle_engine_combo.setEnabled(not batch_subtitle_mode)
        if batch_subtitle_mode:
            index = self.subtitle_engine_combo.findData("youtube")
            if index >= 0:
                self.subtitle_engine_combo.setCurrentIndex(index)

        pause_visible = supports_pause_resume(task_type, subtitle_engine)
        self.pause_button.setVisible(pause_visible)
        self.resume_button.setVisible(pause_visible)
        self.update_pause_buttons()

    def current_task_type(self) -> str:
        return str(self.task_type_combo.currentData())

    def current_batch_mode(self) -> str:
        return str(self.batch_mode_combo.currentData())

    def current_subtitle_engine(self) -> str:
        return str(self.subtitle_engine_combo.currentData())

    def current_subtitle_source(self) -> str:
        return str(self.subtitle_source_combo.currentData())

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

    def update_pause_buttons(self) -> None:
        worker_running = self.worker is not None and self.worker.isRunning()
        pause_supported = worker_running and self.worker.supports_pause_resume()
        paused = pause_supported and self.worker.is_paused()
        self.pause_button.setEnabled(pause_supported and not paused)
        self.resume_button.setEnabled(pause_supported and paused)

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
            self.vad_checkbox,
            self.batch_mode_combo,
            self.audio_file_button,
            self.output_dir_button,
            self.start_button,
        )
        for widget in controls:
            widget.setEnabled(not busy)
        self.update_pause_buttons()

    def collect_config(self) -> TaskConfig:
        task_type = self.current_task_type()
        subtitle_source = self.current_subtitle_source()
        subtitle_engine = self.current_subtitle_engine()
        batch_mode = self.current_batch_mode()
        visibility = compute_visibility(task_type, batch_mode, subtitle_engine, subtitle_source)

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
