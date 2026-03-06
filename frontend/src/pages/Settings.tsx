import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";

const DEFAULT_PROMPT_PLACEHOLDER = `You are a senior financial analyst at a venture capital firm specializing in deal document intelligence.

PRIMARY OBJECTIVE: Analyze a batch of investment documents and extract structured metadata for each one — doc_type, deal_name, doc_date, and a two-sentence summary.

(Leave empty to use the full default prompt. The output schema will always be appended automatically.)`;

const Settings = () => {
  const { user, isLoading, refreshUser } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [companyName, setCompanyName] = useState("");
  const [customPrompt, setCustomPrompt] = useState("");
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [isSavingPrompt, setIsSavingPrompt] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) navigate("/", { replace: true });
  }, [user, isLoading, navigate]);

  useEffect(() => {
    if (user) {
      setCompanyName(user.company_name ?? "");
      setCustomPrompt(user.custom_prompt ?? "");
    }
  }, [user]);

  if (isLoading || !user) return null;

  const handleSaveProfile = async () => {
    setIsSavingProfile(true);
    try {
      await api.updateProfile({ company_name: companyName });
      await refreshUser();
      toast({ title: "Profile saved" });
    } catch (err: unknown) {
      toast({
        title: "Failed to save",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setIsSavingProfile(false);
    }
  };

  const handleSavePrompt = async () => {
    setIsSavingPrompt(true);
    try {
      await api.updateProfile({ custom_prompt: customPrompt.trim() || null });
      await refreshUser();
      toast({ title: "Prompt saved" });
    } catch (err: unknown) {
      toast({
        title: "Failed to save",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setIsSavingPrompt(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-2xl px-6 pt-24 pb-16">
        <h1 className="font-heading text-3xl font-semibold text-foreground">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">{user.email}</p>

        {/* Company Name */}
        <section className="mt-10">
          <h2 className="font-heading text-lg font-medium text-foreground">Company</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Your firm name shown across the app.
          </p>
          <div className="mt-4 flex gap-3">
            <Input
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="e.g. Acme Ventures"
              className="border-border bg-background text-foreground placeholder:text-muted-foreground/60"
            />
            <Button
              onClick={handleSaveProfile}
              disabled={isSavingProfile}
              className="shrink-0 bg-primary text-primary-foreground hover:bg-accent"
            >
              {isSavingProfile ? "Saving…" : "Save"}
            </Button>
          </div>
        </section>

        {/* Custom Analysis Prompt */}
        <section className="mt-10">
          <h2 className="font-heading text-lg font-medium text-foreground">Analysis Prompt</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Customize the prompt used when classifying your documents. Leave empty to use the
            default prompt. The output schema is always appended automatically.
          </p>
          <Textarea
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            placeholder={DEFAULT_PROMPT_PLACEHOLDER}
            rows={14}
            className="mt-4 border-border bg-background font-mono text-sm text-foreground placeholder:text-muted-foreground/50"
          />
          <div className="mt-3 flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              The output schema (<code>custom_id</code>, <code>doc_type</code>,&nbsp;
              <code>deal_name</code>, etc.) will be appended automatically if not present.
            </p>
            <Button
              onClick={handleSavePrompt}
              disabled={isSavingPrompt}
              className="ml-4 shrink-0 bg-primary text-primary-foreground hover:bg-accent"
            >
              {isSavingPrompt ? "Saving…" : "Save Prompt"}
            </Button>
          </div>
        </section>
      </main>
    </div>
  );
};

export default Settings;
