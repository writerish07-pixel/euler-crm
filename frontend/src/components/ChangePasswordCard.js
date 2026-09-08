import React, { useState } from "react";
import { KeyRound } from "lucide-react";
import { toast } from "sonner";
import { post, apiErrorMessage } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Card, Button, Field, Input } from "./ui";

export default function ChangePasswordCard({ compact = false, onSaved }) {
  const { user } = useAuth();
  const [pwForm, setPwForm] = useState({ currentPassword: "", newPassword: "", confirmPassword: "" });
  const [pwBusy, setPwBusy] = useState(false);

  const changePassword = async () => {
    if (!pwForm.currentPassword || !pwForm.newPassword) {
      return toast.error("Enter current and new password");
    }
    if (pwForm.newPassword.length < 6) {
      return toast.error("New password must be at least 6 characters");
    }
    if (pwForm.newPassword !== pwForm.confirmPassword) {
      return toast.error("New password and confirmation do not match");
    }
    setPwBusy(true);
    try {
      await post("/auth/change-password", {
        currentPassword: pwForm.currentPassword,
        newPassword: pwForm.newPassword,
      });
      toast.success("Password updated");
      setPwForm({ currentPassword: "", newPassword: "", confirmPassword: "" });
      if (onSaved) onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not change password"));
    } finally {
      setPwBusy(false);
    }
  };

  return (
    <Card className={compact ? "p-4 mb-6" : "p-5 mb-6"} data-testid="change-password-card">
      <div className="flex items-center gap-2 mb-1">
        <KeyRound size={16} className="text-ink-soft" />
        <h3 className="font-heading font-bold text-ink">Change password</h3>
      </div>
      <p className="text-sm text-ink-soft mb-3">
        Signed in as <span className="font-mono text-ink">{user?.loginId || user?.email}</span>.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
        <Field label="Current password">
          <Input data-testid="current-password" type="password" autoComplete="current-password"
            value={pwForm.currentPassword}
            onChange={(e) => setPwForm({ ...pwForm, currentPassword: e.target.value })} />
        </Field>
        <Field label="New password">
          <Input data-testid="new-password" type="password" autoComplete="new-password"
            value={pwForm.newPassword}
            onChange={(e) => setPwForm({ ...pwForm, newPassword: e.target.value })} />
        </Field>
        <Field label="Confirm new password">
          <Input data-testid="confirm-password" type="password" autoComplete="new-password"
            value={pwForm.confirmPassword}
            onChange={(e) => setPwForm({ ...pwForm, confirmPassword: e.target.value })} />
        </Field>
        <Button data-testid="change-password-btn" onClick={changePassword} disabled={pwBusy}>
          <KeyRound size={15} /> {pwBusy ? "Saving…" : "Update password"}
        </Button>
      </div>
    </Card>
  );
}
