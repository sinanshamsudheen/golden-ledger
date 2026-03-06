import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api, DealResponse } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Folder, FolderOpen } from "lucide-react";

const Documents = () => {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();
  const [deals, setDeals] = useState<DealResponse[]>([]);
  const [fetching, setFetching] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) navigate("/", { replace: true });
  }, [user, isLoading, navigate]);

  useEffect(() => {
    if (!user) return;
    setFetching(true);
    api.getDeals().then(setDeals).catch(() => null).finally(() => setFetching(false));
  }, [user]);

  if (isLoading || !user) return null;

  // Separate deals with docs from ungrouped (deal_count === 0 filtered out server-side,
  // but the "Uncategorized" pseudo-deal is handled by the backend eventually)
  const dealsWithDocs = deals
    .filter((d) => d.doc_count > 0 || d.archived.length > 0)
    .sort((a, b) => {
      const filledA = Object.values(a.documents).filter(Boolean).length;
      const filledB = Object.values(b.documents).filter(Boolean).length;
      return filledB - filledA; // most complete first
    });

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-6xl px-6 pt-24 pb-16">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-heading text-3xl font-semibold text-foreground">Deals</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {user.company_name && (
                <span className="font-medium text-foreground">{user.company_name} · </span>
              )}
              {dealsWithDocs.length} deal{dealsWithDocs.length !== 1 ? "s" : ""}
            </p>
          </div>
        </div>

        {/* Skeleton */}
        {fetching && (
          <div className="mt-8 grid gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex flex-col gap-3 rounded-xl border border-border p-5">
                <Skeleton className="h-10 w-10 rounded-lg" />
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-20" />
              </div>
            ))}
          </div>
        )}

        {/* Empty state */}
        {!fetching && dealsWithDocs.length === 0 && (
          <p className="mt-16 text-center text-sm text-muted-foreground">
            No deals found. Run the worker after configuring your Drive folder.
          </p>
        )}

        {/* Deal folder grid */}
        {!fetching && dealsWithDocs.length > 0 && (
          <div className="mt-8 grid gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {dealsWithDocs.map((deal) => (
              <DealCard key={deal.id} deal={deal} onClick={() => navigate(`/documents/${deal.id}`)} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
};

function DealCard({ deal, onClick }: { deal: DealResponse; onClick: () => void }) {
  const [hovered, setHovered] = useState(false);

  const filledSlots = Object.values(deal.documents).filter(Boolean).length;
  const totalSlots = 4;

  return (
    <button
      className="group flex cursor-pointer flex-col gap-4 rounded-xl border border-border bg-card p-5 text-left transition-all duration-150 hover:border-primary/40 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Folder icon */}
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary transition-colors duration-150 group-hover:bg-primary/20">
        {hovered ? (
          <FolderOpen className="h-7 w-7" />
        ) : (
          <Folder className="h-7 w-7" />
        )}
      </div>

      {/* Deal name */}
      <div className="flex-1">
        <p className="font-medium text-foreground line-clamp-2">{deal.name}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {filledSlots}/{totalSlots} documents
        </p>
      </div>

      {/* Doc type badges */}
      <div className="flex flex-wrap gap-1">
        {(["pitch_deck", "investment_memo", "prescreening_report", "meeting_minutes"] as const).map(
          (type) => (
            <span
              key={type}
              className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${
                deal.documents[type]
                  ? "bg-primary/15 text-primary"
                  : "bg-muted text-muted-foreground/50"
              }`}
            >
              {TYPE_SHORT[type]}
            </span>
          )
        )}
      </div>

      {/* Archive badge */}
      {deal.archived.length > 0 && (
        <Badge variant="outline" className="w-fit border-muted text-[10px] text-muted-foreground">
          {deal.archived.length} archived
        </Badge>
      )}
    </button>
  );
}

const TYPE_SHORT: Record<string, string> = {
  pitch_deck: "Deck",
  investment_memo: "Memo",
  prescreening_report: "Pre-screen",
  meeting_minutes: "Minutes",
};

export default Documents;
