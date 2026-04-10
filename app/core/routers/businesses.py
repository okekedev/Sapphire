"""
Business management routes — CRUD + profile management.

Handles:
  - Business CRUD (database)
  - Company profile read/write (stored in dedicated columns on businesses table)
  - Connected accounts listing
  - Onboarding (Marketing head interview → company profile creation)
  - Team member management
"""

import logging
import re
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.models.business import Business, BusinessMember
from app.core.models.connected_account import ConnectedAccount
from app.core.models.user import User
from app.core.schemas.business import (
    BusinessCreate, BusinessOut, BusinessUpdate,
    CompanyProfileInput, CompanyProfileOut,
)
from app.core.services.auth_service import get_current_user_id

router = APIRouter(prefix="/businesses")


# ── Helpers ──


async def _get_business_for_user(
    business_id: UUID, user_id: UUID, db: AsyncSession, require_admin: bool = False
) -> Business:
    """Get a business the user is a member of."""
    stmt = (
        select(Business)
        .join(BusinessMember, BusinessMember.business_id == Business.id)
        .where(Business.id == business_id, BusinessMember.user_id == user_id)
    )
    if require_admin:
        stmt = stmt.where(BusinessMember.is_owner == True)  # noqa: E712

    result = await db.execute(stmt)
    business = result.scalar_one_or_none()
    if not business:
        detail = "Business not found or insufficient permissions" if require_admin else "Business not found"
        raise HTTPException(status_code=404, detail=detail)
    return business



# ── CRUD ──


@router.post("", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
async def create_business(
    body: BusinessCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a new business. Each user account is limited to one business."""
    # Enforce single business per account
    existing = await db.execute(
        select(Business)
        .join(BusinessMember, BusinessMember.business_id == Business.id)
        .where(BusinessMember.user_id == user_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a business. Only one business per account is allowed.",
        )

    business = Business(
        name=body.name,
        website=body.website,
        industry=body.industry,
        created_by=user_id,
    )
    db.add(business)
    await db.flush()

    # Creator becomes the owner
    member = BusinessMember(
        business_id=business.id,
        user_id=user_id,
        is_owner=True,
    )
    db.add(member)
    await db.flush()

    return business


@router.get("", response_model=list[BusinessOut])
async def list_businesses(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all businesses the current user is a member of."""
    result = await db.execute(
        select(Business)
        .join(BusinessMember, BusinessMember.business_id == Business.id)
        .where(BusinessMember.user_id == user_id)
    )
    return result.scalars().all()


@router.get("/{business_id}", response_model=BusinessOut)
async def get_business(
    business_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific business (must be a member)."""
    return await _get_business_for_user(business_id, user_id, db)


@router.patch("/{business_id}", response_model=BusinessOut)
async def update_business(
    business_id: UUID,
    body: BusinessUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update business details (owner/admin only)."""
    business = await _get_business_for_user(business_id, user_id, db, require_admin=True)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(business, field, value)

    await db.flush()
    return business


# ── Company Profile (predefined columns) ──


@router.get("/{business_id}/company-profile", response_model=CompanyProfileOut)
async def get_company_profile(
    business_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the structured company profile from dedicated columns."""
    business = await _get_business_for_user(business_id, user_id, db)
    return CompanyProfileOut(narrative=business.narrative)


@router.put("/{business_id}/company-profile", response_model=CompanyProfileOut)
async def save_company_profile(
    business_id: UUID,
    body: CompanyProfileInput,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Save the business narrative."""
    business = await _get_business_for_user(business_id, user_id, db, require_admin=True)
    if body.narrative is not None:
        business.narrative = body.narrative
    await db.flush()
    return CompanyProfileOut(narrative=business.narrative)


# ── Connected Accounts ──


@router.get("/{business_id}/accounts")
async def list_connected_accounts(
    business_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all connected platform accounts for a business."""
    await _get_business_for_user(business_id, user_id, db)

    result = await db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.business_id == business_id,
            ConnectedAccount.status == "active",
        )
    )
    accounts = result.scalars().all()

    return {
        "accounts": [
            {
                "id": str(a.id),
                "platform": a.platform,
                "status": a.status,
                "connected_at": a.connected_at.isoformat(),
            }
            for a in accounts
        ],
        "total": len(accounts),
    }


# ── Team Members ──


class MemberOut(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    full_name: str
    is_owner: bool
    allowed_tabs: list[str] | None  # None = all tabs (owner / legacy)
    joined_at: str


class MyMembershipOut(BaseModel):
    id: UUID
    is_owner: bool
    allowed_tabs: list[str] | None  # None = all tabs


class InviteMemberRequest(BaseModel):
    email: str = Field(..., max_length=255)
    # allowed_tabs: which tab paths this member can see.
    # Pass null / omit to grant access to all tabs.
    allowed_tabs: list[str] | None = None


class UpdateMemberTabsRequest(BaseModel):
    allowed_tabs: list[str] | None = None


@router.get("/{business_id}/members", response_model=list[MemberOut])
async def list_members(
    business_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all team members for a business."""
    await _get_business_for_user(business_id, user_id, db)

    result = await db.execute(
        select(BusinessMember, User)
        .join(User, User.id == BusinessMember.user_id)
        .where(BusinessMember.business_id == business_id)
        .order_by(BusinessMember.joined_at.asc())
    )
    rows = result.all()
    return [
        MemberOut(
            id=member.id,
            user_id=member.user_id,
            email=user.email,
            full_name=user.full_name,
            is_owner=member.is_owner,
            allowed_tabs=None if member.is_owner else member.allowed_tabs,
            joined_at=member.joined_at.isoformat(),
        )
        for member, user in rows
    ]


@router.get("/{business_id}/my-membership", response_model=MyMembershipOut)
async def get_my_membership(
    business_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's membership record for a business (is_owner + allowed_tabs)."""
    result = await db.execute(
        select(BusinessMember).where(
            BusinessMember.business_id == business_id,
            BusinessMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Not a member of this business")
    return MyMembershipOut(
        id=member.id,
        is_owner=member.is_owner,
        # Owners always see all tabs regardless of allowed_tabs field
        allowed_tabs=None if member.is_owner else member.allowed_tabs,
    )


@router.post("/{business_id}/members", status_code=201)
async def invite_member(
    business_id: UUID,
    payload: InviteMemberRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Invite a user to the business by email (owner/admin only)."""
    await _get_business_for_user(business_id, user_id, db, require_admin=True)

    # Find the user by email
    result = await db.execute(select(User).where(User.email == payload.email))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="No user found with that email")

    # Check if already a member
    existing = await db.execute(
        select(BusinessMember).where(
            BusinessMember.business_id == business_id,
            BusinessMember.user_id == target_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already a member")

    member = BusinessMember(
        business_id=business_id,
        user_id=target_user.id,
        is_owner=False,
        allowed_tabs=payload.allowed_tabs,
        invited_by=user_id,
    )
    db.add(member)
    tab_summary = f"{len(payload.allowed_tabs)} tabs" if payload.allowed_tabs else "all tabs"
    return {"message": f"Invited {payload.email} with access to {tab_summary}"}


@router.patch("/{business_id}/members/{member_id}")
async def update_member_tabs(
    business_id: UUID,
    member_id: UUID,
    payload: UpdateMemberTabsRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update which tabs a team member can access (owner/admin only)."""
    await _get_business_for_user(business_id, user_id, db, require_admin=True)

    result = await db.execute(
        select(BusinessMember).where(
            BusinessMember.id == member_id,
            BusinessMember.business_id == business_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.is_owner:
        raise HTTPException(status_code=403, detail="Cannot change the owner's tab access")

    member.allowed_tabs = payload.allowed_tabs
    tab_summary = f"{len(payload.allowed_tabs)} tabs" if payload.allowed_tabs else "all tabs"
    return {"message": f"Tab access updated to {tab_summary}"}


@router.delete("/{business_id}/members/{member_id}", status_code=204)
async def remove_member(
    business_id: UUID,
    member_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Remove a team member (owner/admin only). Cannot remove the owner."""
    await _get_business_for_user(business_id, user_id, db, require_admin=True)

    result = await db.execute(
        select(BusinessMember).where(
            BusinessMember.id == member_id,
            BusinessMember.business_id == business_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.is_owner:
        raise HTTPException(status_code=403, detail="Cannot remove the owner")

    await db.delete(member)


# ── Onboarding (dynamic — uses Marketing dept head) ──


logger = logging.getLogger(__name__)


class OnboardingMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class SeedInfo(BaseModel):
    """Initial seed info the user provides to kick off onboarding."""
    company_name: str = ""
    phone: str = ""
    city: str = ""
    industry: str = ""
    website: str = ""
    socials: str = ""  # comma-separated handles or URLs


class OnboardingRequest(BaseModel):
    """Send a message to the onboarding employee."""
    user_message: str = Field(..., min_length=1, max_length=5000)
    conversation: list[OnboardingMessage] = Field(
        default_factory=list,
        description="Previous onboarding conversation history",
    )
    seed_info: Optional[SeedInfo] = None
    thread_id: Optional[str] = None


class OnboardingResponse(BaseModel):
    response: str
    employee_name: str = "Assistant"
    employee_title: str = ""
    profile_updated: bool = False
    onboarding_complete: bool = False
    auth_error: bool = False
    auth_error_type: Optional[str] = None  # "token_expired" | "not_connected"





@router.post("/{business_id}/onboard", response_model=OnboardingResponse)
async def onboard_business(
    business_id: UUID,
    payload: OnboardingRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Onboarding conversation — uses the James Foundry agent.

    James conducts a discovery interview to build the business profile.
    When ready, outputs a markdown profile block between
    ```markdown:profile markers. The backend detects this, parses sections,
    and saves each section to its dedicated column on the businesses table.
    """
    business = await _get_business_for_user(business_id, user_id, db)

    from app.core.services.foundry_service import foundry_service, FoundryServiceError
    from app.core.services.openai_service import build_profile_context

    profile_ctx = build_profile_context(business)
    business_context = (
        f"Business: {business.name}\n\n{profile_ctx}"
        if profile_ctx
        else f"Business: {business.name}"
    )

    # Build conversation history as a single user message
    history_parts = []
    for msg in payload.conversation[-20:]:
        role_label = "User" if msg.role == "user" else "James"
        history_parts.append(f"{role_label}: {msg.content}")
    history_parts.append(f"User: {payload.user_message}")
    user_message = "\n\n".join(history_parts)

    try:
        content, thread_id = await foundry_service.chat(
            agent_name="james",
            message=user_message,
            business_context=business_context,
            thread_id=payload.thread_id,
            business_id=str(business_id),
        )
    except FoundryServiceError as e:
        logger.error(f"Profile chat failed for business {business_id}: {e}")
        return OnboardingResponse(
            response="I'm having trouble connecting right now. Please try again.",
            employee_name="James",
            employee_title="Assistant",
        )

    # Detect profile block
    profile_match = re.search(
        r"```markdown:profile\s*\n(.*?)\n```",
        content,
        re.DOTALL,
    )
    profile_updated = False
    onboarding_complete = False

    if profile_match:
        narrative = profile_match.group(1).strip()
        business.narrative = narrative
        if payload.seed_info and payload.seed_info.industry and not business.industry:
            business.industry = payload.seed_info.industry
        await db.flush()
        profile_updated = True
        onboarding_complete = True
        logger.info(f"Onboarding complete: narrative saved for business {business_id}")

    return OnboardingResponse(
        response=content,
        employee_name="James",
        employee_title="Assistant",
        profile_updated=profile_updated,
        onboarding_complete=onboarding_complete,
    )
