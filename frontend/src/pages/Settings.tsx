import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import Navbar from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";

const DEFAULT_PROMPT = `You are a senior financial analyst at a venture capital firm specializing in deal document intelligence.

PRIMARY OBJECTIVE: Analyze a batch of investment documents and extract structured metadata for each one — doc_type, deal_name, doc_date, and a two-sentence summary.

## FIELD RULES

### \`custom_id\`
- Copy exactly from the document header: \`--- <custom_id>: filename ---\`
- Do not modify, truncate, or infer.

### \`is_client\`
Set to \`true\` if this document belongs to an **existing portfolio company / current client** (a company the fund already manages or has already invested in), NOT a new deal being evaluated.

Signals → \`true\` (existing client/portfolio):
- Quarterly/annual report, board update, or investor update *from* a portfolio company
- Folder path contains words like "Portfolio", "Clients", "Current Investments", "Post-Investment", "Active"
- Operational report, cap table update, or company financials sent *to* investors (no fundraising ask)
- Governance documents, AGM minutes, or shareholder letters for an already-invested company

Signals → \`false\` (new deal / opportunity being evaluated):
- Fundraising ask, pitch deck, term sheet, or investment memo for evaluation
- Prescreening or first-look of a company seeking capital
- IC meeting minutes discussing *whether* to invest in a new company (formal committee session, not a call recap)
- Data room materials from an external company seeking investment

**When in doubt, default to \`false\`** (assume deal/opportunity).

### \`doc_type\`
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

DEFAULT: If none match → \`other\`

### \`deal_name\`
- Extract from **document content first** — folder path is supporting context only.
- Return the shortest unambiguous name (max 3 words). Strip legal suffixes (Inc, Ltd, LLC, Corp).
- Return \`null\` if the deal name cannot be determined with confidence.

### \`doc_date\`
- Find the date the document was **authored or published** — not dates referenced in the body.
- Scan: \`Date:\` headers, title pages, opening paragraph, footers.
- Normalize any format to \`YYYY-MM-DD\` (e.g. "April 4th, 2024" → "2024-04-04").
- Return \`null\` **only** if no date appears anywhere in the text.

### \`summary\`
- Exactly **two sentences**.
- Sentence 1: what the document is and who/what it concerns.
- Sentence 2: the single most important insight, metric, decision, or next step.
- Be specific — include numbers, names, outcomes where available.
- Do not begin with "This document".

## DOCUMENTS TO ANALYZE

{DOCUMENTS}`;

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
      setCustomPrompt(user.custom_prompt ?? DEFAULT_PROMPT);
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
      await api.updateProfile({ custom_prompt: value === DEFAULT_PROMPT.trim() ? null : value || null });
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
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="font-heading text-lg font-medium text-foreground">Analysis Prompt</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Customize the prompt used when classifying your documents. <code className="text-xs">{"{DOCUMENTS}"}</code> is replaced with the actual document text at runtime.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCustomPrompt(DEFAULT_PROMPT)}
              className="shrink-0 border-border text-muted-foreground hover:text-foreground"
            >
              Reset to Default
            </Button>
          </div>
          <Textarea
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            rows={22}
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
