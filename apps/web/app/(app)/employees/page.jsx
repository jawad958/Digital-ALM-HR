"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/Button";
import { Drawer } from "@/components/Drawer";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import { EmptyState, ErrorBanner, Loading, Tabs, money } from "@/components/Shared";
import { api } from "@/lib/api";

const STATUS_PILL = {
  onboarding: ["warn", "Onboarding"],
  probation: ["warn", "Probation"],
  active: ["ok", "Active"],
  on_leave: ["default", "On leave"],
  notice_period: ["bad", "Notice period"],
  exited: ["default", "Exited"],
};

const DIVISION_LABEL = {
  manufacturing: "Manufacturing",
  civil: "Civil",
  electro_mechanical: "Electro Mechanical",
  operations: "Operations",
  // legacy values, in case any rows predate the division rename
  head_office: "Head Office",
  contracting: "Contracting",
};

export default function EmployeesPage() {
  const router = useRouter();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("all");
  const [q, setQ] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      setRows(await api.get("/api/v1/employees"));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const all = rows ?? [];
  const filtered = all
    .filter((e) => {
      if (tab === "all") return true;
      if (tab === "onboarding") return e.status === "onboarding";
      return e.division === tab;      // tab key is the division value
    })
    .filter((e) => {
      if (!q.trim()) return true;
      const hay = `${e.full_name} ${e.employee_code} ${e.job_title} ${e.department}`.toLowerCase();
      return hay.includes(q.toLowerCase());
    });

  const headcount = all.filter((e) => e.status !== "exited").length;
  const onboarding = all.filter((e) => e.status === "onboarding").length;

  // Build the division tabs from the data, so a new division needs no code change
  const divisionTabs = Object.entries(
    all.reduce((acc, e) => {
      acc[e.division] = (acc[e.division] || 0) + 1;
      return acc;
    }, {})
  )
    .sort((a, b) => b[1] - a[1])
    .map(([value, count]) => ({
      key: value,
      label: DIVISION_LABEL[value] || value,
      count,
    }));

  return (
    <>
      <Topbar
        crumb="People · Employee directory"
        title="Employees"
        sub={rows === null ? "Loading…" : `${headcount} active · ${onboarding} onboarding`}
        actions={<Button variant="primary" onClick={() => setDrawerOpen(true)}>+ Add employee</Button>}
      />

      <ErrorBanner message={error} />

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, marginBottom: 18 }}>
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { key: "all", label: "Everyone", count: all.length },
            { key: "onboarding", label: "Onboarding", count: onboarding },
            ...divisionTabs,
          ]}
        />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search name, code or role…"
          style={{ maxWidth: 280 }}
        />
      </div>

      <Panel bodyPadding={false}>
        {rows === null ? (
          <Loading />
        ) : filtered.length === 0 ? (
          <EmptyState title="No employees">
            {all.length === 0
              ? "Add your first employee, or accept an offer to create one automatically."
              : "Nothing matches that filter."}
          </EmptyState>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Role</th>
                <th>Department</th>
                <th>Division</th>
                <th>Joined</th>
                <th>Package</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e) => {
                const [v, l] = STATUS_PILL[e.status] || ["default", e.status];
                return (
                  <tr key={e.id} onClick={() => router.push(`/employees/${e.id}`)}>
                    <td>
                      <div style={{ fontWeight: 600, color: "var(--color-ink)" }}>{e.full_name}</div>
                      <div className="num" style={{ fontSize: 10, color: "var(--color-muted)" }}>
                        {e.employee_code}
                      </div>
                    </td>
                    <td>{e.job_title}</td>
                    <td>{e.department}</td>
                    <td>{DIVISION_LABEL[e.division] || e.division}</td>
                    <td className="num" style={{ fontSize: 12 }}>{e.join_date || "—"}</td>
                    <td className="num">{money(e.total_package ?? e.base_salary, e.currency)}</td>
                    <td><Pill variant={v}>{l}</Pill></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>

      <NewEmployeeDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onCreated={() => { setDrawerOpen(false); load(); }}
      />
    </>
  );
}

function NewEmployeeDrawer({ open, onClose, onCreated }) {
  const blank = {
    full_name: "", job_title: "", department: "", division: "manufacturing",
    employment_type: "full_time", personal_email: "", phone: "", nationality: "",
    join_date: "", base_salary: "", currency: "AED", seed_onboarding: true,
  };
  const [form, setForm] = useState(blank);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  function set(k, v) { setForm((f) => ({ ...f, [k]: v })); }

  async function submit(e) {
    e?.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.post("/api/v1/employees", {
        ...form,
        personal_email: form.personal_email || null,
        join_date: form.join_date || null,
        nationality: form.nationality || null,
        phone: form.phone || null,
        base_salary: form.base_salary ? parseInt(form.base_salary, 10) : null,
      });
      setForm(blank);
      onCreated();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open} onClose={onClose} title="Add employee"
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            onClick={submit}
            disabled={saving || !form.full_name || !form.job_title || !form.department}
          >
            {saving ? "Creating…" : "Create employee"}
          </Button>
        </>
      }
    >
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <ErrorBanner message={error} />

        <div><label className="field-label">Full name</label>
          <input value={form.full_name} onChange={(e) => set("full_name", e.target.value)} required /></div>

        <div><label className="field-label">Job title</label>
          <input value={form.job_title} onChange={(e) => set("job_title", e.target.value)} required /></div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div><label className="field-label">Department</label>
            <input value={form.department} onChange={(e) => set("department", e.target.value)} required /></div>
          <div><label className="field-label">Division</label>
            <select value={form.division} onChange={(e) => set("division", e.target.value)}>
              <option value="manufacturing">Manufacturing</option>
              <option value="civil">Civil</option>
              <option value="electro_mechanical">Electro Mechanical</option>
              <option value="operations">Operations</option>
            </select></div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div><label className="field-label">Employment type</label>
            <select value={form.employment_type} onChange={(e) => set("employment_type", e.target.value)}>
              <option value="full_time">Full time</option>
              <option value="part_time">Part time</option>
              <option value="contract">Contract</option>
              <option value="intern">Intern</option>
            </select></div>
          <div><label className="field-label">Join date</label>
            <input type="date" value={form.join_date} onChange={(e) => set("join_date", e.target.value)} /></div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div><label className="field-label">Personal email</label>
            <input type="email" value={form.personal_email} onChange={(e) => set("personal_email", e.target.value)} /></div>
          <div><label className="field-label">Phone</label>
            <input value={form.phone} onChange={(e) => set("phone", e.target.value)} placeholder="+971 50 000 0000" /></div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div><label className="field-label">Nationality</label>
            <input value={form.nationality} onChange={(e) => set("nationality", e.target.value)} /></div>
          <div><label className="field-label">Base salary</label>
            <input type="number" min="0" value={form.base_salary} onChange={(e) => set("base_salary", e.target.value)} /></div>
        </div>

        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
          <input
            type="checkbox" style={{ width: "auto" }}
            checked={form.seed_onboarding}
            onChange={(e) => set("seed_onboarding", e.target.checked)}
          />
          <span>Create the standard joining checklist (IT, assets, PRO, HR)</span>
        </label>
      </form>
    </Drawer>
  );
}
