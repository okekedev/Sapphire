"""
OrgGraph — DB-driven organization relationship maps.

Single source of truth for all org-structure constants. Replaces hardcoded
DIRECTOR_TEAMS, SUPERVISOR_MAP, DEPARTMENT_HEADS, etc.

Loads departments + employees from the DB (business_id IS NULL = base rows)
and derives all relationship maps. Cached with a 60-second TTL to avoid
repeated queries within the same request burst.

Usage:
    from app.core.services.org_graph import org_graph

    await org_graph.load(db)          # Call once per request
    org_graph.director_teams          # {"elena_cmo": ["alex_content_creator", ...]}
    org_graph.supervisor_map          # {"alex_content_creator": "elena_cmo", ...}
    org_graph.department_heads        # {"elena_cmo", "jordan_director_of_sales", ...}
    org_graph.valid_departments       # {"Marketing", "Sales", ...}
    org_graph.department_head_map     # {"Marketing": "elena_cmo", ...}
"""

import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.models.organization import Department, Employee

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 60


class OrgGraph:
    """Builds and caches org relationship maps from the DB."""

    def __init__(self) -> None:
        self._loaded_at: float = 0
        self._director_teams: dict[str, list[str]] = {}
        self._supervisor_map: dict[str, str] = {}
        self._department_heads: set[str] = set()
        self._valid_departments: set[str] = set()
        self._department_head_map: dict[str, str] = {}

    @property
    def is_stale(self) -> bool:
        return (time.monotonic() - self._loaded_at) > _CACHE_TTL_SECONDS

    async def load(self, db: AsyncSession) -> None:
        """Load org data from DB if cache is stale. Safe to call repeatedly."""
        if not self.is_stale:
            return

        # Fetch all base departments
        dept_result = await db.execute(
            select(Department)
            .where(Department.business_id.is_(None))
            .order_by(Department.display_order, Department.name)
        )
        departments = list(dept_result.scalars().all())

        # Fetch all base employees with their department eagerly loaded
        emp_result = await db.execute(
            select(Employee)
            .where(Employee.business_id.is_(None))
            .where(Employee.status == "active")
            .options(selectinload(Employee.department))
        )
        employees = list(emp_result.scalars().all())

        # Build lookup maps
        dept_by_id: dict[str, str] = {str(d.id): d.name for d in departments}
        emp_by_id: dict[str, Employee] = {str(e.id): e for e in employees}

        # ── valid_departments ──
        self._valid_departments = {d.name for d in departments}

        # ── Group employees by department ──
        dept_employees: dict[str, list[Employee]] = {}  # dept_name → [employees]
        for emp in employees:
            dept_name = dept_by_id.get(str(emp.department_id), "Unknown")
            dept_employees.setdefault(dept_name, []).append(emp)

        # ── director_teams ──
        # For each head employee, their team = non-head employees in same department
        self._director_teams = {}
        self._department_heads = set()
        self._department_head_map = {}

        for emp in employees:
            if emp.is_head:
                dept_name = dept_by_id.get(str(emp.department_id), "Unknown")
                team_members = [
                    e.file_stem
                    for e in dept_employees.get(dept_name, [])
                    if not e.is_head and e.file_stem != emp.file_stem
                ]
                self._director_teams[emp.file_stem] = team_members
                self._department_heads.add(emp.file_stem)
                self._department_head_map[dept_name] = emp.file_stem

        # ── supervisor_map ──
        # Built from reports_to FK. Heads with no reports_to → "owner"
        self._supervisor_map = {}
        for emp in employees:
            if emp.reports_to:
                supervisor = emp_by_id.get(str(emp.reports_to))
                if supervisor:
                    self._supervisor_map[emp.file_stem] = supervisor.file_stem
            elif emp.is_head:
                # Department heads with no reports_to escalate to owner
                self._supervisor_map[emp.file_stem] = "owner"

        self._loaded_at = time.monotonic()
        logger.info(
            f"OrgGraph loaded: {len(departments)} departments, "
            f"{len(employees)} employees, "
            f"{len(self._director_teams)} directors"
        )

    # ── Public properties ──

    @property
    def director_teams(self) -> dict[str, list[str]]:
        """Director file_stem → list of team member file_stems."""
        return self._director_teams

    @property
    def supervisor_map(self) -> dict[str, str]:
        """Employee file_stem → supervisor file_stem. Top-level → 'owner'."""
        return self._supervisor_map

    @property
    def department_heads(self) -> set[str]:
        """Set of file_stems for department heads (is_head=True)."""
        return self._department_heads

    @property
    def valid_departments(self) -> set[str]:
        """All department names from DB."""
        return self._valid_departments

    @property
    def department_head_map(self) -> dict[str, str]:
        """Department name → head's file_stem."""
        return self._department_head_map


# Module-level singleton
org_graph = OrgGraph()
