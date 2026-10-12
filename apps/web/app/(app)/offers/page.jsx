"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/Button";
import { Drawer } from "@/components/Drawer";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import { api } from "@/lib/api";
import { ErrorBanner } from "../hiring/page";

const STATUS_PILL = {
  draft: "default", pending_approval: "warn", approved: "ok",
  rejected_internally: "bad", sent: "gold", accepted: "ok",
  declined: "bad", expired: "default", withdrawn: "default",
};

export default function OffersListPage() {
  const [rows, setRows] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [error, setError] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  async function load() {
    try {
      setError(null);
      setRows(await api.get("/api/v1/offers"));
      setCandidates(await api.get("/api/v1/candidates"));
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, []);

  return (
    <>
      <Topbar
        crumb="Offers · All"
        title="Offers"
        sub={rows ? `${rows.length} total` : "Loading…"}
        actions={<Button variant="primary" onClick={() => setDrawerOpen(true)} disabled={candidates.length === 0}>+ Draft offer</Button>}
      />
      {error && <ErrorBanner message={error} />}

      <Panel bodyPadding={false}>
        <table className="data-table">
          <thead><tr><th>Candidate</th><th>Role</th><th>Package</th><th>Start</th><th>Status</th></tr></thead>
          <tbody>
            {(rows ?? []).map((o) => {
              const cand = candidates.find((c) => c.id === o.candidate_id);
              return (
                <tr key={o.id} onClick={() => window.location.assign(`/offers/${o.id}`)}>
                  <td style={{ fontWeight: 600, color: "var(--color-ink)" }}>{cand?.name || o.candidate_id.slice(0, 8)}</td>
                  <td>{o.role_title}</td>
                  <td className="num">{o.currency} {o.base_salary.toLocaleString()}</td>
                  <td>{new Date(o.start_date).toLocaleDateString()}</td>
                  <td><Pill variant={STATUS_PILL[o.status]}>{o.status}</Pill></td>
                </tr>
              );
            })}
            {rows?.length === 0 && (
              <tr><td colSpan={5} style={{ textAlign: "center", padding: 40, color: "var(--color-muted)" }}>
                No offers yet.
              </td></tr>
            )}
          </tbody>
        </table>
      </Panel>

      <DraftOfferDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} onCreated={() => { setDrawerOpen(false); load(); }} candidates={candidates} />
    </>
  );
}

function DraftOfferDrawer({ open, onClose, onCreated, candidates }) {
  const [form, setForm] = useState({
    candidate_id: "", role_title: "", base_salary: "",
    currency: "AED", start_date: "", housing: "", transport: "",
    draft_letter: true,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open && candidates.length) {
      setForm((f) => ({ ...f, candidate_id: f.candidate_id || candidates[0].id }));
    }
  }, [open, candidates]);

  async function submit() {
    setSaving(true); setError(null);
    try {
      const allowances = {};
      if (form.housing) allowances.housing = parseInt(form.housing);
      if (form.transport) allowances.transport = parseInt(form.transport);
      await api.post("/api/v1/offers", {
        candidate_id: form.candidate_id,
        role_title: form.role_title,
        base_salary: parseInt(form.base_salary),
        currency: form.currency,
        allowances,
        start_date: new Date(form.start_date).toISOString(),
        draft_letter: form.draft_letter,
      });
      onCreated();
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Draft offer"
      actions={<>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={submit} disabled={saving || !form.candidate_id || !form.role_title || !form.base_salary || !form.start_date}>
          {saving ? "Drafting…" : "Submit for approval"}
        </Button>
      </>}>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {error && <ErrorBanner message={error} />}
        <div><label className="field-label">Candidate</label>
          <select value={form.candidate_id} onChange={(e) => setForm((f) => ({ ...f, candidate_id: e.target.value }))}>
            {candidates.map((c) => <option key={c.id} value={c.id}>{c.name} — {c.email}</option>)}
          </select></div>
        <div><label className="field-label">Role title</label>
          <input value={form.role_title} onChange={(e) => setForm((f) => ({ ...f, role_title: e.target.value }))} /></div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 100px", gap: 10 }}>
          <div><label className="field-label">Base salary / month</label>
            <input type="number" min="0" value={form.base_salary} onChange={(e) => setForm((f) => ({ ...f, base_salary: e.target.value }))} /></div>
          <div><label className="field-label">Currency</label>
            <input value={form.currency} onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value }))} /></div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div><label className="field-label">Housing allowance</label>
            <input type="number" min="0" value={form.housing} onChange={(e) => setForm((f) => ({ ...f, housing: e.target.value }))} /></div>
          <div><label className="field-label">Transport</label>
            <input type="number" min="0" value={form.transport} onChange={(e) => setForm((f) => ({ ...f, transport: e.target.value }))} /></div>
        </div>
        <div><label className="field-label">Start date</label>
          <input type="date" value={form.start_date} onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))} /></div>
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
          <input type="checkbox" style={{ width: "auto" }} checked={form.draft_letter} onChange={(e) => setForm((f) => ({ ...f, draft_letter: e.target.checked }))} />
          <span>Draft the offer letter with AI</span>
        </label>
      </div>
    </Drawer>
  );
}
