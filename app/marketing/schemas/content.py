"""Pydantic schemas for Content Studio: media files and content posts."""

from uuid import UUID
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field


# ── Media File ──

class MediaFileOut(BaseModel):
    id: UUID
    business_id: UUID
    filename: str
    file_path: str
    mime_type: str
    size_bytes: int
    uploaded_by: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MediaFileListResponse(BaseModel):
    files: list[MediaFileOut]
    total: int


# ── Content Post ──

class ContentPostCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    platform_targets: list[str] = Field(default_factory=list)
    media_ids: list[UUID] = Field(default_factory=list)


class ContentPostUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1, max_length=5000)
    platform_targets: Optional[list[str]] = None
    media_ids: Optional[list[UUID]] = None


class ContentPostOut(BaseModel):
    id: UUID
    business_id: UUID
    content: str
    platform_targets: list[str]
    media_ids: list[UUID]
    status: str
    posted_at: Optional[datetime] = None
    posted_by: Optional[UUID] = None
    platform_results: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContentPostListResponse(BaseModel):
    posts: list[ContentPostOut]
    total: int
