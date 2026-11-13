import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { get, post, put, apiErrorMessage } from "../lib/api";
import { inr } from "../lib/format";
import { PageHeader, Table, Badge, Button, Card, Field, Input } from "../components/ui";
import { useAuth } from "../context/AuthContext";

const TABS = [
  ["today", "Today"],
  ["mail", "Mail"],
  ["buy", "Buy parts"],
  ["warranty", "Warranty"],
  ["jobs", "Jobs"],
  ["money", "Money"],
  ["rules", "Rules"],
];

const TONE = {
  warning: "bg-amber-50 text-amber-800 ring-amber-600/20",
  danger: "bg-red-50 text-red-700 ring-red-600/20",
  info: "bg-sky-50 text-sky-800 ring-sky-600/20",
  success: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
};

function stageTone(stage) {
  if (stage === "short") return TONE.danger;
  if (stage === "received") return TONE.success;
  if (stage === "reorder" || stage === "transit" || stage === "paid") return TONE.info;
  return TONE.warning;
}

export default function Workshop() {
  const { isOwner } = useAuth();
  const [tab, setTab] = useState("today");
  const [desk, setDesk] = useState(null);
  const [selectedMail, setSelectedMail] = useState("");
  const [selectedLine, setSelectedLine] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [fileTo, setFileTo] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const load = useCallback(() => get("/workshop").then((data) => {
    setDesk(data);
    if (data?.serviceLogin?.username) setUsername(data.serviceLogin.username);
    return data;
  }).catch((err) => {
    toast.error(apiErrorMessage(err, "Could not open the workshop desk"));
  }), []);

  useEffect(() => { load(); }, [load]);

  const apply = (data) => {
    setDesk(data);
    if (data?.serviceLogin?.username) setUsername(data.serviceLogin.username);
  };
  const run = (path, payload) => post(path, payload || {}, path === "/workshop/sync" ? { timeout: 90000 } : {})
    .then((data) => {
      apply(data);
      return data;
    })
    .catch((err) => {
      toast.error(apiErrorMessage(err, "Could not update the desk"));
      load();
      return null;
    });

  const lines = desk?.lines || [];
  const mails = desk?.mails || [];
  const mail = mails.find((item) => item.id === selectedMail) || mails.find((item) => item.status === "unread") || mails[0];
  const line = lines.find((item) => item.id === selectedLine) || lines[0];
  const requests = [...new Set(lines.map((item) => item.requestNo).filter(Boolean))];

  return (
    <div data-testid="workshop-desk">
      <PageHeader
        title="Workshop Desk"
        subtitle="One place for parts the store buys, warranty parts coming back, and the service mailbox. Same app, same database."
        actions={
          <>
            {!lines.length && !mails.length && (
              <Button variant="secondary" onClick={() => run("/workshop/sample").then((data) => data && toast.success("Loaded this morning’s workshop"))}>
                Load this morning
              </Button>
            )}
            <Button onClick={() => run("/workshop/sync").then((data) => data && toast.success("Synced from Service Coulson"))}>
              Sync from Coulson
            </Button>
          </>
        }
      />

      {desk?.syncError && (
        <div className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-600/20">
          Last sync: {desk.syncError}
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-4">
        {TABS.map(([id, label]) => (
            <button
            key={id}
            type="button"
            data-testid={`workshop-tab-${id}`}
            onClick={() => setTab(id)}
            className={
              tab === id
                ? "rounded-full bg-cobalt px-3 py-1 text-sm font-medium text-white"
                : "rounded-full bg-zinc-100 px-3 py-1 text-sm font-medium text-ink-soft"
            }
          >
            {label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
        <Card className="p-4">
          <div className="text-xs uppercase tracking-wider text-ink-faint">Unread mails</div>
          <div className="text-2xl font-heading font-extrabold">{mails.filter((item) => !item.applied || item.status === "unread").length}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs uppercase tracking-wider text-ink-faint">Parts missing from a box</div>
          <div className="text-2xl font-heading font-extrabold">{lines.filter((item) => item.stage === "short").length}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs uppercase tracking-wider text-ink-faint">Company advance</div>
          <div className="text-2xl font-heading font-extrabold">{inr(desk?.advanceTotal || 0)}</div>
        </Card>
      </div>

      {tab === "today" && (
        <Table
          columns={[
            { key: "title", label: "Waiting" },
            { key: "detail", label: "Why it is here" },
            { key: "go", label: "", render: (row) => (
              <Button variant="secondary" onClick={() => {
                if (row.mailId) { setSelectedMail(row.mailId); setTab("mail"); }
                else if (row.lineId) { setSelectedLine(row.lineId); setTab("buy"); }
                else if (String(row.id || "").startsWith("war")) setTab("warranty");
                else setTab("jobs");
              }}>Open</Button>
            ) },
          ]}
          rows={desk?.today || []}
          rowKey="id"
          empty="Nothing is waiting. Load this morning’s workshop, or sync Service Coulson."
        />
      )}

      {tab === "mail" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <Table
              columns={[
                { key: "subject", label: "Mail" },
                { key: "status", label: "Join", render: (row) => (
                  <Badge tone={row.status === "unmatched" ? TONE.warning : row.applied ? TONE.success : TONE.warning}>
                    {row.requestNo ? `Ticket ${row.requestNo}` : "No ticket"}
                  </Badge>
                ) },
              ]}
              rows={mails}
              rowKey="id"
              onRowClick={(row) => setSelectedMail(row.id)}
              empty="No mail yet. Paste one below, or load this morning’s thread."
            />
            <Card className="p-4 mt-4">
              <div className="font-medium mb-2">Paste a mail from the service mailbox</div>
              <p className="text-sm text-ink-soft mb-3">
                The desk reads the ticket number, the part codes, and the words “not dispatched”. A direct mailbox connection will use this same reader.
              </p>
              <Field label="Subject">
                <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Re: Ticket 10412 — dispatch update" />
              </Field>
              <Field label="Mail">
                <textarea
                  className="block w-full rounded-lg border-0 py-2 px-3 text-sm text-ink ring-1 ring-inset ring-line focus:ring-2 focus:ring-cobalt min-h-28"
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  placeholder={"Ticket 10412\nCD4C001800 is not dispatched\n₹18,400 is parked as advance."}
                />
              </Field>
              <Button onClick={() => run("/workshop/mails", { subject, body }).then((data) => {
                if (!data) return;
                setSubject("");
                setBody("");
                setTab("mail");
              })}>
                Add to the desk
              </Button>
            </Card>
          </div>
          {mail && (
            <Card className="p-4">
              <div className="text-xs text-ink-faint">{mail.direction} · {mail.when}</div>
              <h2 className="font-heading font-bold text-lg mt-1">{mail.subject}</h2>
              <pre className="mt-3 whitespace-pre-wrap text-sm text-ink font-sans">{mail.body}</pre>
              <div className="mt-4">
                <Table
                  columns={[
                    { key: "name", label: "In the mail" },
                    { key: "value", label: "Read as" },
                  ]}
                  rows={(mail.finds || []).map(([name, value]) => ({ name, value }))}
                  empty="Nothing recognised."
                />
              </div>
              <p className="text-sm text-ink-soft mt-3">{mail.result}</p>
              <div className="flex flex-wrap gap-2 mt-3">
                {!mail.applied && (
                  <Button onClick={() => run(`/workshop/mails/${mail.id}/read`)}>
                    Read this mail and join it
                  </Button>
                )}
                {mail.status === "unmatched" && (
                  <>
                    <Input
                      value={fileTo}
                      onChange={(e) => setFileTo(e.target.value)}
                      placeholder={requests[0] ? `Ticket ${requests[0]}` : "Ticket number"}
                      className="max-w-40"
                    />
                    <Button variant="secondary" onClick={() => run(`/workshop/mails/${mail.id}/file`, { requestNo: fileTo })}>
                      File onto that ticket
                    </Button>
                  </>
                )}
              </div>
            </Card>
          )}
        </div>
      )}

      {tab === "buy" && (
        <div className="grid gap-4 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <Table
              columns={[
                { key: "part", label: "Part" },
                { key: "requestNo", label: "Ticket", render: (row) => row.requestNo || "Not asked yet" },
                { key: "stageLabel", label: "Stage", render: (row) => <Badge tone={stageTone(row.stage)}>{row.stageLabel}</Badge> },
                { key: "advance", label: "Advance", align: "right", render: (row) => row.advance ? inr(row.advance) : "—" },
              ]}
              rows={lines}
              rowKey="id"
              onRowClick={(row) => setSelectedLine(row.id)}
              empty="No parts yet. Sync Service Coulson, or load this morning."
            />
          </div>
          {line && (
            <Card className="p-4 lg:col-span-2">
              <div className="text-xs text-ink-faint">{line.code}{line.requestNo ? ` · ticket ${line.requestNo}` : ""}{line.pi ? ` · ${line.pi}` : ""}</div>
              <h2 className="font-heading font-bold text-lg">{line.part}</h2>
              <div className="mt-2"><Badge tone={stageTone(line.stage)}>{line.stageLabel}</Badge></div>
              <p className="text-sm text-ink-soft mt-3">{line.note}</p>
              {line.overCap && (
                <p className="text-sm text-amber-800 mt-2">Suggested quantity {line.suggestedQty} is not usable. It will not be mailed until a person sets it.</p>
              )}
              <div className="flex flex-wrap gap-2 mt-4">
                {line.stage === "short" && (
                  <Button onClick={() => run(`/workshop/lines/${line.id}/reorder`).then((data) => data && toast.success("Follow-up mail is on the thread"))}>
                    Approve the follow-up mail
                  </Button>
                )}
                {(line.stage === "reorder" || line.stage === "transit") && (
                  <Button onClick={() => run(`/workshop/lines/${line.id}/receive`).then((data) => data && toast.success("Counted into the store"))}>
                    Count into the store
                  </Button>
                )}
              </div>
            </Card>
          )}
        </div>
      )}

      {tab === "warranty" && (
        <div className="space-y-4">
          <p className="text-sm text-ink-soft">
            {desk?.warranty?.total || 0} inbound claims, {inr(desk?.warranty?.amount || 0)}. These parts come off a job. They are not a purchase.
            The credit note is the sign the company has agreed the money.
          </p>
          <Table
            columns={[
              { key: "label", label: "Where the claim sits" },
              { key: "count", label: "Claims", align: "right" },
            ]}
            rows={desk?.warranty?.breakdown || []}
            empty="Sync Service Coulson to load warranty claims."
          />
          <Table
            columns={[
              { key: "claimNumber", label: "Claim" },
              { key: "part", label: "Note" },
              { key: "status", label: "Status" },
              { key: "amount", label: "Amount", align: "right", render: (row) => inr(row.amount) },
            ]}
            rows={desk?.warranty?.rows || []}
            empty="No claim lines loaded."
          />
        </div>
      )}

      {tab === "jobs" && (
        <div className="space-y-4">
          <Table
            columns={[
              { key: "ticketId", label: "Ticket" },
              { key: "type", label: "Type" },
              { key: "status", label: "Status" },
              { key: "partNotAvailable", label: "Part", render: (row) => row.partNotAvailable ? "Not available" : "—" },
            ]}
            rows={desk?.jobs?.openTickets || []}
            empty="No open job on the last sync."
          />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              ["Overdue service", desk?.jobs?.overdue],
              ["Due soon", desk?.jobs?.dueSoon],
              ["Booked", desk?.jobs?.booked],
              ["Complaints open", desk?.jobs?.complaintsOpen],
            ].map(([label, value]) => (
              <Card key={label} className="p-4">
                <div className="text-xs uppercase tracking-wider text-ink-faint">{label}</div>
                <div className="text-2xl font-heading font-extrabold">{value || 0}</div>
              </Card>
            ))}
          </div>
          {(desk?.jobs?.coverage || []).length > 0 && (
            <Table
              columns={[
                { key: "label", label: "Finished-job coverage" },
                { key: "count", label: "Lines", align: "right" },
              ]}
              rows={desk.jobs.coverage}
            />
          )}
        </div>
      )}

      {tab === "money" && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Card className="p-4">
              <div className="text-xs uppercase tracking-wider text-ink-faint">Advance with the company</div>
              <div className="text-2xl font-heading font-extrabold">{inr(desk?.advanceTotal || 0)}</div>
            </Card>
            <Card className="p-4">
              <div className="text-xs uppercase tracking-wider text-ink-faint">Warranty claims open</div>
              <div className="text-2xl font-heading font-extrabold">{inr(desk?.warranty?.amount || 0)}</div>
            </Card>
            <Card className="p-4">
              <div className="text-xs uppercase tracking-wider text-ink-faint">Missing lines still on an advance</div>
              <div className="text-2xl font-heading font-extrabold">{(desk?.advances || []).length}</div>
            </Card>
          </div>
          <Table
            columns={[
              { key: "requestNo", label: "Ticket" },
              { key: "parts", label: "Parts still tied to the advance", render: (row) => (row.parts || []).join(", ") },
              { key: "amount", label: "Advance", align: "right", render: (row) => inr(row.amount) },
            ]}
            rows={desk?.advances || []}
            empty="No advance. A missing paid part will show here after its dispatch mail is read."
          />
        </div>
      )}

      {tab === "rules" && (
        <Card className="p-4 max-w-xl">
          <h2 className="font-heading font-bold text-lg">Service Coulson login</h2>
          <p className="text-sm text-ink-soft mt-1 mb-4">
            Saved in the same database as the sales app. The password is not shown again. Sync reads stock, open requests, warranty claims, service due, and jobs.
          </p>
          {isOwner ? (
            <>
              <Field label="Username">
                <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Service username" />
              </Field>
              <Field label="Password">
                <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Leave blank to keep the saved password" />
              </Field>
              <Button onClick={() => put("/workshop/service-login", { username, password }).then((data) => {
                apply(data);
                setPassword("");
                toast.success(data?.serviceLogin?.configured ? "Service login saved" : "Saved");
              }).catch((err) => toast.error(apiErrorMessage(err, "Could not save the login")))}>
                Save login
              </Button>
            </>
          ) : (
            <p className="text-sm">The owner saves the service login. You can still sync and work the desk.</p>
          )}
          <ul className="mt-5 text-sm text-ink-soft space-y-2 list-disc pl-5">
            <li>A mail joins a request when it says ticket and the Coulson request number.</li>
            <li>Not dispatched, plus a part code, marks that part missing and parks the paid amount as advance.</li>
            <li>The follow-up mail asks the company to send the same part against that advance. It does not raise a new PI.</li>
            <li>A mail with no ticket number waits until a person files it.</li>
            <li>A suggested order quantity that is not usable waits. It is not mailed.</li>
          </ul>
        </Card>
      )}
    </div>
  );
}
