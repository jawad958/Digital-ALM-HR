"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/Button";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import { FormReadout } from "@/components/FormRenderer";
import { ActivityFeed, ErrorBanner, Loading, formatWhen } from "@/components/Shared";
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

const STEP_PILL = {
  waiting: ["default", "Waiting"],
  pending: ["default", "Waiting"],
  active: ["warn", "Awaiting decision"],
  approved: ["ok", "Approved"],
  rejected: ["bad", "Rejected"],
  skipped: ["default", "Skipped"],
  delegated: ["default", "Delegated"],
};

export default function FormDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [form, setForm] = useState(null);
  const [definition, setDefinition] = useState(null);
  const [approval, setApproval] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      const f = await api.get(`/api/v1/forms/${id}`);
      setForm(f);
      const d = await api.get(`/api/v1/forms/definitions/${f.form_type}`);
      setDefinition(d);
      if (f.approval_request_id) {
        try {
          setApproval(await api.get(`/api/v1/approvals/${f.approval_request_id}`));
        } catch {
          setApproval(null);
        }
      }
    } catch (e) {
      setError(e.message);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function acknowledge() {
    setBusy(true);
    try {
      await api.post(`/api/v1/forms/${id}/acknowledge`, { note: null });
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <><Topbar crumb="HR · Forms" title="Form" /><ErrorBanner message={error} /></>;
  if (!form || !definition) return <><Topbar crumb="HR · Forms" title="Form" /><Panel><Loading /></Panel></>;

  const [sv, sl] = STATUS_PILL[form.status] || ["default", form.status];
  const steps = [...(approval?.steps || [])].sort((a, b) => a.step_index - b.step_index);
  const needsAck = definition.requires_acknowledgement && !form.acknowledged_at;

  return (
    <>
      <Topbar
        crumb={`HR · Forms · ${form.reference}`}
        title={definition.title}
        sub={`${form.form_code}${form.employee_name ? ` · ${form.employee_name}` : ""} · raised ${formatWhen(form.created_at)}`}
        actions={
          <>
            <Button onClick={() => router.push("/forms")}>Back to forms</Button>
            <Button onClick={() => window.print()}>Print</Button>
            <Pill variant={sv}>{sl}</Pill>
          </>
        }
      />

      {needsAck && (
        <Panel
          title="Employee acknowledgement required"
          actions={
            <Button variant="primary" onClick={acknowledge} disabled={busy}>
              {busy ? "Saving…" : "Acknowledge"}
            </Button>
          }
        >
          <p style={{ fontSize: 13, lineHeight: 1.7, margin: 0, color: "var(--color-ink-2)" }}>
            {definition.acknowledgement_text}
          </p>
        </Panel>
      )}

      {form.acknowledged_at && (
        <div style={{
          padding: "11px 14px", borderRadius: 10, marginBottom: 16, fontSize: 13,
          background: "var(--color-ok-soft)", border: "1px solid var(--color-ok)",
          color: "var(--color-ok)",
        }}>
          Acknowledged by the employee on {new Date(form.acknowledged_at).toLocaleString()}.
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(260px, 1fr)", gap: 18, alignItems: "start", marginTop: needsAck ? 18 : 0 }}>
        <Panel title="Form contents">
          <FormReadout definition={definition} data={form.data || {}} />
        </Panel>

        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <Panel title="Approval route">
            {steps.length === 0 ? (
              <p style={{ fontSize: 12, color: "var(--color-muted)", margin: 0 }}>
                No approval chain is configured for this form type.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                {steps.map((s, i) => {
                  const [v, l] = STEP_PILL[s.status] || ["default", s.status];
                  const label = definition.chain[i]?.label || s.approver_role;
                  return (
                    <div
                      key={s.id}
                      style={{
                        padding: "10px 12px", borderRadius: 9,
                        border: `1px solid ${s.status === "active" ? "var(--color-brand)" : "var(--color-stroke)"}`,
                        background: s.status === "active" ? "var(--color-brand-soft)" : "var(--color-surface-2)",
                      }}
                    >
                      <div className="upper" style={{ fontSize: 9 }}>Step {i + 1}</div>
                      <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--color-ink)", marginTop: 2 }}>
                        {label}
                      </div>
                      <div style={{ marginTop: 6 }}><Pill variant={v}>{l}</Pill></div>
                      {s.decided_at && (
                        <div style={{ fontSize: 10, color: "var(--color-muted)", marginTop: 5 }}>
                          {formatWhen(s.decided_at)}
                        </div>
                      )}
                      {s.comment && (
                        <div style={{ fontSize: 11, color: "var(--color-ink-2)", marginTop: 4, fontStyle: "italic" }}>
                          &ldquo;{s.comment}&rdquo;
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </Panel>

          <Panel title="Audit trail">
            <ActivityFeed subjectType="form_submission" subjectId={form.id} limit={40} />
          </Panel>
        </div>
      </div>
    </>
  );
}
