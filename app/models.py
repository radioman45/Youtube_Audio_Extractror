from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.services.extractor import SUPPORTED_FORMATS, is_supported_youtube_url
from app.services.time_utils import parse_timestamp, validate_time_range


class ExtractRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    url: str = Field(..., min_length=10, max_length=2048)
    audio_format: str = "mp3"
    start_time: str | None = None
    end_time: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not is_supported_youtube_url(value):
            raise ValueError("Only YouTube links are supported.")
        return value

    @field_validator("audio_format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        if value not in SUPPORTED_FORMATS:
            raise ValueError("Unsupported audio format.")
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
