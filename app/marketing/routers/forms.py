"""Contact form router.

Public (no auth) endpoint: POST /forms/{form_id}/submit
  — creates or updates a Contact with source_channel="form"
  — logs an Interaction of type "form_submit"

Admin endpoints (authenticated): CRUD for ContactForm records.
"""
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.marketing.models import Contact, ContactForm, Interaction
from app.core.services.auth_service import get_current_user_id
from app.core.services.phone_utils import normalize_phone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/forms", tags=["forms"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── Pydantic schemas ──────────────────────────────────────

class FormSubmitPayload(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: str
    reason: str
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


class FormCreate(BaseModel):
    name: str
    redirect_url: Optional[str] = None


class FormOut(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    redirect_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Public submit endpoint ────────────────────────────────

@router.post("/{form_id}/submit", status_code=200)
async def submit_form(
    form_id: uuid.UUID,
    payload: FormSubmitPayload,
    db: AsyncSession = Depends(get_db),
):
    # Validate
    payload.first_name = payload.first_name.strip()
    payload.last_name = payload.last_name.strip()
    if not payload.first_name or not payload.last_name:
        raise HTTPException(400, "first_name and last_name are required")
    if not _EMAIL_RE.match(payload.email.strip()):
        raise HTTPException(400, "Invalid email address")
    phone = normalize_phone(payload.phone.strip())
    if not phone:
        raise HTTPException(400, "Invalid phone number")

    # Look up form
    form_row = await db.get(ContactForm, form_id)
    if not form_row:
        raise HTTPException(404, "Form not found")
    business_id = form_row.business_id

    full_name = f"{payload.first_name} {payload.last_name}"

    # Upsert contact by phone
    result = await db.execute(
        select(Contact).where(
            Contact.business_id == business_id,
            Contact.phone == phone,
        )
    )
    contact = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if contact is None:
        contact = Contact(
            business_id=business_id,
            full_name=full_name,
            phone=phone,
            email=payload.email.strip(),
            source_channel="form",
            status="new",
            created_at=now,
            updated_at=now,
        )
        db.add(contact)
        await db.flush()
    else:
        if not contact.email:
            contact.email = payload.email.strip()
        contact.updated_at = now

    # Log interaction
    interaction = Interaction(
        contact_id=contact.id,
        business_id=business_id,
        type="form_submit",
        subject=f"Form submission: {payload.reason[:120]}",
        body=payload.reason,
        direction="inbound",
        metadata_={
            "form_id": str(form_id),
            "utm_source": payload.utm_source,
            "utm_medium": payload.utm_medium,
            "utm_campaign": payload.utm_campaign,
        },
        created_at=now,
    )
    db.add(interaction)
    await db.flush()

    redirect = form_row.redirect_url
    return {"ok": True, "contact_id": str(contact.id), "redirect_url": redirect}


# ── Admin CRUD ────────────────────────────────────────────

@router.get("", response_model=list[FormOut])
async def list_forms(
    business_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _uid: str = Depends(get_current_user_id),
):
    result = await db.execute(
        select(ContactForm).where(ContactForm.business_id == business_id)
    )
    return result.scalars().all()


@router.post("", response_model=FormOut, status_code=201)
async def create_form(
    business_id: uuid.UUID,
    payload: FormCreate,
    db: AsyncSession = Depends(get_db),
    _uid: str = Depends(get_current_user_id),
):
    form = ContactForm(
        business_id=business_id,
        name=payload.name.strip(),
        redirect_url=payload.redirect_url,
        created_at=datetime.now(timezone.utc),
    )
    db.add(form)
    await db.flush()
    await db.refresh(form)
    return form


@router.delete("/{form_id}", status_code=204)
async def delete_form(
    form_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _uid: str = Depends(get_current_user_id),
):
    form = await db.get(ContactForm, form_id)
    if not form:
        raise HTTPException(404, "Form not found")
    await db.delete(form)
    await db.flush()
    return Response(status_code=204)


# ── Embed JS ──────────────────────────────────────────────

@router.get("/{form_id}/embed.js", response_class=Response)
async def embed_js(
    form_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    form = await db.get(ContactForm, form_id)
    if not form:
        raise HTTPException(404, "Form not found")

    from app.config import settings
    api_base = settings.api_prefix  # e.g. "/api/v1"

    js = f"""
(function(){{
  var FORM_ID="{form_id}";
  var API=window.location.origin+"{api_base}/forms/"+FORM_ID+"/submit";

  function formatPhone(v){{
    var d=v.replace(/[^0-9]/g,"");
    if(d.length<=3)return d;
    if(d.length<=6)return"("+d.slice(0,3)+") "+d.slice(3);
    return"("+d.slice(0,3)+") "+d.slice(3,6)+"-"+d.slice(6,10);
  }}

  function render(el){{
    el.innerHTML='<form id="sph-form" style="font-family:sans-serif;max-width:420px;display:flex;flex-direction:column;gap:12px">'
      +'<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">'
      +'<input id="sph-fn" required placeholder="First name*" style="padding:8px 12px;border:1px solid #ccc;border-radius:8px;font-size:14px">'
      +'<input id="sph-ln" required placeholder="Last name*" style="padding:8px 12px;border:1px solid #ccc;border-radius:8px;font-size:14px">'
      +'</div>'
      +'<input id="sph-ph" required placeholder="Phone*" style="padding:8px 12px;border:1px solid #ccc;border-radius:8px;font-size:14px">'
      +'<input id="sph-em" required type="email" placeholder="Email*" style="padding:8px 12px;border:1px solid #ccc;border-radius:8px;font-size:14px">'
      +'<textarea id="sph-rs" required placeholder="How can we help?*" rows="3" style="padding:8px 12px;border:1px solid #ccc;border-radius:8px;font-size:14px;resize:vertical"></textarea>'
      +'<div id="sph-err" style="color:#b91c1c;font-size:13px;display:none"></div>'
      +'<button type="submit" id="sph-btn" style="background:#2563eb;color:#fff;padding:10px;border:none;border-radius:8px;font-size:14px;cursor:pointer">Send Message</button>'
      +'</form>';

    var ph=el.querySelector("#sph-ph");
    ph.addEventListener("input",function(){{ph.value=formatPhone(ph.value);}});

    el.querySelector("#sph-form").addEventListener("submit",async function(e){{
      e.preventDefault();
      var btn=el.querySelector("#sph-btn");
      var err=el.querySelector("#sph-err");
      btn.disabled=true;btn.textContent="Sending…";err.style.display="none";
      try{{
        var r=await fetch(API,{{method:"POST",headers:{{"Content-Type":"application/json"}},
          body:JSON.stringify({{first_name:el.querySelector("#sph-fn").value,last_name:el.querySelector("#sph-ln").value,phone:el.querySelector("#sph-ph").value,email:el.querySelector("#sph-em").value,reason:el.querySelector("#sph-rs").value}})
        }});
        var d=await r.json();
        if(!r.ok)throw new Error(d.detail||"Submission failed");
        el.innerHTML="<p style='color:#166534;font-size:14px'>Thanks! We'll be in touch soon.</p>";
        if(d.redirect_url)setTimeout(function(){{window.location.href=d.redirect_url;}},1500);
      }}catch(ex){{
        err.textContent=ex.message;err.style.display="block";
        btn.disabled=false;btn.textContent="Send Message";
      }}
    }});
  }}

  document.querySelectorAll("[data-sapphire-form=\\"{form_id}\\"]").forEach(render);
  if(document.readyState==="loading"){{
    document.addEventListener("DOMContentLoaded",function(){{
      document.querySelectorAll("[data-sapphire-form=\\"{form_id}\\"]").forEach(render);
    }});
  }}
}})();
""".strip()

    return Response(content=js, media_type="application/javascript")
