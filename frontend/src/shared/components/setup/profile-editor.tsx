/**
 * ProfileEditor — Per-section editable company profile fields.
 *
 * Each field is its own collapsible section with its own Edit / Save / Cancel
 * buttons. Saves are scoped to the one field being edited — no global edit mode.
 */
import { useState, useEffect } from "react";
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

// ── Per-section component ──

function ProfileSection({
  label,
  fieldKey,
  value,
  businessId,
}: {
  label: string;
  fieldKey: keyof CompanyProfile;
  value: string;
  businessId: string;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  // Keep draft in sync when profile refreshes externally
  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  const saveMutation = useMutation({
    mutationFn: () =>
      saveCompanyProfile(businessId, {
        [fieldKey]: draft.trim(),
        source: "manual_edit",
      }),
    onSuccess: () => {
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ["company-profile", businessId] });
    },
  });

  const handleEdit = () => {
    setOpen(true);
    setEditing(true);
  };

  const handleCancel = () => {
    setDraft(value);
    setEditing(false);
  };

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      {/* Header row — toggle left, edit button right */}
      <div className="flex items-center px-4 py-3 hover:bg-muted/50 transition-colors">
        <button
          onClick={() => !editing && setOpen((v) => !v)}
          className="flex flex-1 items-center justify-between text-left min-w-0 gap-2"
        >
          <span className="text-sm font-medium">{label}</span>
          {!editing && (
            <ChevronDown
              size={14}
              className={cn(
                "shrink-0 text-muted-foreground transition-transform duration-200",
                open && "rotate-180",
              )}
            />
          )}
        </button>

        {!editing && value.trim() && (
          <button
            onClick={handleEdit}
            className="ml-3 flex shrink-0 items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <Pencil size={11} />
            Edit
          </button>
        )}
      </div>

      {/* Expanded content */}
      {(open || editing) && (
        <div className="border-t border-border px-4 py-3">
          {editing ? (
            <div className="space-y-2">
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={Math.max(3, draft.split("\n").length + 1)}
                autoFocus
                className={cn(
                  "w-full rounded-md border bg-background px-3 py-2 text-sm leading-relaxed",
                  "placeholder:text-muted-foreground/50 resize-y",
                  "focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary",
                )}
              />
              {saveMutation.isError && (
                <p className="text-xs text-red-500">Failed to save. Please try again.</p>
              )}
              <div className="flex justify-end gap-2">
                <button
                  onClick={handleCancel}
                  className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium hover:bg-muted"
                >
                  <X size={12} />
                  Cancel
                </button>
                <button
                  onClick={() => saveMutation.mutate()}
                  disabled={saveMutation.isPending || !draft.trim()}
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
              </div>
            </div>
          ) : (
            <div className="text-sm leading-relaxed text-foreground/90 whitespace-pre-wrap">
              {value}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main component ──

export function ProfileEditor({ businessId, profile }: ProfileEditorProps) {
  const hasContent = PROFILE_FIELDS.some(({ key }) => profile[key]?.trim());

  if (!hasContent) {
    return (
      <p className="py-4 text-sm text-muted-foreground">
        No profile data yet. Use the chat below to build your company profile.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {PROFILE_FIELDS.map(({ key, label }) => {
        const value = profile[key] ?? "";
        if (!value.trim()) return null;
        return (
          <ProfileSection
            key={key}
            label={label}
            fieldKey={key}
            value={value}
            businessId={businessId}
          />
        );
      })}
    </div>
  );
}
