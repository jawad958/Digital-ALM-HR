"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/Button";
import { Drawer } from "@/components/Drawer";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import { api } from "@/lib/api";
import { ErrorBanner } from "../hiring/page";

const STAGE_PILL = {
  sourced: "default", screened: "default", shortlisted: "gold",
  interviewing: "warn", offer: "gold", hired: "ok",
  rejected: "bad", withdrawn: "default",
};

export default function CandidatesListPage() {
  const params = useSearchParams();
  const hiringFilter = params.get("hiring");
  const [rows, setRows] = useState(null);
  const [hiringReqs, setHiringReqs] = useState([]);
  const [error, setError] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  async function load() {
    try {
      setError(null);
      const path = hiringFilter
        ? `/api/v1/candidates?hiring_request_id=${hiringFilter}`
        : `/api/v1/candidates`;
      setRows(await api.get(path));
      setHiringReqs(await api.get("/api/v1/hiring"));
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, [hiringFilter]);

  return (
    <>
      <Topbar
        crumb="Candidates · Pipeline"
        title="Candidates"
        sub={rows ? `${rows.length} total` : "Loading…"}
        actions={<Button variant="primary" onClick={() => setDrawerOpen(true)} disabled={hiringReqs.length === 0}>+ Add candidate</Button>}
      />
      {error && <ErrorBanner message={error} />}

      <Panel bodyPadding={false}>
        <table className="data-table">
          <thead><tr><th>Name</th><th>Role</th><th>Stage</th><th>Experience</th><th>Expected</th><th>AI score</th></tr></thead>
          <tbody>
            {(rows ?? []).map((c) => {
              const score = c.cvs?.[0]?.ai_score?.score;
              return (
                <tr key={c.id} onClick={() => window.location.assign(`/candidates/${c.id}`)}>
                  <td style={{ fontWeight: 600, color: "var(--color-ink)" }}>
                    {c.name}<div style={{ fontSize: 11, color: "var(--color-muted)" }}>{c.email}</div>
                  </td>
                  <td>{c.current_role || "—"}</td>
                  <td><Pill variant={STAGE_PILL[c.stage]}>{c.stage}</Pill></td>
                  <td>{c.years_experience ? `${c.years_experience}y` : "—"}</td>
                  <td className="num">{c.expected_salary ? c.expected_salary.toLocaleString() : "—"}</td>
                  <td className="num display" style={{ color: "var(--color-brand)", fontSize: 18 }}>
                    {score != null ? score : "—"}
                  </td>
                </tr>
              );
            })}
            {rows?.length === 0 && (
              <tr><td colSpan={6} style={{ textAlign: "center", padding: 40, color: "var(--color-muted)" }}>
                {hiringReqs.length === 0 ? "Create a hiring request first." : "No candidates yet."}
              </td></tr>
            )}
          </tbody>
        </table>
      </Panel>

      <AddCandidateDrawer
        open={drawerOpen} onClose={() => setDrawerOpen(false)}
        onCreated={() => { setDrawerOpen(false); load(); }}
        hiringReqs={hiringReqs} defaultHiringId={hiringFilter}
      />
    </>
  );
}

function AddCandidateDrawer({ open, onClose, onCreated, hiringReqs, defaultHiringId }) {
  const [form, setForm] = useState({
    hiring_request_id: defaultHiringId || "", name: "", email: "", phone: "",
    source: "direct", current_role: "", years_experience: "", expected_salary: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open) setForm((f) => ({ ...f, hiring_request_id: defaultHiringId || hiringReqs[0]?.id || "" }));
  }, [open, defaultHiringId, hiringReqs]);

  function set(k, v) { setForm((f) => ({ ...f, [k]: v })); }

  async function submit() {
    setSaving(true); setError(null);
    try {
      await api.post("/api/v1/candidates", {
        hiring_request_id: form.hiring_request_id,
        name: form.name, email: form.email,
        phone: form.phone || null, source: form.source,
        current_role: form.current_role || null,
        years_experience: form.years_experience ? parseInt(form.years_experience) : null,
        expected_salary: form.expected_salary ? parseInt(form.expected_salary) : null,
      });
      onCreated();
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Add candidate"
      actions={<>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={submit} disabled={saving || !form.name || !form.email || !form.hiring_request_id}>
          {saving ? "Adding…" : "Add candidate"}
        </Button>
      </>}>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {error && <ErrorBanner message={error} />}
        <div><label className="field-label">For role</label>
          <select value={form.hiring_request_id} onChange={(e) => set("hiring_request_id", e.target.value)}>
            {hiringReqs.map((h) => <option key={h.id} value={h.id}>{h.role_title} — {h.department}</option>)}
          </select></div>
        <div><label className="field-label">Name</label>
          <input value={form.name} onChange={(e) => set("name", e.target.value)} required /></div>
        <div><label className="field-label">Email</label>
          <input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} required /></div>
        <div><label className="field-label">Phone</label>
          <input value={form.phone} onChange={(e) => set("phone", e.target.value)} placeholder="+971 50 …" /></div>
        <div><label className="field-label">Current role</label>
          <input value={form.current_role} onChange={(e) => set("current_role", e.target.value)} /></div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
          <div><label className="field-label">Years exp</label>
            <input type="number" min="0" value={form.years_experience} onChange={(e) => set("years_experience", e.target.value)} /></div>
          <div><label className="field-label">Expected</label>
            <input type="number" min="0" value={form.expected_salary} onChange={(e) => set("expected_salary", e.target.value)} /></div>
          <div><label className="field-label">Source</label>
            <select value={form.source} onChange={(e) => set("source", e.target.value)}>
              <option value="direct">Direct</option><option value="referral">Referral</option>
              <option value="agency">Agency</option><option value="jobsite">Job site</option>
              <option value="linkedin">LinkedIn</option>
            </select></div>
        </div>
      </div>
    </Drawer>
  );
}
