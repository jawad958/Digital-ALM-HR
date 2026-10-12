"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/Button";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import {
  ActivityFeed, EmptyState, ErrorBanner, Loading, Tabs, formatWhen,
} from "@/components/Shared";
import { api } from "@/lib/api";

const REQ_PILL = {
  draft: ["default", "Draft"],
  pending: ["warn", "Pending"],
  in_review: ["warn", "In review"],
  approved: ["ok", "Approved"],
  rejected: ["bad", "Rejected"],
  changes_requested: ["warn", "Changes requested"],
  cancelled: ["default", "Cancelled"],
};

const STEP_PILL = {
  waiting: ["default", "Waiting"],
  pending: ["default", "Waiting"],
  active: ["warn", "Awaiting decision"],
  approved: ["ok", "Approved"],
  rejected: ["bad", "Rejected"],
  changes_requested: ["warn", "Changes requested"],
  skipped: ["default", "Skipped"],
  delegated: ["default", "Delegated"],
};

const TYPE_LABEL = {
  hiring_request: "Hiring request",
  offer: "Offer",
};

export default function ApprovalsPage() {
  const [tab, setTab] = useState("mine");
  const [mine, setMine] = useState(null);
  const [all, setAll] = useState(null);
  const [stuck, setStuck] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [m, a, u] = await Promise.all([
        api.get("/api/v1/approvals/pending"),
        api.get("/api/v1/approvals"),
        api.get("/api/v1/approvals/unassigned"),
      ]);
      setMine(m); setAll(a); setStuck(u);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function decide(stepId, decision) {
    setBusy(stepId);
    try {
      await api.post(`/api/v1/approvals/steps/${stepId}/decide`, { decision, comment: null });
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  const rows = tab === "mine" ? mine : tab === "stuck" ? stuck : all;

  return (
    <>
      <Topbar
        crumb="Approvals · Decision queue"
        title="Approvals"
        sub={
          mine === null
            ? "Loading…"
            : mine.length
              ? `${mine.length} waiting on you`
              : "Nothing waiting on you right now"
        }
        actions={<Button onClick={load}>Refresh</Button>}
      />

      <ErrorBanner message={error} />

      {stuck?.length > 0 && (
        <div style={{
          padding: "11px 14px", borderRadius: 10, marginBottom: 16,
          background: "var(--color-warn-soft)", border: "1px solid var(--color-warn)",
          color: "var(--color-warn)", fontSize: 13,
        }}>
          <strong>{stuck.length}</strong> request{stuck.length === 1 ? " is" : "s are"} waiting on a
          role with nobody assigned to it. Assign that role under Settings &rarr; Users &amp; roles,
          or they will sit here indefinitely.
        </div>
      )}

      <div style={{ marginBottom: 18 }}>
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { key: "mine", label: "Waiting on me", count: mine?.length },
            { key: "all", label: "All requests", count: all?.length },
            { key: "stuck", label: "Unassigned", count: stuck?.length },
          ]}
        />
      </div>

      {rows === null ? (
        <Panel><Loading /></Panel>
      ) : rows.length === 0 ? (
        <Panel>
          <EmptyState title="Nothing here">
            {tab === "mine"
              ? "No approvals are waiting on your decision."
              : tab === "stuck"
                ? "Every active step has an approver assigned."
                : "No approval requests have been raised yet."}
          </EmptyState>
        </Panel>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {rows.map((r) => (
            <RequestCard
              key={r.id}
              req={r}
              onDecide={decide}
              busy={busy}
              actionable={tab === "mine"}
            />
          ))}
        </div>
      )}

      <div style={{ marginTop: 28 }}>
        <Panel title="Recent approval activity">
          <ActivityFeed subjectType="approval_request" limit={15} />
        </Panel>
      </div>
    </>
  );
}

function RequestCard({ req, onDecide, busy, actionable }) {
  const [rv, rl] = REQ_PILL[req.status] || ["default", req.status];
  const steps = [...(req.steps || [])].sort((a, b) => a.step_index - b.step_index);
  const activeStep = steps.find((s) => s.status === "active");
  const ctx = req.context || {};
  const subject = ctx.role_title || ctx.title || TYPE_LABEL[req.request_type] || req.request_type;

  return (
    <Panel
      title={
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <h2 style={{ fontSize: 19 }}>{subject}</h2>
          <Pill variant={rv}>{rl}</Pill>
        </div>
      }
      sub={`${TYPE_LABEL[req.request_type] || req.request_type} · raised ${formatWhen(req.created_at)}${ctx.department ? ` · ${ctx.department}` : ""}`}
      actions={
        actionable && activeStep ? (
          <>
            <Button
              className="btn-danger"
              disabled={busy === activeStep.id}
              onClick={() => onDecide(activeStep.id, "reject")}
            >
              Reject
            </Button>
            <Button
              variant="primary"
              disabled={busy === activeStep.id}
              onClick={() => onDecide(activeStep.id, "approve")}
            >
              {busy === activeStep.id ? "Saving…" : "Approve"}
            </Button>
          </>
        ) : null
      }
    >
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
        {steps.map((s, i) => {
          const [sv, sl] = STEP_PILL[s.status] || ["default", s.status];
          return (
            <div
              key={s.id}
              style={{
                flex: "1 1 170px", minWidth: 170,
                padding: "11px 13px", borderRadius: 10,
                border: `1px solid ${s.status === "active" ? "var(--color-brand)" : "var(--color-stroke)"}`,
                background: s.status === "active" ? "var(--color-brand-soft)" : "var(--color-surface-2)",
              }}
            >
              <div className="upper" style={{ fontSize: 9 }}>Step {i + 1}</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-ink)", marginTop: 3 }}>
                {(s.approver_role || "").toUpperCase()}
              </div>
              <div style={{ marginTop: 7 }}><Pill variant={sv}>{sl}</Pill></div>
              {!s.approver_user_id && s.status === "active" && (
                <div style={{ fontSize: 10, color: "var(--color-bad)", marginTop: 6 }}>
                  No user holds this role
                </div>
              )}
              {s.decided_at && (
                <div style={{ fontSize: 10, color: "var(--color-muted)", marginTop: 6 }}>
                  {formatWhen(s.decided_at)}
                </div>
              )}
              {s.comment && (
                <div style={{ fontSize: 11, color: "var(--color-ink-2)", marginTop: 5, fontStyle: "italic" }}>
                  &ldquo;{s.comment}&rdquo;
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
