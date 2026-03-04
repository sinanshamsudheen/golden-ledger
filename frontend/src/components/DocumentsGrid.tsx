import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import DocumentCard from "./DocumentCard";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";

interface Doc {
  type: string;
  name: string;
  date: string | null;
  description: string | null;
}

const TYPE_LABELS: Record<string, string> = {
  pitch_deck: "Pitch Deck",
  investment_report: "Investment Report",
  deal_memo: "Deal Memo",
  financial_report: "Financial Report",
  other: "Other",
};

const DocumentsGrid = () => {
  const { user } = useAuth();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!user) return;
    setIsLoading(true);
    api
      .getLatestDocuments()
      .then(setDocs)
      .catch(() => null)
      .finally(() => setIsLoading(false));
  }, [user]);

  return (
    <motion.section
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.6 }}
      className="mx-auto max-w-6xl px-6 py-24"
    >
      <h2 className="font-heading text-3xl font-semibold text-foreground">
        Latest Documents
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Recently processed investment documents.
      </p>
      <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {isLoading && (
          <p className="col-span-full text-sm text-muted-foreground">Loading…</p>
        )}
        {!isLoading && docs.length === 0 && (
          <p className="col-span-full text-sm text-muted-foreground">
            {user ? "No processed documents yet. Run the worker after setting a folder." : "Sign in to view your documents."}
          </p>
        )}
        {docs.map((doc) => (
          <DocumentCard
            key={doc.type}
            type={TYPE_LABELS[doc.type] ?? doc.type}
            name={doc.name}
            date={doc.date ?? "—"}
            description={doc.description ?? ""}
          />
        ))}
      </div>
    </motion.section>
  );
};

export default DocumentsGrid;
