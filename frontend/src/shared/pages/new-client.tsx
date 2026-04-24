import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { createBusiness } from "@/shared/api/businesses";
import { useAppStore } from "@/shared/stores/app-store";
import { Spinner } from "@/shared/components/ui/spinner";

const INDUSTRIES = [
  "HVAC", "Plumbing", "Electrical", "Roofing", "Landscaping", "Cleaning",
  "Construction", "Property Management", "Real Estate", "Healthcare",
  "Legal", "Accounting", "Consulting", "Retail", "Restaurant", "Other",
];

export default function NewClientPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { setActiveBusiness } = useAppStore();

  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [industry, setIndustry] = useState("");
  const [step, setStep] = useState<"form" | "seeding">("form");
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setStep("seeding");
    setError("");
    try {
      const biz = await createBusiness({
        name: name.trim(),
        website: website.trim() || undefined,
        industry: industry || undefined,
      });
      await queryClient.invalidateQueries({ queryKey: ["businesses"] });
      setActiveBusiness(biz);
      navigate("/dashboard", { replace: true });
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to create client. Please try again.");
      setStep("form");
    }
  };

  if (step === "seeding") {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-24">
        <Spinner className="h-8 w-8 text-primary" />
        <div className="text-center">
          <p className="font-semibold">Setting up client workspace…</p>
          <p className="mt-1 text-sm text-muted-foreground">Provisioning AI team. This only takes a moment.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center py-16">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-1 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
            <Building2 size={24} className="text-primary" />
          </div>
          <h1 className="text-2xl font-bold">Add new client</h1>
          <p className="text-sm text-muted-foreground">
            A full AI team will be provisioned instantly.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Client name <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Acme Corp"
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              autoFocus
              required
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Industry
            </label>
            <select
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">Select industry…</option>
              {INDUSTRIES.map((i) => (
                <option key={i} value={i}>{i}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Website
            </label>
            <input
              type="url"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              placeholder="https://example.com"
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="flex-1 rounded-lg border border-input px-4 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!name.trim()}
              className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              Create client
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
