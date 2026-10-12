"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/Button";
import { Drawer } from "@/components/Drawer";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import { api } from "@/lib/api";

const STATUS_PILL = {
  draft: ["default", "Draft"],
  pending_approval: ["warn", "Pending approval"],
  approved: ["ok", "Approved"],
  rejected: ["bad", "Rejected"],
  sourcing: ["gold", "Sourcing"],
  filled: ["ok", "Filled"],
  closed: ["default", "Closed"],
  cancelled: ["default", "Cancelled"],
};

export default function HiringListPage() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  async function load() {
    try {
      setError(null);
      setRows(await api.get("/api/v1/hiring"));
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <>
      <Topbar
        crumb="Hiring · Open requests"
        title="Hiring requests"
        sub={rows ? `${rows.length} total` : "Loading…"}
        actions={<Button variant="primary" onClick={() => setDrawerOpen(true)}>+ New hiring request</Button>}
      />

      {error && <ErrorBanner message={error} />}

      <Panel bodyPadding={false}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Role</th>
              <th>Department</th>
              <th>Positions</th>
              <th>Band</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {(rows ?? []).map((r) => {
              const [variant, label] = STATUS_PILL[r.status] || ["default", r.status];
              return (
                <tr key={r.id} onClick={() => window.location.assign(`/hiring/${r.id}`)}>
                  <td style={{ fontWeight: 600, color: "var(--color-ink)" }}>{r.role_title}</td>
                  <td>{r.department}</td>
                  <td className="num">{r.positions}</td>
                  <td className="num">
                    {r.salary_min && r.salary_max
                      ? `${r.currency} ${r.salary_min.toLocaleString()} – ${r.salary_max.toLocaleString()}`
                      : "—"}
                  </td>
                  <td><Pill variant={variant}>{label}</Pill></td>
                  <td style={{ fontSize: 11, color: "var(--color-muted)" }}>
                    {new Date(r.created_at).toLocaleDateString()}
                  </td>
                </tr>
              );
            })}
            {rows?.length === 0 && (
              <tr><td colSpan={6} style={{ textAlign: "center", padding: 40, color: "var(--color-muted)" }}>
                No hiring requests yet. Click "+ New hiring request" to create one.
              </td></tr>
            )}
          </tbody>
        </table>
      </Panel>

      <NewRequestDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} onCreated={() => { setDrawerOpen(false); load(); }} />
    </>
  );
}

function NewRequestDrawer({ open, onClose, onCreated }) {
  const [form, setForm] = useState({
    role_title: "", department: "", seniority: "mid", positions: 1,
    salary_min: "", salary_max: "", currency: "AED", justification: "",
    generate_jd: true,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  function set(k, v) { setForm((f) => ({ ...f, [k]: v })); }

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.post("/api/v1/hiring", {
        ...form,
        positions: parseInt(form.positions) || 1,
        salary_min: form.salary_min ? parseInt(form.salary_min) : null,
        salary_max: form.salary_max ? parseInt(form.salary_max) : null,
      });
      onCreated();
      setForm({ role_title: "", department: "", seniority: "mid", positions: 1, salary_min: "", salary_max: "", currency: "AED", justification: "", generate_jd: true });
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open} onClose={onClose} title="New hiring request"
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={submit} disabled={saving || !form.role_title || !form.department}>
            {saving ? "Creating…" : "Submit for approval"}
          </Button>
        </>
      }
    >
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {error && <ErrorBanner message={error} />}

        <div><label className="field-label">Role title</label>
          <input value={form.role_title} onChange={(e) => set("role_title", e.target.value)} placeholder="e.g. Marketing Manager" required /></div>

        <div><label className="field-label">Department</label>
          <input value={form.department} onChange={(e) => set("department", e.target.value)} placeholder="Contracting Division" required /></div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div><label className="field-label">Seniority</label>
            <select value={form.seniority} onChange={(e) => set("seniority", e.target.value)}>
              <option value="junior">Junior</option><option value="mid">Mid</option>
              <option value="senior">Senior</option><option value="lead">Lead</option>
              <option value="director">Director</option>
            </select></div>
          <div><label className="field-label">Positions</label>
            <input type="number" min="1" max="50" value={form.positions} onChange={(e) => set("positions", e.target.value)} /></div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
          <div><label className="field-label">Salary min</label>
            <input type="number" min="0" value={form.salary_min} onChange={(e) => set("salary_min", e.target.value)} placeholder="28000" /></div>
          <div><label className="field-label">Salary max</label>
            <input type="number" min="0" value={form.salary_max} onChange={(e) => set("salary_max", e.target.value)} placeholder="34000" /></div>
          <div><label className="field-label">Currency</label>
            <input value={form.currency} onChange={(e) => set("currency", e.target.value)} maxLength={10} /></div>
        </div>

        <div><label className="field-label">Justification</label>
          <textarea rows={4} value={form.justification} onChange={(e) => set("justification", e.target.value)} placeholder="Why hire this role now?" /></div>

        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
          <input type="checkbox" style={{ width: "auto" }}
            checked={form.generate_jd} onChange={(e) => set("generate_jd", e.target.checked)} />
          <span>Draft the job description with AI</span>
        </label>
      </form>
    </Drawer>
  );
}

export function ErrorBanner({ message }) {
  return (
    <div style={{
      padding: 12, borderRadius: 8, marginBottom: 16,
      background: "var(--color-bad-soft)", color: "var(--color-bad)",
      border: "1px solid var(--color-bad)", fontSize: 13,
    }}>
      {message}
    </div>
  );
}
