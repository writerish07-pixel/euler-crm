import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { get, post } from "../lib/api";
import { Button, Card, Field, Input } from "../components/ui";

export default function LeadWhatsApp({ leadId }) {
  const [data, setData] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);

  const load = useCallback(() => {
    get(`/leads/${leadId}/whatsapp`).then(setData).catch(() => toast.error("Could not load WhatsApp thread"));
  }, [leadId]);
  useEffect(() => { load(); }, [load]);

  const send = async () => {
    if (!text.trim()) return toast.error("Type a reply");
    setBusy(true);
    try {
      await post(`/leads/${leadId}/whatsapp/reply`, { text: text.trim() });
      toast.success("Reply sent");
      setText("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Reply failed");
    } finally {
      setBusy(false);
    }
  };

  const sendReview = async (force) => {
    setReviewBusy(true);
    try {
      const r = await post(`/leads/${leadId}/whatsapp/google-review`, { force: !!force });
      if (r.skipped) toast.success("Google review WhatsApp was already sent for this lead");
      else toast.success("Google review WhatsApp sent");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not send Google review WhatsApp");
    } finally {
      setReviewBusy(false);
    }
  };

  if (!data) return <div className="text-sm text-ink-faint">Loading WhatsApp…</div>;

  return (
    <div data-testid="lead-whatsapp-tab">
      <p className="text-xs text-ink-soft mb-3">
        Only this Euler lead’s chat. Tata / other BotSpace contacts never appear here.
        {data.optOut ? " Customer sent STOP — auto follow-ups are off." : ""}
      </p>

      {data.canSendReview && (
        <Card className="p-4 mb-4" data-testid="google-review-card">
          <div className="font-heading font-bold text-ink text-sm">Google review WhatsApp</div>
          <p className="text-xs text-ink-soft mt-1 mb-3">
            Sends the delivered + Google review template to this customer.
            {data.deliveryReviewSentAt ? ` Last sent ${data.deliveryReviewSentAt.slice(0, 16).replace("T", " ")}.` : " Not sent yet."}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button data-testid="send-google-review-btn" onClick={() => sendReview(false)} disabled={reviewBusy}>
              {reviewBusy ? "Sending…" : (data.deliveryReviewSentAt ? "Already sent" : "Send Google review")}
            </Button>
            {data.deliveryReviewSentAt && (
              <Button variant="secondary" onClick={() => sendReview(true)} disabled={reviewBusy}>Send again</Button>
            )}
          </div>
        </Card>
      )}

      <div className="space-y-2 max-h-80 overflow-auto mb-4">
        {(data.messages || []).length === 0 && (
          <div className="text-sm text-ink-faint text-center py-6">No WhatsApp messages yet</div>
        )}
        {(data.messages || []).map((m) => (
          <div key={m.messageId}
            className={`rounded-lg px-3 py-2 text-sm border ${m.direction === "inbound" ? "bg-white border-line" : "bg-cobalt-tint/40 border-cobalt/20 ml-8"}`}>
            <div className="text-[11px] text-ink-faint uppercase tracking-wide mb-0.5">
              {m.direction === "inbound" ? "Customer" : (m.kind === "finance_exec" ? "To executive" : "Euler")}
              {m.status ? ` · ${m.status}` : ""}
            </div>
            <div className="text-ink whitespace-pre-wrap">{m.text || "—"}</div>
          </div>
        ))}
      </div>
      <Card className="p-4">
        {data.sessionOpen ? (
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <Field label="Reply (24-hour window is open)">
                <Input data-testid="whatsapp-reply" value={text} onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") send(); }} placeholder="Type a reply" />
              </Field>
            </div>
            <Button data-testid="whatsapp-send-btn" onClick={send} disabled={busy}>{busy ? "Sending…" : "Send"}</Button>
          </div>
        ) : (
          <p className="text-sm text-ink-soft">
            24-hour reply window is closed. After the customer writes, you can reply here.
            Outside the window, send an approved template from BotSpace.
          </p>
        )}
      </Card>
    </div>
  );
}
