import client from "@/shared/api/client";

export interface GeocodeResult {
  lat: number;
  lng: number;
}

export interface RouteStop {
  lat: number;
  lng: number;
  label?: string;
}

export interface RouteLeg {
  summary: {
    lengthInMeters: number;
    travelTimeInSeconds: number;
    trafficDelayInSeconds?: number;
    departureTime: string;
    arrivalTime: string;
  };
  points: Array<{ latitude: number; longitude: number }>;
}

export interface RouteResult {
  routes: Array<{
    summary: {
      lengthInMeters: number;
      travelTimeInSeconds: number;
      departureTime: string;
      arrivalTime: string;
    };
    legs: RouteLeg[];
    // Azure Maps returns reordered indices when computeBestOrder=true
    optimizedWaypoints?: Array<{
      providedIndex: number;
      optimizedIndex: number;
    }>;
  }>;
}

export async function getMapsKey(): Promise<string> {
  const res = await client.get<{ subscription_key: string }>("/maps/config");
  return res.data.subscription_key;
}

export async function geocodeAddress(address: string): Promise<GeocodeResult> {
  const res = await client.post<GeocodeResult>("/maps/geocode", { address });
  return res.data;
}

export async function calculateRoute(
  origin: RouteStop,
  stops: RouteStop[],
  optimize = true,
): Promise<RouteResult> {
  const res = await client.post<RouteResult>("/maps/route", {
    origin,
    stops,
    optimize,
  });
  return res.data;
}
