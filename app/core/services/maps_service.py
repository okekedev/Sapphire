"""Azure Maps service — geocoding and route optimization."""

from typing import Optional
import httpx
from app.config import settings

MAPS_BASE = "https://atlas.microsoft.com"


async def geocode(address: str) -> Optional[tuple[float, float]]:
    """Geocode an address string. Returns (lat, lng) or None."""
    if not settings.azure_maps_key or not address.strip():
        return None
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{MAPS_BASE}/search/address/json",
                params={
                    "api-version": "1.0",
                    "query": address,
                    "subscription-key": settings.azure_maps_key,
                    "limit": 1,
                },
                timeout=5.0,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                return None
            pos = results[0]["position"]
            return float(pos["lat"]), float(pos["lon"])
        except Exception:
            return None


async def get_route(
    origin: tuple[float, float],
    stops: list[tuple[float, float]],
    optimize: bool = True,
) -> dict:
    """Calculate optimal route from origin through all stops.

    Returns the raw Azure Maps route response including:
    - routes[0].summary: totalTime, totalDistance
    - routes[0].legs[]: per-leg travel time + distance
    - routes[0].optimizedWaypoints: reordered stop indices (when optimize=True)
    - routes[0].legs[].points[]: encoded polyline points
    """
    waypoints = ":".join(
        f"{lat},{lng}" for lat, lng in [origin] + stops
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{MAPS_BASE}/route/directions/json",
            params={
                "api-version": "1.0",
                "query": waypoints,
                "subscription-key": settings.azure_maps_key,
                "computeBestOrder": "true" if optimize else "false",
                "routeType": "fastest",
                "travelMode": "car",
                "traffic": "true",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()
