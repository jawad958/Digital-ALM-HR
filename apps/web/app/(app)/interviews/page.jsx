"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/Button";
import { Drawer } from "@/components/Drawer";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import { api } from "@/lib/api";
import { ErrorBanner } from "../hiring/page";

export default function InterviewsPage() {
  const [rows, setRows] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [error, setError] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  async function load() {
    try {
      setError(null);
      setRows(await api.get("/api/v1/interviews/mine"));
      setCandidates(await api.get("/api/v1/candidates"));
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, []);

  return (
    <>
      <Topbar
        crumb="Interviews · Mine"
        title="Interviews"
        sub={rows ? `${rows.length} total` : "Loading…"}
        actions={<Button variant="primary" onClick={() => setDrawerOpen(true)} disabled={candidates.length === 0}>+ Schedule interview</Button>}
      />
      {error && <ErrorBanner message={error} />}

      <Panel bodyPadding={false}>
        <table className="data-table">
          <thead><tr><th>Candidate</th><th>Round</th><th>When</th><th>Mode</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {(rows ?? []).map((i) => {
              const cand = candidates.find((c) => c.id === i.candidate_id);
              return (
                <tr key={i.id} onClick={(e) => e.target.tagName !== "BUTTON" && window.location.assign(`/interviews/${i.id}`)}>
                  <td style={{ fontWeight: 600, color: "var(--color-ink)" }}>{cand?.name || i.candidate_id.slice(0, 8)}</td>
                  <td>{i.round_name}</td>
                  <td>{new Date(i.scheduled_at).toLocaleString()}</td>
                  <td>{i.mode}</td>
                  <td><Pill variant={i.status === "completed" ? "ok" : i.status === "scheduled" ? "warn" : "default"}>{i.status}</Pill></td>
                  <td>
                    {i.status === "scheduled" && (
                      <Button className="btn-sm" onClick={() => window.location.assign(`/interviews/${i.id}`)}>Evaluate</Button>
                    )}
                    {i.evaluations?.length > 0 && (
                      <span className="upper">{i.evaluations.length} eval{i.evaluations.length > 1 ? "s" : ""}</span>
                    )}
                  </td>
                </tr>
              );
            })}
            {rows?.length === 0 && (
              <tr><td colSpan={6} style={{ textAlign: "center", padding: 40, color: "var(--color-muted)" }}>
                No interviews yet.
              </td></tr>
            )}
          </tbody>
        </table>
      </Panel>

      <ScheduleDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} onCreated={() => { setDrawerOpen(false); load(); }} candidates={candidates} />
    </>
  );
}

function ScheduleDrawer({ open, onClose, onCreated, candidates }) {
  const [form, setForm] = useState({
    candidate_id: "", round_name: "Round 1",
    scheduled_at: "", duration_minutes: 60, mode: "video",
    location_or_link: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open && candidates.length) setForm((f) => ({ ...f, candidate_id: f.candidate_id || candidates[0].id }));
  }, [open, candidates]);

  async function submit() {
    setSaving(true); setError(null);
    try {
      await api.post("/api/v1/interviews", {
        ...form,
        scheduled_at: new Date(form.scheduled_at).toISOString(),
        duration_minutes: parseInt(form.duration_minutes),
        interviewer_user_ids: [],
      });
      onCreated();
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Schedule interview"
      actions={<>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={submit} disabled={saving || !form.candidate_id || !form.scheduled_at}>
          {saving ? "Scheduling…" : "Schedule"}
        </Button>
      </>}>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {error && <ErrorBanner message={error} />}
        <div><label className="field-label">Candidate</label>
          <select value={form.candidate_id} onChange={(e) => setForm((f) => ({ ...f, candidate_id: e.target.value }))}>
            {candidates.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select></div>
        <div><label className="field-label">Round</label>
          <input value={form.round_name} onChange={(e) => setForm((f) => ({ ...f, round_name: e.target.value }))} /></div>
        <div><label className="field-label">When</label>
          <input type="datetime-local" value={form.scheduled_at} onChange={(e) => setForm((f) => ({ ...f, scheduled_at: e.target.value }))} /></div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div><label className="field-label">Duration (min)</label>
            <input type="number" min="15" max="240" value={form.duration_minutes} onChange={(e) => setForm((f) => ({ ...f, duration_minutes: e.target.value }))} /></div>
          <div><label className="field-label">Mode</label>
            <select value={form.mode} onChange={(e) => setForm((f) => ({ ...f, mode: e.target.value }))}>
              <option value="video">Video</option><option value="in_person">In person</option><option value="phone">Phone</option>
            </select></div>
        </div>
        <div><label className="field-label">Location or link</label>
          <input value={form.location_or_link} onChange={(e) => setForm((f) => ({ ...f, location_or_link: e.target.value }))} placeholder="Google Meet link or office address" /></div>
      </div>
    </Drawer>
  );
}

