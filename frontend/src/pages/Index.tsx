import Navbar from "@/components/Navbar";
import Hero from "@/components/Hero";
import DriveConnectCard from "@/components/DriveConnectCard";
import SyncStatusCard from "@/components/SyncStatusCard";
import DocumentsGrid from "@/components/DocumentsGrid";
import DealsGrid from "@/components/DealsGrid";
import ProtectedFilesSection from "@/components/ProtectedFilesSection";

const Index = () => {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <Hero />
      <DriveConnectCard />
      <SyncStatusCard />
      <DocumentsGrid />
      <ProtectedFilesSection />
      <DealsGrid />
      <footer className="border-t border-border py-12 text-center text-xs text-muted-foreground">
        © 2025 Document Intelligence. All rights reserved.
      </footer>
    </div>
  );
};

export default Index;
