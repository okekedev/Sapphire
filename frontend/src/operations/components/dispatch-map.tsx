/**
 * DispatchMap — Azure Maps route planner for job dispatch.
 *
 * Shows all jobs with service addresses as map pins, lets the dispatcher
 * select a worker and jobs, then calculates the optimal driving route with
 * per-leg drive times.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import * as atlas from "azure-maps-control";
import "azure-maps-control/dist/atlas.min.css";
import { Loader2, MapPin, Navigation, Clock, Route, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import { listStaff, type StaffMember } from "@/operations/api/staff";
import { getMapsKey, geocodeAddress, calculateRoute, type RouteStop } from "@/operations/api/maps";
import type { JobItem } from "@/sales/api/sales";

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m} min`;
}

function fmtDistance(meters: number): string {
  const miles = meters / 1609.34;
  return `${miles.toFixed(1)} mi`;
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface GeocodedJob {
  job: JobItem;
  lat: number;
  lng: number;
}

interface RouteLegSummary {
  jobId: string;
  jobTitle: string;
  address: string;
  travelTime: number;  // seconds
  distance: number;    // meters
}

interface Props {
  businessId: string;
  jobs: JobItem[];
}

// ── Component ─────────────────────────────────────────────────────────────────

export function DispatchMap({ businessId, jobs }: Props) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<atlas.Map | null>(null);
  const datasourceRef = useRef<atlas.source.DataSource | null>(null);

  const [expanded, setExpanded] = useState(false);
  const [selectedStaffId, setSelectedStaffId] = useState<string>("");
  const [selectedJobIds, setSelectedJobIds] = useState<Set<string>>(new Set());
  const [geocoding, setGeocoding] = useState(false);
  const [routing, setRouting] = useState(false);
  const [routeLegs, setRouteLegs] = useState<RouteLegSummary[]>([]);
  const [totalTime, setTotalTime] = useState<number | null>(null);
  const [totalDist, setTotalDist] = useState<number | null>(null);
  const [geocodeCache, setGeocodeCache] = useState<Record<string, { lat: number; lng: number }>>({});

  // ── Data ──
  const { data: mapsKey } = useQuery({
    queryKey: ["maps-config"],
    queryFn: getMapsKey,
    enabled: expanded,
    staleTime: Infinity,
  });

  const { data: staff = [] } = useQuery({
    queryKey: ["staff", businessId],
    queryFn: () => listStaff(businessId),
    enabled: expanded && !!businessId,
  });

  // Jobs that have a service address
  const addressedJobs = jobs.filter((j) => !!j.service_address);

  // ── Map init ──────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!expanded || !mapsKey || !mapContainerRef.current) return;
    if (mapRef.current) return; // already initialized

    const map = new atlas.Map(mapContainerRef.current, {
      authOptions: {
        authType: "subscriptionKey" as atlas.AuthenticationType,
        subscriptionKey: mapsKey,
      },
      center: [-97.7431, 30.2672],
      zoom: 10,
      style: "road_shaded_relief",
      language: "en-US",
    });

    map.events.add("ready", () => {
      const ds = new atlas.source.DataSource();
      map.sources.add(ds);
      datasourceRef.current = ds;

      // Job pins layer
      map.layers.add(new atlas.layer.BubbleLayer(ds, "job-pins", {
        filter: ["==", ["get", "type"], "job"],
        color: ["get", "color"],
        radius: 10,
        strokeColor: "#fff",
        strokeWidth: 2,
      }));

      // Worker origin pin layer
      map.layers.add(new atlas.layer.BubbleLayer(ds, "worker-pin", {
        filter: ["==", ["get", "type"], "worker"],
        color: "#2563eb",
        radius: 12,
        strokeColor: "#fff",
        strokeWidth: 3,
      }));

      // Route line layer
      map.layers.add(new atlas.layer.LineLayer(ds, "route-line", {
        filter: ["==", ["get", "type"], "route"],
        strokeColor: "#6366f1",
        strokeWidth: 4,
        strokeDashArray: [1, 0],
      }), "job-pins");

      // Symbol labels
      map.layers.add(new atlas.layer.SymbolLayer(ds, "labels", {
        filter: ["==", ["get", "type"], "label"],
        textOptions: {
          textField: ["get", "label"],
          offset: [0, -2.2],
          color: "#fff",
          font: ["StandardFont-Bold"],
          size: 12,
        },
        iconOptions: { image: "none" },
      }));
    });

    mapRef.current = map;

    return () => {
      map.dispose();
      mapRef.current = null;
      datasourceRef.current = null;
    };
  }, [expanded, mapsKey]);

  // ── Geocode all addressed jobs when map opens ──────────────────────────────

  useEffect(() => {
    if (!expanded || addressedJobs.length === 0) return;

    const uncached = addressedJobs.filter(
      (j) => j.service_address && !geocodeCache[j.service_address]
    );
    if (uncached.length === 0) return;

    setGeocoding(true);
    Promise.all(
      uncached.map(async (j) => {
        try {
          const result = await geocodeAddress(j.service_address!);
          return { address: j.service_address!, ...result };
        } catch {
          return null;
        }
      })
    ).then((results) => {
      const newCache: Record<string, { lat: number; lng: number }> = {};
      for (const r of results) {
        if (r) newCache[r.address] = { lat: r.lat, lng: r.lng };
      }
      setGeocodeCache((prev) => ({ ...prev, ...newCache }));
      setGeocoding(false);
    });
  }, [expanded, addressedJobs.length]);

  // ── Re-render job pins whenever geocode cache updates ─────────────────────

  useEffect(() => {
    const ds = datasourceRef.current;
    if (!ds) return;

    // Remove old job pins
    const existing = ds.getShapes().filter((s) => {
      const p = (s as atlas.Shape).getProperties();
      return p?.type === "job" || p?.type === "label";
    });
    existing.forEach((s) => ds.remove(s as atlas.Shape));

    // Add fresh pins
    addressedJobs.forEach((job) => {
      const coords = job.service_address ? geocodeCache[job.service_address] : null;
      if (!coords) return;
      const isSelected = selectedJobIds.has(job.id);
      ds.add(new atlas.Shape(new atlas.data.Feature(
        new atlas.data.Point([coords.lng, coords.lat]),
        {
          type: "job",
          jobId: job.id,
          color: isSelected ? "#f59e0b" : "#64748b",
        }
      )));
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geocodeCache, selectedJobIds]);

  // ── Plan route ────────────────────────────────────────────────────────────

  const planRoute = useCallback(async () => {
    const staffMember = staff.find((s) => s.id === selectedStaffId);
    if (!staffMember) return;

    const selectedJobs = addressedJobs.filter((j) => selectedJobIds.has(j.id));
    if (selectedJobs.length === 0) return;

    setRouting(true);
    setRouteLegs([]);
    setTotalTime(null);
    setTotalDist(null);

    try {
      // Geocode worker home address if not already lat/lng
      let originLat = staffMember.home_lat;
      let originLng = staffMember.home_lng;
      if ((!originLat || !originLng) && staffMember.home_address) {
        const geo = await geocodeAddress(staffMember.home_address);
        originLat = geo.lat;
        originLng = geo.lng;
      }
      if (!originLat || !originLng) {
        alert("This worker has no home address set. Add one in the Job Team tab.");
        setRouting(false);
        return;
      }

      const origin: RouteStop = { lat: originLat, lng: originLng, label: "Start" };
      const stops: RouteStop[] = selectedJobs.map((j) => {
        const coords = geocodeCache[j.service_address!];
        return { lat: coords.lat, lng: coords.lng, label: j.title };
      });

      const result = await calculateRoute(origin, stops, true);
      const route = result.routes[0];
      if (!route) return;

      // Build ordered stop list using optimizedWaypoints
      const orderedStops = stops.slice();
      if (route.optimizedWaypoints?.length) {
        const sorted = [...route.optimizedWaypoints].sort(
          (a, b) => a.optimizedIndex - b.optimizedIndex
        );
        sorted.forEach((wp, i) => {
          orderedStops[i] = stops[wp.providedIndex];
        });
      }

      const legs: RouteLegSummary[] = route.legs.map((leg, i) => {
        const job = selectedJobs.find((j) => {
          const c = geocodeCache[j.service_address!];
          return c?.lat === orderedStops[i]?.lat && c?.lng === orderedStops[i]?.lng;
        }) ?? selectedJobs[i];
        return {
          jobId: job?.id ?? "",
          jobTitle: job?.title ?? `Stop ${i + 1}`,
          address: job?.service_address ?? "",
          travelTime: leg.summary.travelTimeInSeconds,
          distance: leg.summary.lengthInMeters,
        };
      });

      setRouteLegs(legs);
      setTotalTime(route.summary.travelTimeInSeconds);
      setTotalDist(route.summary.lengthInMeters);

      // Draw on map
      const ds = datasourceRef.current;
      const map = mapRef.current;
      if (ds && map) {
        // Remove old route shapes
        const old = ds.getShapes().filter((s) => {
          const p = (s as atlas.Shape).getProperties();
          return p?.type === "route" || p?.type === "worker";
        });
        old.forEach((s) => ds.remove(s as atlas.Shape));

        // Worker origin pin
        ds.add(new atlas.Shape(new atlas.data.Feature(
          new atlas.data.Point([originLng, originLat]),
          { type: "worker" }
        )));

        // Route polyline — combine all leg points
        const allPoints: atlas.data.Position[] = [
          [originLng, originLat],
        ];
        for (const leg of route.legs) {
          for (const pt of leg.points) {
            allPoints.push([pt.longitude, pt.latitude]);
          }
        }
        ds.add(new atlas.Shape(new atlas.data.Feature(
          new atlas.data.LineString(allPoints),
          { type: "route" }
        )));

        // Fit map to route
        const bounds = atlas.data.BoundingBox.fromPositions(allPoints);
        map.setCamera({ bounds, padding: 60 });
      }
    } catch (err) {
      console.error("Route planning failed", err);
    } finally {
      setRouting(false);
    }
  }, [selectedStaffId, selectedJobIds, staff, addressedJobs, geocodeCache]);

  // ── Toggle job selection ───────────────────────────────────────────────────

  const toggleJob = (id: string) =>
    setSelectedJobIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <Card className="overflow-hidden">
      {/* Header toggle */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold hover:bg-muted/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Route className="h-4 w-4 text-primary" />
          Route Planner
          {geocoding && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground ml-1" />}
        </div>
        {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>

      {expanded && (
        <div className="border-t border-border">
          <div className="flex flex-col md:flex-row h-[520px]">
            {/* ── Sidebar ── */}
            <div className="w-full md:w-64 md:shrink-0 border-b md:border-b-0 md:border-r border-border flex flex-col">
              <div className="flex-1 overflow-y-auto p-3 space-y-4">
                {/* Worker selector */}
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                    Worker
                  </p>
                  <select
                    value={selectedStaffId}
                    onChange={(e) => {
                      setSelectedStaffId(e.target.value);
                      setRouteLegs([]);
                      setTotalTime(null);
                    }}
                    className="w-full rounded-lg border border-border bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary"
                  >
                    <option value="">— Select worker —</option>
                    {staff.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.first_name} {s.last_name ?? ""}
                        {!s.home_address ? " (no address)" : ""}
                      </option>
                    ))}
                  </select>
                  {selectedStaffId && (() => {
                    const s = staff.find((m) => m.id === selectedStaffId);
                    return s?.home_address ? (
                      <p className="mt-1 text-[11px] text-muted-foreground flex items-center gap-1">
                        <MapPin size={10} /> {s.home_address}
                      </p>
                    ) : (
                      <p className="mt-1 text-[11px] text-amber-600">
                        No home address — add one in Job Team tab
                      </p>
                    );
                  })()}
                </div>

                {/* Job selector */}
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                    Jobs to Route ({selectedJobIds.size} selected)
                  </p>
                  {addressedJobs.length === 0 ? (
                    <p className="text-xs text-muted-foreground italic">
                      No jobs have service addresses yet
                    </p>
                  ) : (
                    <div className="space-y-1">
                      {addressedJobs.map((job) => (
                        <label
                          key={job.id}
                          className={cn(
                            "flex items-start gap-2 rounded-lg px-2 py-1.5 cursor-pointer transition-colors text-xs",
                            selectedJobIds.has(job.id)
                              ? "bg-amber-50 dark:bg-amber-950/30"
                              : "hover:bg-muted",
                          )}
                        >
                          <input
                            type="checkbox"
                            className="mt-0.5 shrink-0 accent-amber-500"
                            checked={selectedJobIds.has(job.id)}
                            onChange={() => toggleJob(job.id)}
                          />
                          <span>
                            <span className="font-medium">{job.title}</span>
                            {job.contact_name && (
                              <span className="text-muted-foreground"> · {job.contact_name}</span>
                            )}
                            <br />
                            <span className="text-muted-foreground">{job.service_address}</span>
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Plan button */}
              <div className="p-3 border-t border-border">
                <Button
                  size="sm"
                  className="w-full"
                  disabled={
                    !selectedStaffId ||
                    selectedJobIds.size === 0 ||
                    routing ||
                    geocoding
                  }
                  onClick={planRoute}
                >
                  {routing ? (
                    <><Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> Planning…</>
                  ) : (
                    <><Navigation size={14} className="mr-1.5" /> Plan Route</>
                  )}
                </Button>
              </div>

              {/* Route summary */}
              {routeLegs.length > 0 && (
                <div className="border-t border-border p-3 space-y-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Route Summary
                  </p>
                  {routeLegs.map((leg, i) => (
                    <div key={leg.jobId} className="text-xs">
                      <span className="font-medium text-muted-foreground mr-1">{i + 1}.</span>
                      <span className="font-medium">{leg.jobTitle}</span>
                      <div className="flex gap-3 text-muted-foreground mt-0.5 pl-3">
                        <span className="flex items-center gap-0.5">
                          <Clock size={9} /> {fmtDuration(leg.travelTime)}
                        </span>
                        <span>{fmtDistance(leg.distance)}</span>
                      </div>
                    </div>
                  ))}
                  {totalTime !== null && (
                    <div className="pt-1 border-t border-border flex justify-between text-xs font-semibold">
                      <span>Total</span>
                      <span className="text-primary">
                        {fmtDuration(totalTime)} · {fmtDistance(totalDist ?? 0)}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* ── Map canvas ── */}
            <div className="flex-1 relative min-h-[280px]">
              {!mapsKey ? (
                <div className="absolute inset-0 flex items-center justify-center bg-muted/30">
                  <div className="text-center text-sm text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin mx-auto mb-2" />
                    Loading map…
                  </div>
                </div>
              ) : (
                <div ref={mapContainerRef} className="absolute inset-0" />
              )}
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
