"""Maps router — Azure Maps geocoding and route planning."""

import logging
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.core.services import maps_service
from app.core.services.auth_service import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/maps", tags=["Maps"])


@router.get("/config")
async def get_maps_config(
    _: UUID = Depends(get_current_user_id),
):
    """Return the Azure Maps subscription key for client-side SDK use."""
    if not settings.azure_maps_key:
        raise HTTPException(status_code=503, detail="Azure Maps not configured")
    return {"subscription_key": settings.azure_maps_key}


class GeocodeRequest(BaseModel):
    address: str


@router.post("/geocode")
async def geocode_address(
    body: GeocodeRequest,
    _: UUID = Depends(get_current_user_id),
):
    """Geocode an address to lat/lng coordinates."""
    result = await maps_service.geocode(body.address)
    if not result:
        raise HTTPException(status_code=404, detail="Address not found")
    return {"lat": result[0], "lng": result[1]}


class RouteStop(BaseModel):
    lat: float
    lng: float
    label: Optional[str] = None


class RouteRequest(BaseModel):
    origin: RouteStop
    stops: list[RouteStop]
    optimize: bool = True


@router.post("/route")
async def calculate_route(
    body: RouteRequest,
    _: UUID = Depends(get_current_user_id),
):
    """Calculate optimized driving route from origin through all stops."""
    if not body.stops:
        raise HTTPException(status_code=400, detail="At least one stop required")
    origin = (body.origin.lat, body.origin.lng)
    stops = [(s.lat, s.lng) for s in body.stops]
    try:
        result = await maps_service.get_route(origin, stops, body.optimize)
        return result
    except Exception as e:
        logger.error("Route calculation failed: %s", e)
        raise HTTPException(status_code=502, detail="Route calculation failed")
