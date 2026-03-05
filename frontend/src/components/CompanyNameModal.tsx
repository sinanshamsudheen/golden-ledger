import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { toast } from "sonner";

interface Props {
  open: boolean;
  onSaved: (companyName: string) => void;
  onClose: () => void;
}

export default function CompanyNameModal({ open, onSaved, onClose }: Props) {
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setSaving(true);

    try {
      const updated = await api.updateProfile({ company_name: trimmed });
      onSaved(updated.company_name ?? trimmed);
      toast.success("Company name saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save company name");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Welcome to Golden Ledger</DialogTitle>
          <DialogDescription>
            Enter your company name to personalise your workspace. You can update this later from
            the Dashboard.
          </DialogDescription>
        </DialogHeader>

        <div className="mt-2 space-y-2">
          <Label htmlFor="company-name">Company name</Label>
          <Input
            id="company-name"
            placeholder="Acme Capital"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSave()}
            autoFocus
          />
        </div>

        <DialogFooter className="mt-4">
          <Button onClick={handleSave} disabled={!value.trim() || saving}>
            {saving ? "Saving…" : "Continue"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
