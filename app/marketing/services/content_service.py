"""Content Studio service — media upload, post CRUD."""

import os
import uuid
from pathlib import Path

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.marketing.models import MediaFile, ContentPost


ALLOWED_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _media_dir(business_id: str) -> Path:
    """Return (and create) the media directory for a business."""
    p = Path(settings.base_dir) / "businesses" / business_id / "media"
    p.mkdir(parents=True, exist_ok=True)
    return p


async def save_upload(
    db: AsyncSession,
    business_id: str,
    filename: str,
    content: bytes,
    mime_type: str,
    user_id: str | None = None,
) -> MediaFile:
    """Write file to disk and create DB record."""
    if mime_type not in ALLOWED_MIMES:
        raise ValueError(f"Unsupported file type: {mime_type}. Allowed: {', '.join(ALLOWED_MIMES)}")
    if len(content) > MAX_FILE_SIZE:
        raise ValueError(f"File too large ({len(content)} bytes). Max: {MAX_FILE_SIZE // 1024 // 1024} MB")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    file_id = uuid.uuid4()
    rel_path = f"businesses/{business_id}/media/{file_id}.{ext}"

    # Write to disk
    dest = _media_dir(business_id) / f"{file_id}.{ext}"
    dest.write_bytes(content)

    row = MediaFile(
        id=file_id,
        business_id=uuid.UUID(business_id),
        filename=filename,
        file_path=rel_path,
        mime_type=mime_type,
        size_bytes=len(content),
        uploaded_by=uuid.UUID(user_id) if user_id else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_media(
    db: AsyncSession, business_id: str, limit: int = 50, offset: int = 0,
) -> tuple[list[MediaFile], int]:
    """List media files for a business, newest first."""
    total_q = await db.execute(
        select(func.count(MediaFile.id)).where(MediaFile.business_id == business_id)
    )
    total = total_q.scalar() or 0

    rows_q = await db.execute(
        select(MediaFile)
        .where(MediaFile.business_id == business_id)
        .order_by(MediaFile.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return rows_q.scalars().all(), total


async def delete_media(db: AsyncSession, business_id: str, media_id: str) -> bool:
    """Delete a media file from disk and DB."""
    row = await db.get(MediaFile, uuid.UUID(media_id))
    if not row or str(row.business_id) != business_id:
        return False

    # Remove file from disk
    full_path = Path(settings.base_dir) / row.file_path
    if full_path.exists():
        full_path.unlink()

    await db.delete(row)
    await db.commit()
    return True


async def get_media_file(db: AsyncSession, business_id: str, media_id: str) -> MediaFile | None:
    """Get a single media file record."""
    row = await db.get(MediaFile, uuid.UUID(media_id))
    if not row or str(row.business_id) != business_id:
        return None
    return row


# ── Content Posts ──

async def create_post(
    db: AsyncSession, business_id: str, content: str,
    platform_targets: list[str], media_ids: list[str],
) -> ContentPost:
    row = ContentPost(
        business_id=uuid.UUID(business_id),
        content=content,
        platform_targets=platform_targets,
        media_ids=[str(m) for m in media_ids],
        status="draft",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_posts(
    db: AsyncSession, business_id: str, status: str | None = None,
    limit: int = 20, offset: int = 0,
) -> tuple[list[ContentPost], int]:
    base = select(ContentPost).where(ContentPost.business_id == business_id)
    count_q = select(func.count(ContentPost.id)).where(ContentPost.business_id == business_id)
    if status:
        base = base.where(ContentPost.status == status)
        count_q = count_q.where(ContentPost.status == status)

    total = (await db.execute(count_q)).scalar() or 0
    rows = (await db.execute(
        base.order_by(ContentPost.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()
    return rows, total


async def get_post(db: AsyncSession, business_id: str, post_id: str) -> ContentPost | None:
    row = await db.get(ContentPost, uuid.UUID(post_id))
    if not row or str(row.business_id) != business_id:
        return None
    return row


async def update_post(
    db: AsyncSession, business_id: str, post_id: str,
    content: str | None = None,
    platform_targets: list[str] | None = None,
    media_ids: list[str] | None = None,
) -> ContentPost | None:
    row = await get_post(db, business_id, post_id)
    if not row:
        return None
    if content is not None:
        row.content = content
    if platform_targets is not None:
        row.platform_targets = platform_targets
    if media_ids is not None:
        row.media_ids = [str(m) for m in media_ids]
    await db.commit()
    await db.refresh(row)
    return row


async def delete_post(db: AsyncSession, business_id: str, post_id: str) -> bool:
    row = await get_post(db, business_id, post_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def mark_posted(
    db: AsyncSession, business_id: str, post_id: str,
    employee_id: str | None = None,
    platform_results: dict | None = None,
) -> ContentPost | None:
    from datetime import datetime, timezone
    row = await get_post(db, business_id, post_id)
    if not row:
        return None
    row.status = "posted"
    row.posted_at = datetime.now(timezone.utc)
    if employee_id:
        row.posted_by = uuid.UUID(employee_id)
    if platform_results:
        row.platform_results = platform_results
    await db.commit()
    await db.refresh(row)
    return row
