import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { FileText, FileType, File, ExternalLink } from "lucide-react";

interface Doc {
  id: number;
  file_id: string;
  type: string;
  name: string;
  date: string | null;
  description: string | null;
  status: string;
}

const TYPE_LABELS: Record<string, string> = {
  pitch_deck: "Pitch Deck",
  investment_report: "Investment Report",
  deal_memo: "Deal Memo",
  financial_report: "Financial Report",
  other: "Other",
};

const ALL_TYPES = ["all", ...Object.keys(TYPE_LABELS)];

function getFileIcon(name: string) {
  const lower = name.toLowerCase();
  if (lower.endsWith(".pdf"))
    return <FileText className="h-8 w-8" />;
  if (lower.endsWith(".pptx") || lower.endsWith(".ppt"))
    return <FileType className="h-8 w-8" />;
  return <File className="h-8 w-8" />;
}

function getIconBg(name: string): string {
  const lower = name.toLowerCase();
  if (lower.endsWith(".pdf")) return "bg-red-500/15 text-red-400";
  if (lower.endsWith(".pptx") || lower.endsWith(".ppt")) return "bg-amber-500/15 text-amber-400";
  if (lower.endsWith(".docx") || lower.endsWith(".doc")) return "bg-blue-500/15 text-blue-400";
  return "bg-muted text-muted-foreground";
}

function formatName(raw: string): string {
  return raw.replace(/\.[^/.]+$/, "").replace(/[_-]+/g, " ");
}

function formatDate(raw: string | null): string {
  if (!raw) return "—";
  const d = new Date(raw);
  if (isNaN(d.getTime())) return raw;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

function driveUrl(fileId: string): string {
  return `https://drive.google.com/file/d/${fileId}/view`;
}

const Documents = () => {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [fetching, setFetching] = useState(false);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    if (!isLoading && !user) navigate("/", { replace: true });
  }, [user, isLoading, navigate]);

  useEffect(() => {
    if (!user) return;
    setFetching(true);
    api.getAllDocuments().then(setDocs).catch(() => null).finally(() => setFetching(false));
  }, [user]);

  if (isLoading || !user) return null;

  const visible = filter === "all" ? docs : docs.filter((d) => d.type === filter);

  return (
    <TooltipProvider>
      <div className="min-h-screen bg-background">
        <Navbar />
        <main className="mx-auto max-w-6xl px-6 pt-24 pb-16">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="font-heading text-3xl font-semibold text-foreground">Documents</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {docs.length} processed document{docs.length !== 1 ? "s" : ""}
              </p>
            </div>
          </div>

          {/* Filter bar */}
          <div className="mt-6 flex flex-wrap gap-2">
            {ALL_TYPES.map((t) => (
              <Button
                key={t}
                variant={filter === t ? "default" : "outline"}
                size="sm"
                onClick={() => setFilter(t)}
                className={
                  filter === t
                    ? "bg-primary text-primary-foreground"
                    : "border-border text-muted-foreground hover:text-foreground"
                }
              >
                {t === "all" ? "All" : TYPE_LABELS[t]}
              </Button>
            ))}
          </div>

          {/* Grid */}
          <div className="mt-8 grid gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
            {fetching &&
              Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex flex-col items-center gap-2 p-4">
                  <Skeleton className="h-16 w-16 rounded-xl" />
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="h-3 w-16" />
                </div>
              ))}

            {!fetching && visible.length === 0 && (
              <p className="col-span-full pt-12 text-center text-sm text-muted-foreground">
                No documents found.
              </p>
            )}

            {!fetching &&
              visible.map((doc) => (
                <Tooltip key={doc.id}>
                  <TooltipTrigger asChild>
                    <button
                      className="group flex cursor-pointer flex-col items-center gap-3 rounded-xl border border-transparent p-4 text-center transition-all duration-150 hover:border-border hover:bg-card focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                      onDoubleClick={() => window.open(driveUrl(doc.file_id), "_blank")}
                      aria-label={`Open ${doc.name} in Google Drive`}
                    >
                      {/* Icon */}
                      <div
                        className={`flex h-16 w-16 items-center justify-center rounded-xl ${getIconBg(doc.name)} transition-transform duration-150 group-hover:scale-105`}
                      >
                        {getFileIcon(doc.name)}
                      </div>

                      {/* Name */}
                      <span className="line-clamp-2 w-full text-xs font-medium text-foreground">
                        {formatName(doc.name)}
                      </span>

                      {/* Meta */}
                      <div className="flex flex-col items-center gap-1">
                        <Badge
                          variant="outline"
                          className="border-primary/30 px-1.5 py-0 text-[10px] text-primary"
                        >
                          {TYPE_LABELS[doc.type] ?? doc.type}
                        </Badge>
                        <span className="text-[10px] text-muted-foreground">
                          {formatDate(doc.date)}
                        </span>
                      </div>

                      {/* Open link on hover */}
                      <a
                        href={driveUrl(doc.file_id)}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="flex items-center gap-1 text-[10px] text-muted-foreground opacity-0 transition-opacity duration-150 group-hover:opacity-100 hover:text-primary"
                      >
                        <ExternalLink className="h-3 w-3" />
                        Open in Drive
                      </a>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom" className="max-w-xs text-xs">
                    {doc.description ?? doc.name}
                  </TooltipContent>
                </Tooltip>
              ))}
          </div>
        </main>
      </div>
    </TooltipProvider>
  );
};

export default Documents;
