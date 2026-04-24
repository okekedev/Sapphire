import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Loader2, Check, ChevronDown, ChevronRight, GripVertical } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Card, CardContent } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";
import {
  listTemplates, createTemplate, updateTemplate, deleteTemplate,
  type JobTemplate, type TemplateSection, type TemplateField, type FieldType,
} from "@/operations/api/job-templates";

const FIELD_TYPE_OPTIONS: { value: FieldType; label: string }[] = [
  { value: "text", label: "Text / Notes" },
  { value: "checkbox", label: "Checkbox" },
  { value: "checklist", label: "Checklist" },
  { value: "number", label: "Number" },
  { value: "url", label: "URL / Link" },
  { value: "signature", label: "Signature" },
  { value: "photo", label: "Photo" },
];

function genId() {
  return Math.random().toString(36).slice(2, 10);
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex items-center justify-between gap-3 cursor-pointer">
      <span className="text-sm text-muted-foreground">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative h-5 w-9 rounded-full transition-colors shrink-0",
          checked ? "bg-primary" : "bg-muted-foreground/30",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-4" : "translate-x-0.5",
          )}
        />
      </button>
    </label>
  );
}

function FieldEditor({
  field,
  onChange,
  onDelete,
}: {
  field: TemplateField;
  onChange: (f: TemplateField) => void;
  onDelete: () => void;
}) {
  const [itemInput, setItemInput] = useState("");

  const addItem = () => {
    const val = itemInput.trim();
    if (!val) return;
    onChange({ ...field, items: [...(field.items ?? []), val] });
    setItemInput("");
  };

  return (
    <div className="rounded-md border border-border bg-background p-3 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <GripVertical className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <select
          value={field.type}
          onChange={(e) => onChange({ ...field, type: e.target.value as FieldType, items: undefined })}
          className="h-7 rounded border border-border bg-background px-1.5 text-xs"
        >
          {FIELD_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <Input
          value={field.label}
          onChange={(e) => onChange({ ...field, label: e.target.value })}
          placeholder="Field label"
          className="flex-1 min-w-[120px] h-7 text-xs"
        />
        <label className="flex items-center gap-1 text-[11px] text-muted-foreground cursor-pointer whitespace-nowrap">
          <input
            type="checkbox"
            checked={!!field.required}
            onChange={(e) => onChange({ ...field, required: e.target.checked })}
            className="h-3 w-3 rounded"
          />
          Required
        </label>
        <button onClick={onDelete} className="text-muted-foreground hover:text-red-500 transition-colors">
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      {field.type === "checklist" && (
        <div className="pl-5 space-y-1.5">
          <div className="flex flex-wrap gap-1">
            {(field.items ?? []).map((item, i) => (
              <span key={i} className="flex items-center gap-1 text-[11px] bg-muted rounded-full px-2 py-0.5">
                {item}
                <button
                  onClick={() => onChange({ ...field, items: (field.items ?? []).filter((_, j) => j !== i) })}
                  className="text-muted-foreground hover:text-red-500 leading-none"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-1.5">
            <Input
              value={itemInput}
              onChange={(e) => setItemInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addItem()}
              placeholder="Add item... (Enter)"
              className="flex-1 h-6 text-xs"
            />
            <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={addItem}>
              Add
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function SectionEditor({
  section,
  index,
  onChange,
  onDelete,
}: {
  section: TemplateSection;
  index: number;
  onChange: (s: TemplateSection) => void;
  onDelete: () => void;
}) {
  const [collapsed, setCollapsed] = useState(false);

  const addField = () => {
    onChange({
      ...section,
      fields: [...section.fields, { id: genId(), type: "text", label: "New Field", required: false }],
    });
  };

  const updateField = (i: number, f: TemplateField) => {
    const fields = [...section.fields];
    fields[i] = f;
    onChange({ ...section, fields });
  };

  const deleteField = (i: number) => {
    onChange({ ...section, fields: section.fields.filter((_, j) => j !== i) });
  };

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <button onClick={() => setCollapsed(!collapsed)} className="text-muted-foreground shrink-0">
          {collapsed
            ? <ChevronRight className="h-3.5 w-3.5" />
            : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
        <Input
          value={section.title}
          onChange={(e) => onChange({ ...section, title: e.target.value })}
          placeholder={`Section ${index + 1} title`}
          className="flex-1 h-7 text-sm font-medium border-none shadow-none focus-visible:ring-0 px-0 bg-transparent"
        />
        <span className="text-[11px] text-muted-foreground shrink-0">
          {section.fields.length} field{section.fields.length !== 1 ? "s" : ""}
        </span>
        <button onClick={onDelete} className="text-muted-foreground hover:text-red-500 transition-colors shrink-0">
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      {!collapsed && (
        <div className="p-3 space-y-2">
          {section.fields.map((field, i) => (
            <FieldEditor
              key={field.id}
              field={field}
              onChange={(f) => updateField(i, f)}
              onDelete={() => deleteField(i)}
            />
          ))}
          <Button size="sm" variant="outline" className="h-7 text-xs w-full" onClick={addField}>
            <Plus className="h-3 w-3 mr-1" /> Add Field
          </Button>
        </div>
      )}
    </div>
  );
}

export function TemplateBuilder({ businessId }: { businessId: string }) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isNew, setIsNew] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [requiresScheduling, setRequiresScheduling] = useState(false);
  const [requiresAssignment, setRequiresAssignment] = useState(false);
  const [requiresDispatch, setRequiresDispatch] = useState(false);
  const [sections, setSections] = useState<TemplateSection[]>([]);

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ["job-templates", businessId],
    queryFn: () => listTemplates(businessId),
    enabled: !!businessId,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["job-templates", businessId] });

  const createMutation = useMutation({
    mutationFn: createTemplate,
    onSuccess: (t) => { invalidate(); loadTemplate(t); },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, ...data }: Parameters<typeof updateTemplate>[1] & { id: string }) =>
      updateTemplate(id, data),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteTemplate,
    onSuccess: () => { invalidate(); setSelectedId(null); setIsNew(false); },
  });

  const loadTemplate = (t: JobTemplate) => {
    setSelectedId(t.id);
    setIsNew(false);
    setName(t.name);
    setDescription(t.description ?? "");
    setRequiresScheduling(t.requires_scheduling);
    setRequiresAssignment(t.requires_assignment);
    setRequiresDispatch(t.requires_dispatch);
    setSections(JSON.parse(JSON.stringify(t.schema.sections)));
  };

  const startNew = () => {
    setSelectedId(null);
    setIsNew(true);
    setName("");
    setDescription("");
    setRequiresScheduling(false);
    setRequiresAssignment(false);
    setRequiresDispatch(false);
    setSections([]);
  };

  const handleSave = () => {
    if (!name.trim()) return;
    const schema = { sections };
    if (isNew) {
      createMutation.mutate({
        business_id: businessId,
        name: name.trim(),
        description: description.trim() || undefined,
        requires_scheduling: requiresScheduling,
        requires_assignment: requiresAssignment,
        requires_dispatch: requiresDispatch,
        schema,
      });
    } else if (selectedId) {
      updateMutation.mutate({
        id: selectedId,
        name: name.trim(),
        description: description.trim() || undefined,
        requires_scheduling: requiresScheduling,
        requires_assignment: requiresAssignment,
        requires_dispatch: requiresDispatch,
        schema,
      });
    }
  };

  const addSection = () => {
    setSections([...sections, { title: "New Section", fields: [] }]);
  };

  const updateSection = (i: number, s: TemplateSection) => {
    const next = [...sections];
    next[i] = s;
    setSections(next);
  };

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const showEditor = isNew || selectedId !== null;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
      {/* Left: Template list */}
      <div className="space-y-2">
        <Button size="sm" className="h-7 text-xs w-full" onClick={startNew}>
          <Plus className="h-3 w-3 mr-1" /> New Template
        </Button>

        {isLoading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : templates.length === 0 && !isNew ? (
          <p className="text-xs text-muted-foreground text-center py-6">No templates yet</p>
        ) : (
          <div className="space-y-1.5">
            {templates.map((t) => (
              <button
                key={t.id}
                onClick={() => loadTemplate(t)}
                className={cn(
                  "w-full text-left rounded-lg border px-3 py-2.5 transition-colors",
                  selectedId === t.id
                    ? "border-primary bg-primary/5"
                    : "border-border hover:border-primary/50 hover:bg-muted/50",
                )}
              >
                <p className="text-sm font-medium truncate">{t.name}</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {t.requires_scheduling && (
                    <span className="text-[10px] bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300 rounded-full px-1.5 py-0.5">Schedule</span>
                  )}
                  {t.requires_dispatch && (
                    <span className="text-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300 rounded-full px-1.5 py-0.5">Dispatch</span>
                  )}
                  <span className="text-[10px] text-muted-foreground">
                    {t.schema.sections.reduce((sum, s) => sum + s.fields.length, 0)} fields
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Right: Editor */}
      {showEditor ? (
        <div className="space-y-4">
          <Card>
            <CardContent className="p-4 space-y-3">
              <p className="text-sm font-semibold">{isNew ? "New Template" : "Template Settings"}</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Template name *"
                  className="text-sm h-8"
                />
                <Input
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Description (optional)"
                  className="text-sm h-8"
                />
              </div>
              <div className="border-t border-border pt-3 space-y-2.5">
                <Toggle checked={requiresScheduling} onChange={setRequiresScheduling} label="Requires scheduling (date/time picker in dispatch)" />
                <Toggle checked={requiresAssignment} onChange={setRequiresAssignment} label="Requires assignment (tech must be assigned)" />
                <Toggle checked={requiresDispatch} onChange={setRequiresDispatch} label="Requires dispatch (sends SMS to technician)" />
              </div>
            </CardContent>
          </Card>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold">Form Sections</p>
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={addSection}>
                <Plus className="h-3 w-3 mr-1" /> Add Section
              </Button>
            </div>

            {sections.length === 0 ? (
              <div className="rounded-lg border border-dashed p-8 text-center">
                <p className="text-xs text-muted-foreground">No sections yet.</p>
                <p className="text-xs text-muted-foreground mt-0.5">Add sections to build your job form.</p>
                <Button size="sm" className="h-7 text-xs mt-3" onClick={addSection}>
                  <Plus className="h-3 w-3 mr-1" /> Add First Section
                </Button>
              </div>
            ) : (
              sections.map((section, i) => (
                <SectionEditor
                  key={i}
                  section={section}
                  index={i}
                  onChange={(s) => updateSection(i, s)}
                  onDelete={() => setSections(sections.filter((_, j) => j !== i))}
                />
              ))
            )}
          </div>

          <div className="flex items-center gap-2 pt-1 pb-4">
            <Button className="h-8" onClick={handleSave} disabled={!name.trim() || isSaving}>
              {isSaving
                ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
                : <Check className="h-3.5 w-3.5 mr-1.5" />}
              {isNew ? "Create Template" : "Save Changes"}
            </Button>
            {!isNew && selectedId && (
              <Button
                size="sm"
                variant="ghost"
                className="h-8 text-xs text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
                onClick={() => {
                  if (window.confirm("Delete this template?")) {
                    deleteMutation.mutate(selectedId);
                  }
                }}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending
                  ? <Loader2 className="h-3 w-3 animate-spin mr-1" />
                  : <Trash2 className="h-3.5 w-3.5 mr-1" />}
                Delete
              </Button>
            )}
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-center rounded-lg border border-dashed p-12 text-center">
          <div>
            <p className="text-sm text-muted-foreground">Select a template to edit</p>
            <p className="text-xs text-muted-foreground mt-1">or create a new one</p>
          </div>
        </div>
      )}
    </div>
  );
}
