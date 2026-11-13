import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { get, post, put, del, postForm, apiErrorMessage } from "../lib/api";
import { inr } from "../lib/format";
import { PageHeader, Table, Badge, Button, Card, Field, Input } from "../components/ui";
import { useAuth } from "../context/AuthContext";

const TABS = [
  ["today", "Today", "today"],
  ["mail", "Mail", "mail"],
  ["buy", "Buy parts", "buy"],
  ["warranty", "Warranty", "warranty"],
  ["jobs", "Jobs", "jobs"],
  ["money", "Money", "money"],
  ["payments", "Payment proof", "payments"],
  ["people", "People", "users"],
  ["rules", "Rules", "gmail"],
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
  const [session, setSession] = useState("");
  const [payRequest, setPayRequest] = useState("");
  const [payUtr, setPayUtr] = useState("");
  const [payAmount, setPayAmount] = useState("");
  const [payFile, setPayFile] = useState(null);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");

  const load = useCallback(() => get("/workshop").then((data) => {
    setDesk(data);
    return data;
  }).catch((err) => {
    toast.error(apiErrorMessage(err, "Could not open the workshop desk"));
  }), []);

  useEffect(() => { load(); }, [load]);

  const apply = (data) => {
    setDesk(data);
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

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const code = query.get("code");
    const state = query.get("state");
    if (!code || !state) return;
    post("/workshop/gmail/finish", {
      code,
      state,
      redirectUri: `${window.location.origin}/service`,
    }).then((data) => {
      apply(data);
      toast.success(data?.gmail?.email ? `Gmail connected as ${data.gmail.email}` : "Gmail connected");
      window.history.replaceState({}, "", "/service");
    }).catch((err) => toast.error(apiErrorMessage(err, "Could not connect Gmail")));
  }, []);

  const lines = desk?.lines || [];
  const mails = desk?.mails || [];
  const mail = mails.find((item) => item.id === selectedMail) || mails.find((item) => item.status === "unread") || mails[0];
  const line = lines.find((item) => item.id === selectedLine) || lines[0];
  const requests = [...new Set(lines.map((item) => item.requestNo).filter(Boolean))];

  return (
    <div data-testid="workshop-desk">
      <PageHeader
        title="Service"
        subtitle="The service desk. The owner adds people from the staff list. A payment proof filed here is posted onto that request’s mail."
        actions={
          <>
            {(desk?.access?.owner || isOwner) && !lines.length && !mails.length && (
              <Button variant="secondary" onClick={() => run("/workshop/sample").then((data) => data && toast.success("Loaded this morning’s workshop"))}>
                Load this morning
              </Button>
            )}
            {(desk?.access?.owner || isOwner) && (
              <Button onClick={() => run("/workshop/sync").then((data) => data && toast.success("Synced from Service Coulson"))}>
                Sync from Coulson
              </Button>
            )}
          </>
        }
      />

      {desk?.syncError && (
        <div className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-600/20">
          Last sync: {desk.syncError}
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-4">
        {TABS.filter(([, , area]) => {
          const access = desk?.access;
          if (!access) return isOwner || area === "today";
          if (access.owner) return true;
          return (access.areas || []).includes(area);
        }).map(([id, label]) => (
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
              {(desk?.gmail?.connected || desk?.access?.owner) && (
                <Button variant="secondary" className="mb-3" onClick={() => run("/workshop/gmail/pull").then((data) => data && toast.success("Mailbox pulled onto the desk"))}>
                  Pull the mailbox
                </Button>
              )}
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

      {tab === "payments" && (
        <Card className="p-4 max-w-xl">
          <h2 className="font-heading font-bold text-lg">Payment proof</h2>
          <p className="text-sm text-ink-soft mt-1 mb-4">
            The proof is saved on this ticket and posted onto the company mail for that request. One place updates the desk and the thread.
          </p>
          <Field label="Ticket">
            <Input value={payRequest} onChange={(e) => setPayRequest(e.target.value)} placeholder={requests[0] ? `Ticket ${requests[0]}` : "Ticket number"} />
          </Field>
          <Field label="Payment reference">
            <Input value={payUtr} onChange={(e) => setPayUtr(e.target.value)} placeholder="UTR from the bank" />
          </Field>
          <Field label="Amount">
            <Input value={payAmount} onChange={(e) => setPayAmount(e.target.value)} placeholder="Optional" />
          </Field>
          <Field label="Proof">
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp,application/pdf"
              className="block w-full text-sm"
              onChange={(e) => setPayFile(e.target.files && e.target.files[0])}
            />
          </Field>
          <Button onClick={() => {
            if (!payFile) {
              toast.error("Attach the payment proof.");
              return;
            }
            const form = new FormData();
            form.append("requestNo", payRequest);
            form.append("utr", payUtr);
            form.append("amount", payAmount);
            form.append("file", payFile);
            return postForm("/workshop/payments", form, { timeout: 60000 }).then((data) => {
              apply(data);
              setPayUtr("");
              setPayAmount("");
              setPayFile(null);
              if (data?.posted) toast.success("Proof posted onto the request mail");
              else toast.success(data?.postError || "Proof saved on the desk");
            }).catch((err) => toast.error(apiErrorMessage(err, "Could not file the proof")));
          }}>
            Post onto the request mail
          </Button>
          <div className="mt-4">
            <Table
              columns={[
                { key: "requestNo", label: "Ticket" },
                { key: "utr", label: "Reference" },
                { key: "filename", label: "Proof" },
                { key: "posted", label: "Mail", render: (row) => row.posted ? "Posted" : "Waiting" },
              ]}
              rows={desk?.proofs || []}
              rowKey="id"
              empty="No payment proof filed yet."
            />
          </div>
        </Card>
      )}

      {tab === "people" && (
        <PeoplePanel />
      )}

      {tab === "rules" && (
        <Card className="p-4 max-w-xl">
          <h2 className="font-heading font-bold text-lg">Service Coulson session</h2>
          <p className="text-sm text-ink-soft mt-1 mb-4">
            Sign in at coulson.eulerlogistics.com with the service user. Open the browser console, run the line below, then paste the copied session here. Sync uses that session. The password is not used.
          </p>
          {isOwner ? (
            <>
              {desk?.serviceLogin?.configured && (
                <p className="text-sm mb-3">Session saved{desk.serviceLogin.username ? ` for ${desk.serviceLogin.username}` : ""}.</p>
              )}
              {desk?.serviceLogin?.sessionExpired && (
                <p className="text-sm text-amber-800 mb-3">That session has expired. Sign in again and paste a new one.</p>
              )}
              <Field label="Paste coulson_auth">
                <textarea
                  className="block w-full rounded-lg border-0 py-2 px-3 text-sm text-ink ring-1 ring-inset ring-line focus:ring-2 focus:ring-cobalt min-h-24 font-mono"
                  value={session}
                  onChange={(e) => setSession(e.target.value)}
                  placeholder='copy(localStorage.getItem("coulson_auth"))'
                />
              </Field>
              <p className="text-xs text-ink-faint mb-3 font-mono">copy(localStorage.getItem("coulson_auth"))</p>
              <Button onClick={() => put("/workshop/service-login", { sessionToken: session }).then((data) => {
                apply(data);
                setSession("");
                toast.success(data?.serviceLogin?.configured ? "Service session saved" : "Saved");
              }).catch((err) => toast.error(apiErrorMessage(err, "Could not save the session")))}>
                Save session
              </Button>
            </>
          ) : (
            <p className="text-sm">The owner pastes the service session. You can still work the desk.</p>
          )}
          <h2 className="font-heading font-bold text-lg mt-8">Gmail</h2>
          <p className="text-sm text-ink-soft mt-1 mb-4">
            {desk?.gmail?.connected
              ? `Connected as ${desk.gmail.email}. Pulled mail joins a ticket number, and a payment proof is replied onto that thread.`
              : "Save the Google client, then connect the service mailbox. Add this return address in Google: "}
            {!desk?.gmail?.connected && <span className="font-mono text-xs">{typeof window !== "undefined" ? `${window.location.origin}/service` : "/service"}</span>}
          </p>
          <Field label="Client id">
            <Input value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder={desk?.gmail?.clientId || "Google client id"} />
          </Field>
          <Field label="Client secret">
            <Input type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} placeholder="Leave blank to keep the saved secret" />
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => put("/workshop/gmail", { clientId, clientSecret }).then((data) => {
              apply(data);
              setClientSecret("");
              toast.success("Gmail client saved");
            }).catch((err) => toast.error(apiErrorMessage(err, "Could not save Gmail")))}>
              Save Gmail client
            </Button>
            <Button variant="secondary" onClick={() => post("/workshop/gmail/start", { redirectUri: `${window.location.origin}/service` }).then((data) => {
              if (data?.url) window.location.href = data.url;
            }).catch((err) => toast.error(apiErrorMessage(err, "Could not start Gmail")))}>
              Connect mailbox
            </Button>
          </div>
          <ul className="mt-5 text-sm text-ink-soft space-y-2 list-disc pl-5">
            <li>A mail joins a request when it says ticket and the Coulson request number.</li>
            <li>Not dispatched, plus a part code, marks that part missing and parks the paid amount as advance.</li>
            <li>The follow-up mail asks the company to send the same part against that advance. It does not raise a new PI.</li>
            <li>A mail with no ticket number, or two ticket numbers, waits until a person files it.</li>
            <li>A payment proof is posted onto the mail for that ticket.</li>
            <li>A suggested order quantity that is not usable waits. It is not mailed.</li>
          </ul>
        </Card>
      )}
    </div>
  );
}

function PeoplePanel() {
  const [pack, setPack] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [passwords, setPasswords] = useState({});
  const loadPeople = useCallback(() => get("/workshop/people").then((data) => {
    setPack(data);
    const next = {};
    (data?.people || []).forEach((person) => {
      next[person.staffId] = person.areas && person.areas.length ? person.areas : person.preset;
    });
    setDrafts(next);
  }).catch((err) => toast.error(apiErrorMessage(err, "Could not load the staff list"))), []);
  useEffect(() => { loadPeople(); }, [loadPeople]);
  const toggle = (staffId, area) => {
    setDrafts((cur) => {
      const have = new Set(cur[staffId] || []);
      if (have.has(area)) have.delete(area);
      else have.add(area);
      return { ...cur, [staffId]: [...have] };
    });
  };
  return (
    <div className="space-y-3" data-testid="service-people">
      <p className="text-sm text-ink-soft">
        Pick someone from the staff list. They keep their sales login and only see the parts of Service you open. A password is used only when that person has no login yet.
      </p>
      {(pack?.people || []).map((person) => (
        <Card key={person.staffId} className="p-4">
          <div className="font-medium">{person.name}</div>
          <div className="text-xs text-ink-faint mt-0.5">{person.role}{person.hasLogin ? " · has a login" : " · no login yet"}</div>
          <div className="flex flex-wrap gap-2 mt-3">
            {(pack.areas || []).map((area) => {
              const on = (drafts[person.staffId] || []).includes(area.id);
              return (
                <button
                  key={area.id}
                  type="button"
                  onClick={() => toggle(person.staffId, area.id)}
                  className={on
                    ? "rounded-full bg-cobalt px-3 py-1 text-xs font-medium text-white"
                    : "rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-ink-soft"}
                >
                  {area.label}
                </button>
              );
            })}
          </div>
          {!person.hasLogin && (
            <Field label="First password">
              <Input type="password" value={passwords[person.staffId] || ""} onChange={(e) => setPasswords((cur) => ({ ...cur, [person.staffId]: e.target.value }))} placeholder="At least 6 characters" />
            </Field>
          )}
          <div className="flex flex-wrap gap-2 mt-3">
            <Button onClick={() => put(`/workshop/people/${person.staffId}`, {
              areas: drafts[person.staffId] || [],
              password: passwords[person.staffId] || "",
            }).then((data) => {
              setPack(data);
              setPasswords((cur) => ({ ...cur, [person.staffId]: "" }));
              toast.success(`${person.name} can open Service`);
            }).catch((err) => toast.error(apiErrorMessage(err, "Could not save access")))}>
              Save access
            </Button>
            {!!person.areas?.length && (
              <Button variant="secondary" onClick={() => del(`/workshop/people/${person.staffId}`).then((data) => {
                setPack(data);
                toast.success("Service access removed");
              }).catch((err) => toast.error(apiErrorMessage(err, "Could not remove access")))}>
                Remove
              </Button>
            )}
          </div>
        </Card>
      ))}
      {pack && !(pack.people || []).length && (
        <p className="text-sm text-ink-faint">No active staff yet. Add them on Staff and Reports, then come back here.</p>
      )}
    </div>
  );
}
