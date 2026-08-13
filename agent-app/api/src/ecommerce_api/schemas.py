"""HTTP request and response schemas for the public generation API.

These models define the stable wire contract. Business-domain models stay in
``ecommerce_agent.domain`` so the core package remains transport-independent.
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


ALLOWED_PLATFORMS = {"taobao", "amazon", "douyin", "tiktok", "xiaohongshu"}
ALLOWED_TONES = {"professional", "casual", "trendy", "luxury", "cute"}


class GenerateRequest(BaseModel):
    """Common structured product input accepted by every generation mode."""

    title: str = Field(..., min_length=1, description="Product title")
    category: str = Field("other", description="Product category")
    attributes: dict[str, str] = Field(default_factory=dict, description="Product attributes")
    selling_points: list[str] = Field(default_factory=list, description="Existing selling points")
    target_audience: str = ""
    price_positioning: str = ""
    platform: str = "taobao"
    tone: str = "professional"
    constraints: list[str] = Field(default_factory=list)
    original_description: str = ""

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str) -> str:
        if value not in ALLOWED_PLATFORMS:
            raise ValueError(f"platform must be one of: {', '.join(sorted(ALLOWED_PLATFORMS))}")
        return value

    @field_validator("tone")
    @classmethod
    def validate_tone(cls, value: str) -> str:
        if value not in ALLOWED_TONES:
            raise ValueError(f"tone must be one of: {', '.join(sorted(ALLOWED_TONES))}")
        return value


class GenerateVideoRequest(GenerateRequest):
    """Generation input with an optional user-authored video prompt."""

    custom_video_prompt: str = ""


class GenerateImageRequest(GenerateRequest):
    """Generation input with an optional user-authored image prompt."""

    custom_image_prompt: str = ""


class GenerateAllRequest(GenerateRequest):
    """Generation input for a complete copy, image, and video package."""

    custom_image_prompt: str = ""
    custom_video_prompt: str = ""


class GenerateResponse(BaseModel):
    """Generated copy and optional browser-addressable media results."""

    optimized_title: str
    selling_points: list[str]
    description: str
    seo_keywords: list[str]
    social_copy: str
    quality_score: dict
    rewrite_reason: str
    rewrite_history: list
    platform: str
    image: Optional[dict] = None
    video: Optional[dict] = None


class TaskAccepted(BaseModel):
    """Reference returned when an asynchronous media task is queued."""

    task_id: str
    kind: str
    status: str
    status_url: str
    poll_timeout_seconds: int


class TaskResponse(TaskAccepted):
    """Current asynchronous task state and its terminal payload, if available."""

    result: Optional[dict] = None
    error: Optional[dict] = None
    upstream_task_id: Optional[str] = None
    created_at: str
    updated_at: str


class ProviderSettings(BaseModel):
    """Editable non-secret settings and masked credential state for one provider."""

    backend: str
    model: str
    api_url: str
    query_url: str = ""
    api_key_configured: bool = False
    managed_by_env: bool = False


class ModelSettingsResponse(BaseModel):
    """Current effective model settings without exposing API keys."""

    text: ProviderSettings
    image: ProviderSettings
    video: ProviderSettings


class ProviderSettingsUpdate(BaseModel):
    """Provider changes; a blank API key preserves the current credential."""

    backend: str
    model: str
    api_url: str
    query_url: str = ""
    api_key: str = Field("", max_length=4096)


class ModelSettingsUpdate(BaseModel):
    """Atomic runtime update for text, image, and video providers."""

    text: ProviderSettingsUpdate
    image: ProviderSettingsUpdate
    video: ProviderSettingsUpdate
