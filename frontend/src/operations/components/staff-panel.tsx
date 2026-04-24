import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil, Loader2, Check, X } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Card, CardContent } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";
import {
  listStaff, createStaff, updateStaff, deleteStaff,
  type StaffMember, type CreateStaffRequest, type UpdateStaffRequest,
} from "@/operations/api/staff";

const ROLE_CONFIG = {
  admin:      { label: "Admin",      bg: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300" },
  dispatcher: { label: "Dispatcher", bg: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300" },
  technician: { label: "Technician", bg: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
} as const;

const DEFAULT_COLORS = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6"];

function StaffForm({
  initialData,
  businessId,
  onSave,
  onCancel,
  isPending,
}: {
  initialData?: Partial<StaffMember>;
  businessId: string;
  onSave: (data: CreateStaffRequest | UpdateStaffRequest) => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [firstName, setFirstName] = useState(initialData?.first_name ?? "");
  const [lastName, setLastName] = useState(initialData?.last_name ?? "");
  const [phone, setPhone] = useState(initialData?.phone ?? "");
  const [email, setEmail] = useState(initialData?.email ?? "");
  const [role, setRole] = useState<"admin" | "dispatcher" | "technician">(initialData?.role ?? "technician");
  const [color, setColor] = useState(initialData?.color ?? DEFAULT_COLORS[0]);

  const handleSave = () => {
    if (!firstName.trim()) return;
    onSave({
      ...(initialData?.id ? {} : { business_id: businessId }),
      first_name: firstName.trim(),
      last_name: lastName.trim() || undefined,
      phone: phone.trim() || undefined,
      email: email.trim() || undefined,
      role,
      color,
    });
  };

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <p className="text-sm font-semibold">{initialData?.id ? "Edit Staff Member" : "Add Staff Member"}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Input value={firstName} onChange={(e) => setFirstName(e.target.value)} placeholder="First name *" className="text-sm h-8" />
          <Input value={lastName} onChange={(e) => setLastName(e.target.value)} placeholder="Last name" className="text-sm h-8" />
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Phone (for SMS dispatch)" className="text-sm h-8" />
          <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" className="text-sm h-8" />
        </div>

        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <p className="text-xs text-muted-foreground">Role:</p>
            {(["technician", "dispatcher", "admin"] as const).map((r) => (
              <button
                key={r}
                onClick={() => setRole(r)}
                className={cn(
                  "text-[11px] font-semibold rounded-full px-2.5 py-0.5 transition-opacity",
                  ROLE_CONFIG[r].bg,
                  role !== r && "opacity-40",
                )}
              >
                {ROLE_CONFIG[r].label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5">
            <p className="text-xs text-muted-foreground">Color:</p>
            {DEFAULT_COLORS.map((c) => (
              <button
                key={c}
                onClick={() => setColor(c)}
                className="h-5 w-5 rounded-full border-2 transition-all"
                style={{ backgroundColor: c, borderColor: color === c ? "#000" : "transparent" }}
              />
            ))}
          </div>
        </div>

        <div className="flex gap-2">
          <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={!firstName.trim() || isPending}>
            {isPending ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Check className="h-3 w-3 mr-1" />}
            Save
          </Button>
          <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={onCancel}>Cancel</Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function StaffPanel({ businessId }: { businessId: string }) {
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const { data: staff = [], isLoading } = useQuery({
    queryKey: ["staff", businessId],
    queryFn: () => listStaff(businessId),
    enabled: !!businessId,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["staff", businessId] });

  const createMutation = useMutation({
    mutationFn: (data: CreateStaffRequest) => createStaff(data),
    onSuccess: () => { invalidate(); setShowAdd(false); },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateStaffRequest }) => updateStaff(id, data),
    onSuccess: () => { invalidate(); setEditingId(null); },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteStaff(id),
    onSuccess: invalidate,
  });

  if (isLoading) return (
    <div className="flex items-center justify-center py-12">
      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <Button size="sm" className="h-7 text-xs" onClick={() => setShowAdd(!showAdd)}>
          <Plus className="h-3 w-3 mr-1" /> Add Staff
        </Button>
      </div>

      {showAdd && (
        <StaffForm
          businessId={businessId}
          onSave={(data) => createMutation.mutate(data as CreateStaffRequest)}
          onCancel={() => setShowAdd(false)}
          isPending={createMutation.isPending}
        />
      )}

      {staff.length === 0 && !showAdd ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          No staff yet. Add your team members to enable job dispatch.
        </div>
      ) : (
        <div className="space-y-2">
          {staff.map((member) =>
            editingId === member.id ? (
              <StaffForm
                key={member.id}
                initialData={member}
                businessId={businessId}
                onSave={(data) => updateMutation.mutate({ id: member.id, data: data as UpdateStaffRequest })}
                onCancel={() => setEditingId(null)}
                isPending={updateMutation.isPending}
              />
            ) : (
              <Card key={member.id} className={cn(!member.is_active && "opacity-50")}>
                <CardContent className="flex items-center gap-4 p-3">
                  {/* Color dot */}
                  <div className="h-3 w-3 rounded-full shrink-0" style={{ backgroundColor: member.color }} />

                  {/* Name + role */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">
                      {member.first_name} {member.last_name ?? ""}
                    </p>
                    <p className="text-xs text-muted-foreground">{member.phone ?? member.email ?? "—"}</p>
                  </div>

                  <span className={cn("text-[10px] font-semibold rounded-full px-2 py-0.5 shrink-0", ROLE_CONFIG[member.role]?.bg)}>
                    {ROLE_CONFIG[member.role]?.label ?? member.role}
                  </span>

                  {/* Actions */}
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => setEditingId(member.id)}
                      className="p-1 text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => deleteMutation.mutate(member.id)}
                      className="p-1 text-muted-foreground hover:text-red-500 transition-colors"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </CardContent>
              </Card>
            )
          )}
        </div>
      )}
    </div>
  );
}
