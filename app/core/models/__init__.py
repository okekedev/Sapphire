# Import all models so SQLAlchemy's create_all discovers them
from app.core.models.user import User  # noqa: F401
from app.core.models.business import Business, BusinessMember  # noqa: F401
from app.core.models.role import Role, BusinessMemberRole  # noqa: F401
from app.core.models.organization import Department, Employee  # noqa: F401
from app.core.models.connected_account import ConnectedAccount  # noqa: F401
