"""Pydantic schemas for auth routes."""

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    roles: list[str]        # e.g. ["sales_executive", "analyst"]
    permissions: list[str]  # e.g. ["access_sales", "assign_leads", ...]
