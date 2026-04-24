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
from app.core.models.organization import Department, Employee
from app.core.models.user import User
from app.core.schemas.business import (
    BusinessCreate, BusinessOut, BusinessUpdate,
    CompanyProfileInput, CompanyProfileOut,
)
from app.core.services.auth_service import get_current_user_id

router = APIRouter(prefix="/businesses")


# ── Helpers ──


async def _seed_workspace(db: AsyncSession, business_id: UUID) -> None:
    """Copy template departments + employees into a new business workspace.

    Template rows have business_id=NULL. This function:
      1. Copies all template departments to the new business.
      2. Copies all template employees, remapping department_id and reports_to.
    """
    # 1. Load template departments
    dept_result = await db.execute(
        select(Department).where(Department.business_id.is_(None))
        .order_by(Department.display_order, Department.name)
    )
    template_depts = dept_result.scalars().all()

    # 2. Create business-scoped departments, track old→new ID mapping
    dept_id_map: dict[UUID, UUID] = {}
    for tmpl in template_depts:
        new_dept = Department(
            business_id=business_id,
            name=tmpl.name,
            description=tmpl.description,
            documentation=tmpl.documentation,
            icon=tmpl.icon,
            display_order=tmpl.display_order,
        )
        db.add(new_dept)
        await db.flush()
        dept_id_map[tmpl.id] = new_dept.id

    # 3. Load template employees
    emp_result = await db.execute(
        select(Employee).where(Employee.business_id.is_(None))
        .order_by(Employee.name)
    )
    template_emps = emp_result.scalars().all()

    # 4. Create new employees (reports_to=None first — set after all IDs are known)
    emp_id_map: dict[UUID, UUID] = {}
    pending_reports: list[tuple[Employee, UUID]] = []  # (new_emp, template_reports_to_id)

    for tmpl in template_emps:
        new_dept_id = dept_id_map.get(tmpl.department_id)
        if not new_dept_id:
            continue
        new_emp = Employee(
            business_id=business_id,
            department_id=new_dept_id,
            name=tmpl.name,
            title=tmpl.title,
            file_stem=tmpl.file_stem,
            model_tier=tmpl.model_tier,
            system_prompt=tmpl.system_prompt,
            reports_to=None,
            status=tmpl.status,
            capabilities=tmpl.capabilities,
            job_skills=tmpl.job_skills,
            is_head=tmpl.is_head,
        )
        db.add(new_emp)
        await db.flush()
        emp_id_map[tmpl.id] = new_emp.id
        if tmpl.reports_to:
            pending_reports.append((new_emp, tmpl.reports_to))

    # 5. Patch reports_to using the completed mapping
    for new_emp, template_reports_to in pending_reports:
        mapped = emp_id_map.get(template_reports_to)
        if mapped:
            new_emp.reports_to = mapped

    await db.flush()


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
    """Create a new client workspace. Agency admins can create many."""
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

    # Seed departments + employees from templates
    await _seed_workspace(db, business.id)

    # Grant all other existing platform users access to this new client workspace.
    # Roles are assigned separately via the team management API (POST /team/members).
    existing_members = await db.execute(
        select(BusinessMember.user_id)
        .where(BusinessMember.user_id != user_id)
        .distinct()
    )
    seen_users: set[UUID] = set()
    for (uid,) in existing_members.all():
        if uid in seen_users:
            continue
        seen_users.add(uid)
        db.add(BusinessMember(
            business_id=business.id,
            user_id=uid,
            is_owner=False,
            invited_by=user_id,
        ))
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


class ConnectedAccountItem(BaseModel):
    id: str
    platform: str
    status: str
    connected_at: str


class ConnectedAccountListOut(BaseModel):
    accounts: list[ConnectedAccountItem]
    total: int


class MessageOut(BaseModel):
    message: str


@router.get("/{business_id}/accounts", response_model=ConnectedAccountListOut)
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


# Team member management is handled by the dedicated team router (POST /team/*)
# which uses the RBAC roles system. See app/core/routers/team.py.


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
