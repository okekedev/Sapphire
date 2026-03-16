"""
Organization Router — CRUD for departments and employees.

Manages the AI workforce: departments, employees, hierarchy,
model tiers, and system prompts. Changes are reflected both
in the database and on the filesystem (.md files for CLI compat).
"""

import logging
import re
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.core.models.organization import Department, Employee
from app.core.schemas.organization import (
    DepartmentCreate, DepartmentUpdate, DepartmentOut, DepartmentWithEmployees,
    EmployeeCreate, EmployeeUpdate, EmployeeOut, EmployeeDetail,
    OrgChartNode,
)
from app.core.services.auth_service import get_current_user_id
from app.core.services.claude_cli_service import claude_cli

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organization", tags=["Organization"])


# ── Departments ──


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(
    business_id: UUID | None = Query(None),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List departments. Always reads base rows (business_id IS NULL)."""
    stmt = (
        select(Department)
        .where(Department.business_id.is_(None))
        .order_by(Department.display_order, Department.name)
    )
    result = await db.execute(stmt)
    return [DepartmentOut.model_validate(d) for d in result.scalars().all()]


@router.post("/departments", response_model=DepartmentOut, status_code=201)
async def create_department(
    payload: DepartmentCreate,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a new department."""
    # Check for duplicate name within business scope
    dup_stmt = select(Department).where(func.lower(Department.name) == payload.name.lower())
    if payload.business_id:
        dup_stmt = dup_stmt.where(Department.business_id == payload.business_id)
    else:
        dup_stmt = dup_stmt.where(Department.business_id.is_(None))
    existing = await db.execute(dup_stmt)
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Department with this name already exists")

    dept = Department(
        business_id=payload.business_id,
        name=payload.name,
        description=payload.description,
        icon=payload.icon,
        display_order=payload.display_order,
    )
    db.add(dept)
    await db.flush()
    return DepartmentOut.model_validate(dept)


@router.patch("/departments/{dept_id}", response_model=DepartmentOut)
async def update_department(
    dept_id: UUID,
    payload: DepartmentUpdate,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update a department."""
    dept = await db.get(Department, dept_id)
    if not dept:
        raise HTTPException(404, "Department not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(dept, key, value)

    await db.flush()
    return DepartmentOut.model_validate(dept)


@router.delete("/departments/{dept_id}")
async def delete_department(
    dept_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a department (cascades to employees)."""
    dept = await db.get(Department, dept_id)
    if not dept:
        raise HTTPException(404, "Department not found")

    # Check for employees
    emp_count = await db.execute(
        select(func.count()).select_from(Employee).where(Employee.department_id == dept_id)
    )
    count = emp_count.scalar()
    if count > 0:
        raise HTTPException(
            400,
            f"Cannot delete department with {count} employees. "
            f"Move or deactivate them first."
        )

    await db.delete(dept)
    return {"message": f"Department '{dept.name}' deleted"}


# ── Employees ──


@router.get("/employees", response_model=list[EmployeeOut])
async def list_employees(
    business_id: UUID | None = Query(None),
    department_id: UUID | None = Query(None),
    status: str | None = Query(None, pattern="^(active|inactive)$"),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List employees. Always reads base rows (business_id IS NULL)."""
    stmt = select(Employee).where(Employee.business_id.is_(None)).order_by(Employee.name)
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    if status:
        stmt = stmt.where(Employee.status == status)
    result = await db.execute(stmt)
    return [EmployeeOut.model_validate(e) for e in result.scalars().all()]


@router.get("/employees/{emp_id}", response_model=EmployeeDetail)
async def get_employee(
    emp_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get full employee details including system prompt."""
    emp = await db.get(Employee, emp_id)
    if not emp:
        raise HTTPException(404, "Employee not found")

    # Get department name and supervisor name
    dept = await db.get(Department, emp.department_id)
    supervisor_name = None
    if emp.reports_to:
        supervisor = await db.get(Employee, emp.reports_to)
        if supervisor:
            supervisor_name = supervisor.name

    return EmployeeDetail(
        **EmployeeOut.model_validate(emp).model_dump(),
        system_prompt=emp.system_prompt,
        department_name=dept.name if dept else None,
        supervisor_name=supervisor_name,
    )


@router.post("/employees", response_model=EmployeeOut, status_code=201)
async def create_employee(
    payload: EmployeeCreate,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a new employee and write their .md file."""
    # Verify department exists
    dept = await db.get(Department, payload.department_id)
    if not dept:
        raise HTTPException(404, "Department not found")

    # Check for duplicate file_stem within business scope
    dup_stmt = select(Employee).where(Employee.file_stem == payload.file_stem)
    if payload.business_id:
        dup_stmt = dup_stmt.where(Employee.business_id == payload.business_id)
    else:
        dup_stmt = dup_stmt.where(Employee.business_id.is_(None))
    existing = await db.execute(dup_stmt)
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Employee with file_stem '{payload.file_stem}' already exists")

    # Validate reports_to if provided
    if payload.reports_to:
        supervisor = await db.get(Employee, payload.reports_to)
        if not supervisor:
            raise HTTPException(400, "Supervisor (reports_to) not found")

    emp = Employee(
        business_id=payload.business_id,
        department_id=payload.department_id,
        name=payload.name,
        title=payload.title,
        file_stem=payload.file_stem,
        model_tier=payload.model_tier,
        system_prompt=payload.system_prompt,
        reports_to=payload.reports_to,
        capabilities=payload.capabilities,
        is_head=payload.is_head,
    )
    db.add(emp)
    await db.flush()

    # Write .md file for CLI compatibility
    try:
        claude_cli.write_employee_file(
            department=dept.name,
            file_stem=payload.file_stem,
            content=payload.system_prompt,
        )
    except Exception as e:
        logger.warning(f"Failed to write .md file for {payload.file_stem}: {e}")

    return EmployeeOut.model_validate(emp)


@router.patch("/employees/{emp_id}", response_model=EmployeeOut)
async def update_employee(
    emp_id: UUID,
    payload: EmployeeUpdate,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update an employee. Regenerates .md file if system_prompt or model_tier changes."""
    emp = await db.get(Employee, emp_id)
    if not emp:
        raise HTTPException(404, "Employee not found")

    update_data = payload.model_dump(exclude_unset=True)

    # Validate department if changing
    if "department_id" in update_data:
        dept = await db.get(Department, update_data["department_id"])
        if not dept:
            raise HTTPException(400, "Target department not found")

    # Validate supervisor if changing
    if "reports_to" in update_data and update_data["reports_to"]:
        supervisor = await db.get(Employee, update_data["reports_to"])
        if not supervisor:
            raise HTTPException(400, "Supervisor (reports_to) not found")
        if supervisor.id == emp_id:
            raise HTTPException(400, "Employee cannot report to themselves")

    for key, value in update_data.items():
        setattr(emp, key, value)

    await db.flush()

    # Regenerate .md file if prompt or model changed
    if "system_prompt" in update_data or "model_tier" in update_data:
        try:
            dept = await db.get(Department, emp.department_id)
            claude_cli.write_employee_file(
                department=dept.name if dept else "unknown",
                file_stem=emp.file_stem,
                content=emp.system_prompt,
            )
        except Exception as e:
            logger.warning(f"Failed to update .md file for {emp.file_stem}: {e}")

    return EmployeeOut.model_validate(emp)


@router.delete("/employees/{emp_id}")
async def deactivate_employee(
    emp_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete an employee (set status=inactive)."""
    emp = await db.get(Employee, emp_id)
    if not emp:
        raise HTTPException(404, "Employee not found")

    emp.status = "inactive"
    return {"message": f"Employee '{emp.name}' deactivated"}


# ── Org Chart ──


@router.get("/org-chart", response_model=list[OrgChartNode])
async def get_org_chart(
    business_id: UUID | None = Query(None),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the full org chart as a tree structure.
    Returns top-level employees (those with no supervisor or whose
    supervisor is the owner) as roots, with children nested.
    """
    # Load all active base employees with their departments
    stmt = (
        select(Employee, Department.name.label("dept_name"))
        .join(Department, Employee.department_id == Department.id)
        .where(Employee.status == "active")
        .where(Employee.business_id.is_(None))
        .order_by(Employee.name)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Build lookup maps
    employees_by_id = {}
    children_map: dict[UUID | None, list] = {None: []}

    for emp, dept_name in rows:
        node = OrgChartNode(
            id=emp.id,
            name=emp.name,
            title=emp.title,
            department=dept_name,
            model_tier=emp.model_tier,
            is_head=emp.is_head,
            status=emp.status,
            job_skills=emp.job_skills,
            children=[],
        )
        employees_by_id[emp.id] = node

        parent_id = emp.reports_to
        if parent_id not in children_map:
            children_map[parent_id] = []
        children_map[parent_id].append(node)

    # Build tree by assigning children
    for emp_id, node in employees_by_id.items():
        if emp_id in children_map:
            node.children = children_map[emp_id]

    # Return root nodes (those with no supervisor, or supervisor not in set)
    roots = children_map.get(None, [])

    # Also include employees whose supervisor isn't in the active set
    for emp_id, node in employees_by_id.items():
        parent_key = None
        for emp, dept_name in rows:
            if emp.id == emp_id:
                parent_key = emp.reports_to
                break
        if parent_key and parent_key not in employees_by_id and node not in roots:
            roots.append(node)

    return roots


# ── Hot Reload ──


def _parse_md_metadata(content: str) -> dict:
    """Parse name, title, model from the first ~30 lines of an employee .md file."""
    meta = {"name": "", "title": "", "model": "haiku"}
    for line in content.split("\n")[:30]:
        if line.startswith("- **Name**:"):
            meta["name"] = line.split(":", 1)[1].strip()
        elif line.startswith("- **Title**:"):
            meta["title"] = line.split(":", 1)[1].strip()
        elif line.startswith("- **Model**:"):
            val = line.split(":", 1)[1].strip().lower()
            if val in ("opus", "sonnet", "haiku"):
                meta["model"] = val
    return meta


@router.post("/reseed")
async def reseed_from_files(
    business_id: UUID | None = Query(None),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Hot-reload employee prompts and metadata from .md files on disk.

    Diffs each employee's .md file against the DB and updates changed fields
    (system_prompt, name, title, model_tier). No server restart needed.

    If business_id is provided, reseeds business-scoped employees.
    Otherwise reseeds global (template) employees.
    """
    company_path = Path(settings.base_dir) / "company"
    if not company_path.exists():
        raise HTTPException(500, "company/ directory not found")

    # Load all employees in scope
    stmt = select(Employee).where(Employee.status == "active")
    if business_id:
        stmt = stmt.where(Employee.business_id == business_id)
    else:
        stmt = stmt.where(Employee.business_id.is_(None))

    result = await db.execute(stmt)
    employees = result.scalars().all()

    updated = []
    skipped = []
    errors = []

    for emp in employees:
        try:
            # Read from .md file if it exists on disk
            from pathlib import Path as PathlibPath

            # Try to find the employee's .md file
            found = False
            md_path = None
            if emp.business_id:
                business_company_path = company_path / str(emp.business_id)
                for dept_dir in business_company_path.glob("*"):
                    if dept_dir.is_dir():
                        potential_path = dept_dir / f"{emp.file_stem}.md"
                        if potential_path.exists():
                            md_path = potential_path
                            found = True
                            break

            if not found:
                # Look in global company/ directory
                for dept_dir in company_path.glob("*"):
                    if dept_dir.is_dir():
                        potential_path = dept_dir / f"{emp.file_stem}.md"
                        if potential_path.exists():
                            md_path = potential_path
                            found = True
                            break

            if not found:
                errors.append(f"{emp.file_stem}: .md file not found")
                skipped.append(emp.file_stem)
                continue

            content = md_path.read_text()
            meta = _parse_md_metadata(content)

            changed_fields = []

            if emp.system_prompt != content:
                emp.system_prompt = content
                changed_fields.append("system_prompt")
            if meta["name"] and emp.name != meta["name"]:
                emp.name = meta["name"]
                changed_fields.append("name")
            if meta["title"] and emp.title != meta["title"]:
                emp.title = meta["title"]
                changed_fields.append("title")
            if emp.model_tier != meta["model"]:
                emp.model_tier = meta["model"]
                changed_fields.append("model_tier")

            if changed_fields:
                updated.append({
                    "file_stem": emp.file_stem,
                    "name": emp.name,
                    "changed": changed_fields,
                })
            else:
                skipped.append(emp.file_stem)

        except Exception as e:
            errors.append(f"{emp.file_stem}: {e}")

    await db.commit()

    logger.info(
        f"Reseed complete: {len(updated)} updated, "
        f"{len(skipped)} unchanged, {len(errors)} errors"
    )

    return {
        "updated": updated,
        "unchanged_count": len(skipped),
        "errors": errors,
    }
