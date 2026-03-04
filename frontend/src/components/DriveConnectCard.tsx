import { useState } from "react";
import { motion } from "framer-motion";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

const DriveConnectCard = () => {
  const { user, login, refreshUser } = useAuth();
  const { toast } = useToast();
  const [folderPath, setFolderPath] = useState(user?.folder_id ? "" : "");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!folderPath.trim()) return;
    setIsSubmitting(true);
    try {
      await api.setFolder(folderPath.trim());
      await refreshUser();
      toast({ title: "Folder configured", description: folderPath.trim() });
    } catch (err: unknown) {
      toast({
        title: "Failed to set folder",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!user) {
    return (
      <motion.section
        initial={{ opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.6 }}
        className="flex flex-col items-center px-6 py-24"
      >
        <div className="w-full max-w-lg rounded-lg border border-border bg-card p-8 text-center">
          <h2 className="font-heading text-2xl font-semibold text-foreground">
            Connect Your Drive
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Sign in with Google to link your Drive folder.
          </p>
          <Button
            onClick={login}
            className="mt-6 w-full bg-primary text-primary-foreground hover:bg-accent"
          >
            Sign in with Google
          </Button>
        </div>
      </motion.section>
    );
  }

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
          {user.folder_id
            ? "Folder is configured. Update it below."
            : "Link a folder to begin syncing documents."}
        </p>
        <div className="mt-6 space-y-4">
          <Input
            value={folderPath}
            onChange={(e) => setFolderPath(e.target.value)}
            placeholder="Paste a Drive URL or path like /InvestmentDocs/StartupA/"
            className="border-border bg-background text-foreground placeholder:text-muted-foreground/60"
          />
          <Button
            onClick={handleSubmit}
            disabled={isSubmitting || !folderPath.trim()}
            className="w-full bg-primary text-primary-foreground hover:bg-accent"
          >
            {isSubmitting ? "Saving…" : "Start Sync"}
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
