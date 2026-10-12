"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/Button";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import { EvaluationForm, EvaluationReadout } from "@/components/EvaluationForm";
import { ActivityFeed, EmptyState, ErrorBanner, Loading, formatWhen } from "@/components/Shared";
import { api, auth } from "@/lib/api";

const STATUS_PILL = {
  scheduled: ["warn", "Scheduled"],
  completed: ["ok", "Completed"],
  cancelled: ["default", "Cancelled"],
  no_show: ["bad", "No show"],
};

const MODE_LABEL = { in_person: "In person", video: "Video call", phone: "Phone" };

export default function InterviewDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [interview, setInterview] = useState(null);
  const [candidate, setCandidate] = useState(null);
  const [formDef, setFormDef] = useState(null);
  const [error, setError] = useState(null);
  const [evaluating, setEvaluating] = useState(false);
  const [loadingQ, setLoadingQ] = useState(false);

  const me = auth.getUser();

  const load = useCallback(async () => {
    try {
      setError(null);
      const i = await api.get(`/api/v1/interviews/${id}`);
      setInterview(i);
      const [c, f] = await Promise.all([
        api.get(`/api/v1/candidates/${i.candidate_id}`).catch(() => null),
        api.get("/api/v1/interviews/evaluation-form").catch(() => null),
      ]);
      setCandidate(c);
      setFormDef(f);
    } catch (e) {
      setError(e.message);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function generateQuestions() {
    setLoadingQ(true);
    try {
      const i = await api.post(`/api/v1/interviews/${id}/questions`, {});
      setInterview(i);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoadingQ(false);
    }
  }

  if (error && !interview) {
    return <><Topbar crumb="Hiring · Interviews" title="Interview" /><ErrorBanner message={error} /></>;
  }
  if (!interview) {
    return <><Topbar crumb="Hiring · Interviews" title="Interview" /><Panel><Loading /></Panel></>;
  }

  const [sv, sl] = STATUS_PILL[interview.status] || ["default", interview.status];
  const evaluations = interview.evaluations || [];
  const alreadyEvaluated = me && evaluations.some((e) => e.interviewer_user_id === me.id);

  return (
    <>
      <Topbar
        crumb={`Hiring · Interviews · ${interview.round_name}`}
        title={candidate?.name || "Interview"}
        sub={`${new Date(interview.scheduled_at).toLocaleString()} · ${MODE_LABEL[interview.mode] || interview.mode} · ${interview.duration_minutes} min`}
        actions={
          <>
            <Button onClick={() => router.push("/interviews")}>Back</Button>
            {!alreadyEvaluated && !evaluating && (
              <Button variant="primary" onClick={() => setEvaluating(true)}>
                Fill evaluation form
              </Button>
            )}
            <Pill variant={sv}>{sl}</Pill>
          </>
        }
      />

      <ErrorBanner message={error} />

      {evaluating ? (
        <EvaluationForm
          interview={interview}
          candidate={candidate}
          onCancel={() => setEvaluating(false)}
          onSubmitted={() => { setEvaluating(false); load(); }}
        />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(280px, 1fr)", gap: 18, alignItems: "start" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <Panel
              title={`Evaluations (${evaluations.length})`}
              sub={formDef?.code}
            >
              {evaluations.length === 0 ? (
                <EmptyState title="Not evaluated yet">
                  Fill the evaluation form once the interview has taken place.
                </EmptyState>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
                  {evaluations.map((ev, i) => (
                    <div
                      key={ev.id}
                      style={i > 0 ? { paddingTop: 22, borderTop: "1px solid var(--color-stroke)" } : undefined}
                    >
                      <div style={{ fontSize: 11, color: "var(--color-muted)", marginBottom: 10 }}>
                        Submitted {formatWhen(ev.created_at)}
                      </div>
                      <EvaluationReadout
                        evaluation={ev}
                        criteria={formDef?.criteria}
                        scale={formDef?.scale}
                      />
                    </div>
                  ))}
                </div>
              )}
            </Panel>

            <Panel
              title="Interview questions"
              sub={interview.questions_generated_by_ai ? "Drafted with AI" : "Prepared questions"}
              actions={
                <Button className="btn-sm" onClick={generateQuestions} disabled={loadingQ}>
                  {loadingQ ? "Drafting…" : "Generate with AI"}
                </Button>
              }
            >
              {interview.questions?.length ? (
                <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: 1.8, color: "var(--color-ink-2)" }}>
                  {interview.questions.map((q, i) => (
                    <li key={i} style={{ marginBottom: 10 }}>
                      <div style={{ color: "var(--color-ink)", fontWeight: 500 }}>
                        {q.question || String(q)}
                      </div>
                      {q.rationale && (
                        <div style={{ color: "var(--color-muted)", fontSize: 11.5, marginTop: 2 }}>
                          {q.rationale}
                        </div>
                      )}
                    </li>
                  ))}
                </ol>
              ) : (
                <EmptyState>No questions prepared.</EmptyState>
              )}
            </Panel>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <Panel title="Candidate">
              <dl className="kv" style={{ gridTemplateColumns: "120px 1fr" }}>
                <dt>Name</dt><dd>{candidate?.name || "—"}</dd>
                <dt>Current role</dt><dd>{candidate?.current_role || "—"}</dd>
                <dt>Experience</dt>
                <dd>{candidate?.years_experience != null ? `${candidate.years_experience} years` : "—"}</dd>
                <dt>Expected</dt>
                <dd className="num">
                  {candidate?.expected_salary ? `AED ${candidate.expected_salary.toLocaleString()}` : "—"}
                </dd>
                <dt>Visa status</dt><dd>{candidate?.visa_status || "—"}</dd>
                <dt>Availability</dt><dd>{candidate?.joining_availability || "—"}</dd>
                <dt>Stage</dt><dd>{candidate?.stage || "—"}</dd>
              </dl>
              {candidate && (
                <div style={{ marginTop: 14 }}>
                  <Button className="btn-sm" onClick={() => router.push(`/candidates/${candidate.id}`)}>
                    Open candidate
                  </Button>
                </div>
              )}
            </Panel>

            <Panel title="Activity">
              <ActivityFeed subjectType="candidate" subjectId={interview.candidate_id} limit={20} />
            </Panel>
          </div>
        </div>
      )}
    </>
  );
}
