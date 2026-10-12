"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/Button";
import { Drawer } from "@/components/Drawer";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import { FormRenderer } from "@/components/FormRenderer";
import { ActivityFeed, EmptyState, ErrorBanner, Loading, Tabs, formatWhen } from "@/components/Shared";
import { api } from "@/lib/api";

const STATUS_PILL = {
  draft: ["default", "Draft"],
  pending_approval: ["warn", "Pending approval"],
  approved: ["ok", "Approved"],
  rejected: ["bad", "Rejected"],
  acknowledged: ["ok", "Acknowledged"],
  completed: ["ok", "Completed"],
  cancelled: ["default", "Cancelled"],
};

const CATEGORY_LABEL = {
  request: "Request",
  letter: "Letter",
  record: "Record",
};

export default function FormsPage() {
  const router = useRouter();
  const [defs, setDefs] = useState(null);
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("submitted");
  const [picking, setPicking] = useState(false);
  const [active, setActive] = useState(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [d, r] = await Promise.all([
        api.get("/api/v1/forms/definitions"),
        api.get("/api/v1/forms"),
      ]);
      setDefs(d);
      setRows(r);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const byKey = useMemo(
    () => Object.fromEntries((defs ?? []).map((d) => [d.key, d])),
    [defs]
  );

  return (
    <>
      <Topbar
        crumb="HR · Official forms"
        title="Forms"
        sub={
          defs === null
            ? "Loading…"
            : `${defs.length} official forms · ${rows?.length ?? 0} submitted`
        }
        actions={
          <Button variant="primary" onClick={() => setPicking(true)}>
            + Raise a form
          </Button>
        }
      />

      <ErrorBanner message={error} />

      <div style={{ marginBottom: 18 }}>
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { key: "submitted", label: "Submitted", count: rows?.length },
            { key: "catalogue", label: "Form catalogue", count: defs?.length },
          ]}
        />
      </div>

      {tab === "catalogue" ? (
        <CatalogueGrid defs={defs} onPick={(d) => setActive(d)} />
      ) : (
        <Panel bodyPadding={false}>
          {rows === null ? (
            <Loading />
          ) : rows.length === 0 ? (
            <EmptyState title="No forms submitted yet">
              Click &ldquo;Raise a form&rdquo; to submit one of Alpago&rsquo;s official HR forms.
            </EmptyState>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Reference</th><th>Form</th><th>Employee</th>
                  <th>Raised</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const [v, l] = STATUS_PILL[r.status] || ["default", r.status];
                  return (
                    <tr key={r.id} onClick={() => router.push(`/forms/${r.id}`)}>
                      <td className="num" style={{ fontWeight: 600, color: "var(--color-ink)" }}>
                        {r.reference}
                      </td>
                      <td>
                        <div style={{ color: "var(--color-ink)" }}>{r.title}</div>
                        <div className="num" style={{ fontSize: 10, color: "var(--color-muted)" }}>
                          {r.form_code}
                        </div>
                      </td>
                      <td>{r.employee_name || "—"}</td>
                      <td style={{ fontSize: 11, color: "var(--color-muted)" }}>
                        {formatWhen(r.created_at)}
                      </td>
                      <td><Pill variant={v}>{l}</Pill></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Panel>
      )}

      <div style={{ marginTop: 28 }}>
        <Panel title="Recent form activity">
          <ActivityFeed subjectType="form_submission" limit={12} />
        </Panel>
      </div>

      {/* Pick which form to raise */}
      <Drawer open={picking} onClose={() => setPicking(false)} title="Choose a form">
        <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
          {(defs ?? []).map((d) => (
            <button
              key={d.key}
              type="button"
              onClick={() => { setPicking(false); setActive(d); }}
              style={{
                textAlign: "left", font: "inherit", cursor: "pointer",
                padding: "12px 14px", borderRadius: 10,
                border: "1px solid var(--color-stroke)",
                background: "var(--color-surface-2)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--color-ink)" }}>{d.title}</span>
                <Pill>{CATEGORY_LABEL[d.category] || d.category}</Pill>
              </div>
              <div style={{ fontSize: 11, color: "var(--color-muted)", marginTop: 4 }}>
                {d.description}
              </div>
              <div className="num" style={{ fontSize: 10, color: "var(--color-muted)", marginTop: 5 }}>
                {d.code} · raised by {d.raised_by}
              </div>
            </button>
          ))}
        </div>
      </Drawer>

      <SubmitFormDrawer
        definition={active}
        onClose={() => setActive(null)}
        onSubmitted={() => { setActive(null); setTab("submitted"); load(); }}
      />
    </>
  );
}

function CatalogueGrid({ defs, onPick }) {
  if (!defs) return <Panel><Loading /></Panel>;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 14 }}>
      {defs.map((d) => (
        <Panel
          key={d.key}
          title={d.title}
          sub={`${d.code} · raised by ${d.raised_by}`}
          actions={<Pill>{CATEGORY_LABEL[d.category] || d.category}</Pill>}
        >
          <p style={{ fontSize: 12.5, color: "var(--color-ink-2)", lineHeight: 1.6, margin: "0 0 12px" }}>
            {d.description}
          </p>
          <div className="upper" style={{ marginBottom: 6 }}>Approval route</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5, alignItems: "center" }}>
            {d.chain.length === 0 ? (
              <span style={{ fontSize: 12, color: "var(--color-muted)" }}>No approval required</span>
            ) : (
              d.chain.map((step, i) => (
                <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                  {i > 0 && <span style={{ color: "var(--color-muted)" }}>→</span>}
                  <Pill variant="gold">{step.label || step.role}</Pill>
                </span>
              ))
            )}
          </div>
          <div style={{ marginTop: 14 }}>
            <Button className="btn-sm" onClick={() => onPick(d)}>Raise this form</Button>
          </div>
        </Panel>
      ))}
    </div>
  );
}

function SubmitFormDrawer({ definition, onClose, onSubmitted }) {
  const [data, setData] = useState({});
  const [employeeName, setEmployeeName] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [employees, setEmployees] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData({});
    setEmployeeName("");
    setEmployeeId("");
    setError(null);
    if (definition) {
      api.get("/api/v1/employees").then(setEmployees).catch(() => setEmployees([]));
    }
  }, [definition]);

  async function submit() {
    setSaving(true);
    setError(null);
    try {
      await api.post("/api/v1/forms", {
        form_type: definition.key,
        employee_id: employeeId || null,
        employee_name: employeeName || null,
        data,
      });
      onSubmitted();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (!definition) return null;

  return (
    <Drawer
      open={!!definition}
      onClose={onClose}
      title={definition.title}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={submit} disabled={saving}>
            {saving ? "Submitting…" : "Submit for approval"}
          </Button>
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
        <ErrorBanner message={error} />

        <div style={{
          padding: "10px 13px", borderRadius: 9, fontSize: 11,
          background: "var(--color-surface-2)", border: "1px solid var(--color-stroke)",
          color: "var(--color-muted)",
        }}>
          <span className="num">{definition.code}</span>
          {definition.chain.length > 0 && (
            <> · routes to {definition.chain.map((s) => s.label || s.role).join(" → ")}</>
          )}
        </div>

        <section>
          <div
            className="upper"
            style={{
              paddingBottom: 8, marginBottom: 14,
              borderBottom: "1px solid var(--color-stroke)",
              color: "var(--color-brand)",
            }}
          >
            Employee
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 13 }}>
            <div>
              <label className="field-label">Employee on record</label>
              <select
                value={employeeId}
                onChange={(e) => {
                  setEmployeeId(e.target.value);
                  const emp = employees.find((x) => x.id === e.target.value);
                  if (emp) setEmployeeName(emp.full_name);
                }}
              >
                <option value="">— not on record / enter manually —</option>
                {employees.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.full_name} ({e.employee_code}) — {e.job_title}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="field-label">Employee name</label>
              <input
                value={employeeName}
                onChange={(e) => setEmployeeName(e.target.value)}
                placeholder="Full name as it appears on the passport"
              />
            </div>
          </div>
        </section>

        <FormRenderer definition={definition} value={data} onChange={setData} />
      </div>
    </Drawer>
  );
}
