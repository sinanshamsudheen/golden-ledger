import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

const Landing = () => {
  const { user, login, isLoading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoading && user) navigate("/dashboard", { replace: true });
  }, [user, isLoading, navigate]);

  return (
    <div className="min-h-screen bg-background">
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border/30 bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <span className="font-heading text-xl font-semibold tracking-wide text-foreground">
            Document Intelligence
          </span>
        </div>
      </nav>

      <motion.section
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="flex min-h-screen flex-col items-center justify-center px-6 text-center"
      >
        <h1 className="font-heading text-5xl font-bold leading-tight tracking-tight text-foreground md:text-6xl lg:text-7xl">
          Investment Document
          <br />
          Intelligence
        </h1>
        <p className="mt-6 max-w-xl text-lg text-muted-foreground">
          Automatically organize and analyze your investment documents from Google Drive.
        </p>
        {!isLoading && (
          <Button
            onClick={login}
            variant="outline"
            className="mt-10 border-primary bg-transparent px-8 py-6 text-sm font-medium tracking-wider text-primary transition-all duration-300 hover:bg-primary hover:text-primary-foreground"
          >
            Connect Google Drive
          </Button>
        )}
      </motion.section>

      <footer className="border-t border-border py-12 text-center text-xs text-muted-foreground">
        © 2025 Document Intelligence. All rights reserved.
      </footer>
    </div>
  );
};

export default Landing;
