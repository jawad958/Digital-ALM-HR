"use client";

/** Shared building blocks used across modules — kept in one file on purpose. */

import { useEffect, useState } from "react";
import { Button } from "./Button";
import { Drawer } from "./Drawer";
import { Pill } from "./Pill";
import { api, auth } from "@/lib/api";

/**
 * Download a document. A plain <a href> can't carry the Authorization header,
 * so fetch the file with the JWT attached and hand the browser a blob instead.
 */
export async function downloadDocument(docId, filename) {
  const res = await fetch(`/api/v1/documents/${docId}/download`, {
    headers: auth.getToken() ? { Authorization: `Bearer ${auth.getToken()}` } : {},
  });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "document";
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Give the browser a moment before revoking, or Safari cancels the download.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function DownloadLink({ docId, filename, children, className = "btn btn-sm" }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  return (
    <button
      type="button"
      className={className}
      disabled={busy}
      title={err || undefined}
      onClick={async (e) => {
        e.stopPropagation();
        setBusy(true);
        setErr(null);
        try {
          await downloadDocument(docId, filename);
        } catch (ex) {
          setErr(ex.message);
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? "Opening…" : children}
    </button>
  );
}

// ─────────────────── feedback ──────────────────────────────────────────────

export function ErrorBanner({ message }) {
  if (!message) return null;
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

export function EmptyState({ title, children }) {
  return (
    <div className="empty">
      {title && <div className="empty-title">{title}</div>}
      <div>{children}</div>
    </div>
  );
}

export function Loading({ label = "Loading…" }) {
  return <div className="empty">{label}</div>;
}

// ─────────────────── tabs ──────────────────────────────────────────────────

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          className="tab"
          data-active={active === t.key}
          aria-selected={active === t.key}
          onClick={() => onChange(t.key)}
        >
          {t.label}
          {typeof t.count === "number" && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

// ─────────────────── activity timeline ─────────────────────────────────────

export function ActivityFeed({ subjectType, subjectId, limit = 30 }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (subjectType) params.set("subject_type", subjectType);
    if (subjectId) params.set("subject_id", subjectId);
    api
      .get(`/api/v1/activity?${params}`)
      .then(setRows)
      .catch((e) => setError(e.message));
  }, [subjectType, subjectId, limit]);

  if (error) return <ErrorBanner message={error} />;
  if (!rows) return <Loading />;
  if (!rows.length) return <EmptyState>No activity recorded yet.</EmptyState>;

  return (
    <div className="timeline">
      {rows.map((r) => (
        <div className="tl-item" key={r.id}>
          <div className="tl-when">{formatWhen(r.created_at)}</div>
          <div className="tl-what">
            <strong style={{ fontWeight: 600 }}>{r.actor_name || "System"}</strong>{" "}
            {r.action_label}
          </div>
          {r.context?.reason && <div className="tl-who">“{r.context.reason}”</div>}
        </div>
      ))}
    </div>
  );
}

// ─────────────────── documents ─────────────────────────────────────────────

export const EXPIRY_PILL = {
  expired: ["bad", "Expired"],
  urgent_7: ["bad", "7 days"],
  warn_30: ["warn", "30 days"],
  warn_60: ["warn", "60 days"],
  ok: ["ok", "Valid"],
  none: ["default", "—"],
};

export const DOC_STATUS_PILL = {
  pending_review: ["warn", "Pending review"],
  verified: ["ok", "Verified"],
  rejected: ["bad", "Rejected"],
  expired: ["bad", "Expired"],
};

export const DOC_TYPES = [
  ["passport", "Passport"],
  ["visa", "Residence Visa"],
  ["emirates_id", "Emirates ID"],
  ["labour_card", "Labour Card"],
  ["photo", "Passport Photo"],
  ["offer_letter", "Offer Letter"],
  ["contract", "Employment Contract"],
  ["noc", "NOC"],
  ["salary_certificate", "Salary Certificate"],
  ["cv", "CV / Résumé"],
  ["degree_certificate", "Degree Certificate"],
  ["experience_letter", "Experience Letter"],
  ["trade_licence", "Trade Licence"],
  ["medical_fitness", "Medical Fitness"],
  ["health_insurance", "Health Insurance"],
  ["other", "Other"],
];

/** Document checklist + list for one owner (employee or candidate). */
export function DocumentsPanel({ ownerType, ownerId, onChanged }) {
  const [checklist, setChecklist] = useState(null);
  const [docs, setDocs] = useState(null);
  const [error, setError] = useState(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [presetType, setPresetType] = useState(null);

  async function load() {
    try {
      setError(null);
      const [c, d] = await Promise.all([
        api.get(`/api/v1/documents/checklist/${ownerType}/${ownerId}`),
        api.get(`/api/v1/documents?owner_type=${ownerType}&owner_id=${ownerId}`),
      ]);
      setChecklist(c);
      setDocs(d);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [ownerType, ownerId]);

  async function verify(docId, approved) {
    try {
      await api.post(`/api/v1/documents/${docId}/verify`, { approved });
      await load();
      onChanged?.();
    } catch (e) {
      setError(e.message);
    }
  }

  async function remove(docId) {
    try {
      await api.del(`/api/v1/documents/${docId}`);
      await load();
      onChanged?.();
    } catch (e) {
      setError(e.message);
    }
  }

  if (error) return <ErrorBanner message={error} />;
  if (!checklist || !docs) return <Loading />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      {/* Completeness */}
      <div>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 8 }}>
          <div className="upper">Required documents</div>
          <div style={{ fontSize: 13, color: "var(--color-ink)" }}>
            <strong>{checklist.present_required}</strong>
            <span style={{ color: "var(--color-muted)" }}> / {checklist.total_required} on file</span>
          </div>
        </div>
        <div className="progress"><i style={{ width: `${checklist.percent_complete}%` }} /></div>
        {checklist.missing.length > 0 && (
          <div style={{ marginTop: 10, fontSize: 12, color: "var(--color-bad)" }}>
            Missing: {checklist.missing.join(", ")}
          </div>
        )}
      </div>

      {/* Checklist grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 10 }}>
        {checklist.items.map((it) => {
          const [ev, el] = EXPIRY_PILL[it.expiry_bucket] || EXPIRY_PILL.none;
          return (
            <div
              key={it.doc_type}
              style={{
                padding: "11px 13px", borderRadius: 10,
                border: `1px solid ${it.present ? "var(--color-stroke)" : "var(--color-bad)"}`,
                background: it.present ? "var(--color-surface-2)" : "var(--color-bad-soft)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: "var(--color-ink)" }}>{it.label}</span>
                {!it.required && <span className="upper" style={{ fontSize: 9 }}>Optional</span>}
              </div>
              <div style={{ marginTop: 7, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                {it.present ? (
                  <>
                    <Pill variant={DOC_STATUS_PILL[it.status]?.[0] || "default"}>
                      {DOC_STATUS_PILL[it.status]?.[1] || it.status}
                    </Pill>
                    {it.expiry_date && <Pill variant={ev}>{el}</Pill>}
                  </>
                ) : (
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => { setPresetType(it.doc_type); setUploadOpen(true); }}
                  >
                    Upload
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Files on record */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <div className="upper">Files on record ({docs.length})</div>
          <Button variant="primary" className="btn-sm" onClick={() => { setPresetType(null); setUploadOpen(true); }}>
            + Upload document
          </Button>
        </div>

        {docs.length === 0 ? (
          <EmptyState>Nothing uploaded yet.</EmptyState>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Document</th><th>Type</th><th>Number</th>
                <th>Expires</th><th>Status</th><th></th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => {
                const [ev, el] = EXPIRY_PILL[d.expiry_bucket] || EXPIRY_PILL.none;
                return (
                  <tr key={d.id}>
                    <td style={{ fontWeight: 600, color: "var(--color-ink)" }}>
                      <DownloadLink docId={d.id} filename={d.filename} className="btn btn-sm btn-ghost">
                        {d.filename}
                      </DownloadLink>
                      <div style={{ fontSize: 10, color: "var(--color-muted)", fontWeight: 400 }}>
                        {Math.round((d.size_bytes || 0) / 1024)} KB
                      </div>
                    </td>
                    <td>{d.doc_type_label}</td>
                    <td className="num">{d.document_number || "—"}</td>
                    <td>
                      {d.expiry_date ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                          <span className="num" style={{ fontSize: 12 }}>{d.expiry_date}</span>
                          <Pill variant={ev}>{el}</Pill>
                        </div>
                      ) : "—"}
                    </td>
                    <td>
                      <Pill variant={DOC_STATUS_PILL[d.status]?.[0] || "default"}>
                        {DOC_STATUS_PILL[d.status]?.[1] || d.status}
                      </Pill>
                    </td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {d.status !== "verified" && (
                        <button type="button" className="btn btn-sm" onClick={() => verify(d.id, true)}>
                          Verify
                        </button>
                      )}{" "}
                      <button type="button" className="btn btn-sm btn-danger" onClick={() => remove(d.id)}>
                        Remove
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <UploadDocumentDrawer
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        ownerType={ownerType}
        ownerId={ownerId}
        presetType={presetType}
        onUploaded={() => { setUploadOpen(false); load(); onChanged?.(); }}
      />
    </div>
  );
}

export function UploadDocumentDrawer({ open, onClose, ownerType, ownerId, presetType, onUploaded }) {
  const [file, setFile] = useState(null);
  const [docType, setDocType] = useState(presetType || "passport");
  const [number, setNumber] = useState("");
  const [issue, setIssue] = useState("");
  const [expiry, setExpiry] = useState("");
  const [country, setCountry] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { if (presetType) setDocType(presetType); }, [presetType]);

  async function submit(e) {
    e?.preventDefault();
    if (!file) { setError("Choose a file first."); return; }
    setSaving(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("owner_type", ownerType);
      fd.append("owner_id", ownerId);
      fd.append("doc_type", docType);
      fd.append("file", file);
      if (number) fd.append("document_number", number);
      if (issue) fd.append("issue_date", issue);
      if (expiry) fd.append("expiry_date", expiry);
      if (country) fd.append("issuing_country", country);
      if (notes) fd.append("notes", notes);

      await api.upload("/api/v1/documents", fd);
      setFile(null); setNumber(""); setIssue(""); setExpiry(""); setCountry(""); setNotes("");
      onUploaded();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open} onClose={onClose} title="Upload document"
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={submit} disabled={saving || !file}>
            {saving ? "Uploading…" : "Upload"}
          </Button>
        </>
      }
    >
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <ErrorBanner message={error} />

        <div>
          <label className="field-label">Document type</label>
          <select value={docType} onChange={(e) => setDocType(e.target.value)}>
            {DOC_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>

        <div>
          <label className="field-label">File</label>
          <input
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.doc,.docx"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <div style={{ fontSize: 11, color: "var(--color-muted)", marginTop: 5 }}>
            PDF, image or Word document, up to 15 MB.
          </div>
        </div>

        <div><label className="field-label">Document number</label>
          <input value={number} onChange={(e) => setNumber(e.target.value)} placeholder="e.g. P1234567" /></div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div><label className="field-label">Issue date</label>
            <input type="date" value={issue} onChange={(e) => setIssue(e.target.value)} /></div>
          <div><label className="field-label">Expiry date</label>
            <input type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} /></div>
        </div>

        <div><label className="field-label">Issuing country</label>
          <input value={country} onChange={(e) => setCountry(e.target.value)} placeholder="United Arab Emirates" /></div>

        <div><label className="field-label">Notes</label>
          <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
      </form>
    </Drawer>
  );
}

// ─────────────────── helpers ───────────────────────────────────────────────

export function formatWhen(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)} d ago`;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function money(amount, currency = "AED") {
  if (amount == null) return "—";
  return `${currency} ${Number(amount).toLocaleString()}`;
}
