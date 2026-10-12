"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/Button";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import {
  ActivityFeed, DocumentsPanel, EmptyState, ErrorBanner, Loading, Tabs, money,
} from "@/components/Shared";
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
};

const CATEGORY_LABEL = {
  it: "IT",
  assets: "Assets",
  hr: "HR",
  pro: "PRO / Government",
  finance: "Finance",
};

export default function EmployeeDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [emp, setEmp] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("profile");

  const load = useCallback(async () => {
    try {
      setError(null);
      setEmp(await api.get(`/api/v1/employees/${id}`));
    } catch (e) {
      setError(e.message);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  if (error) return <><Topbar crumb="People" title="Employee" /><ErrorBanner message={error} /></>;
  if (!emp) return <><Topbar crumb="People" title="Employee" /><Panel><Loading /></Panel></>;

  const [sv, sl] = STATUS_PILL[emp.status] || ["default", emp.status];

  return (
    <>
      <Topbar
        crumb={`People · ${emp.employee_code}`}
        title={emp.full_name}
        sub={`${emp.job_title} · ${emp.department}`}
        actions={
          <>
            <Button onClick={() => router.push("/employees")}>Back to directory</Button>
            <Pill variant={sv}>{sl}</Pill>
          </>
        }
      />

      {/* Completeness summary */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 14, marginBottom: 22 }}>
        <div className="stat">
          <div className="stat-l">Onboarding</div>
          <div className="stat-v">{emp.onboarding_percent}%</div>
          <div className="progress" style={{ marginTop: 10 }}>
            <i style={{ width: `${emp.onboarding_percent}%` }} />
          </div>
        </div>
        <div className={`stat ${emp.documents_percent < 100 ? "" : "stat-lead"}`}>
          <div className="stat-l">Documents</div>
          <div className="stat-v">{emp.documents_percent}%</div>
          <div className="stat-s">
            {emp.documents_missing.length
              ? `Missing: ${emp.documents_missing.slice(0, 2).join(", ")}${emp.documents_missing.length > 2 ? "…" : ""}`
              : "All required documents on file"}
          </div>
        </div>
        <div className="stat">
          <div className="stat-l">Total package</div>
          <div className="stat-v" style={{ fontSize: 30 }}>
            {money(emp.total_package ?? emp.base_salary, emp.currency)}
          </div>
          <div className="stat-s">Base {money(emp.base_salary, emp.currency)}</div>
        </div>
        <div className="stat">
          <div className="stat-l">Joined</div>
          <div className="stat-v" style={{ fontSize: 26 }}>{emp.join_date || "—"}</div>
          <div className="stat-s">{emp.employment_type?.replace("_", " ")}</div>
        </div>
      </div>

      <div style={{ marginBottom: 18 }}>
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { key: "profile", label: "Profile" },
            { key: "onboarding", label: "Onboarding", count: emp.onboarding_tasks?.length },
            { key: "documents", label: "Documents" },
            { key: "activity", label: "Activity" },
          ]}
        />
      </div>

      {tab === "profile" && <ProfileTab emp={emp} />}
      {tab === "onboarding" && <OnboardingTab emp={emp} onChanged={load} />}
      {tab === "documents" && (
        <Panel><DocumentsPanel ownerType="employee" ownerId={emp.id} onChanged={load} /></Panel>
      )}
      {tab === "activity" && (
        <Panel title="Full audit trail">
          <ActivityFeed subjectType="employee" subjectId={emp.id} limit={100} />
        </Panel>
      )}
    </>
  );
}

function ProfileTab({ emp }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(330px, 1fr))", gap: 16 }}>
      <Panel title="Personal">
        <dl className="kv">
          <dt>Full name</dt><dd>{emp.full_name}</dd>
          <dt>Employee code</dt><dd className="num">{emp.employee_code}</dd>
          <dt>Nationality</dt><dd>{emp.nationality || "—"}</dd>
          <dt>Date of birth</dt><dd className="num">{emp.date_of_birth || "—"}</dd>
          <dt>Personal email</dt><dd>{emp.personal_email || "—"}</dd>
          <dt>Work email</dt><dd>{emp.work_email || "—"}</dd>
          <dt>Phone</dt><dd className="num">{emp.phone || "—"}</dd>
        </dl>
      </Panel>

      <Panel title="Employment">
        <dl className="kv">
          <dt>Job title</dt><dd>{emp.job_title}</dd>
          <dt>Department</dt><dd>{emp.department}</dd>
          <dt>Division</dt><dd>{DIVISION_LABEL[emp.division] || emp.division}</dd>
          <dt>Type</dt><dd>{(emp.employment_type || "").replace("_", " ")}</dd>
          <dt>Join date</dt><dd className="num">{emp.join_date || "—"}</dd>
          <dt>Probation ends</dt><dd className="num">{emp.probation_end_date || "—"}</dd>
          <dt>Contract ends</dt><dd className="num">{emp.contract_end_date || "—"}</dd>
        </dl>
      </Panel>

      <Panel title="Compensation">
        <dl className="kv">
          <dt>Base salary</dt><dd className="num">{money(emp.base_salary, emp.currency)}</dd>
          {Object.entries(emp.allowances || {}).map(([k, v]) => (
            <div key={k} style={{ display: "contents" }}>
              <dt>{k}</dt><dd className="num">{money(v, emp.currency)}</dd>
            </div>
          ))}
          <dt>Total package</dt>
          <dd className="num" style={{ fontWeight: 600 }}>
            {money(emp.total_package ?? emp.base_salary, emp.currency)}
          </dd>
        </dl>
      </Panel>

      <Panel title="Compliance">
        <dl className="kv">
          <dt>Passport no.</dt><dd className="num">{emp.passport_number || "—"}</dd>
          <dt>Emirates ID</dt><dd className="num">{emp.emirates_id || "—"}</dd>
          <dt>Visa status</dt><dd>{emp.visa_status || "—"}</dd>
        </dl>
      </Panel>

      <Panel title="Emergency contact">
        <dl className="kv">
          <dt>Name</dt><dd>{emp.emergency_name || "—"}</dd>
          <dt>Relationship</dt><dd>{emp.emergency_relation || "—"}</dd>
          <dt>Phone</dt><dd className="num">{emp.emergency_phone || "—"}</dd>
        </dl>
      </Panel>

      {emp.notes && <Panel title="Notes"><p style={{ fontSize: 13, lineHeight: 1.7 }}>{emp.notes}</p></Panel>}
    </div>
  );
}

function OnboardingTab({ emp, onChanged }) {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  async function toggle(task) {
    setBusy(task.id);
    try {
      await api.post(`/api/v1/employees/onboarding/${task.id}/complete?done=${!task.completed}`);
      onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  const tasks = emp.onboarding_tasks || [];
  if (!tasks.length) return <Panel><EmptyState>No onboarding checklist for this employee.</EmptyState></Panel>;

  const grouped = tasks.reduce((acc, t) => {
    (acc[t.category] ||= []).push(t);
    return acc;
  }, {});

  return (
    <>
      <ErrorBanner message={error} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(330px, 1fr))", gap: 16 }}>
        {Object.entries(grouped).map(([cat, items]) => {
          const done = items.filter((t) => t.completed).length;
          return (
            <Panel
              key={cat}
              title={CATEGORY_LABEL[cat] || cat}
              sub={`${done} of ${items.length} complete`}
            >
              <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
                {items.map((t) => (
                  <label
                    key={t.id}
                    style={{
                      display: "flex", alignItems: "flex-start", gap: 10,
                      cursor: busy === t.id ? "wait" : "pointer",
                      opacity: busy === t.id ? 0.55 : 1,
                    }}
                  >
                    <input
                      type="checkbox"
                      style={{ width: "auto", marginTop: 2, flexShrink: 0 }}
                      checked={t.completed}
                      disabled={busy === t.id}
                      onChange={() => toggle(t)}
                    />
                    <span style={{ minWidth: 0 }}>
                      <span style={{
                        display: "block", fontSize: 13, fontWeight: 550,
                        color: t.completed ? "var(--color-muted)" : "var(--color-ink)",
                        textDecoration: t.completed ? "line-through" : "none",
                      }}>
                        {t.title}
                      </span>
                      {t.description && (
                        <span style={{ display: "block", fontSize: 11, color: "var(--color-muted)", marginTop: 2 }}>
                          {t.description}
                        </span>
                      )}
                      {t.owner_role && (
                        <span className="upper" style={{ fontSize: 9, marginTop: 4, display: "inline-block" }}>
                          Owner: {t.owner_role.replace("_", " ")}
                        </span>
                      )}
                    </span>
                  </label>
                ))}
              </div>
            </Panel>
          );
        })}
      </div>
    </>
  );
}
