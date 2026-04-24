"""
Team management router — invite members, assign roles, remove members.

All endpoints require manage_team permission.

Endpoints:
  GET    /team/members              — list all members for a business
  GET    /team/roles                — list all available roles (system + custom)
  POST   /team/members              — invite a user by email + assign initial roles
  PATCH  /team/members/{member_id}/roles — replace a member's roles
  DELETE /team/members/{member_id}  — remove a member from the business
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.services.auth_service import get_current_user_id
from app.core.models.user import User
from app.core.models.business import Business, BusinessMember
from app.core.models.role import Role, BusinessMemberRole

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/team", tags=["Team"])


# ── Schemas ──

class RoleOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    permissions: list[str]
    is_system: bool

    model_config = {"from_attributes": True}


class MemberRoleOut(BaseModel):
    id: UUID
    name: str
    description: str | None

    model_config = {"from_attributes": True}


class MemberOut(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    full_name: str | None
    is_owner: bool
    roles: list[MemberRoleOut]

    model_config = {"from_attributes": True}


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role_names: list[str]  # e.g. ["sales_rep", "analyst"]


class UpdateRolesRequest(BaseModel):
    role_names: list[str]


# ── Helpers ──

async def _require_manage_team(user_id: UUID, business_id: UUID, db: AsyncSession) -> BusinessMember:
    """Ensure the calling user has manage_team permission."""
    from app.core.services.permission_service import get_member_permissions
    perms = await get_member_permissions(db, user_id, business_id)
    if "*" not in perms and "manage_team" not in perms:
        raise HTTPException(status_code=403, detail="manage_team permission required")
    member = await db.execute(
        select(BusinessMember).where(
            BusinessMember.user_id == user_id,
            BusinessMember.business_id == business_id,
        )
    )
    m = member.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=403, detail="Not a member of this business")
    return m


async def _resolve_roles(db: AsyncSession, business_id: UUID, role_names: list[str]) -> list[Role]:
    """Look up roles by name — system roles + business-specific roles."""
    result = await db.execute(
        select(Role).where(
            Role.name.in_(role_names),
            (Role.business_id == business_id) | Role.business_id.is_(None),
        )
    )
    found = result.scalars().all()
    found_names = {r.name for r in found}
    missing = set(role_names) - found_names
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown roles: {', '.join(missing)}")
    return list(found)


def _member_out(member: BusinessMember) -> MemberOut:
    roles = [
        MemberRoleOut(
            id=bmr.role.id,
            name=bmr.role.name,
            description=bmr.role.description,
        )
        for bmr in member.roles_assoc
        if bmr.role is not None
    ]
    return MemberOut(
        id=member.id,
        user_id=member.user_id,
        email=member.user.email,
        full_name=member.user.full_name,
        is_owner=member.is_owner,
        roles=roles,
    )


# ── Endpoints ──

@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Return all roles available in this business (system + custom)."""
    result = await db.execute(
        select(Role).where(
            Role.business_id.is_(None) | (Role.business_id == business_id)
        ).order_by(Role.is_system.desc(), Role.name)
    )
    return [RoleOut.model_validate(r) for r in result.scalars().all()]


@router.get("/members", response_model=list[MemberOut])
async def list_members(
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all members of a business with their roles.

    Requires being a member of the business. No elevated permission needed —
    team member names/roles are visible to all members (needed for lead assignment).
    """
    # Verify caller is a member of this business
    caller = await db.execute(
        select(BusinessMember).where(
            BusinessMember.user_id == current_user_id,
            BusinessMember.business_id == business_id,
        )
    )
    if not caller.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a member of this business")

    result = await db.execute(
        select(BusinessMember).where(BusinessMember.business_id == business_id)
    )
    members = result.scalars().all()
    return [_member_out(m) for m in members]


@router.post("/members", response_model=MemberOut, status_code=201)
async def invite_member(
    business_id: UUID = Query(...),
    body: InviteMemberRequest = ...,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Invite a user by email and assign initial roles.

    If the user doesn't have an account yet, a placeholder is created.
    They'll be fully provisioned on first login via Azure AD.
    """
    caller = await _require_manage_team(current_user_id, business_id, db)

    # Find or create user by email
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        user = User(email=body.email, password_hash="", full_name="")
        db.add(user)
        await db.flush()

    # Check not already a member
    existing = await db.execute(
        select(BusinessMember).where(
            BusinessMember.business_id == business_id,
            BusinessMember.user_id == user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already a member of this business")

    # Resolve roles
    roles = await _resolve_roles(db, business_id, body.role_names)

    # Create member
    member = BusinessMember(
        business_id=business_id,
        user_id=user.id,
        is_owner=False,
        invited_by=current_user_id,
    )
    db.add(member)
    await db.flush()

    # Assign roles
    for role in roles:
        db.add(BusinessMemberRole(
            member_id=member.id,
            role_id=role.id,
            assigned_by=current_user_id,
        ))
    await db.flush()
    await db.refresh(member)

    return _member_out(member)


@router.patch("/members/{member_id}/roles", response_model=MemberOut)
async def update_member_roles(
    member_id: UUID,
    body: UpdateRolesRequest,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Replace a member's roles entirely."""
    await _require_manage_team(current_user_id, business_id, db)

    result = await db.execute(
        select(BusinessMember).where(
            BusinessMember.id == member_id,
            BusinessMember.business_id == business_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Don't let someone remove their own global_admin role
    if member.user_id == current_user_id and "global_admin" not in body.role_names:
        caller_roles = [bmr.role.name for bmr in member.roles_assoc if bmr.role]
        if "global_admin" in caller_roles:
            raise HTTPException(
                status_code=400,
                detail="Cannot remove your own global_admin role",
            )

    new_roles = await _resolve_roles(db, business_id, body.role_names)
    new_role_ids = {r.id for r in new_roles}

    # Remove roles not in new set
    for bmr in list(member.roles_assoc):
        if bmr.role_id not in new_role_ids:
            await db.delete(bmr)

    # Add new roles
    existing_role_ids = {bmr.role_id for bmr in member.roles_assoc}
    for role in new_roles:
        if role.id not in existing_role_ids:
            db.add(BusinessMemberRole(
                member_id=member.id,
                role_id=role.id,
                assigned_by=current_user_id,
            ))

    await db.flush()
    await db.refresh(member)
    return _member_out(member)


@router.delete("/members/{member_id}", status_code=204)
async def remove_member(
    member_id: UUID,
    business_id: UUID = Query(...),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from the business."""
    await _require_manage_team(current_user_id, business_id, db)

    result = await db.execute(
        select(BusinessMember).where(
            BusinessMember.id == member_id,
            BusinessMember.business_id == business_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    if member.user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    if member.is_owner:
        raise HTTPException(status_code=400, detail="Cannot remove the business owner")

    await db.delete(member)
