import { motion } from "framer-motion";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const DriveConnectCard = () => {
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
          Connect Your Drive
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Link a folder to begin syncing documents.
        </p>
        <div className="mt-6 space-y-4">
          <Input
            placeholder="/InvestmentDocs/StartupA/"
            className="border-border bg-background text-foreground placeholder:text-muted-foreground/60"
          />
          <Button className="w-full bg-primary text-primary-foreground hover:bg-accent">
            Start Sync
          </Button>
        </div>
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        Your documents will be automatically processed during the nightly sync.
      </p>
    </motion.section>
  );
};

export default DriveConnectCard;
