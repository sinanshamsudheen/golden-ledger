import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";

interface DocumentStats {
  total_validated: number;
  shortlisted: number;
  archived: number;
  knowledge_base: number;
  duplicates: number;
}

const STATUS_LABELS: Record<string, string> = {
  not_connected: "Not Connected",
  no_folder: "No Folder Set",
  processing: "Processing",
  idle: "Up to Date",
};

const SyncStatusCard = () => {
  const { user } = useAuth();
  const [syncStatus, setSyncStatus] = useState<{ status: string; next_sync: string } | null>(null);
  const [stats, setStats] = useState<DocumentStats | null>(null);

  useEffect(() => {
    if (!user) return;
    api.getSyncStatus().then(setSyncStatus).catch(() => null);
    api.getDocumentStats().then(setStats).catch(() => null);
  }, [user]);

  const label = syncStatus ? (STATUS_LABELS[syncStatus.status] ?? syncStatus.status) : "Yet to Sync";

  const rows: { label: string; value: number | string; muted?: boolean }[] = stats
    ? [
        { label: "Total Documents Validated", value: stats.total_validated },
        { label: "Documents Shortlisted", value: stats.shortlisted },
        { label: "Documents Archived", value: stats.archived },
        { label: "Added to Knowledge Base", value: stats.knowledge_base },
        { label: "Duplicate Files Found", value: stats.duplicates, muted: stats.duplicates === 0 },
      ]
    : [];

  return (
    <motion.section
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.6 }}
      className="flex flex-col items-center px-6 py-24"
    >
      <div className="w-full max-w-lg rounded-lg border border-border bg-card p-8">
        <h2 className="font-heading text-2xl font-semibold text-foreground">
          Sync Status
        </h2>
        <div className="mt-6 flex items-center gap-3">
          <span className="relative flex h-3 w-3">
            <span className="absolute inline-flex h-full w-full animate-pulse-gold rounded-full bg-primary opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-primary" />
          </span>
          <span className="text-sm font-medium text-muted-foreground">{label}</span>
        </div>

        {rows.length > 0 && (
          <div className="mt-4 space-y-2 border-t border-border pt-4 text-sm">
            {rows.map((row) => (
              <div key={row.label} className="flex justify-between">
                <span className="text-muted-foreground">{row.label}</span>
                <span className={`font-medium ${row.muted ? "text-muted-foreground" : "text-foreground"}`}>
                  {row.value}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="mt-4 flex items-center justify-between border-t border-border pt-4">
          <span className="text-xs text-muted-foreground">Next Sync</span>
          <span className="text-sm font-medium text-foreground">
            {syncStatus?.next_sync ?? "02:00 AM"}
          </span>
        </div>
      </div>
    </motion.section>
  );
};

export default SyncStatusCard;
