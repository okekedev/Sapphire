"""Permission resolution — derives a user's effective permissions from their roles."""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.role import Role, BusinessMemberRole, ALL_PERMISSIONS
from app.core.models.business import BusinessMember


async def get_member_permissions(
    db: AsyncSession,
    user_id: UUID,
    business_id: UUID,
) -> set[str]:
    """Return the effective permission set for a user in a business.

    Looks up all roles assigned to the member and unions their permissions.
    A role with ["*"] grants all permissions.
    """
    result = await db.execute(
        select(Role.permissions)
        .join(BusinessMemberRole, BusinessMemberRole.role_id == Role.id)
        .join(BusinessMember, BusinessMember.id == BusinessMemberRole.member_id)
        .where(
            BusinessMember.user_id == user_id,
            BusinessMember.business_id == business_id,
        )
    )
    all_perms: set[str] = set()
    for (perms,) in result.all():
        if "*" in perms:
            return ALL_PERMISSIONS | {"*"}
        all_perms.update(perms)
    return all_perms


async def get_member_roles(
    db: AsyncSession,
    user_id: UUID,
    business_id: UUID,
) -> list[str]:
    """Return list of role names for a user in a business."""
    result = await db.execute(
        select(Role.name)
        .join(BusinessMemberRole, BusinessMemberRole.role_id == Role.id)
        .join(BusinessMember, BusinessMember.id == BusinessMemberRole.member_id)
        .where(
            BusinessMember.user_id == user_id,
            BusinessMember.business_id == business_id,
        )
    )
    return [row[0] for row in result.all()]


def can(permissions: set[str], fn: str) -> bool:
    """Check if a permission set includes a function."""
    return "*" in permissions or fn in permissions
