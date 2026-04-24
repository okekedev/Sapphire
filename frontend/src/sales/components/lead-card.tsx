import { useState, useRef, useEffect } from "react";
import {
  ChevronDown, Send, Loader2, ArrowRight, Pencil, X,
  DollarSign, StickyNote, Save, FileText, MessageSquare,
} from "lucide-react";
import { MarkdownMessage } from "@/shared/components/ui/markdown-message";
import { ScoreBadge } from "@/shared/components/ui/score-badge";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { formatDateShort } from "@/shared/lib/format";
import { cn } from "@/shared/lib/utils";
import { sendEmployeeChat } from "@/shared/api/chat";
import type { CustomerItem } from "@/sales/api/sales";

function stripPriority(text: string): string {
  return text.replace(/^(HIGH PRIORITY|PRIORITY|URGENT|LOW PRIORITY|MEDIUM PRIORITY)\s*[:—\-]\s*/i, "").trim();
}

export function LeadCard({
  lead,
  businessId,
  employeeId,
  onConvert,
  onUpdateNotes,
  isPending,
}: {
  lead: CustomerItem;
  businessId: string;
  employeeId: string;
  onConvert: (title: string, description?: string, estimate?: number) => void;
  onUpdateNotes: (notes: string) => void;
  isPending: boolean;
}) {
  const [showConvert, setShowConvert] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const [showMiniChat, setShowMiniChat] = useState(false);
  const [notesExpanded, setNotesExpanded] = useState(false);
  const [transcriptExpanded, setTranscriptExpanded] = useState(false);
  const [notesText, setNotesText] = useState(lead.notes || "");
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<HTMLInputElement>(null);
  const [jobEstimate, setJobEstimate] = useState("");
  const [jobTitle, setJobTitle] = useState(() => {
    if (lead.call_category && lead.full_name) return `${lead.call_category} — ${lead.full_name}`;
    return `Service for ${lead.full_name || "Customer"}`;
  });
  const [jobDescription, setJobDescription] = useState(() => {
    const parts: string[] = [];
    if (lead.call_summary) parts.push(lead.call_summary);
    if (lead.suggested_action) parts.push(`Next step: ${lead.suggested_action}`);
    if (lead.campaign_name) parts.push(`Source: ${lead.campaign_name}`);
    return parts.join("\n") || "";
  });

  useEffect(() => { setNotesText(lead.notes || ""); }, [lead.notes]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chatMessages]);
  useEffect(() => { if (showMiniChat) chatInputRef.current?.focus(); }, [showMiniChat]);

  const handleMiniChatSend = async () => {
    const msg = chatInput.trim();
    if (!msg || chatLoading) return;
    setChatMessages((prev) => [...prev, { role: "user" as const, content: msg }]);
    setChatInput("");
    setChatLoading(true);
    const leadContext = [
      `[Lead context — keep responses concise, 2-4 sentences, markdown formatting]`,
      `Lead: ${lead.full_name || "Unknown"}`,
      lead.phone ? `Phone: ${lead.phone}` : null,
      lead.call_summary ? `Call summary: ${lead.call_summary}` : null,
      lead.transcript ? `Transcript:\n${lead.transcript}` : null,
      lead.suggested_action ? `Recommendation: ${lead.suggested_action}` : null,
      lead.notes ? `Existing notes:\n${lead.notes}` : null,
    ].filter(Boolean).join("\n");
    try {
      const res = await sendEmployeeChat({
        business_id: businessId,
        employee_id: employeeId,
        messages: chatMessages.map((m) => ({ role: m.role, content: m.content })),
        user_message: `${leadContext}\n\nQuestion: ${msg}`,
      });
      setChatMessages((prev) => [...prev, { role: "assistant" as const, content: res.content }]);
      const timestamp = new Date().toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
      const noteEntry = `**${timestamp}** — _${msg}_\n${res.content}`;
      const updatedNotes = lead.notes ? `${lead.notes}\n\n---\n\n${noteEntry}` : noteEntry;
      onUpdateNotes(updatedNotes);
    } catch {
      setChatMessages((prev) => [...prev, { role: "assistant", content: "Sorry, something went wrong. Try again." }]);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <p className="font-semibold text-sm">{lead.full_name || "Unknown"}</p>
              <ScoreBadge score={lead.score} />
            </div>
            <p className="text-xs text-muted-foreground font-mono">{lead.phone || "—"}</p>
          </div>
          <span className="text-[11px] text-muted-foreground">{formatDateShort(lead.created_at)}</span>
        </div>

        {(lead.call_summary || lead.transcript) && (
          <div className="text-xs space-y-1.5">
            <p className="text-[10px] font-semibold uppercase text-muted-foreground mb-0.5">Summary</p>
            {lead.call_summary && <p className="text-foreground/80 leading-relaxed">{lead.call_summary}</p>}
            {lead.transcript && (
              <>
                <button
                  onClick={() => setTranscriptExpanded(!transcriptExpanded)}
                  className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  <FileText className="h-3 w-3" />
                  <span>View transcript</span>
                  <ChevronDown className={cn("h-3 w-3 transition-transform", transcriptExpanded && "rotate-180")} />
                </button>
                {transcriptExpanded && (
                  <div className="rounded-md border bg-muted/30 p-3 max-h-[300px] overflow-y-auto">
                    <p className="text-xs text-foreground/80 leading-relaxed whitespace-pre-wrap">{lead.transcript}</p>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {lead.notes && (
          <div className="text-xs">
            <button
              onClick={() => setNotesExpanded(!notesExpanded)}
              className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors mb-1"
            >
              <StickyNote className="h-3 w-3" />
              <span>Notes</span>
              <ChevronDown className={cn("h-3 w-3 transition-transform", notesExpanded && "rotate-180")} />
            </button>
            {notesExpanded && (
              <div className="rounded-md border bg-muted/30 p-3 max-h-[200px] overflow-y-auto">
                <div className="text-xs text-foreground/80 leading-relaxed whitespace-pre-wrap">
                  <MarkdownMessage content={lead.notes!} />
                </div>
              </div>
            )}
          </div>
        )}

        {lead.suggested_action && (
          <div className="rounded-md bg-blue-50 dark:bg-blue-950/50 px-3 py-2">
            <p className="text-[10px] font-semibold uppercase text-blue-600 dark:text-blue-400 mb-0.5">Recommendation</p>
            <p className="text-xs text-blue-700 dark:text-blue-300">{stripPriority(lead.suggested_action)}</p>
          </div>
        )}

        {showMiniChat && (
          <div className="space-y-2 rounded-md border p-3 bg-muted/30">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-semibold text-muted-foreground">Quick Notes</p>
              <button onClick={() => setShowMiniChat(false)} className="text-muted-foreground hover:text-foreground"><X className="h-3 w-3" /></button>
            </div>
            {chatMessages.length > 0 && (
              <div className="max-h-[200px] overflow-y-auto space-y-2">
                {chatMessages.map((m, i) => (
                  <div key={i} className={cn("text-xs rounded-md px-2.5 py-1.5", m.role === "user" ? "bg-primary/10 text-foreground" : "bg-background border text-foreground/80")}>
                    {m.role === "assistant" ? <MarkdownMessage content={m.content} /> : <p>{m.content}</p>}
                  </div>
                ))}
                {chatLoading && (
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground px-2.5 py-1.5">
                    <Loader2 className="h-3 w-3 animate-spin" /> Thinking...
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            )}
            <div className="flex gap-1.5">
              <Input
                ref={chatInputRef}
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleMiniChatSend()}
                placeholder="Ask about this lead..."
                className="text-xs h-7 flex-1"
                disabled={chatLoading}
              />
              <Button size="sm" className="h-7 w-7 p-0" onClick={handleMiniChatSend} disabled={!chatInput.trim() || chatLoading}>
                <Send className="h-3 w-3" />
              </Button>
            </div>
          </div>
        )}

        {showNotes && (
          <div className="space-y-2 rounded-md border p-3 bg-muted/30">
            <p className="text-[11px] font-semibold text-muted-foreground">Edit Notes</p>
            <textarea
              value={notesText}
              onChange={(e) => setNotesText(e.target.value)}
              placeholder="Add notes about this lead..."
              className="w-full rounded-md border bg-background px-3 py-2 text-xs min-h-[60px] resize-none outline-none focus:border-primary"
              autoFocus
            />
            <div className="flex gap-2">
              <Button size="sm" className="h-7 text-xs" onClick={() => { onUpdateNotes(notesText); setShowNotes(false); }} disabled={isPending}>
                {isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <><Save className="mr-1 h-3 w-3" /> Save</>}
              </Button>
              <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setShowNotes(false)}>Cancel</Button>
            </div>
          </div>
        )}

        {showConvert && (
          <div className="space-y-2 rounded-md border p-3 bg-muted/30">
            <p className="text-[11px] font-semibold text-muted-foreground">Convert to Job</p>
            <div className="flex items-center gap-1.5">
              <Pencil className="h-3 w-3 text-muted-foreground flex-shrink-0" />
              <Input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} placeholder="Job title" className="text-xs h-8" />
            </div>
            <textarea
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              placeholder="Description"
              className="w-full rounded-md border bg-background px-3 py-2 text-xs min-h-[60px] resize-none outline-none focus:border-primary"
            />
            <div className="flex items-center gap-1.5">
              <DollarSign className="h-3 w-3 text-muted-foreground flex-shrink-0" />
              <Input type="number" value={jobEstimate} onChange={(e) => setJobEstimate(e.target.value)} placeholder="Estimate (optional)" className="text-xs h-8" min="0" step="0.01" />
            </div>
            <div className="flex gap-2">
              <Button size="sm" className="h-7 text-xs" onClick={() => onConvert(jobTitle, jobDescription || undefined, jobEstimate ? parseFloat(jobEstimate) : undefined)} disabled={!jobTitle.trim() || isPending}>
                {isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Create Job"}
              </Button>
              <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setShowConvert(false)}>Cancel</Button>
            </div>
          </div>
        )}

        {!showConvert && !showNotes && !showMiniChat && (
          <div className="flex gap-2">
            <Button size="sm" className="h-7 flex-1 text-xs" onClick={() => setShowConvert(true)} disabled={isPending}>
              <ArrowRight className="mr-1 h-3 w-3" /> Convert to Job
            </Button>
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setShowNotes(true)} title="Edit notes">
              <StickyNote className="h-3 w-3" />
            </Button>
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setShowMiniChat(true)} title="Quick AI notes">
              <MessageSquare className="h-3 w-3" />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
