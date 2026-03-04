import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import DriveConnectCard from "@/components/DriveConnectCard";
import SyncStatusCard from "@/components/SyncStatusCard";
import { Button } from "@/components/ui/button";
import { FolderOpen } from "lucide-react";

const Dashboard = () => {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoading && !user) navigate("/", { replace: true });
  }, [user, isLoading, navigate]);

  if (isLoading || !user) return null;

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-3xl px-6 pt-28 pb-24">
        <h1 className="font-heading text-3xl font-semibold text-foreground">Dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Signed in as <span className="text-foreground font-medium">{user.email}</span>
        </p>

        <div className="mt-8 space-y-0 [&_section]:py-6">
          <DriveConnectCard />
          <SyncStatusCard />
        </div>

        {user.folder_id && (
          <div className="mt-8 flex justify-end">
            <Button
              onClick={() => navigate("/documents")}
              className="gap-2 bg-primary text-primary-foreground hover:bg-accent"
            >
              <FolderOpen className="h-4 w-4" />
              Browse Documents
            </Button>
          </div>
        )}
      </main>

      <footer className="border-t border-border py-8 text-center text-xs text-muted-foreground">
        © 2025 Document Intelligence. All rights reserved.
      </footer>
    </div>
  );
};

export default Dashboard;
