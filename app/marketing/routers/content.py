"""
Content Studio Router — media upload, content post CRUD.

Endpoints:
  POST   /marketing/media/upload              — upload image
  GET    /marketing/media                     — list media files
  GET    /marketing/media/{media_id}/file     — serve media file
  DELETE /marketing/media/{media_id}          — delete media file

  POST   /marketing/posts                     — create post draft
  GET    /marketing/posts                     — list posts
  PATCH  /marketing/posts/{post_id}           — update draft
  DELETE /marketing/posts/{post_id}           — delete post
  POST   /marketing/posts/{post_id}/publish   — mark post as published
"""

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.marketing.schemas.content import (
    MediaFileOut,
    MediaFileListResponse,
    ContentPostCreate,
    ContentPostUpdate,
    ContentPostOut,
    ContentPostListResponse,
)
from app.marketing.services import content_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketing", tags=["Marketing — Content Studio"])


# ─── Media Endpoints ───


@router.post("/media/upload", response_model=MediaFileOut)
async def upload_media(
    business_id: UUID = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload an image file (jpeg, png, gif, webp — max 10 MB)."""
    content = await file.read()
    try:
        row = await content_service.save_upload(
            db=db,
            business_id=str(business_id),
            filename=file.filename or "upload",
            content=content,
            mime_type=file.content_type or "application/octet-stream",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return row


@router.get("/media", response_model=MediaFileListResponse)
async def list_media(
    business_id: UUID = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    files, total = await content_service.list_media(db, str(business_id), limit, offset)
    return MediaFileListResponse(files=files, total=total)


@router.get("/media/{media_id}/file")
async def serve_media_file(
    media_id: UUID,
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Serve the actual media file bytes."""
    row = await content_service.get_media_file(db, str(business_id), str(media_id))
    if not row:
        raise HTTPException(status_code=404, detail="Media file not found")
    full_path = Path(settings.base_dir) / row.file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(full_path, media_type=row.mime_type, filename=row.filename)


@router.delete("/media/{media_id}", status_code=204)
async def delete_media(
    media_id: UUID,
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    ok = await content_service.delete_media(db, str(business_id), str(media_id))
    if not ok:
        raise HTTPException(status_code=404, detail="Media file not found")


# ─── Content Post Endpoints ───


@router.post("/posts", response_model=ContentPostOut)
async def create_post(
    body: ContentPostCreate,
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    row = await content_service.create_post(
        db=db,
        business_id=str(business_id),
        content=body.content,
        platform_targets=body.platform_targets,
        media_ids=[str(m) for m in body.media_ids],
    )
    return row


@router.get("/posts", response_model=ContentPostListResponse)
async def list_posts(
    business_id: UUID = Query(...),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    posts, total = await content_service.list_posts(db, str(business_id), status, limit, offset)
    return ContentPostListResponse(posts=posts, total=total)


@router.patch("/posts/{post_id}", response_model=ContentPostOut)
async def update_post(
    post_id: UUID,
    body: ContentPostUpdate,
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    row = await content_service.update_post(
        db=db,
        business_id=str(business_id),
        post_id=str(post_id),
        content=body.content,
        platform_targets=body.platform_targets,
        media_ids=[str(m) for m in body.media_ids] if body.media_ids is not None else None,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    return row


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: UUID,
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    ok = await content_service.delete_post(db, str(business_id), str(post_id))
    if not ok:
        raise HTTPException(status_code=404, detail="Post not found")


@router.post("/posts/{post_id}/publish", response_model=ContentPostOut)
async def publish_post(
    post_id: UUID,
    business_id: UUID = Query(...),
    employee_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Mark a post as published (called after the AI agent posts it)."""
    row = await content_service.mark_posted(
        db=db,
        business_id=str(business_id),
        post_id=str(post_id),
        employee_id=str(employee_id) if employee_id else None,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    return row
