"use client";

/**
 * Alpago Interview Evaluation Form (2024-Alpago/HR/IEF form-1.2).
 *
 * Laid out like the paper document: candidate header, the six criteria on the
 * agreement scale, the relevant/UAE experience block, then strengths, areas for
 * improvement and comments. The criteria come from the API so the form and the
 * backend can never drift apart.
 */

import { useEffect, useMemo, useState } from "react";
import { Button } from "./Button";
import { Panel } from "./Panel";
import { Pill } from "./Pill";
import { ErrorBanner, Loading } from "./Shared";
import { api } from "@/lib/api";

export function EvaluationForm({ interview, candidate, onSubmitted, onCancel }) {
  const [form, setForm] = useState(null);
  const [scores, setScores] = useState({});
  const [industry, setIndustry] = useState(null);
  const [uae, setUae] = useState(null);
  const [strengths, setStrengths] = useState("");
  const [improvements, setImprovements] = useState("");
  const [comments, setComments] = useState("");
  const [hrNotes, setHrNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get("/api/v1/interviews/evaluation-form").then(setForm).catch((e) => setError(e.message));
  }, []);

  const answered = form ? form.criteria.filter((c) => scores[c.key]).length : 0;
  const complete = form && answered === form.criteria.length;

  const preview = useMemo(() => {
    const pts = { strongly_agree: 5, agree: 4, disagree: 2 };
    const vals = Object.values(scores).map((v) => pts[v]).filter((n) => n !== undefined);
    if (!vals.length) return null;
    return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length);
  }, [scores]);

  const recommendation = scores.recommended;

  async function submit() {
    setSaving(true);
    setError(null);
    try {
      await api.post(`/api/v1/interviews/${interview.id}/evaluate`, {
        scores,
        relevant_industry_experience: industry,
        uae_work_experience: uae,
        strengths: strengths || null,
        areas_for_improvement: improvements || null,
        additional_comments: comments || null,
        hr_notes: hrNotes || null,
      });
      onSubmitted?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (error && !form) return <ErrorBanner message={error} />;
  if (!form) return <Loading label="Loading evaluation form…" />;

  return (
    <Panel
      title="Interview Evaluation Form"
      sub={`${form.code} · ${answered} of ${form.criteria.length} criteria answered`}
      actions={
        recommendation ? (
          <Pill variant={recommendation === "strongly_agree" || recommendation === "agree" ? "ok" : "bad"}>
            {recommendation === "strongly_agree" || recommendation === "agree"
              ? "Recommended"
              : recommendation === "disagree" ? "Not recommended" : "Undetermined"}
          </Pill>
        ) : null
      }
      footer={
        <>
          <span style={{ fontSize: 12, color: "var(--color-muted)" }}>
            {preview ? `Overall score ${preview} / 5` : "Answer the criteria to score"}
          </span>
          <span style={{ display: "flex", gap: 8 }}>
            {onCancel && <Button variant="ghost" onClick={onCancel}>Cancel</Button>}
            <Button variant="primary" onClick={submit} disabled={saving || !complete}>
              {saving ? "Submitting…" : "Submit evaluation"}
            </Button>
          </span>
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        <ErrorBanner message={error} />

        {/* Candidate information — straight off the form header */}
        <section>
          <SectionTitle>Candidate information</SectionTitle>
          <dl className="kv">
            <dt>Name</dt><dd>{candidate?.name || "—"}</dd>
            <dt>Position title</dt><dd>{interview?.round_name || "—"}</dd>
            <dt>Interview date</dt>
            <dd className="num">
              {interview?.scheduled_at ? new Date(interview.scheduled_at).toLocaleString() : "—"}
            </dd>
            <dt>Expected salary</dt>
            <dd className="num">
              {candidate?.expected_salary ? `AED ${candidate.expected_salary.toLocaleString()}` : "—"}
            </dd>
            <dt>Visa status</dt><dd>{candidate?.visa_status || "—"}</dd>
            <dt>Joining availability</dt><dd>{candidate?.joining_availability || "—"}</dd>
          </dl>
        </section>

        {/* The six criteria */}
        <section>
          <SectionTitle>Evaluation criteria</SectionTitle>
          <div className="panel" style={{ marginTop: 6 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: 32 }}>#</th>
                  <th>Criterion</th>
                  {form.scale.map((s) => (
                    <th key={s.value} style={{ textAlign: "center", width: 96 }}>{s.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {form.criteria.map((c, i) => (
                  <tr key={c.key}>
                    <td className="num" style={{ color: "var(--color-muted)" }}>{i + 1}</td>
                    <td style={{ color: "var(--color-ink)" }}>{c.label}</td>
                    {form.scale.map((s) => (
                      <td key={s.value} style={{ textAlign: "center" }}>
                        <input
                          type="radio"
                          style={{ width: "auto" }}
                          name={`crit-${c.key}`}
                          checked={scores[c.key] === s.value}
                          onChange={() => setScores((p) => ({ ...p, [c.key]: s.value }))}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Relevant / UAE experience */}
        <section>
          <SectionTitle>Relevant / UAE experience</SectionTitle>
          <div className="panel" style={{ marginTop: 6 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Question</th>
                  <th style={{ textAlign: "center", width: 72 }}>Yes</th>
                  <th style={{ textAlign: "center", width: 72 }}>No</th>
                </tr>
              </thead>
              <tbody>
                <YesNoRow
                  label="Possesses relevant industry experience"
                  name="industry" value={industry} onChange={setIndustry}
                />
                <YesNoRow
                  label="Possesses UAE work experience"
                  name="uae" value={uae} onChange={setUae}
                />
              </tbody>
            </table>
          </div>
        </section>

        {/* Strengths / improvements side by side, as on the form */}
        <section>
          <SectionTitle>Assessment</SectionTitle>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div>
              <label className="field-label">Candidate&rsquo;s strengths</label>
              <textarea rows={4} value={strengths} onChange={(e) => setStrengths(e.target.value)} />
            </div>
            <div>
              <label className="field-label">Areas for improvement</label>
              <textarea rows={4} value={improvements} onChange={(e) => setImprovements(e.target.value)} />
            </div>
          </div>
          <div style={{ marginTop: 14 }}>
            <label className="field-label">Additional comments</label>
            <textarea rows={3} value={comments} onChange={(e) => setComments(e.target.value)} />
          </div>
          <div style={{ marginTop: 14 }}>
            <label className="field-label">For HR use</label>
            <textarea rows={2} value={hrNotes} onChange={(e) => setHrNotes(e.target.value)} />
          </div>
        </section>
      </div>
    </Panel>
  );
}

function YesNoRow({ label, name, value, onChange }) {
  return (
    <tr>
      <td style={{ color: "var(--color-ink)" }}>{label}</td>
      {[true, false].map((v) => (
        <td key={String(v)} style={{ textAlign: "center" }}>
          <input
            type="radio" style={{ width: "auto" }} name={name}
            checked={value === v} onChange={() => onChange(v)}
          />
        </td>
      ))}
    </tr>
  );
}

function SectionTitle({ children }) {
  return (
    <div
      className="upper"
      style={{
        paddingBottom: 8, marginBottom: 12,
        borderBottom: "1px solid var(--color-stroke)",
        color: "var(--color-brand)",
      }}
    >
      {children}
    </div>
  );
}

/** Read-only rendering of a submitted evaluation. */
export function EvaluationReadout({ evaluation, criteria, scale }) {
  const labelFor = (v) => scale?.find((s) => s.value === v)?.label ?? v ?? "—";
  const toneFor = (v) =>
    v === "strongly_agree" ? "ok" : v === "agree" ? "ok" : v === "disagree" ? "bad" : "default";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <Pill variant={evaluation.verdict === "recommend" ? "ok" : evaluation.verdict === "not_recommend" ? "bad" : "warn"}>
          {evaluation.verdict === "recommend" ? "Recommended"
            : evaluation.verdict === "not_recommend" ? "Not recommended" : "Hold"}
        </Pill>
        {evaluation.overall_score != null && (
          <span style={{ fontSize: 13, color: "var(--color-ink-2)" }}>
            Overall <strong style={{ color: "var(--color-brand)" }}>{evaluation.overall_score} / 5</strong>
          </span>
        )}
        {evaluation.relevant_industry_experience != null && (
          <Pill variant={evaluation.relevant_industry_experience ? "ok" : "default"}>
            Industry experience: {evaluation.relevant_industry_experience ? "Yes" : "No"}
          </Pill>
        )}
        {evaluation.uae_work_experience != null && (
          <Pill variant={evaluation.uae_work_experience ? "ok" : "default"}>
            UAE experience: {evaluation.uae_work_experience ? "Yes" : "No"}
          </Pill>
        )}
      </div>

      {criteria?.length > 0 && (
        <table className="data-table">
          <tbody>
            {criteria.map((c) => (
              <tr key={c.key}>
                <td style={{ color: "var(--color-ink)" }}>{c.label}</td>
                <td style={{ width: 150, textAlign: "right" }}>
                  <Pill variant={toneFor(evaluation.scores?.[c.key])}>
                    {labelFor(evaluation.scores?.[c.key])}
                  </Pill>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {evaluation.strengths && (
        <Block title="Strengths">{evaluation.strengths}</Block>
      )}
      {evaluation.areas_for_improvement && (
        <Block title="Areas for improvement">{evaluation.areas_for_improvement}</Block>
      )}
      {evaluation.additional_comments && (
        <Block title="Additional comments">{evaluation.additional_comments}</Block>
      )}
      {evaluation.hr_notes && <Block title="For HR use">{evaluation.hr_notes}</Block>}
    </div>
  );
}

function Block({ title, children }) {
  return (
    <div>
      <div className="upper" style={{ marginBottom: 5 }}>{title}</div>
      <p style={{ fontSize: 13, lineHeight: 1.7, margin: 0, whiteSpace: "pre-wrap", color: "var(--color-ink-2)" }}>
        {children}
      </p>
    </div>
  );
}
