"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/Button";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import { api } from "@/lib/api";
import { ErrorBanner } from "../page";

export default function HiringDetailPage() {
  const { id } = useParams();
  const [req, setReq] = useState(null);
  const [approval, setApproval] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [error, setError] = useState(null);
  const [regenNotes, setRegenNotes] = useState("");

  async function load() {
    try {
      setError(null);
      const r = await api.get(`/api/v1/hiring/${id}`);
      setReq(r);
      if (r.approval_request_id) {
        setApproval(await api.get(`/api/v1/approvals/${r.approval_request_id}`));
      }
      setCandidates(await api.get(`/api/v1/candidates?hiring_request_id=${id}`));
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, [id]);

  async function regenerateJd() {
    try {
      await api.post(`/api/v1/hiring/${id}/generate-jd`, { notes: regenNotes });
      await load();
      setRegenNotes("");
    } catch (e) { setError(e.message); }
  }

  if (!req) return (
    <>
      <Topbar crumb="Hiring" title="Loading…" />
      {error && <ErrorBanner message={error} />}
    </>
  );

  return (
    <>
      <Topbar
        crumb={`Hiring · ${req.id.slice(0, 8)}`}
        title={req.role_title}
        sub={`${req.department} · ${req.positions} position${req.positions > 1 ? "s" : ""} · ${req.seniority}`}
      />
      {error && <ErrorBanner message={error} />}

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 20 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <Panel
            title="Job description"
            sub={req.jd_generated_by_ai ? "AI-drafted" : "Hand-written"}
            actions={
              <div style={{ display: "flex", gap: 6 }}>
                <input
                  value={regenNotes}
                  onChange={(e) => setRegenNotes(e.target.value)}
                  placeholder="Notes for AI (optional)"
                  style={{ width: 220, fontSize: 12, padding: "6px 10px" }}
                />
                <Button className="btn-sm" onClick={regenerateJd}>✦ Regenerate</Button>
              </div>
            }
          >
            {req.jd_markdown ? (
              <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontFamily: "var(--font-sans)", fontSize: 13, lineHeight: 1.7, color: "var(--color-ink-2)" }}>
                {req.jd_markdown}
              </pre>
            ) : (
              <div style={{ color: "var(--color-muted)", textAlign: "center", padding: 32 }}>
                No JD yet. Click "✦ Regenerate" to have Claude draft one.
              </div>
            )}
          </Panel>

          <Panel
            title="Candidates"
            sub={`${candidates.length} in pipeline`}
            actions={
              <Link href={`/candidates?hiring=${id}`}>
                <Button className="btn-sm">Manage pipeline →</Button>
              </Link>
            }
            bodyPadding={false}
          >
            {candidates.length === 0 ? (
              <div style={{ padding: 32, textAlign: "center", color: "var(--color-muted)" }}>
                No candidates yet. Add candidates from the Candidates page.
              </div>
            ) : (
              <table className="data-table">
                <thead><tr><th>Name</th><th>Stage</th><th>Experience</th><th>Expected</th></tr></thead>
                <tbody>
                  {candidates.slice(0, 10).map((c) => (
                    <tr key={c.id} onClick={() => window.location.assign(`/candidates/${c.id}`)}>
                      <td style={{ fontWeight: 600, color: "var(--color-ink)" }}>{c.name}</td>
                      <td><Pill>{c.stage}</Pill></td>
                      <td>{c.years_experience ? `${c.years_experience}y` : "—"}</td>
                      <td className="num">{c.expected_salary ? c.expected_salary.toLocaleString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <Panel title="Approval chain">
            {approval ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div><Pill variant={approval.status === "approved" ? "ok" : approval.status === "rejected" ? "bad" : "warn"}>{approval.status}</Pill></div>
                {approval.steps.map((s, i) => (
                  <div key={s.id} style={{ display: "flex", gap: 10, paddingBottom: 10, borderBottom: i < approval.steps.length - 1 ? "1px solid var(--color-stroke)" : "none" }}>
                    <div style={{
                      width: 10, height: 10, marginTop: 5, borderRadius: 99,
                      background: s.status === "approved" ? "var(--color-ok)" : s.status === "active" ? "var(--color-brand)" : s.status === "rejected" ? "var(--color-bad)" : "var(--color-stroke-strong)",
                    }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{s.approver_role.toUpperCase()}</div>
                      <div style={{ fontSize: 11, color: "var(--color-muted)" }}>
                        {s.status} · SLA {s.sla_hours}h
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ color: "var(--color-muted)", fontSize: 13 }}>No approval attached.</div>
            )}
          </Panel>

          <Panel title="Details">
            <Row label="Status"><Pill>{req.status}</Pill></Row>
            <Row label="Band" value={req.salary_min && req.salary_max ? `${req.currency} ${req.salary_min.toLocaleString()} – ${req.salary_max.toLocaleString()}` : "Not set"} />
            <Row label="Target start" value={req.target_start_date ? new Date(req.target_start_date).toLocaleDateString() : "—"} />
            <Row label="Justification" value={req.justification || "—"} />
          </Panel>
        </div>
      </div>
    </>
  );
}

function Row({ label, value, children }) {
  return (
    <div style={{ padding: "8px 0", borderBottom: "1px solid var(--color-stroke)", display: "grid", gridTemplateColumns: "90px 1fr", gap: 10, fontSize: 12 }}>
      <span className="upper">{label}</span>
      <span style={{ color: "var(--color-ink)" }}>{children || value}</span>
    </div>
  );
}
