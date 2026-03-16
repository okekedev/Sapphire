"""Pydantic schemas for organization (departments + employees)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Department ──

class DepartmentCreate(BaseModel):
    business_id: UUID | None = None
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    icon: str | None = None
    display_order: int = 0


class DepartmentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    display_order: int | None = None
    forward_number: str | None = None
    enabled: bool | None = None


class DepartmentOut(BaseModel):
    id: UUID
    business_id: UUID | None = None
    name: str
    description: str | None
    icon: str | None
    display_order: int
    forward_number: str | None = None
    enabled: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


class DepartmentWithEmployees(DepartmentOut):
    employees: list["EmployeeOut"] = Field(default_factory=list)


# ── Employee ──

class EmployeeCreate(BaseModel):
    business_id: UUID | None = None
    department_id: UUID
    name: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    file_stem: str = Field(..., min_length=1, max_length=200)
    model_tier: str = Field("haiku", pattern="^(opus|sonnet|haiku)$")
    system_prompt: str = Field(..., min_length=10)
    reports_to: UUID | None = None
    capabilities: dict | None = None
    is_head: bool = False
    job_skills: str | None = None


class EmployeeUpdate(BaseModel):
    department_id: UUID | None = None
    name: str | None = None
    title: str | None = None
    model_tier: str | None = Field(None, pattern="^(opus|sonnet|haiku)$")
    system_prompt: str | None = None
    reports_to: UUID | None = None
    status: str | None = Field(None, pattern="^(active|inactive)$")
    capabilities: dict | None = None
    is_head: bool | None = None
    job_skills: str | None = None


class EmployeeOut(BaseModel):
    id: UUID
    business_id: UUID | None = None
    department_id: UUID
    name: str
    title: str
    file_stem: str
    model_tier: str
    reports_to: UUID | None
    status: str
    capabilities: dict | None
    is_head: bool
    job_skills: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmployeeDetail(EmployeeOut):
    system_prompt: str
    department_name: str | None = None
    supervisor_name: str | None = None


# ── Org Chart ──

class OrgChartNode(BaseModel):
    id: UUID
    name: str
    title: str
    department: str
    model_tier: str
    is_head: bool
    status: str
    job_skills: str | None = None
    children: list["OrgChartNode"] = Field(default_factory=list)


# Forward refs
DepartmentWithEmployees.model_rebuild()
OrgChartNode.model_rebuild()
