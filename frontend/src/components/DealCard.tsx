import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { DealDocSlot, DealDocSlots, DealResponse } from "@/lib/api";

export type { DealDocSlot, DealDocSlots };
export type Deal = DealResponse;

// ── Constants ─────────────────────────────────────────────────────────────────

const DOC_TYPE_LABELS: Record<string, string> = {
  pitch_deck: "Pitch Deck",
  investment_memo: "Investment Memo",
  prescreening_report: "Pre-screening",
  meeting_minutes: "Meeting Minutes",
};

const DOC_TYPE_ORDER = [
  "pitch_deck",
  "investment_memo",
  "prescreening_report",
  "meeting_minutes",
] as const;

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatName(raw: string): string {
  return raw.replace(/\.[^/.]+$/, "").replace(/[_-]+/g, " ");
}

function formatDate(raw: string | null): string {
  if (!raw) return "";
  const d = new Date(raw);
  if (isNaN(d.getTime())) return raw;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string | null }) {
  if (!status) {
    return (
      <Badge variant="outline" className="border-muted-foreground/30 text-muted-foreground">
        Pending analysis
      </Badge>
    );
  }
  const accepted = status === "accepted";
  return (
    <Badge
      className={cn(
        "border-transparent font-semibold",
        accepted
          ? "bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25"
          : "bg-red-500/15 text-red-400 hover:bg-red-500/25",
      )}
    >
      {accepted ? "✓ Accepted" : "✕ Rejected"}
    </Badge>
  );
}

function InvestmentTypeBadge({ type }: { type: string | null }) {
  if (!type) return null;
  const styles: Record<string, string> = {
    Fund: "bg-indigo-500/15 text-indigo-400 border-transparent",
    Direct: "bg-amber-500/15 text-amber-400 border-transparent",
    "Co-Investment": "bg-purple-500/15 text-purple-400 border-transparent",
  };
  return (
    <Badge className={cn("text-xs font-medium", styles[type] ?? "border-muted-foreground/30 text-muted-foreground")}>
      {type}
    </Badge>
  );
}

function DocSlot({
  typeKey,
  slot,
}: {
  typeKey: string;
  slot: DealDocSlot | null;
}) {
  const label = DOC_TYPE_LABELS[typeKey] ?? typeKey;

  if (!slot) {
    return (
      <div className="flex items-start gap-2.5 opacity-35">
        <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground" />
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2.5">
      <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
      <div className="min-w-0">
        <p className="truncate text-xs font-medium text-foreground">
          {formatName(slot.name)}
        </p>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2">
          {slot.date && (
            <span className="text-[10px] text-muted-foreground">{formatDate(slot.date)}</span>
          )}
          {slot.vectorizer_doc_id && (
            <span
              className="font-mono text-[10px] text-muted-foreground/60"
              title={`Vectorizer doc ID: ${slot.vectorizer_doc_id}`}
            >
              #{slot.vectorizer_doc_id.slice(0, 8)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const DealCard = ({ deal }: { deal: Deal }) => {
  return (
    <motion.div
      whileHover={{ y: -4, borderColor: "hsl(38 38% 60%)" }}
      transition={{ duration: 0.2 }}
      className="flex flex-col rounded-lg border border-border bg-card p-6 transition-shadow duration-300 hover:shadow-[0_0_20px_hsl(38_38%_60%/0.08)]"
    >
      {/* Header row */}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="font-heading text-base font-semibold text-foreground leading-tight">
          {deal.name}
        </h3>
        <StatusBadge status={deal.deal_status} />
      </div>

      {/* Investment type */}
      <div className="mt-2">
        <InvestmentTypeBadge type={deal.investment_type} />
      </div>

      {/* Reason */}
      {deal.deal_reason ? (
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground line-clamp-3">
          {deal.deal_reason}
        </p>
      ) : (
        <p className="mt-3 text-xs italic text-muted-foreground/50">
          Analysis pending — run the worker to process this deal.
        </p>
      )}

      {/* Document slots */}
      <div className="mt-5 space-y-2 border-t border-border pt-4">
        {DOC_TYPE_ORDER.map((key) => (
          <DocSlot key={key} typeKey={key} slot={deal.documents[key]} />
        ))}
      </div>
    </motion.div>
  );
};

export default DealCard;
