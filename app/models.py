from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.services.extractor import (
    SUPPORTED_FORMATS,
    SUPPORTED_VIDEO_QUALITIES,
    is_supported_youtube_url,
    normalize_mp3_bitrate,
    normalize_split_size_mb,
)
from app.services.subtitle_extractor import normalize_language_code, normalize_subtitle_format
from app.services.whisper_subtitle_extractor import (
    normalize_subtitle_engine,
    normalize_whisper_device,
    normalize_whisper_model,
)
from app.services.time_utils import parse_timestamp, validate_time_range


TaskType = Literal["audio", "song_mp3", "video", "subtitle", "batch"]
BatchMode = Literal["audio", "song_mp3", "video", "subtitle"]
SubtitleEngine = Literal["auto", "youtube", "whisper"]
SubtitleFormat = Literal["timestamped", "clean"]
WhisperDevice = Literal["auto", "cpu", "cuda"]
WhisperRuntime = Literal["local", "colab"]


class RequestBase(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    url: str = Field(..., min_length=10, max_length=2048)
    start_time: str | None = None
    end_time: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not is_supported_youtube_url(value):
            raise ValueError("Only YouTube links are supported.")
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_timestamp(cls, value: str | None) -> str | None:
        parse_timestamp(value)
        return value

    @model_validator(mode="after")
    def validate_time_order(self) -> Self:
        validate_time_range(self.start_time, self.end_time)
        return self


class ExtractRequest(RequestBase):
    audio_format: str = "mp3"
    mp3_bitrate: str | None = None
    split_size_mb: int | None = None

    @field_validator("audio_format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        if value not in SUPPORTED_FORMATS:
            raise ValueError("Unsupported audio format.")
        return value

    @field_validator("mp3_bitrate")
    @classmethod
    def validate_mp3_bitrate(cls, value: str | None) -> str | None:
        return normalize_mp3_bitrate(value)

    @field_validator("split_size_mb")
    @classmethod
    def validate_split_size_mb(cls, value: int | None) -> int | None:
        return normalize_split_size_mb(value)

    @model_validator(mode="after")
    def validate_audio_processing_options(self) -> Self:
        if self.audio_format != "mp3":
            if self.mp3_bitrate is not None:
                raise ValueError("MP3 bitrate is only available for MP3 output.")
            if self.split_size_mb is not None:
                raise ValueError("File splitting is only available for MP3 output.")
        return self


class SubtitleRequest(RequestBase):
    subtitle_language: str = "ko"
    subtitle_engine: SubtitleEngine = "auto"
    subtitle_format: SubtitleFormat = "timestamped"
    whisper_model: str = "base"
    whisper_device: WhisperDevice = "auto"
    whisper_runtime: WhisperRuntime = "local"
    vad_filter: bool = True

    @field_validator("subtitle_language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_language_code(value)

    @field_validator("subtitle_engine")
    @classmethod
    def validate_engine(cls, value: str) -> str:
        return normalize_subtitle_engine(value)

    @field_validator("subtitle_format")
    @classmethod
    def validate_subtitle_format_name(cls, value: str) -> str:
        return normalize_subtitle_format(value)

    @field_validator("whisper_model")
    @classmethod
    def validate_whisper_model_name(cls, value: str) -> str:
        return normalize_whisper_model(value)

    @field_validator("whisper_device")
    @classmethod
    def validate_whisper_device_name(cls, value: str) -> str:
        return normalize_whisper_device(value)

    @model_validator(mode="after")
    def validate_runtime_support(self) -> Self:
        if self.whisper_runtime == "colab":
            raise ValueError("Colab runtime is only supported for uploaded audio subtitle jobs.")
        return self


class JobRequest(RequestBase):
    task_type: TaskType
    audio_format: str = "mp3"
    mp3_bitrate: str | None = None
    split_size_mb: int | None = None
    video_quality: str = "1080p"
    subtitle_language: str = "ko"
    subtitle_engine: SubtitleEngine = "auto"
    subtitle_format: SubtitleFormat = "timestamped"
    whisper_model: str = "base"
    whisper_device: WhisperDevice = "auto"
    whisper_runtime: WhisperRuntime = "local"
    vad_filter: bool = True
    batch_mode: BatchMode | None = None

    @field_validator("audio_format")
    @classmethod
    def validate_audio_format(cls, value: str) -> str:
        if value not in SUPPORTED_FORMATS:
            raise ValueError("Unsupported audio format.")
        return value

    @field_validator("mp3_bitrate")
    @classmethod
    def validate_job_mp3_bitrate(cls, value: str | None) -> str | None:
        return normalize_mp3_bitrate(value)

    @field_validator("split_size_mb")
    @classmethod
    def validate_job_split_size_mb(cls, value: int | None) -> int | None:
        return normalize_split_size_mb(value)

    @field_validator("video_quality")
    @classmethod
    def validate_video_quality(cls, value: str) -> str:
        if value not in SUPPORTED_VIDEO_QUALITIES:
            raise ValueError("Unsupported video quality.")
        return value

    @field_validator("subtitle_language")
    @classmethod
    def validate_subtitle_language(cls, value: str) -> str:
        return normalize_language_code(value)

    @field_validator("subtitle_engine")
    @classmethod
    def validate_subtitle_engine_name(cls, value: str) -> str:
        return normalize_subtitle_engine(value)

    @field_validator("subtitle_format")
    @classmethod
    def validate_job_subtitle_format_name(cls, value: str) -> str:
        return normalize_subtitle_format(value)

    @field_validator("whisper_model")
    @classmethod
    def validate_job_whisper_model_name(cls, value: str) -> str:
        return normalize_whisper_model(value)

    @field_validator("whisper_device")
    @classmethod
    def validate_job_whisper_device_name(cls, value: str) -> str:
        return normalize_whisper_device(value)

    @model_validator(mode="after")
    def validate_conditional_fields(self) -> Self:
        if self.task_type == "batch" and self.batch_mode is None:
            raise ValueError("batchMode is required for batch tasks.")
        if self.task_type == "batch" and self.batch_mode == "subtitle":
            if self.subtitle_engine == "whisper":
                raise ValueError("Whisper subtitle generation is only supported for single-video subtitle tasks.")
            if self.subtitle_engine == "auto":
                self.subtitle_engine = "youtube"
        if self.whisper_runtime == "colab":
            raise ValueError("Colab runtime is only supported for uploaded audio subtitle jobs.")
        uses_audio_processing = self.task_type == "audio" or (
            self.task_type == "batch" and self.batch_mode == "audio"
        )
        if not uses_audio_processing:
            if self.mp3_bitrate is not None:
                raise ValueError("MP3 bitrate is only available for audio extraction.")
            if self.split_size_mb is not None:
                raise ValueError("File splitting is only available for audio extraction.")
        elif self.audio_format != "mp3":
            if self.mp3_bitrate is not None:
                raise ValueError("MP3 bitrate is only available for MP3 output.")
            if self.split_size_mb is not None:
                raise ValueError("File splitting is only available for MP3 output.")
        return self
