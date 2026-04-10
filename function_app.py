"""
Azure Functions v2 — ASGI adapter for FastAPI.

The Functions runtime routes all HTTP requests to the FastAPI app.
host.json sets routePrefix: "" so no extra prefix is added.
"""

import azure.functions as func
from app.main import app

function_app = func.AsgiFunctionApp(app=app, http_auth_level=func.AuthLevel.ANONYMOUS)
