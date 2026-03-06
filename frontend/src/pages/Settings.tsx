import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";

const DEFAULT_FIRM_CONTEXT = `You are a senior financial analyst at a venture capital firm specializing in deal document intelligence.

PRIMARY OBJECTIVE: Analyze a batch of investment documents and extract structured metadata for each one — doc_type, deal_name, doc_date, and a two-sentence summary.

## DOC TYPE CLASSIFICATION RULES
Apply in strict order (stop at the first match):

[T1] MEETING MINUTES — IC/Investment Committee only
- MUST be a formal Investment Committee (IC) session where a deal is deliberated or voted on.
- Strong signals: "Investment Committee", "IC minutes", "IC meeting", "committee resolution", "investment approved", "investment rejected", "proceed with investment", "pass on deal", "IC recommendation", "voted to invest", "motion carried", "quorum"
- The document must record a formal DECISION process — not just discussion or an update.

EXCLUDE from \`meeting_minutes\` — classify as \`other\` instead:
- Call notes, call recap, catch-up notes, intro call, exploratory call, reference call
- Due diligence calls, DD call notes, founder call notes
- Board updates, management updates, LP updates, quarterly/annual reviews
- Any meeting that is informational or operational (no investment vote/resolution)
→ \`meeting_minutes\`

[T2] PRESCREENING REPORT
- Contains: initial assessment, first look, deal screening, opportunity overview, "next steps: schedule partner meeting", fund thesis fit
→ \`prescreening_report\`

[T3] INVESTMENT MEMO
- Contains: financial analysis, due diligence, term sheet, investment recommendation, ARR/MRR, unit economics, LTV/CAC, burn rate, cap table, deal memo
→ \`investment_memo\`

[T4] PITCH DECK
- Contains: company overview, funding ask, go-to-market, product pitch, market size, founding team, use of proceeds
→ \`pitch_deck\`

DEFAULT: If none match → \`other\``;

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
      setCustomPrompt(user.custom_prompt ?? DEFAULT_FIRM_CONTEXT);
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
      const value = customPrompt.trim();
      await api.updateProfile({ custom_prompt: value === DEFAULT_FIRM_CONTEXT.trim() ? null : value || null });
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

        {/* Firm Context & Classification Rules */}
        <section className="mt-10">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="font-heading text-lg font-medium text-foreground">Firm Context &amp; Classification Rules</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Customize your firm's role and how documents are classified. Output format, field rules, and examples are managed automatically.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCustomPrompt(DEFAULT_FIRM_CONTEXT)}
              className="shrink-0 border-border text-muted-foreground hover:text-foreground"
            >
              Reset to Default
            </Button>
          </div>
          <Textarea
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            rows={28}
            className="mt-4 border-border bg-background font-mono text-sm text-foreground"
          />
          <div className="mt-3 flex justify-end">
            <Button
              onClick={handleSavePrompt}
              disabled={isSavingPrompt}
              className="bg-primary text-primary-foreground hover:bg-accent"
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
