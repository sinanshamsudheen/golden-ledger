import { useState } from "react";
import { motion } from "framer-motion";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { api, DriveFolder } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { ExternalLink, Trash2, FolderPlus, FolderOpen } from "lucide-react";

const DriveConnectCard = () => {
  const { user, login, refreshUser } = useAuth();
  const { toast } = useToast();
  const [folderPath, setFolderPath] = useState("");
  const [isAdding, setIsAdding] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const handleAdd = async () => {
    if (!folderPath.trim()) return;
    setIsAdding(true);
    try {
      await api.addFolder(folderPath.trim());
      await refreshUser();
      setFolderPath("");
      toast({ title: "Folder added" });
    } catch (err: unknown) {
      toast({
        title: "Failed to add folder",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setIsAdding(false);
    }
  };

  const handleRemove = async (folderId: string) => {
    setRemovingId(folderId);
    try {
      await api.removeFolder(folderId);
      await refreshUser();
      toast({ title: "Folder removed" });
    } catch (err: unknown) {
      toast({
        title: "Failed to remove folder",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setRemovingId(null);
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
            Sign in with Google to link your Drive folders.
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

  const folders: DriveFolder[] = user.folder_ids ?? (
    user.folder_id ? [{ id: user.folder_id, label: user.folder_id }] : []
  );

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
          Add one or more Drive folders to sync documents from.
        </p>

        {/* Folder list */}
        <div className="mt-6">
          {folders.length === 0 ? (
            <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border py-8 text-center">
              <FolderOpen className="h-8 w-8 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">No folders configured yet.</p>
            </div>
          ) : (
            <ul className="space-y-2">
              {folders.map((f) => (
                <li
                  key={f.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background px-4 py-3"
                >
                  <a
                    href={`https://drive.google.com/drive/folders/${f.id}`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex min-w-0 items-center gap-2 text-sm text-primary hover:underline"
                  >
                    <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{f.label}</span>
                  </a>
                  <button
                    onClick={() => handleRemove(f.id)}
                    disabled={removingId === f.id}
                    aria-label="Remove folder"
                    className="shrink-0 cursor-pointer rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Add folder input */}
        <div className="mt-4 flex gap-2">
          <Input
            value={folderPath}
            onChange={(e) => setFolderPath(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            placeholder="Paste a Drive URL or path like /InvestmentDocs/"
            className="border-border bg-background text-foreground placeholder:text-muted-foreground/60"
          />
          <Button
            onClick={handleAdd}
            disabled={isAdding || !folderPath.trim()}
            className="shrink-0 bg-primary text-primary-foreground hover:bg-accent"
          >
            <FolderPlus className="mr-1.5 h-4 w-4" />
            {isAdding ? "Adding…" : "Add"}
          </Button>
        </div>
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        Documents will be automatically processed during the nightly sync.
      </p>
    </motion.section>
  );
};

export default DriveConnectCard;
