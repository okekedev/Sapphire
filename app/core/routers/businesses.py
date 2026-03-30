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
from app.core.services.anthropic_service import claude_cli, ClaudeCliError, ClaudeCliNotReady, ClaudeCliTokenExpired

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


# ── Profile field names (predefined columns) ──

PROFILE_FIELDS = [
    "description",
    "services",
    "target_audience",
    "online_presence",
    "brand_voice",
    "goals",
    "competitive_landscape",
]


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
    return CompanyProfileOut(
        description=business.description,
        services=business.services,
        target_audience=business.target_audience,
        online_presence=business.online_presence,
        brand_voice=business.brand_voice,
        goals=business.goals,
        competitive_landscape=business.competitive_landscape,
        profile_source=business.profile_source,
    )


@router.put("/{business_id}/company-profile", response_model=CompanyProfileOut)
async def save_company_profile(
    business_id: UUID,
    body: CompanyProfileInput,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Save the company profile to dedicated columns."""
    business = await _get_business_for_user(business_id, user_id, db, require_admin=True)

    profile_data = body.model_dump(exclude_none=True)
    source = profile_data.pop("source", "manual_edit")

    for field in PROFILE_FIELDS:
        if field in profile_data:
            setattr(business, field, profile_data[field])

    business.profile_source = source
    await db.flush()

    return CompanyProfileOut(
        description=business.description,
        services=business.services,
        target_audience=business.target_audience,
        online_presence=business.online_presence,
        brand_voice=business.brand_voice,
        goals=business.goals,
        competitive_landscape=business.competitive_landscape,
        profile_source=business.profile_source,
    )


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


class OnboardingResponse(BaseModel):
    response: str
    employee_name: str = "Assistant"
    employee_title: str = ""
    profile_updated: bool = False
    onboarding_complete: bool = False
    auth_error: bool = False
    auth_error_type: Optional[str] = None  # "token_expired" | "not_connected"


async def _get_onboarding_employee(db: AsyncSession):
    """Look up the Marketing department head to run onboarding.

    Falls back to any is_head employee if Marketing has none,
    then to any employee at all.
    """
    from app.core.models.organization import Department, Employee

    # Try marketing head first
    stmt = (
        select(Employee)
        .join(Department, Employee.department_id == Department.id)
        .where(
            Department.name == "Marketing",
            Department.business_id.is_(None),
            Employee.business_id.is_(None),
            Employee.is_head.is_(True),
            Employee.status == "active",
        )
    )
    result = await db.execute(stmt)
    emp = result.scalar_one_or_none()
    if emp:
        return emp

    # Fallback: any department head
    stmt = (
        select(Employee)
        .where(
            Employee.business_id.is_(None),
            Employee.is_head.is_(True),
            Employee.status == "active",
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _parse_profile_sections(profile_md: str) -> dict[str, str]:
    """Parse a markdown profile block into field → content mapping.

    Maps ## headings to column names:
      About → description
      Services & Products → services
      Target Audience → target_audience
      Online Presence → online_presence
      Brand Voice & Tone → brand_voice
      Goals & Priorities → goals
      Competitive Landscape → competitive_landscape
    """
    HEADING_MAP = {
        "about": "description",
        "description": "description",
        "services": "services",
        "services & products": "services",
        "services and products": "services",
        "target audience": "target_audience",
        "online presence": "online_presence",
        "brand voice": "brand_voice",
        "brand voice & tone": "brand_voice",
        "brand voice and tone": "brand_voice",
        "goals": "goals",
        "goals & priorities": "goals",
        "goals and priorities": "goals",
        "competitive landscape": "competitive_landscape",
        "competitors": "competitive_landscape",
    }

    result: dict[str, str] = {}
    lines = profile_md.split("\n")
    current_field: str | None = None
    current_lines: list[str] = []

    for line in lines:
        h2_match = re.match(r"^##\s+(.+)", line)
        if h2_match:
            # Save previous section
            if current_field and current_lines:
                result[current_field] = "\n".join(current_lines).strip()
            # Map heading to field name
            heading = h2_match.group(1).strip().lower()
            current_field = HEADING_MAP.get(heading)
            current_lines = []
        elif current_field is not None:
            current_lines.append(line)

    # Save last section
    if current_field and current_lines:
        result[current_field] = "\n".join(current_lines).strip()

    return result


@router.post("/{business_id}/onboard", response_model=OnboardingResponse)
async def onboard_business(
    business_id: UUID,
    payload: OnboardingRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Onboarding conversation — dynamically uses the Marketing department head.

    The employee conducts a discovery interview to build the business profile.
    When ready, outputs a markdown profile block between
    ```markdown:profile markers. The backend detects this, parses sections,
    and saves each section to its dedicated column on the businesses table.
    """
    await _get_business_for_user(business_id, user_id, db)

    # Look up the onboarding employee dynamically
    employee = await _get_onboarding_employee(db)
    if not employee:
        raise HTTPException(
            status_code=500,
            detail="No onboarding employee found. Seed your Marketing department first.",
        )

    emp_name = employee.name
    emp_title = employee.title or ""

    # Build the onboarding-specific instruction
    onboarding_instruction = (
        f"You are {emp_name}, {emp_title}, onboarding a new business.\n\n"
        "## Your Mission\n"
        "Build a comprehensive company profile by researching the business online. "
        "The user has given you seed information (company name, city, industry, socials). "
        "Use web search to find their website, social media, recent news, reviews, "
        "and anything else that helps you understand their business deeply.\n\n"
        "## Process\n"
        "1. **Research first**: When you get the seed info, search the web extensively. "
        "Look up their website, LinkedIn, social media, Google Business profile, "
        "review sites, press mentions, etc.\n"
        "2. **Confirm**: Present what you found and ask 'Is this your business?' "
        "Show the website URL, a brief description, and key details you discovered.\n"
        "3. **Ask follow-up questions**: After confirmation, ask about anything you "
        "couldn't find online — target audience, brand voice preferences, current goals.\n"
        "4. **Build the profile**: When you have enough info, compile everything into "
        "a profile block.\n\n"
        "## Output Format\n"
        "When ready, output the profile between ```markdown:profile``` markers.\n"
        "IMPORTANT: Use EXACTLY these section headings — they map to database columns:\n\n"
        "```markdown:profile\n"
        "# Company Profile — [Business Name]\n\n"
        "## About\n[Description based on research + user input]\n\n"
        "## Services & Products\n[What they offer]\n\n"
        "## Target Audience\n[Who they serve]\n\n"
        "## Online Presence\n- Website: [URL]\n- [Social platforms found]\n\n"
        "## Brand Voice & Tone\n[Based on their content + user preference]\n\n"
        "## Goals & Priorities\n[Current objectives]\n\n"
        "## Competitive Landscape\n[Key competitors found]\n"
        "```\n\n"
        "## Style\n"
        "Be conversational, efficient, and impressive. Show the user you've done "
        "your homework. Keep responses concise — no walls of text."
    )

    # Build conversation history for context
    conversation_parts = [onboarding_instruction]

    # Include seed info if this is the first message
    if payload.seed_info:
        seed = payload.seed_info
        seed_parts = []
        if seed.company_name:
            seed_parts.append(f"Company name: {seed.company_name}")
        if seed.phone:
            seed_parts.append(f"Phone: {seed.phone}")
        if seed.city:
            seed_parts.append(f"City: {seed.city}")
        if seed.industry:
            seed_parts.append(f"Industry: {seed.industry}")
        if seed.website:
            seed_parts.append(f"Website: {seed.website}")
        if seed.socials:
            seed_parts.append(f"Social media: {seed.socials}")
        if seed_parts:
            conversation_parts.append(
                "## Seed Information from User\n" + "\n".join(seed_parts)
            )

    for msg in payload.conversation[-20:]:
        role_label = "User" if msg.role == "user" else emp_name
        conversation_parts.append(f"{role_label}: {msg.content}")
    conversation_parts.append(f"User: {payload.user_message}")

    full_message = "\n\n".join(conversation_parts)

    try:
        assistant_response = await claude_cli.call_assistant(
            business_id=business_id,
            file_stem=employee.file_stem,
            message=full_message,
            db=db,
            allowed_tools=["WebSearch", "WebFetch"],
        )
    except ClaudeCliError as e:
        logger.error(f"Onboarding failed for business {business_id}: {e}")
        return OnboardingResponse(
            response="I'm having trouble connecting right now. Please try again.",
            employee_name=emp_name,
            employee_title=emp_title,
        )

    # Detect if the employee output a profile block
    profile_match = re.search(
        r"```markdown:profile\s*\n(.*?)\n```",
        assistant_response,
        re.DOTALL,
    )

    profile_updated = False
    onboarding_complete = False

    if profile_match:
        profile_md = profile_match.group(1).strip()

        # Parse markdown sections into column values
        fields = _parse_profile_sections(profile_md)

        # Save to dedicated columns
        business = await _get_business_for_user(business_id, user_id, db)
        for field_name in PROFILE_FIELDS:
            if field_name in fields:
                setattr(business, field_name, fields[field_name])
        business.profile_source = "onboarding"

        # Seed the industry field if we have seed info
        if payload.seed_info and payload.seed_info.industry and not business.industry:
            business.industry = payload.seed_info.industry
        await db.flush()

        profile_updated = True
        onboarding_complete = True
        logger.info(f"Onboarding complete: profile saved to columns for business {business_id}")

    return OnboardingResponse(
        response=assistant_response,
        employee_name=emp_name,
        employee_title=emp_title,
        profile_updated=profile_updated,
        onboarding_complete=onboarding_complete,
    )
