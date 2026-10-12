"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/Button";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import {
  ActivityFeed, DOC_STATUS_PILL, DownloadLink, EXPIRY_PILL,
  EmptyState, ErrorBanner, Loading, Tabs,
} from "@/components/Shared";
import { api } from "@/lib/api";

export default function DocumentsPage() {
  const router = useRouter();
  const [docs, setDocs] = useState(null);
  const [people, setPeople] = useState({});
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("expiring");
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    try {
      setError(null);
      const [all, employees, candidates] = await Promise.all([
        api.get("/api/v1/documents"),
        api.get("/api/v1/employees"),
        api.get("/api/v1/candidates").catch(() => []),
      ]);
      const map = {};
      for (const e of employees) map[e.id] = { name: e.full_name, href: `/employees/${e.id}`, sub: e.employee_code };
      for (const c of candidates) map[c.id] = { name: c.name, href: `/candidates/${c.id}`, sub: "Candidate" };
      setPeople(map);
      setDocs(all);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const buckets = useMemo(() => {
    const d = docs ?? [];
    return {
      expired: d.filter((x) => x.expiry_bucket === "expired"),
      urgent: d.filter((x) => x.expiry_bucket === "urgent_7"),
      soon: d.filter((x) => ["warn_30", "warn_60"].includes(x.expiry_bucket)),
      pending: d.filter((x) => x.status === "pending_review"),
    };
  }, [docs]);

  const visible = useMemo(() => {
    const d = docs ?? [];
    let rows;
    if (tab === "expiring") {
      rows = d
        .filter((x) => ["expired", "urgent_7", "warn_30", "warn_60"].includes(x.expiry_bucket))
        .sort((a, b) => (a.days_to_expiry ?? 1e9) - (b.days_to_expiry ?? 1e9));
    } else if (tab === "pending") {
      rows = d.filter((x) => x.status === "pending_review");
    } else {
      rows = d;
    }
    if (q.trim()) {
      const needle = q.toLowerCase();
      rows = rows.filter((x) => {
        const who = people[x.owner_id]?.name || "";
        return `${x.filename} ${x.doc_type_label} ${who}`.toLowerCase().includes(needle);
      });
    }
    return rows;
  }, [docs, tab, q, people]);

  return (
    <>
      <Topbar
        crumb="Compliance · Document register"
        title="Documents"
        sub={docs === null ? "Loading…" : `${docs.length} on file across the business`}
        actions={<Button onClick={load}>Refresh</Button>}
      />

      <ErrorBanner message={error} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 14, marginBottom: 22 }}>
        <StatCard label="Expired" value={buckets.expired.length} tone="bad" />
        <StatCard label="Expiring in 7 days" value={buckets.urgent.length} tone="bad" />
        <StatCard label="Expiring in 60 days" value={buckets.soon.length} tone="warn" />
        <StatCard label="Awaiting verification" value={buckets.pending.length} tone="default" />
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, marginBottom: 18 }}>
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { key: "expiring", label: "Expiry watchlist", count: buckets.expired.length + buckets.urgent.length + buckets.soon.length },
            { key: "pending", label: "Awaiting verification", count: buckets.pending.length },
            { key: "all", label: "All documents", count: docs?.length },
          ]}
        />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search person, file or type…"
          style={{ maxWidth: 280 }}
        />
      </div>

      <Panel bodyPadding={false}>
        {docs === null ? (
          <Loading />
        ) : visible.length === 0 ? (
          <EmptyState title="Nothing to action">
            {tab === "expiring"
              ? "No documents are expiring in the next 60 days."
              : tab === "pending"
                ? "Every document has been verified."
                : "No documents uploaded yet."}
          </EmptyState>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Person</th><th>Document</th><th>Type</th>
                <th>Expires</th><th>Days left</th><th>Status</th><th></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((d) => {
                const who = people[d.owner_id];
                const [ev, el] = EXPIRY_PILL[d.expiry_bucket] || EXPIRY_PILL.none;
                const [sv, sl] = DOC_STATUS_PILL[d.status] || ["default", d.status];
                return (
                  <tr key={d.id} onClick={() => who && router.push(who.href)}>
                    <td>
                      <div style={{ fontWeight: 600, color: "var(--color-ink)" }}>
                        {who?.name || "—"}
                      </div>
                      <div className="num" style={{ fontSize: 10, color: "var(--color-muted)" }}>
                        {who?.sub || d.owner_type}
                      </div>
                    </td>
                    <td>{d.filename}</td>
                    <td>{d.doc_type_label}</td>
                    <td className="num" style={{ fontSize: 12 }}>{d.expiry_date || "—"}</td>
                    <td>
                      {d.days_to_expiry == null ? "—" : (
                        <Pill variant={ev}>
                          {d.days_to_expiry < 0
                            ? `${Math.abs(d.days_to_expiry)} d overdue`
                            : `${d.days_to_expiry} d`}
                        </Pill>
                      )}
                    </td>
                    <td><Pill variant={sv}>{sl}</Pill></td>
                    <td style={{ textAlign: "right" }}>
                      <DownloadLink docId={d.id} filename={d.filename}>Open</DownloadLink>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>

      <div style={{ marginTop: 28 }}>
        <Panel title="Recent document activity">
          <ActivityFeed subjectType="document" limit={15} />
        </Panel>
      </div>
    </>
  );
}

function StatCard({ label, value, tone }) {
  const color = tone === "bad" ? "var(--color-bad)"
    : tone === "warn" ? "var(--color-warn)"
      : "var(--color-ink)";
  return (
    <div className="stat">
      <div className="stat-l">{label}</div>
      <div className="stat-v" style={{ color: value > 0 ? color : "var(--color-ink)" }}>{value}</div>
    </div>
  );
}
