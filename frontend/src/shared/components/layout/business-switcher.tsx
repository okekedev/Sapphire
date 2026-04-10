import { useState, useRef, useEffect } from "react";
import { Menu, Plus, Building2, Check } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { useAppStore } from "@/shared/stores/app-store";
import { createBusiness } from "@/shared/api/businesses";
import { cn } from "@/shared/lib/utils";

export function BusinessSwitcher() {
  const {
    activeBusiness,
    businesses,
    setActiveBusiness,
    setBusinesses,
    showBusinessModal,
    setShowBusinessModal,
  } = useAppStore();

  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newWebsite, setNewWebsite] = useState("");
  const [creating, setCreating] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const biz = await createBusiness({
        name: newName.trim(),
        website: newWebsite.trim() || undefined,
      });
      setBusinesses([...businesses, biz]);
      setActiveBusiness(biz);
      setNewName("");
      setNewWebsite("");
      setShowBusinessModal(false);
      setOpen(false);
    } catch {
      // TODO: show error toast
    } finally {
      setCreating(false);
    }
  };

  return (
    <div ref={ref} className="relative">
      {/* Trigger */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-center h-8 w-8 rounded-lg hover:bg-accent transition-colors"
        title="Switch business"
      >
        <Menu className="h-4 w-4" />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 w-72 rounded-lg border border-border bg-card shadow-lg">
          {/* Business list */}
          <div className="max-h-48 overflow-y-auto p-1">
            {businesses.map((biz) => (
              <button
                key={biz.id}
                onClick={() => {
                  setActiveBusiness(biz);
                  setOpen(false);
                }}
                className={cn(
                  "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors",
                  biz.id === activeBusiness?.id
                    ? "bg-accent text-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                <Building2 className="h-4 w-4 shrink-0" />
                <span className="flex-1 truncate">{biz.name}</span>
                {biz.id === activeBusiness?.id && (
                  <Check className="h-4 w-4 text-foreground" />
                )}
              </button>
            ))}
          </div>

          {/* Add Business — only shown if user has no business yet */}
          {businesses.length === 0 && (
            <div className="border-t border-border p-1">
              <button
                onClick={() => setShowBusinessModal(true)}
                className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
              >
                <Plus className="h-4 w-4" />
                <span>Add Business</span>
              </button>
            </div>
          )}
        </div>
      )}

      {/* Add Business Modal */}
      {showBusinessModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-semibold">Add a Business</h2>
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Business Name</label>
                <Input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Okeke LLC"
                  autoFocus
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Website (optional)</label>
                <Input
                  value={newWebsite}
                  onChange={(e) => setNewWebsite(e.target.value)}
                  placeholder="https://example.com"
                />
              </div>
              <div className="flex justify-end gap-2">
                <Button
                  variant="ghost"
                  onClick={() => {
                    setShowBusinessModal(false);
                    setNewName("");
                    setNewWebsite("");
                  }}
                >
                  Cancel
                </Button>
                <Button onClick={handleCreate} disabled={creating || !newName.trim()}>
                  {creating ? "Creating..." : "Create"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
