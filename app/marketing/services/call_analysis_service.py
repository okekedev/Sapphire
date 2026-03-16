"""
Call Analysis Service — Post-call AI analysis for department routing and categorization.

After every call completes, this service:
  1. Analyzes the transcript/IVR data to determine the best department
  2. Tags the interaction with a department_context and call_category
  3. Generates a structured action summary for that department

The department_context drives which tab the call appears in and which AI
employee can auto-process it after human review. Department → employee mapping
is loaded from the DB via org_graph.department_head_map.
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.org_graph import org_graph

logger = logging.getLogger(__name__)

# Call categories per department (semantic labels for AI classification)
CALL_CATEGORIES = {
    "Sales": ["inquiry", "quote_request", "follow_up", "pricing", "new_customer"],
    "Operations": ["job_request", "service_request", "scheduling", "status_check", "complaint"],
    "Finance": ["payment_inquiry", "invoice_question", "refund_request", "account_balance"],
    "Marketing": ["campaign_response", "referral", "partnership", "feedback"],
    "Admin": ["general_inquiry", "transfer_request", "wrong_number"],
}


class CallAnalysisResult:
    """Result of analyzing a call for department routing."""

    def __init__(
        self,
        department: str,
        category: str,
        confidence: float,
        suggested_action: str | None = None,
        notes: str | None = None,
    ):
        self.department = department
        self.category = category
        self.confidence = confidence
        self.suggested_action = suggested_action
        self.notes = notes


class CallAnalysisService:
    """Analyzes calls and determines department routing + category."""

    async def analyze_call(
        self,
        *,
        caller_name: str | None,
        reason: str | None,
        summary: str | None,
        ivr_speech: str | None,
        call_duration: int,
        existing_department: str | None,
        business_id: UUID,
        db: AsyncSession,
    ) -> CallAnalysisResult:
        """
        Analyze a call and determine which department it belongs to.

        If the call was already routed to a department during the IVR (real-time),
        we trust that routing but can refine the category. If not, we do full
        AI analysis to determine the best department.
        """
        # Load org graph for department validation (cached, ~60s TTL)
        await org_graph.load(db)

        # If already routed during IVR, just refine the category
        if existing_department and existing_department in org_graph.valid_departments:
            category = await self._categorize_for_department(
                department=existing_department,
                reason=reason,
                summary=summary,
                ivr_speech=ivr_speech,
                business_id=business_id,
                db=db,
            )
            return CallAnalysisResult(
                department=existing_department,
                category=category,
                confidence=0.9,
                suggested_action=self._default_action(existing_department, category),
            )

        # No existing routing — full AI analysis
        return await self._full_analysis(
            caller_name=caller_name,
            reason=reason,
            summary=summary,
            ivr_speech=ivr_speech,
            call_duration=call_duration,
            business_id=business_id,
            db=db,
        )

    async def _full_analysis(
        self,
        *,
        caller_name: str | None,
        reason: str | None,
        summary: str | None,
        ivr_speech: str | None,
        call_duration: int,
        business_id: UUID,
        db: AsyncSession,
    ) -> CallAnalysisResult:
        """Full AI-powered department + category analysis."""
        # Build context from available data
        context_parts = []
        if caller_name:
            context_parts.append(f"Caller: {caller_name}")
        if reason:
            context_parts.append(f"Reason: {reason}")
        if summary:
            context_parts.append(f"Summary: {summary}")
        if ivr_speech:
            context_parts.append(f"Caller's words: {ivr_speech}")
        context_parts.append(f"Duration: {call_duration}s")

        if not any([reason, summary, ivr_speech]):
            # No data to analyze — default to Admin
            return CallAnalysisResult(
                department="Admin",
                category="general_inquiry",
                confidence=0.3,
                suggested_action="Review call recording and categorize manually",
            )

        call_context = "\n".join(context_parts)

        try:
            from app.core.services.claude_cli_service import claude_cli

            prompt = f"""Analyze this inbound call and determine:
1. Which department should handle it
2. What category of call it is
3. What the suggested next action should be

Available departments: Sales, Operations, Finance, Marketing, Admin

Call information:
{call_context}

Respond in this exact format (no extra text):
DEPARTMENT: [department name]
CATEGORY: [category]
ACTION: [suggested next action in one sentence]"""

            result = await claude_cli._run_claude(
                system_prompt=(
                    "You analyze business phone calls and route them to the correct department. "
                    "Sales = pricing, quotes, new customers, follow-ups. "
                    "Operations = job requests, service scheduling, status checks, complaints. "
                    "Finance = payments, invoices, refunds, account questions. "
                    "Marketing = campaign responses, referrals, partnerships. "
                    "Admin = general inquiries, transfers, wrong numbers. "
                    "Respond with ONLY the requested format."
                ),
                message=prompt,
                label="Call Analysis",
                model="claude-haiku-4-5-20251001",
                db=db,
                business_id=business_id,
            )

            if result:
                return self._parse_analysis(result)

        except Exception as e:
            logger.error(f"Call analysis AI failed: {e}")

        # Fallback: keyword-based routing
        return self._keyword_fallback(reason, summary, ivr_speech)

    def _parse_analysis(self, ai_output: str) -> CallAnalysisResult:
        """Parse the structured AI output into a CallAnalysisResult."""
        department = "Admin"
        category = "general_inquiry"
        action = None

        for line in ai_output.strip().splitlines():
            line = line.strip()
            if line.startswith("DEPARTMENT:"):
                dept = line.replace("DEPARTMENT:", "").strip()
                # Normalize to valid department
                for valid in org_graph.valid_departments:
                    if valid.lower() == dept.lower():
                        department = valid
                        break
            elif line.startswith("CATEGORY:"):
                category = line.replace("CATEGORY:", "").strip().lower().replace(" ", "_")
            elif line.startswith("ACTION:"):
                action = line.replace("ACTION:", "").strip()

        return CallAnalysisResult(
            department=department,
            category=category,
            confidence=0.8,
            suggested_action=action,
        )

    def _keyword_fallback(
        self,
        reason: str | None,
        summary: str | None,
        ivr_speech: str | None,
    ) -> CallAnalysisResult:
        """Simple keyword-based routing as fallback when AI fails."""
        text = " ".join(filter(None, [reason, summary, ivr_speech])).lower()

        sales_keywords = {"price", "pricing", "quote", "cost", "buy", "purchase", "interested", "sales", "new customer"}
        ops_keywords = {"job", "service", "repair", "fix", "schedule", "appointment", "work", "install", "complaint"}
        billing_keywords = {"bill", "invoice", "payment", "pay", "refund", "charge", "balance", "account"}
        marketing_keywords = {"saw your ad", "referral", "google", "facebook", "website", "campaign"}

        scores = {
            "Sales": sum(1 for kw in sales_keywords if kw in text),
            "Operations": sum(1 for kw in ops_keywords if kw in text),
            "Finance": sum(1 for kw in billing_keywords if kw in text),
            "Marketing": sum(1 for kw in marketing_keywords if kw in text),
        }

        best_dept = max(scores, key=scores.get)  # type: ignore
        if scores[best_dept] == 0:
            best_dept = "Admin"

        category_map = {
            "Sales": "inquiry",
            "Operations": "service_request",
            "Finance": "payment_inquiry",
            "Marketing": "campaign_response",
            "Admin": "general_inquiry",
        }

        return CallAnalysisResult(
            department=best_dept,
            category=category_map.get(best_dept, "general_inquiry"),
            confidence=0.5,
            suggested_action=self._default_action(best_dept, category_map.get(best_dept, "general_inquiry")),
        )

    async def _categorize_for_department(
        self,
        *,
        department: str,
        reason: str | None,
        summary: str | None,
        ivr_speech: str | None,
        business_id: UUID,
        db: AsyncSession,
    ) -> str:
        """Given a department, determine the specific call category."""
        categories = CALL_CATEGORIES.get(department, ["general_inquiry"])
        text = " ".join(filter(None, [reason, summary, ivr_speech])).lower()

        if not text:
            return categories[0]

        # Simple keyword matching for speed
        for cat in categories:
            cat_words = cat.replace("_", " ").split()
            if any(w in text for w in cat_words):
                return cat

        return categories[0]

    def _default_action(self, department: str, category: str) -> str:
        """Generate a default suggested action based on department + category."""
        actions = {
            ("Sales", "inquiry"): "Qualify the lead and send follow-up",
            ("Sales", "quote_request"): "Prepare and send a quote",
            ("Sales", "follow_up"): "Review previous interaction and respond",
            ("Sales", "pricing"): "Send pricing information",
            ("Sales", "new_customer"): "Create customer record and welcome",
            ("Operations", "job_request"): "Create a new job and schedule",
            ("Operations", "service_request"): "Schedule the service visit",
            ("Operations", "scheduling"): "Confirm or reschedule appointment",
            ("Operations", "status_check"): "Provide job status update",
            ("Operations", "complaint"): "Document complaint and escalate",
            ("Finance", "payment_inquiry"): "Check account and provide balance",
            ("Finance", "invoice_question"): "Review and send invoice details",
            ("Finance", "refund_request"): "Process refund request",
            ("Finance", "account_balance"): "Send account statement",
            ("Marketing", "campaign_response"): "Track attribution and follow up",
            ("Marketing", "referral"): "Log referral source and qualify",
            ("Admin", "general_inquiry"): "Review and route to correct department",
        }
        return actions.get((department, category), f"Review call and take action ({department})")

    async def process_with_employee(
        self,
        *,
        business_id: UUID,
        department: str,
        caller_name: str | None,
        reason: str | None,
        summary: str | None,
        category: str,
        contact_id: UUID | None,
        interaction_id: UUID,
        db: AsyncSession,
    ) -> dict:
        """
        Invoke the department's AI employee to process a reviewed call.

        This is triggered AFTER human review confirms the department is correct.
        Returns the employee's output + any actions taken.
        """
        # Load org graph for department→employee mapping (cached, ~60s TTL)
        await org_graph.load(db)

        employee_id = org_graph.department_head_map.get(department)
        if not employee_id:
            return {"status": "error", "message": f"No employee mapped for department: {department}"}

        from app.core.services.claude_cli_service import claude_cli

        task = f"""A call has been reviewed and routed to your department ({department}).

## Call Details
- Caller: {caller_name or 'Unknown'}
- Reason: {reason or 'Not stated'}
- Category: {category}
- Summary: {summary or 'No summary available'}

## Your Task
Based on this call, take the appropriate action for your department:
- If this is a sales inquiry, qualify the lead and draft a follow-up message
- If this is a job/service request, outline what needs to be done
- If this is a billing question, check the context and provide guidance
- If you need more information, specify what's needed

Respond with:
ACTION_TAKEN: [what you did or recommend]
NEXT_STEP: [what should happen next]
NOTES: [any additional context]"""

        try:
            output = await claude_cli.call_employee(
                employee_id=employee_id,
                business_id=business_id,
                task=task,
                db=db,
            )

            return {
                "status": "processed",
                "employee": employee_id,
                "department": department,
                "output": output,
            }
        except Exception as e:
            logger.error(f"Employee processing failed for {employee_id}: {e}")
            return {
                "status": "error",
                "employee": employee_id,
                "message": str(e),
            }


# Singleton
call_analysis = CallAnalysisService()
