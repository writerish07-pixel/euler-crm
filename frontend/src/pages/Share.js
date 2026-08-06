import React, { useEffect, useState } from "react";
import { get } from "../lib/api";
import { fmtDate } from "../lib/format";

const SHARE_CSS = `
.share-page{--ink:#07111f;--panel:rgba(12,24,42,0.72);--line:rgba(180,210,230,0.14);--text:#e8f0f7;--muted:#8aa0b5;--lime:#b8f24a;--cyan:#3ecfcf;--warm:#ffb454;position:fixed;inset:0;overflow-y:auto;background:var(--ink);color:var(--text);font-family:"Instrument Sans",system-ui,sans-serif;}
.share-page *{box-sizing:border-box;}
.share-bg{position:fixed;inset:0;z-index:0;pointer-events:none;background:radial-gradient(ellipse 80% 50% at 10% -10%,rgba(62,207,207,0.22),transparent 55%),radial-gradient(ellipse 70% 45% at 95% 5%,rgba(184,242,74,0.12),transparent 50%),linear-gradient(165deg,#07111f 0%,#0c1a2e 45%,#0a1422 100%);}
.share-bg::after{content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,0.03) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.03) 1px,transparent 1px);background-size:48px 48px;mask-image:linear-gradient(180deg,rgba(0,0,0,.55),transparent 75%);}
.share-wrap{position:relative;z-index:1;max-width:1100px;margin:0 auto;padding:28px 20px 56px;}
.share-loading,.share-error{padding:48px 12px;text-align:center;color:var(--muted);font-size:15px;}
.share-hero{margin-bottom:28px;animation:rise .7s ease both;}
.share-brand{font-family:Syne,sans-serif;font-weight:800;font-size:clamp(2.4rem,7vw,4.2rem);line-height:.95;letter-spacing:-.03em;margin:0 0 10px;}
.share-brand span{display:block;background:linear-gradient(100deg,#fff 10%,var(--cyan) 55%,var(--lime) 100%);-webkit-background-clip:text;background-clip:text;color:transparent;}
.share-tag{margin:0;max-width:36rem;color:var(--muted);font-size:1.05rem;line-height:1.45;}
.share-meta{margin-top:14px;display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center;font-size:13px;color:var(--muted);}
.share-meta strong{color:var(--text);font-weight:600;}
.share-pill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,0.03);}
.share-dot{width:7px;height:7px;border-radius:50%;background:var(--lime);box-shadow:0 0 0 3px rgba(184,242,74,0.2);animation:pulse 2s ease infinite;}
.share-kpis{display:grid;grid-template-columns:1.2fr 1.2fr .9fr .9fr;gap:14px;margin-bottom:22px;}
@media(max-width:840px){.share-kpis{grid-template-columns:1fr 1fr;}}
@media(max-width:520px){.share-kpis{grid-template-columns:1fr;}}
.kpi{border:1px solid var(--line);border-radius:18px;background:var(--panel);backdrop-filter:blur(10px);padding:18px 18px 16px;min-height:132px;display:flex;flex-direction:column;justify-content:space-between;animation:rise .75s ease both;}
.kpi:nth-child(1){animation-delay:.05s;}.kpi:nth-child(2){animation-delay:.12s;}.kpi:nth-child(3){animation-delay:.18s;}.kpi:nth-child(4){animation-delay:.24s;}
.kpi-label{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);}
.kpi-value{font-family:Syne,sans-serif;font-weight:800;font-size:clamp(2.6rem,8vw,3.6rem);line-height:1;letter-spacing:-.04em;margin:8px 0 4px;}
.kpi.book .kpi-value{color:var(--cyan);}.kpi.retail .kpi-value{color:var(--lime);}
.kpi.today .kpi-value{color:var(--warm);font-size:clamp(2rem,6vw,2.6rem);}
.kpi-hint{font-size:13px;color:var(--muted);}
.share-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
@media(max-width:800px){.share-grid{grid-template-columns:1fr;}}
.panel{border:1px solid var(--line);border-radius:18px;background:var(--panel);backdrop-filter:blur(10px);overflow:hidden;animation:rise .8s ease both;animation-delay:.2s;}
.panel-head{display:flex;justify-content:space-between;align-items:baseline;padding:14px 16px 10px;border-bottom:1px solid var(--line);}
.panel-head h2{margin:0;font-family:Syne,sans-serif;font-size:1.05rem;font-weight:700;}
.panel-head span{font-size:12px;color:var(--muted);}
.list{max-height:420px;overflow:auto;}
.row{display:grid;grid-template-columns:72px 1fr auto;gap:10px;align-items:center;padding:11px 16px;border-bottom:1px solid rgba(255,255,255,0.04);}
.row:last-child{border-bottom:none;}
.row-date{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums;}
.row-main{min-width:0;}
.row-name{font-weight:600;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.row-sub{font-size:12px;color:var(--muted);margin-top:2px;}
.row-badge{font-size:11px;font-weight:600;padding:3px 8px;border-radius:999px;border:1px solid var(--line);color:var(--cyan);white-space:nowrap;}
.row-badge.retail{color:var(--lime);}
.empty-list{padding:28px 16px;text-align:center;color:var(--muted);font-size:14px;}
.models{display:flex;flex-wrap:wrap;gap:8px;padding:12px 16px 16px;}
.chip{font-size:12px;padding:6px 10px;border-radius:999px;border:1px solid var(--line);background:rgba(255,255,255,0.03);color:var(--text);}
.chip b{color:var(--lime);margin-left:4px;}
.share-foot{margin-top:22px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;font-size:12px;color:var(--muted);}
.share-foot a{color:var(--cyan);text-decoration:none;}
.share-foot button{background:transparent;border:1px solid var(--line);color:var(--text);border-radius:999px;padding:6px 12px;cursor:pointer;font:inherit;}
.share-foot button:hover{border-color:var(--cyan);}
@keyframes rise{from{opacity:0;transform:translateY(12px);}to{opacity:1;transform:translateY(0);}}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:.45;}}
`;

const shortDate = (d) => {
  if (!d) return "—";
  const dt = new Date(String(d).split("T")[0]);
  if (isNaN(dt)) return String(d);
  return dt.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
};

export default function Share() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(false);
  const load = () => get("/share/dashboard").then(setD).catch(() => setErr(true));

  useEffect(() => {
    if (!document.getElementById("share-fonts")) {
      const l = document.createElement("link");
      l.id = "share-fonts";
      l.rel = "stylesheet";
      l.href = "https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=Syne:wght@700;800&display=swap";
      document.head.appendChild(l);
    }
    load();
    const t = setInterval(load, 180000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="share-page">
      <style>{SHARE_CSS}</style>
      <div className="share-bg" aria-hidden="true" />
      <main className="share-wrap">
        {!d && !err && <p className="share-loading">Loading board…</p>}
        {err && <p className="share-error">Could not load the board. Please refresh.</p>}
        {d && (
          <>
            <header className="share-hero">
              <h1 className="share-brand">Euler Motors<span>Bookings &amp; Retail</span></h1>
              <p className="share-tag">Live view of active bookings and this month's retail — straight from the CRM.</p>
              <div className="share-meta">
                <span className="share-pill"><span className="share-dot" /> Live</span>
                <span><strong>{d.month}</strong></span>
                <span>Updated {new Date(d.lastUpdated).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}</span>
              </div>
            </header>

            <section className="share-kpis">
              <div className="kpi book">
                <div className="kpi-label">Active Bookings</div>
                <div className="kpi-value">{d.activeBookings}</div>
                <div className="kpi-hint">awaiting delivery</div>
              </div>
              <div className="kpi retail">
                <div className="kpi-label">Retail · {d.month.split(" ")[0]}</div>
                <div className="kpi-value">{d.retailThisMonth}</div>
                <div className="kpi-hint">delivered this month</div>
              </div>
              <div className="kpi">
                <div className="kpi-label">New Bookings</div>
                <div className="kpi-value">{d.newThisMonth}</div>
                <div className="kpi-hint">this month</div>
              </div>
              <div className="kpi today">
                <div className="kpi-label">Today</div>
                <div className="kpi-value">{d.todayBookings}</div>
                <div className="kpi-hint">bookings today</div>
              </div>
            </section>

            <section className="share-grid">
              <div className="panel">
                <div className="panel-head"><h2>Active Bookings</h2><span>{d.recentBookings.length} shown</span></div>
                <div className="list">
                  {d.recentBookings.length === 0 && <div className="empty-list">No active bookings</div>}
                  {d.recentBookings.map((r, i) => (
                    <div className="row" key={i}>
                      <div className="row-date">{shortDate(r.date)}</div>
                      <div className="row-main">
                        <div className="row-name">{r.name}</div>
                        <div className="row-sub">{r.model}{r.variant ? ` · ${r.variant}` : ""}</div>
                      </div>
                      <div className="row-badge">Booked</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="panel">
                <div className="panel-head"><h2>Retail — {d.month}</h2><span>{d.recentRetail.length} delivered</span></div>
                <div className="list">
                  {d.recentRetail.length === 0 && <div className="empty-list">No retail this month yet</div>}
                  {d.recentRetail.map((r, i) => (
                    <div className="row" key={i}>
                      <div className="row-date">{shortDate(r.date)}</div>
                      <div className="row-main">
                        <div className="row-name">{r.name}</div>
                        <div className="row-sub">{r.model}{r.variant ? ` · ${r.variant}` : ""}</div>
                      </div>
                      <div className="row-badge retail">Delivered</div>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            {d.byModel.length > 0 && (
              <div className="panel" style={{ marginTop: 14 }}>
                <div className="panel-head"><h2>Active Bookings by Model</h2></div>
                <div className="models">
                  {d.byModel.map((m) => <span className="chip" key={m.model}>{m.model}<b>{m.count}</b></span>)}
                </div>
              </div>
            )}

            <footer className="share-foot">
              <span>Euler Motors · Company Board · read-only</span>
              <button onClick={load}>↻ Refresh</button>
            </footer>
          </>
        )}
      </main>
    </div>
  );
}
