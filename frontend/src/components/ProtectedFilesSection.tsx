import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lock, ChevronDown, FileX } from "lucide-react";
import { api, LockedFileWithDeal } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/ui/badge";

function formatName(raw: string): string {
  return raw.replace(/\.[^/.]+$/, "").replace(/[_-]+/g, " ");
}

function formatDate(raw: string | null): string {
  if (!raw) return "—";
  const d = new Date(raw);
  if (isNaN(d.getTime())) return raw;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

const ProtectedFilesSection = () => {
  const { user } = useAuth();
  const [files, setFiles] = useState<LockedFileWithDeal[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!user) return;
    setIsLoading(true);
    api
      .getLockedFiles()
      .then(setFiles)
      .catch(() => null)
      .finally(() => setIsLoading(false));
  }, [user]);

  // Don't render section at all if no locked files (and not loading)
  if (!isLoading && files.length === 0) return null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.6 }}
      className="mx-auto max-w-6xl px-6 pb-24"
    >
      {/* Folder header — click to expand/collapse */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 rounded-lg border border-yellow-500/30 bg-yellow-500/5 px-5 py-4 text-left transition-colors hover:bg-yellow-500/10"
      >
        <Lock className="h-4 w-4 shrink-0 text-yellow-500" />
        <div className="flex-1">
          <span className="font-heading text-sm font-semibold text-foreground">
            Protected Files
          </span>
          <span className="ml-2 text-xs text-muted-foreground">
            {isLoading ? "loading…" : `${files.length} file${files.length !== 1 ? "s" : ""} — password-protected, could not be processed`}
          </span>
        </div>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {/* File rows */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="mt-2 divide-y divide-border rounded-lg border border-border bg-card">
              {isLoading && (
                <p className="px-5 py-4 text-sm text-muted-foreground">Loading…</p>
              )}
              {!isLoading && files.map((f) => (
                <div key={f.id} className="flex items-center gap-4 px-5 py-3">
                  <FileX className="h-4 w-4 shrink-0 text-yellow-500/70" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">
                      {formatName(f.name)}
                    </p>
                    {f.deal_name && (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {f.deal_name}
                      </p>
                    )}
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {formatDate(f.date)}
                  </span>
                  <Badge
                    variant="outline"
                    className="shrink-0 border-yellow-500/40 text-yellow-600 dark:text-yellow-400"
                  >
                    Locked
                  </Badge>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.section>
  );
};

export default ProtectedFilesSection;
