import { useState } from "react";
import { ChevronDown, Clock, FileText, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { ScoreBadge } from "@/shared/components/ui/score-badge";
import { formatDuration } from "@/shared/lib/format";
import { cn, timeAgo } from "@/shared/lib/utils";
import type { ProspectItem } from "@/sales/api/sales";

export function ProspectCard({
  prospect,
  onQualify,
  isPending,
}: {
  prospect: ProspectItem;
  onQualify: (decision: "lead" | "no_lead", reason?: string, leadSummary?: string) => void;
  isPending: boolean;
}) {
  const [transcriptExpanded, setTranscriptExpanded] = useState(false);
  const [showNoLeadInput, setShowNoLeadInput] = useState(false);
  const [noLeadReason, setNoLeadReason] = useState(
    prospect.call_category === "spam" ? "Spam / robocall" : "",
  );

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <p className="font-semibold text-sm">{prospect.caller_name || "Unknown Caller"}</p>
              <ScoreBadge score={prospect.score} />
            </div>
            <p className="text-xs text-muted-foreground font-mono">{prospect.caller_phone || "—"}</p>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            {prospect.duration_s != null && (
              <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {formatDuration(prospect.duration_s)}</span>
            )}
            <span>{timeAgo(prospect.created_at)}</span>
          </div>
        </div>

        {prospect.transcript && (
          <div className="text-xs">
            <button
              onClick={() => setTranscriptExpanded(!transcriptExpanded)}
              className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors mb-1"
            >
              <FileText className="h-3 w-3" />
              <span>Transcript</span>
              <ChevronDown className={cn("h-3 w-3 transition-transform", transcriptExpanded && "rotate-180")} />
            </button>
            {transcriptExpanded && (
              <div className="rounded-md border bg-muted/30 p-3 max-h-[300px] overflow-y-auto">
                <p className="text-xs text-foreground/80 leading-relaxed whitespace-pre-wrap">{prospect.transcript}</p>
              </div>
            )}
          </div>
        )}

        {prospect.call_summary && (
          <div className="text-xs">
            <p className="text-[10px] font-semibold uppercase text-muted-foreground mb-0.5">Summary</p>
            <p className="text-foreground/80 leading-relaxed">{prospect.call_summary}</p>
          </div>
        )}

        {prospect.recording_url && (
          <audio controls src={prospect.recording_url} className="w-full h-8" preload="none" />
        )}

        {showNoLeadInput && (
          <div className="space-y-2 rounded-md border p-3 bg-muted/30">
            <p className="text-[11px] font-semibold text-muted-foreground">Why not a lead?</p>
            <Input
              value={noLeadReason}
              onChange={(e) => setNoLeadReason(e.target.value)}
              placeholder="AI-suggested reason — edit if needed"
              className="text-xs h-8"
            />
            <div className="flex gap-2">
              <Button size="sm" variant="destructive" className="h-7 text-xs" onClick={() => onQualify("no_lead", noLeadReason)} disabled={isPending}>
                {isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Confirm No Lead"}
              </Button>
              <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setShowNoLeadInput(false)}>Cancel</Button>
            </div>
          </div>
        )}

        {!showNoLeadInput && (
          <div className="flex gap-2">
            <Button size="sm" className="h-7 flex-1 text-xs" onClick={() => onQualify("lead", undefined, prospect.call_summary || undefined)} disabled={isPending}>
              {isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <><CheckCircle2 className="mr-1 h-3 w-3" /> Lead</>}
            </Button>
            <Button size="sm" variant="outline" className="h-7 flex-1 text-xs" onClick={() => setShowNoLeadInput(true)} disabled={isPending}>
              <XCircle className="mr-1 h-3 w-3" /> No Lead
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
