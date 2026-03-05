import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api, DealResponse, DealDocSlot, ArchivedDoc, LockedFileDoc } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ArrowLeft, ExternalLink, FileText, FileType, File, ChevronDown, Lock } from "lucide-react";
import { cn } from "@/lib/utils";

const TYPE_LABELS: Record<string, string> = {
  pitch_deck: "Pitch Deck",
  investment_memo: "Investment Memo",
  prescreening_report: "Prescreening Report",
  meeting_minutes: "Meeting Minutes",
};

const DOC_TYPES = ["pitch_deck", "investment_memo", "prescreening_report", "meeting_minutes"] as const;

function driveUrl(fileId: string) {
  return `https://drive.google.com/file/d/${fileId}/view`;
}

function formatName(raw: string) {
  return raw.replace(/\.[^/.]+$/, "").replace(/[_-]+/g, " ");
}

function formatDate(raw: string | null) {
  if (!raw) return "—";
  const d = new Date(raw);
  if (isNaN(d.getTime())) return raw;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

function getFileIcon(name: string) {
  const lower = name.toLowerCase();
  if (lower.endsWith(".pdf")) return <FileText className="h-6 w-6" />;
  if (lower.endsWith(".pptx") || lower.endsWith(".ppt")) return <FileType className="h-6 w-6" />;
  return <File className="h-6 w-6" />;
}

function getIconBg(name: string) {
  const lower = name.toLowerCase();
  if (lower.endsWith(".pdf")) return "bg-red-500/15 text-red-400";
  if (lower.endsWith(".pptx") || lower.endsWith(".ppt")) return "bg-amber-500/15 text-amber-400";
  if (lower.endsWith(".docx") || lower.endsWith(".doc")) return "bg-blue-500/15 text-blue-400";
  return "bg-muted text-muted-foreground";
}

function DocSlotCard({ doc, label }: { doc: DealDocSlot; label: string }) {
  return (
    <a
      href={driveUrl(doc.file_id)}
      target="_blank"
      rel="noreferrer"
      className="group flex flex-col gap-3 rounded-xl border border-border bg-card p-5 transition-all duration-150 hover:border-primary/40 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${getIconBg(doc.name)}`}>
          {getFileIcon(doc.name)}
        </div>
        <ExternalLink className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
      </div>
      <div>
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="mt-1 line-clamp-2 text-sm font-medium text-foreground">{formatName(doc.name)}</p>
        {doc.description && (
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{doc.description}</p>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{formatDate(doc.date)}</p>
    </a>
  );
}

function EmptySlotCard({ label }: { label: string }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-dashed border-border p-5 opacity-50">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
        <File className="h-6 w-6 text-muted-foreground" />
      </div>
      <div>
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="mt-1 text-sm text-muted-foreground">Not available</p>
      </div>
    </div>
  );
}

const DealDetail = () => {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();
  const { dealId } = useParams<{ dealId: string }>();
  const [deal, setDeal] = useState<DealResponse | null>(null);
  const [fetching, setFetching] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) navigate("/", { replace: true });
  }, [user, isLoading, navigate]);

  useEffect(() => {
    if (!user || !dealId) return;
    setFetching(true);
    api.getDeal(Number(dealId))
      .then(setDeal)
      .catch(() => navigate("/documents", { replace: true }))
      .finally(() => setFetching(false));
  }, [user, dealId, navigate]);

  if (isLoading || !user) return null;

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-4xl px-6 pt-24 pb-16">
        {/* Back */}
        <button
          onClick={() => navigate("/documents")}
          className="mb-6 flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Deals
        </button>

        {fetching && (
          <>
            <Skeleton className="h-8 w-48 mb-2" />
            <Skeleton className="h-4 w-32 mb-8" />
            <div className="grid gap-4 sm:grid-cols-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-40 rounded-xl" />
              ))}
            </div>
          </>
        )}

        {!fetching && deal && (
          <>
            <h1 className="font-heading text-3xl font-semibold text-foreground">{deal.name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {deal.doc_count} of 4 document{deal.doc_count !== 1 ? "s" : ""} available
            </p>

            {/* Analysis metadata */}
            <div className="mt-5 flex flex-wrap items-center gap-3">
              {/* Investment type */}
              {deal.investment_type && (() => {
                const styles: Record<string, string> = {
                  Fund: "bg-indigo-500/15 text-indigo-400 border-transparent",
                  Direct: "bg-amber-500/15 text-amber-400 border-transparent",
                  "Co-Investment": "bg-purple-500/15 text-purple-400 border-transparent",
                };
                return (
                  <Badge className={cn("text-xs font-medium", styles[deal.investment_type] ?? "border-muted-foreground/30 text-muted-foreground")}>
                    {deal.investment_type}
                  </Badge>
                );
              })()}

              {/* Deal status */}
              {deal.deal_status ? (
                <Badge
                  className={cn(
                    "border-transparent font-semibold",
                    deal.deal_status === "accepted"
                      ? "bg-emerald-500/15 text-emerald-400"
                      : "bg-red-500/15 text-red-400",
                  )}
                >
                  {deal.deal_status === "accepted" ? "✓ Accepted" : "✕ Rejected"}
                </Badge>
              ) : (
                <Badge variant="outline" className="border-muted-foreground/30 text-muted-foreground text-xs">
                  Pending analysis
                </Badge>
              )}
            </div>

            {/* IC rationale */}
            {deal.deal_reason && (
              <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                <span className="font-medium text-foreground/70">
                  {deal.deal_status === "accepted" ? "Why accepted: " : deal.deal_status === "rejected" ? "Why rejected: " : ""}
                </span>
                {deal.deal_reason}
              </p>
            )}

            {/* 2×2 document slots */}
            <div className="mt-8 grid gap-4 sm:grid-cols-2">
              {DOC_TYPES.map((type) => {
                const doc = deal.documents[type];
                return doc ? (
                  <DocSlotCard key={type} doc={doc} label={TYPE_LABELS[type]} />
                ) : (
                  <EmptySlotCard key={type} label={TYPE_LABELS[type]} />
                );
              })}
            </div>

            {/* Archive */}
            {deal.archived.length > 0 && (
              <Collapsible open={archiveOpen} onOpenChange={setArchiveOpen} className="mt-8">
                <CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground">
                  <ChevronDown
                    className={`h-4 w-4 transition-transform duration-200 ${archiveOpen ? "rotate-180" : ""}`}
                  />
                  Archive ({deal.archived.length})
                </CollapsibleTrigger>
                <CollapsibleContent className="mt-3">
                  <div className="rounded-xl border border-border divide-y divide-border">
                    {deal.archived.map((doc) => (
                      <ArchivedRow key={doc.id} doc={doc} />
                    ))}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            )}

            {/* Password-protected files */}
            {deal.locked_files && deal.locked_files.length > 0 && (
              <div className="mt-8">
                <h2 className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                  <Lock className="h-4 w-4" />
                  Password Protected ({deal.locked_files.length})
                </h2>
                <div className="mt-3 rounded-xl border border-border divide-y divide-border">
                  {deal.locked_files.map((f: LockedFileDoc) => (
                    <div key={f.id} className="flex items-center gap-4 px-4 py-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted/50">
                        <Lock className="h-4 w-4 text-muted-foreground/50" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-muted-foreground">{formatName(f.name)}</p>
                        {f.date && <p className="text-xs text-muted-foreground/60">{formatDate(f.date)}</p>}
                      </div>
                      <span className="shrink-0 rounded-full border border-yellow-500/30 bg-yellow-500/10 px-2 py-0.5 text-[10px] font-medium text-yellow-400">
                        Locked
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
};

function ArchivedRow({ doc }: { doc: ArchivedDoc }) {
  return (
    <a
      href={driveUrl(doc.file_id)}
      target="_blank"
      rel="noreferrer"
      className="group flex items-center gap-4 px-4 py-3 transition-colors hover:bg-muted/50"
    >
      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${getIconBg(doc.name)}`}>
        {getFileIcon(doc.name)}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{formatName(doc.name)}</p>
        <p className="text-xs text-muted-foreground">{formatDate(doc.date)}</p>
      </div>
      <Badge variant="outline" className="shrink-0 border-muted text-[10px] text-muted-foreground">
        {TYPE_LABELS[doc.type] ?? doc.type}
      </Badge>
      <ExternalLink className="h-4 w-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
    </a>
  );
}

export default DealDetail;
