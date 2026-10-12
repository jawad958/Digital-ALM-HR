"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { LogoMark } from "@/components/LogoMark";

/**
 * Public candidate-facing offer page. Loaded via magic link.
 * NOT behind the app sidebar — it's a standalone fullscreen view.
 */
export default function CandidateOfferPage() {
  const { token } = useParams();
  const [offer, setOffer] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setError(null);
      const res = await fetch(`/api/v1/public/offers/accept/${token}`);
      if (!res.ok) throw new Error((await res.json()).detail || "Could not load offer");
      setOffer(await res.json());
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, [token]);

  async function respond(decision) {
    setBusy(true);
    try {
      const res = await fetch(`/api/v1/public/offers/accept/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Could not record response");
      setOffer(await res.json());
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", padding: "40px 20px" }}>
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 32 }}>
          <LogoMark height={32} />
          <span className="display" style={{ fontSize: 16, letterSpacing: "0.42em", paddingLeft: "0.42em" }}>ALPAGO</span>
        </div>

        <div className="panel" style={{ padding: 40 }}>
          {error && (
            <div style={{ padding: 16, background: "var(--color-bad-soft)", borderRadius: 10, color: "var(--color-bad)" }}>
              {error}
            </div>
          )}

          {!offer && !error && <div style={{ color: "var(--color-muted)" }}>Loading your offer…</div>}

          {offer && (
            <>
              <div className="upper" style={{ color: "var(--color-brand)" }}>Your offer from Alpago</div>
              <h1 style={{ marginTop: 10, fontSize: 36 }}>{offer.role_title}</h1>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginTop: 28, paddingTop: 24, borderTop: "1px solid var(--color-stroke)" }}>
                <div>
                  <div className="upper">Base salary</div>
                  <div className="display num" style={{ fontSize: 24, marginTop: 6 }}>
                    {offer.currency} {offer.base_salary.toLocaleString()}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--color-muted)" }}>per month</div>
                </div>
                <div>
                  <div className="upper">Start date</div>
                  <div className="display" style={{ fontSize: 18, marginTop: 6 }}>
                    {new Date(offer.start_date).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" })}
                  </div>
                </div>
                <div>
                  <div className="upper">Allowances</div>
                  {Object.keys(offer.allowances || {}).length ? (
                    Object.entries(offer.allowances).map(([k, v]) => (
                      <div key={k} style={{ fontSize: 13 }}>
                        <span style={{ color: "var(--color-muted)", textTransform: "capitalize" }}>{k}:</span> {offer.currency} {v.toLocaleString()}
                      </div>
                    ))
                  ) : <div style={{ fontSize: 13, color: "var(--color-muted)" }}>None</div>}
                </div>
              </div>

              {offer.letter_markdown && (
                <div style={{ marginTop: 32, paddingTop: 24, borderTop: "1px solid var(--color-stroke)" }}>
                  <div className="upper" style={{ marginBottom: 12 }}>Offer letter</div>
                  <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-sans)", fontSize: 13, lineHeight: 1.75, color: "var(--color-ink-2)", margin: 0 }}>
                    {offer.letter_markdown}
                  </pre>
                </div>
              )}

              <div style={{ marginTop: 40, display: "flex", gap: 12, justifyContent: "flex-end", paddingTop: 24, borderTop: "1px solid var(--color-stroke)" }}>
                {offer.status === "sent" ? (
                  <>
                    <button className="btn btn-danger" onClick={() => respond("decline")} disabled={busy}>Decline</button>
                    <button className="btn btn-primary" onClick={() => respond("accept")} disabled={busy}>Accept offer</button>
                  </>
                ) : (
                  <div style={{ padding: "12px 20px", background: offer.status === "accepted" ? "var(--color-ok-soft)" : "var(--color-bad-soft)", color: offer.status === "accepted" ? "var(--color-ok)" : "var(--color-bad)", borderRadius: 10, fontWeight: 600 }}>
                    You {offer.status} this offer. Thank you.
                  </div>
                )}
              </div>

              {offer.expires_at && (
                <div style={{ marginTop: 16, fontSize: 11, color: "var(--color-muted)", textAlign: "right" }}>
                  Link valid until {new Date(offer.expires_at).toLocaleDateString()}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
