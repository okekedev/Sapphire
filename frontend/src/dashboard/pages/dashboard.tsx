import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ChevronDown,
  Building2,
  Network,
  Sparkles,
} from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { useAppStore } from "@/shared/stores/app-store";
import { useSetupStore } from "@/shared/stores/setup-store";
import { Spinner } from "@/shared/components/ui/spinner";
import { CompanyProfileChat } from "@/shared/components/setup/company-profile-chat";
import { ProfileEditor } from "@/shared/components/setup/profile-editor";

// API imports
import { getOrgChart } from "@/shared/api/organization";
import { getCompanyProfile, type CompanyProfile } from "@/shared/api/businesses";
import type { OrgChartNode } from "@/shared/types/organization";

// ── Main Component ──

export default function DashboardPage() {
  const business = useAppStore((s) => s.activeBusiness);
  const bizId = business?.id ?? "";
  const queryClient = useQueryClient();

  const [profileOpen, setProfileOpen] = useState(false);
  const [orgOpen, setOrgOpen] = useState(true);

  // Auto-open Company Profile if setup isn't complete
  const { profileComplete, setProfileComplete } = useSetupStore();
  const setupComplete = profileComplete;

  useEffect(() => {
    if (!setupComplete) setProfileOpen(true);
  }, [setupComplete]);

  // Fetch dashboard data
  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ["company-profile", bizId],
    queryFn: () => getCompanyProfile(bizId),
    enabled: !!bizId,
  });

  const { data: orgChart, isLoading: orgLoading } = useQuery({
    queryKey: ["org-chart"],
    queryFn: () => getOrgChart(),
    staleTime: 5 * 60 * 1000,
  });

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold">Home</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Overview of {business?.name ?? "your business"}
        </p>
      </div>

      {/* Section 1: Company Profile (with inline chat onboarding) */}
      <CollapsibleSection
        icon={<Building2 size={18} />}
        title="Company Profile"
        open={profileOpen}
        onToggle={() => setProfileOpen((v) => !v)}
        badge={!setupComplete ? "Setup" : undefined}
      >
        {profileLoading ? (
          <div className="flex justify-center py-8">
            <Spinner className="h-6 w-6" />
          </div>
        ) : profile && hasProfileData(profile) ? (
          <>
            <ProfileEditor businessId={bizId} profile={profile} />
            {bizId && (
              <div className="mt-5 border-t border-border pt-5">
                <CompanyProfileChat
                  businessId={bizId}
                  hasExistingProfile={true}
                  onProfileSaved={() =>
                    queryClient.invalidateQueries({ queryKey: ["company-profile", bizId] })
                  }
                />
              </div>
            )}
          </>
        ) : bizId ? (
          <CompanyProfileChat
            businessId={bizId}
            hasExistingProfile={false}
            onProfileSaved={() => {
              setProfileComplete(true);
              queryClient.invalidateQueries({ queryKey: ["company-profile", bizId] });
            }}
          />
        ) : null}
      </CollapsibleSection>

      {/* Section 2: Organization */}
      <CollapsibleSection
        icon={<Network size={18} />}
        title="Organization"
        open={orgOpen}
        onToggle={() => setOrgOpen((v) => !v)}
      >
        {orgLoading ? (
          <div className="flex justify-center py-8">
            <Spinner className="h-6 w-6" />
          </div>
        ) : orgChart && orgChart.length > 0 ? (
          <OrgCardHierarchy nodes={orgChart} />
        ) : (
          <EmptyNotice
            message="No employees added yet."
            linkTo="/workforce"
            linkLabel="Add employees"
          />
        )}
      </CollapsibleSection>
    </div>
  );
}

// ── Sub-components ──

function CollapsibleSection({
  icon,
  title,
  open,
  onToggle,
  action,
  badge,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  open: boolean;
  onToggle: () => void;
  action?: React.ReactNode;
  badge?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-card">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-5 py-4 text-left transition-colors hover:bg-muted/50"
      >
        <span className="flex items-center gap-2.5 font-semibold">
          <span className="text-primary">{icon}</span>
          {title}
          {badge && (
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-primary">
              {badge}
            </span>
          )}
        </span>
        <span className="flex items-center gap-3">
          {action}
          <ChevronDown
            size={16}
            className={cn(
              "text-muted-foreground transition-transform duration-200",
              open && "rotate-180",
            )}
          />
        </span>
      </button>
      {open && <div className="border-t border-border px-5 py-5">{children}</div>}
    </div>
  );
}

function hasProfileData(profile: CompanyProfile): boolean {
  return !!(profile.description || profile.services || profile.target_audience || profile.goals);
}

// ── Card-based Org Hierarchy ──

function OrgCardHierarchy({ nodes }: { nodes: OrgChartNode[] }) {
  // Flatten the tree and group by department
  const allNodes: OrgChartNode[] = [];
  function collect(n: OrgChartNode) {
    allNodes.push(n);
    n.children?.forEach(collect);
  }
  nodes.forEach(collect);

  // Find the owner/CEO (Christian)
  const owner = allNodes.find(
    (n) => n.department === "Administration" && n.title.toLowerCase().includes("ceo"),
  );

  // Group remaining employees by department
  const deptMap = new Map<string, OrgChartNode[]>();
  for (const n of allNodes) {
    if (owner && n.id === owner.id) continue;
    const dept = n.department;
    if (!deptMap.has(dept)) deptMap.set(dept, []);
    deptMap.get(dept)!.push(n);
  }

  // Sort departments: heads first within each dept
  for (const [, emps] of deptMap) {
    emps.sort((a, b) => (a.is_head === b.is_head ? 0 : a.is_head ? -1 : 1));
  }

  const [expandedDepts, setExpandedDepts] = useState<Set<string>>(new Set());
  const [expandedEmployees, setExpandedEmployees] = useState<Set<string>>(new Set());

  const toggleDept = (dept: string) => {
    setExpandedDepts((prev) => {
      const next = new Set(prev);
      next.has(dept) ? next.delete(dept) : next.add(dept);
      return next;
    });
  };

  const toggleEmployee = (id: string) => {
    setExpandedEmployees((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  return (
    <div className="space-y-3">
      {/* Owner card */}
      {owner && (
        <div className="rounded-lg border border-primary/30 bg-primary/5 p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-bold text-white">
              {owner.name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
            </div>
            <div className="flex-1">
              <p className="font-semibold">{owner.name}</p>
              <p className="text-sm text-muted-foreground">{owner.title}</p>
            </div>
          </div>
        </div>
      )}

      {/* Vertical connector from owner */}
      {owner && deptMap.size > 0 && (
        <div className="flex justify-center">
          <div className="h-4 w-px bg-border" />
        </div>
      )}

      {/* Department cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from(deptMap.entries()).map(([dept, emps]) => {
          const isOpen = expandedDepts.has(dept);

          return (
            <div key={dept} className="self-start rounded-lg border border-border bg-card overflow-hidden">
              {/* Department header */}
              <button
                onClick={() => toggleDept(dept)}
                className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-muted/50"
              >
                <div className="flex items-center gap-2">
                  <Building2 size={14} className="text-primary" />
                  <span className="text-sm font-semibold">{dept}</span>
                  <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                    {emps.length}
                  </span>
                </div>
                <ChevronDown
                  size={14}
                  className={cn("text-muted-foreground transition-transform duration-200", isOpen && "rotate-180")}
                />
              </button>

              {/* Expanded employee list */}
              {isOpen && (
                <div className="border-t border-border">
                  {emps.map((emp) => {
                    const empOpen = expandedEmployees.has(emp.id);
                    return (
                      <div key={emp.id} className="border-b border-border last:border-b-0">
                        <button
                          onClick={() => toggleEmployee(emp.id)}
                          className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-muted/30"
                        >
                          <div className={cn(
                            "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
                            emp.is_head
                              ? "bg-primary/15 text-primary"
                              : "bg-muted text-muted-foreground",
                          )}>
                            {emp.name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5">
                              <p className="text-sm font-medium truncate">{emp.name}</p>
                              {emp.is_head && <Sparkles size={10} className="shrink-0 text-amber-500" />}
                            </div>
                            <p className="text-[11px] text-muted-foreground truncate">{emp.title}</p>
                          </div>
                          <ChevronDown
                            size={12}
                            className={cn("shrink-0 text-muted-foreground/50 transition-transform duration-200", empOpen && "rotate-180")}
                          />
                        </button>

                        {/* Expanded employee details */}
                        {empOpen && emp.job_skills && (
                          <div className="bg-muted/30 px-4 py-2.5 pl-14">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                              Skills
                            </p>
                            <div className="flex flex-wrap gap-1">
                              {emp.job_skills.split(",").map((skill, i) => (
                                <span
                                  key={i}
                                  className="rounded-full bg-background border border-border px-2 py-0.5 text-[10px] text-muted-foreground"
                                >
                                  {skill.trim()}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EmptyNotice({
  message,
  linkTo,
  linkLabel,
}: {
  message: string;
  linkTo: string;
  linkLabel: string;
}) {
  return (
    <div className="flex flex-col items-center gap-2 py-8 text-center">
      <p className="text-sm text-muted-foreground">{message}</p>
      <Link to={linkTo} className="text-sm font-medium text-primary hover:underline">
        {linkLabel} &rarr;
      </Link>
    </div>
  );
}
