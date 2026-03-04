import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";

interface SyncStatus {
  status: string;
  next_sync: string;
  total_documents: number;
  processed_documents: number;
  pending_documents: number;
}

const STATUS_LABELS: Record<string, string> = {
  not_connected: "Not Connected",
  no_folder: "No Folder Set",
  processing: "Processing",
  idle: "Up to Date",
};

const SyncStatusCard = () => {
  const { user } = useAuth();
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);

  useEffect(() => {
    if (!user) return;
    api.getSyncStatus().then(setSyncStatus).catch(() => null);
  }, [user]);

  const label = syncStatus ? (STATUS_LABELS[syncStatus.status] ?? syncStatus.status) : "Yet to Sync";

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
        {syncStatus && (
          <div className="mt-4 space-y-2 border-t border-border pt-4 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Total documents</span>
              <span className="font-medium text-foreground">{syncStatus.total_documents}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Processed</span>
              <span className="font-medium text-foreground">{syncStatus.processed_documents}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Pending</span>
              <span className="font-medium text-foreground">{syncStatus.pending_documents}</span>
            </div>
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
