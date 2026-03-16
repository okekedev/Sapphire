"""
ORM models — re-export all models so SQLAlchemy can discover them.

15 tables across 7 departments:
  Core: users, businesses, business_members, connected_accounts,
        conversations, conversation_messages, notifications,
        departments, employees
  Marketing: contacts, interactions, business_phone_lines
  Operations: jobs
  Finance: payments
  Admin: phone_settings
"""

# Core models
from app.core.models.user import User
from app.core.models.business import Business, BusinessMember
from app.core.models.connected_account import ConnectedAccount
from app.core.models.conversation import Conversation, ConversationMessage
from app.core.models.notification import Notification
from app.core.models.organization import Department, Employee

# Department models
from app.marketing.models import Contact, Interaction, BusinessPhoneLine
from app.finance.models import Payment
from app.admin.models import PhoneSettings
from app.operations.models import Job

__all__ = [
    # ── Core ──
    "User", "Business", "BusinessMember", "ConnectedAccount",
    "Conversation", "ConversationMessage", "Notification",
    "Department", "Employee",
    # ── Marketing ──
    "Contact", "Interaction", "BusinessPhoneLine",
    # ── Finance ──
    "Payment",
    # ── Operations ──
    "Job",
    # ── Admin ──
    "PhoneSettings",
]
