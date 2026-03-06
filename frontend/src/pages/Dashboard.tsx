import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import DriveConnectCard from "@/components/DriveConnectCard";
import SyncStatusCard from "@/components/SyncStatusCard";
import CompanyNameModal from "@/components/CompanyNameModal";
import { Button } from "@/components/ui/button";
import { FolderOpen, Pencil } from "lucide-react";

const Dashboard = () => {
  const { user, isLoading, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) navigate("/", { replace: true });
  }, [user, isLoading, navigate]);

  // Prompt for company name on first login (when it's null)
  useEffect(() => {
    if (!isLoading && user && user.company_name === null) {
      setShowModal(true);
    }
  }, [isLoading, user]);

  if (isLoading || !user) return null;

  const handleCompanyNameSaved = () => {
    setShowModal(false);
    refreshUser();
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-3xl px-6 pt-28 pb-24">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="font-heading text-3xl font-semibold text-foreground">
              {user.company_name ?? "Dashboard"}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Signed in as <span className="text-foreground font-medium">{user.email}</span>
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="mt-1 gap-1.5 text-muted-foreground hover:text-foreground"
            onClick={() => setShowModal(true)}
          >
            <Pencil className="h-3.5 w-3.5" />
            {user.company_name ? "Edit company" : "Set company"}
          </Button>
        </div>

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
        © 2025 PCI Intelligence. All rights reserved.
      </footer>

      <CompanyNameModal
        open={showModal}
        onSaved={handleCompanyNameSaved}
        onClose={() => setShowModal(false)}
      />
    </div>
  );
};

export default Dashboard;
