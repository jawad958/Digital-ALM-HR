"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/Button";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import { api } from "@/lib/api";
import { ErrorBanner } from "../../hiring/page";

const STAGES = ["sourced", "screened", "shortlisted", "interviewing", "offer", "hired", "rejected"];

export default function CandidateDetailPage() {
  const { id } = useParams();
  const [cand, setCand] = useState(null);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [screening, setScreening] = useState(false);
  const fileRef = useRef();

  async function load() {
    try { setError(null); setCand(await api.get(`/api/v1/candidates/${id}`)); }
    catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, [id]);

  async function onUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await api.upload(`/api/v1/candidates/${id}/cv`, fd);
      await load();
    } catch (e) { setError(e.message); }
    finally { setUploading(false); fileRef.current.value = ""; }
  }

  async function runScreening() {
    setScreening(true);
    try { await api.post(`/api/v1/candidates/${id}/screen`, {}); await load(); }
    catch (e) { setError(e.message); }
    finally { setScreening(false); }
  }

  async function changeStage(stage) {
    try { await api.post(`/api/v1/candidates/${id}/stage`, { stage }); await load(); }
    catch (e) { setError(e.message); }
  }

  if (!cand) return <Topbar crumb="Candidate" title="Loading…" />;

  const latestCv = cand.cvs?.[0];
  const score = latestCv?.ai_score;

  return (
    <>
      <Topbar
        crumb={`Candidate · ${cand.id.slice(0, 8)}`}
        title={cand.name}
        sub={cand.current_role || cand.email}
        actions={<>
          <select value={cand.stage} onChange={(e) => changeStage(e.target.value)} style={{ width: 180 }}>
            {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </>}
      />
      {error && <ErrorBanner message={error} />}

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 20 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <Panel
            title="AI screening"
            sub={latestCv ? (score ? "Scored" : "Awaiting screening") : "Upload a CV first"}
            actions={
              latestCv && <Button className="btn-sm" onClick={runScreening} disabled={screening}>
                {screening ? "Scoring…" : "✦ Run screening"}
              </Button>
            }
          >
            {!score && (
              <div style={{ color: "var(--color-muted)", fontSize: 13, padding: 16, textAlign: "center" }}>
                {latestCv ? "Click 'Run screening' to score this candidate against the JD." : "Upload a CV to enable AI screening."}
              </div>
            )}
            {score?.error && <ErrorBanner message={`AI error: ${score.error}`} />}
            {score && !score.error && (
              <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
                <div style={{ textAlign: "center", minWidth: 110 }}>
                  <div className="display num" style={{ fontSize: 56, color: "var(--color-brand)", lineHeight: 1 }}>{score.score}</div>
                  <div className="upper">of 100</div>
                  <div className="upper" style={{ color: "var(--color-brand)", marginTop: 8 }}>{score.verdict}</div>
                </div>
                <div style={{ flex: 1 }}>
                  <p style={{ fontSize: 13, color: "var(--color-ink-2)", margin: 0, lineHeight: 1.65 }}>{score.summary}</p>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginTop: 16 }}>
                    <div>
                      <div className="upper" style={{ color: "var(--color-ok)", marginBottom: 8 }}>Strengths · {score.strengths?.length || 0}</div>
                      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--color-ink-2)", lineHeight: 1.7 }}>
                        {score.strengths?.map((s, i) => <li key={i}>{s}</li>)}
                      </ul>
                    </div>
                    <div>
                      <div className="upper" style={{ color: "var(--color-warn)", marginBottom: 8 }}>Gaps · {score.gaps?.length || 0}</div>
                      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--color-ink-2)", lineHeight: 1.7 }}>
                        {score.gaps?.length ? score.gaps.map((g, i) => <li key={i}>{g}</li>) : <li style={{ color: "var(--color-muted)" }}>None identified.</li>}
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </Panel>

          <Panel title="CV">
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <input ref={fileRef} type="file" onChange={onUpload} style={{ flex: 1 }} accept=".pdf,.doc,.docx,.txt" />
              {uploading && <span style={{ fontSize: 12, color: "var(--color-muted)" }}>Uploading…</span>}
            </div>
            {latestCv && (
              <div style={{ marginTop: 14, padding: 12, background: "var(--color-surface-2)", borderRadius: 8, fontSize: 13 }}>
                <div style={{ fontWeight: 600 }}>{latestCv.filename}</div>
                <div style={{ fontSize: 11, color: "var(--color-muted)", marginTop: 2 }}>
                  Uploaded {new Date(latestCv.created_at).toLocaleString()}
                </div>
              </div>
            )}
          </Panel>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <Panel title="Contact">
            <Row label="Email" value={cand.email} />
            <Row label="Phone" value={cand.phone || "—"} />
            <Row label="Source" value={cand.source || "—"} />
            <Row label="Years" value={cand.years_experience ? `${cand.years_experience}y` : "—"} />
            <Row label="Expected" value={cand.expected_salary ? cand.expected_salary.toLocaleString() : "—"} />
          </Panel>
        </div>
      </div>
    </>
  );
}

function Row({ label, value }) {
  return (
    <div style={{ padding: "8px 0", borderBottom: "1px solid var(--color-stroke)", display: "grid", gridTemplateColumns: "80px 1fr", gap: 10, fontSize: 12 }}>
      <span className="upper">{label}</span>
      <span style={{ color: "var(--color-ink)" }}>{value}</span>
    </div>
  );
}
