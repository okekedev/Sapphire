import { useState, useRef, useEffect, useCallback } from "react";
import { X, Save, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { cn } from "@/shared/lib/utils";
import type { JobTemplate, TemplateField } from "@/operations/api/job-templates";

interface Props {
  template: JobTemplate;
  initialData?: Record<string, unknown>;
  onSave: (data: Record<string, unknown>) => void;
  onClose: () => void;
  isPending: boolean;
}

// ── Signature pad (canvas-based, no library) ──
function SignaturePad({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.strokeStyle = "#111";
    ctx.lineWidth = 2;
    ctx.lineCap = "round";
    // Restore saved signature
    if (value) {
      const img = new Image();
      img.src = value;
      img.onload = () => ctx.drawImage(img, 0, 0);
    }
  }, []);

  const getPos = (e: React.MouseEvent | React.TouchEvent, canvas: HTMLCanvasElement) => {
    const rect = canvas.getBoundingClientRect();
    const source = "touches" in e ? e.touches[0] : e;
    return { x: source.clientX - rect.left, y: source.clientY - rect.top };
  };

  const start = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    drawing.current = true;
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    const pos = getPos(e, canvas);
    ctx.beginPath();
    ctx.moveTo(pos.x, pos.y);
  };

  const draw = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    if (!drawing.current) return;
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    const pos = getPos(e, canvas);
    ctx.lineTo(pos.x, pos.y);
    ctx.stroke();
  };

  const stop = () => {
    drawing.current = false;
    const canvas = canvasRef.current;
    if (canvas) onChange(canvas.toDataURL());
  };

  const clear = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    onChange("");
  };

  return (
    <div className="space-y-1">
      <canvas
        ref={canvasRef}
        width={400}
        height={120}
        className="w-full rounded-md border border-border bg-white touch-none cursor-crosshair"
        onMouseDown={start}
        onMouseMove={draw}
        onMouseUp={stop}
        onMouseLeave={stop}
        onTouchStart={start}
        onTouchMove={draw}
        onTouchEnd={stop}
      />
      <button onClick={clear} className="text-[11px] text-muted-foreground hover:text-foreground transition-colors">
        Clear signature
      </button>
    </div>
  );
}

// ── Field renderer ──
function FieldInput({
  field,
  value,
  onChange,
}: {
  field: TemplateField;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  switch (field.type) {
    case "text":
      return (
        <textarea
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Type here..."
          rows={3}
          className="w-full rounded-md border border-border bg-background px-2.5 py-2 text-sm resize-none focus:outline-none focus:border-primary transition-colors"
        />
      );

    case "checkbox":
      return (
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={(value as boolean) ?? false}
            onChange={(e) => onChange(e.target.checked)}
            className="h-4 w-4 rounded"
          />
          <span className="text-sm">{field.label}</span>
        </label>
      );

    case "checklist":
      return (
        <div className="space-y-1.5">
          {(field.items ?? []).map((item) => {
            const checked = Array.isArray(value) && (value as string[]).includes(item);
            return (
              <label key={item} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => {
                    const current = Array.isArray(value) ? (value as string[]) : [];
                    onChange(e.target.checked ? [...current, item] : current.filter((i) => i !== item));
                  }}
                  className="h-4 w-4 rounded"
                />
                <span className="text-sm">{item}</span>
              </label>
            );
          })}
        </div>
      );

    case "number":
      return (
        <Input
          type="number"
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          className="text-sm h-8 font-mono"
        />
      );

    case "url":
      return (
        <Input
          type="url"
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder="https://"
          className="text-sm h-8"
        />
      );

    case "signature":
      return (
        <SignaturePad value={(value as string) ?? ""} onChange={onChange} />
      );

    case "photo":
      return (
        <div className="space-y-2">
          <input
            type="file"
            accept="image/*"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              const reader = new FileReader();
              reader.onload = () => onChange(reader.result as string);
              reader.readAsDataURL(file);
            }}
            className="text-sm text-muted-foreground"
          />
          {typeof value === "string" && value.startsWith("data:image") && (
            <img src={value} alt="Uploaded" className="max-h-32 rounded-md border border-border object-contain" />
          )}
        </div>
      );

    default:
      return null;
  }
}

export function TemplateFillSheet({ template, initialData, onSave, onClose, isPending }: Props) {
  const [formData, setFormData] = useState<Record<string, unknown>>(initialData ?? {});
  const [showErrors, setShowErrors] = useState(false);

  const setValue = useCallback((fieldId: string, value: unknown) => {
    setFormData((prev) => ({ ...prev, [fieldId]: value }));
  }, []);

  // Collect all required fields
  const requiredFields = template.schema.sections
    .flatMap((s) => s.fields)
    .filter((f) => f.required);

  const missingRequired = requiredFields.filter((f) => {
    const val = formData[f.id];
    if (f.type === "checkbox") return !val;
    if (f.type === "checklist") return !Array.isArray(val) || (val as string[]).length === 0;
    if (f.type === "signature") return !val;
    return !val || (typeof val === "string" && !val.trim());
  });

  const handleSave = () => {
    if (missingRequired.length > 0) {
      setShowErrors(true);
      return;
    }
    onSave(formData);
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />
      <div className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-md bg-card border-l border-border shadow-xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div>
            <p className="text-sm font-semibold">{template.name}</p>
            <p className="text-xs text-muted-foreground">Fill out the job form</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {template.schema.sections.map((section, si) => (
            <div key={si} className="space-y-4">
              <h3 className="text-sm font-semibold border-b border-border pb-1.5">{section.title}</h3>
              {section.fields.map((field) => {
                const isMissing = showErrors && missingRequired.some((f) => f.id === field.id);
                return (
                  <div key={field.id} className="space-y-1.5">
                    {field.type !== "checkbox" && (
                      <label className={cn("text-xs font-medium", isMissing && "text-red-500")}>
                        {field.label}
                        {field.required && <span className="text-red-500 ml-0.5">*</span>}
                      </label>
                    )}
                    <FieldInput
                      field={field}
                      value={formData[field.id]}
                      onChange={(v) => setValue(field.id, v)}
                    />
                    {isMissing && (
                      <p className="text-[11px] text-red-500 flex items-center gap-1">
                        <AlertCircle className="h-3 w-3" /> Required
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="border-t border-border p-4 space-y-2">
          {showErrors && missingRequired.length > 0 && (
            <p className="text-xs text-red-500">
              {missingRequired.length} required field{missingRequired.length > 1 ? "s" : ""} missing.
            </p>
          )}
          <Button className="w-full" onClick={handleSave} disabled={isPending}>
            {isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
            Save Form
          </Button>
        </div>
      </div>
    </>
  );
}
