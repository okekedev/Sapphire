/**
 * ProfileEditor — Editable company profile fields synced with DB columns.
 *
 * Each field is its own collapsible section. Maps 1:1 to columns on businesses table.
 */
import { useState, useEffect, useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, Pencil, X, Loader2, ChevronDown } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import {
  saveCompanyProfile,
  PROFILE_FIELDS,
  type CompanyProfile,
} from "@/shared/api/businesses";

interface ProfileEditorProps {
  businessId: string;
  profile: CompanyProfile;
}

function SectionCollapsible({
  label,
  children,
  defaultOpen = false,
}: {
  label: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="rounded-lg border border-border">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-muted/50 transition-colors"
      >
        <span className="text-sm font-medium">{label}</span>
        <ChevronDown
          size={16}
          className={cn(
            "text-muted-foreground transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>
      {open && (
        <div className="border-t border-border px-4 py-3">
          {children}
        </div>
      )}
    </div>
  );
}

export function ProfileEditor({ businessId, profile }: ProfileEditorProps) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<CompanyProfile>({ ...profile });

  // Sync draft when profile changes externally
  useEffect(() => {
    setDraft({ ...profile });
  }, [profile]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, string> = { source: "manual_edit" };
      for (const { key } of PROFILE_FIELDS) {
        const val = draft[key];
        if (val && val.trim()) {
          payload[key] = val.trim();
        }
      }
      return saveCompanyProfile(businessId, payload);
    },
    onSuccess: () => {
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ["company-profile", businessId] });
    },
  });

  const updateField = useCallback((key: keyof CompanyProfile, value: string) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }, []);

  const cancelEdit = useCallback(() => {
    setDraft({ ...profile });
    setEditing(false);
  }, [profile]);

  // Check if any field has content
  const hasContent = PROFILE_FIELDS.some(({ key }) => {
    const val = profile[key];
    return val && val.trim();
  });

  if (!hasContent) {
    return (
      <p className="py-4 text-sm text-muted-foreground">
        No profile data yet. Use the chat below to build your company profile.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header with edit/save buttons */}
      <div className="flex items-center justify-end">
        <div className="flex items-center gap-2">
          {editing ? (
            <>
              <button
                onClick={cancelEdit}
                className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium hover:bg-muted"
              >
                <X size={12} />
                Cancel
              </button>
              <button
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                className={cn(
                  "flex items-center gap-1 rounded-md bg-primary px-2.5 py-1.5 text-xs font-medium text-primary-foreground",
                  "hover:bg-primary/90 disabled:opacity-50",
                )}
              >
                {saveMutation.isPending ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Save size={12} />
                )}
                Save
              </button>
            </>
          ) : (
            <button
              onClick={() => setEditing(true)}
              className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium hover:bg-muted"
            >
              <Pencil size={12} />
              Edit
            </button>
          )}
        </div>
      </div>

      {/* Profile fields — each in its own collapsible section */}
      <div className="space-y-2">
        {PROFILE_FIELDS.map(({ key, label }) => {
          const value = draft[key] ?? "";
          // In view mode, skip empty fields
          if (!editing && !value.trim()) return null;

          return (
            <SectionCollapsible key={key} label={label}>
              {editing ? (
                <textarea
                  value={value}
                  onChange={(e) => updateField(key, e.target.value)}
                  rows={Math.max(3, value.split("\n").length + 1)}
                  className={cn(
                    "w-full rounded-md border bg-background px-3 py-2 text-sm leading-relaxed",
                    "placeholder:text-muted-foreground/50",
                    "focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary",
                    "resize-y",
                  )}
                />
              ) : (
                <div className="text-sm leading-relaxed text-foreground/90 whitespace-pre-wrap">
                  {value}
                </div>
              )}
            </SectionCollapsible>
          );
        })}
      </div>

      {/* Save error */}
      {saveMutation.isError && (
        <p className="text-xs text-red-500">
          Failed to save. Please try again.
        </p>
      )}
    </div>
  );
}
