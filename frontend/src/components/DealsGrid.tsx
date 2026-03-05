import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import DealCard, { type Deal } from "./DealCard";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";

const DealsGrid = () => {
  const { user } = useAuth();
  const [deals, setDeals] = useState<Deal[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!user) return;
    setIsLoading(true);
    api
      .getDeals()
      .then(setDeals)
      .catch(() => null)
      .finally(() => setIsLoading(false));
  }, [user]);

  // Split into two rows: analysed (have status) and pending
  const analysed = deals.filter((d) => d.deal_status !== null);
  const pending = deals.filter((d) => d.deal_status === null);

  return (
    <motion.section
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.6 }}
      className="mx-auto max-w-6xl px-6 py-24"
    >
      <h2 className="font-heading text-3xl font-semibold text-foreground">Deals</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Investment opportunities — classification, IC decision, and source documents.
      </p>

      {isLoading && (
        <p className="mt-10 text-sm text-muted-foreground">Loading…</p>
      )}

      {!isLoading && deals.length === 0 && (
        <p className="mt-10 text-sm text-muted-foreground">
          {user
            ? "No deals found yet. Run the worker after setting a Drive folder."
            : "Sign in to view your deals."}
        </p>
      )}

      {/* Analysed deals */}
      {analysed.length > 0 && (
        <>
          <div className="mt-8 flex items-center gap-3">
            <span className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
              Analysed
            </span>
            <span className="h-px flex-1 bg-border" />
          </div>
          <div className="mt-4 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {analysed.map((deal) => (
              <DealCard key={deal.id} deal={deal} />
            ))}
          </div>
        </>
      )}

      {/* Pending deals */}
      {pending.length > 0 && (
        <>
          <div className="mt-10 flex items-center gap-3">
            <span className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
              Pending analysis
            </span>
            <span className="h-px flex-1 bg-border" />
          </div>
          <div className="mt-4 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {pending.map((deal) => (
              <DealCard key={deal.id} deal={deal} />
            ))}
          </div>
        </>
      )}
    </motion.section>
  );
};

export default DealsGrid;
