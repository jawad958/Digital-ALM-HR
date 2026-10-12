"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/Button";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import { api } from "@/lib/api";
import { ErrorBanner } from "../../hiring/page";

export default function OfferDetailPage() {
  const { id } = useParams();
  const [offer, setOffer] = useState(null);
  const [approval, setApproval] = useState(null);
  const [error, setError] = useState(null);
  const [sending, setSending] = useState(false);
  const [magicLink, setMagicLink] = useState(null);

  async function load() {
    try {
      setError(null);
      const o = await api.get(`/api/v1/offers/${id}`);
      setOffer(o);
      if (o.approval_request_id) setApproval(await api.get(`/api/v1/approvals/${o.approval_request_id}`));
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, [id]);

  async function sendToCandidate() {
    setSending(true);
    try {
      const o = await api.post(`/api/v1/offers/${id}/send`, {});
      if (o.acceptance_token) {
        const url = `${window.location.origin}/offers/accept/${o.acceptance_token}`;
        setMagicLink(url);
      }
      await load();
    } catch (e) { setError(e.message); }
    finally { setSending(false); }
  }

  if (!offer) return <Topbar crumb="Offer" title="Loading…" />;

  return (
    <>
      <Topbar
        crumb={`Offer · ${offer.id.slice(0, 8)}`}
        title={offer.role_title}
        sub={`${offer.currency} ${offer.base_salary.toLocaleString()} / month`}
        actions={
          offer.status === "approved" && (
            <Button variant="primary" onClick={sendToCandidate} disabled={sending}>
              {sending ? "Sending…" : "Send to candidate"}
            </Button>
          )
        }
      />
      {error && <ErrorBanner message={error} />}

      {magicLink && (
        <Panel title="Candidate magic link" sub="Share this URL privately">
          <input readOnly value={magicLink} onClick={(e) => e.target.select()} style={{ fontFamily: "monospace", fontSize: 11 }} />
        </Panel>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 20, marginTop: 20 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <Panel title="Offer letter" sub={offer.letter_markdown ? "AI drafted" : "No letter"}>
            {offer.letter_markdown ? (
              <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontFamily: "var(--font-sans)", fontSize: 13, lineHeight: 1.7, color: "var(--color-ink-2)" }}>
                {offer.letter_markdown}
              </pre>
            ) : <div style={{ color: "var(--color-muted)", padding: 24, textAlign: "center" }}>No letter drafted.</div>}
          </Panel>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <Panel title="Status">
            <Pill variant={offer.status === "accepted" ? "ok" : offer.status === "declined" ? "bad" : "warn"}>{offer.status}</Pill>
            <div style={{ marginTop: 12, fontSize: 11, color: "var(--color-muted)" }}>
              Created {new Date(offer.created_at).toLocaleString()}<br />
              {offer.sent_at && <>Sent {new Date(offer.sent_at).toLocaleString()}<br /></>}
              {offer.responded_at && <>Responded {new Date(offer.responded_at).toLocaleString()}</>}
            </div>
          </Panel>

          {approval && (
            <Panel title="Approval chain">
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <Pill variant={approval.status === "approved" ? "ok" : "warn"}>{approval.status}</Pill>
                {approval.steps.map((s) => (
                  <div key={s.id} style={{ fontSize: 12, display: "flex", gap: 8, alignItems: "center" }}>
                    <div style={{ width: 8, height: 8, borderRadius: 99,
                      background: s.status === "approved" ? "var(--color-ok)" : s.status === "active" ? "var(--color-brand)" : s.status === "rejected" ? "var(--color-bad)" : "var(--color-stroke-strong)" }} />
                    <strong>{s.approver_role.toUpperCase()}</strong>
                    <span style={{ color: "var(--color-muted)", marginLeft: "auto" }}>{s.status}</span>
                  </div>
                ))}
              </div>
            </Panel>
          )}

          <Panel title="Package">
            <Row label="Base" value={`${offer.currency} ${offer.base_salary.toLocaleString()}`} />
            {Object.entries(offer.allowances || {}).map(([k, v]) => (
              <Row key={k} label={k} value={`${offer.currency} ${v.toLocaleString()}`} />
            ))}
            <Row label="Start" value={new Date(offer.start_date).toLocaleDateString()} />
          </Panel>
        </div>
      </div>
    </>
  );
}

function Row({ label, value }) {
  return (
    <div style={{ padding: "7px 0", borderBottom: "1px solid var(--color-stroke)", display: "grid", gridTemplateColumns: "90px 1fr", gap: 10, fontSize: 12 }}>
      <span className="upper">{label}</span>
      <span style={{ color: "var(--color-ink)" }}>{value}</span>
    </div>
  );
}
