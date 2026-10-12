"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/Button";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import { ActivityFeed, EmptyState, ErrorBanner, Loading } from "@/components/Shared";
import { api } from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      setData(await api.get("/api/v1/dashboard"));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const greeting = timeGreeting();
  const dateLine = new Date().toLocaleDateString(undefined, {
    weekday: "long", day: "numeric", month: "long",
  });

  return (
    <>
      <Topbar
        crumb="Dashboard · Overview"
        title={data ? `${greeting}, ${data.greeting_name}` : greeting}
        sub={
          data
            ? `${dateLine} · ${data.attention_count === 0
                ? "nothing needs your attention"
                : `${data.attention_count} item${data.attention_count === 1 ? "" : "s"} need your attention`}`
            : dateLine
        }
        actions={
          <Button variant="primary" onClick={() => router.push("/hiring")}>
            + New hiring request
          </Button>
        }
      />

      <ErrorBanner message={error} />

      {!data ? (
        <Panel><Loading /></Panel>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 14, marginBottom: 24 }}>
            {data.stats.map((s, i) => (
              <button
                key={s.label}
                type="button"
                onClick={() => s.href && router.push(s.href)}
                className={`stat ${i === 0 ? "stat-lead" : ""}`}
                style={{ textAlign: "left", cursor: s.href ? "pointer" : "default", font: "inherit" }}
              >
                <div className="stat-l">{s.label}</div>
                <div
                  className="stat-v"
                  style={s.tone === "bad" && s.value > 0 ? { color: "var(--color-bad)" } : undefined}
                >
                  {s.value}
                </div>
                {s.sub && <div className="stat-s">{s.sub}</div>}
              </button>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(260px, 1fr)", gap: 18, alignItems: "start" }}>
            <Panel
              title="Pending your attention"
              sub="Approvals, expiring documents and stalled onboarding"
              bodyPadding={false}
            >
              {data.attention.length === 0 ? (
                <EmptyState title="All clear">
                  Nothing is waiting on you right now.
                </EmptyState>
              ) : (
                data.attention.map((it, i) => (
                  <AttentionRow key={`${it.kind}-${i}`} item={it} onOpen={() => router.push(it.href)} />
                ))
              )}
            </Panel>

            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              <Panel title="Headcount">
                <div className="display num" style={{ fontSize: 50, lineHeight: 1, color: "var(--color-brand)" }}>
                  {data.headcount}
                </div>
                <div style={{ fontSize: 12, color: "var(--color-muted)", marginTop: 8 }}>
                  Active employees across both divisions
                </div>
                <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid var(--color-stroke)" }}>
                  <div className="upper">Joined this month</div>
                  <div className="display num" style={{ fontSize: 30, lineHeight: 1.1, marginTop: 6 }}>
                    {data.hires_this_month}
                  </div>
                </div>
              </Panel>

              <Panel title="Latest activity">
                <ActivityFeed limit={8} />
              </Panel>
            </div>
          </div>
        </>
      )}
    </>
  );
}

function AttentionRow({ item, onOpen }) {
  return (
    <div
      className="flex items-center gap-4"
      style={{ padding: "15px 20px", borderBottom: "1px solid var(--color-stroke)" }}
    >
      <div
        style={{
          flexShrink: 0, width: 32, height: 32, borderRadius: "50%",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 11, fontWeight: 600,
          background: "var(--color-brand-soft)", color: "var(--color-brand)",
        }}
      >
        {item.initials}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="flex items-center gap-2">
          <Pill variant={item.pill_tone}>{item.pill}</Pill>
          <span className="upper truncate-1">{item.category}</span>
        </div>
        <div style={{ fontWeight: 600, fontSize: 13, marginTop: 6, color: "var(--color-ink)" }}>
          {item.title}
        </div>
        <div style={{ fontSize: 11, color: "var(--color-muted)", marginTop: 2 }}>
          {item.meta}
        </div>
      </div>
      <Button onClick={onOpen}>Open</Button>
    </div>
  );
}

function timeGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}
