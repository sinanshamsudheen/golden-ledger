import { motion } from "framer-motion";

const SyncStatusCard = () => {
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
          <span className="text-sm font-medium text-muted-foreground">
            Yet to Sync
          </span>
        </div>
        <div className="mt-4 flex items-center justify-between border-t border-border pt-4">
          <span className="text-xs text-muted-foreground">Next Sync</span>
          <span className="text-sm font-medium text-foreground">02:00 AM</span>
        </div>
      </div>
    </motion.section>
  );
};

export default SyncStatusCard;
