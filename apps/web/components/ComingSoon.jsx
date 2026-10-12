import { Topbar } from "./Topbar";

/**
 * Placeholder for routes that aren't built yet.
 * Keeps the sidebar nav working during Weeks 3+ development.
 */
export function ComingSoon({ crumb, title, sub, week }) {
  return (
    <>
      <Topbar crumb={crumb} title={title} sub={sub} />

      <div
        className="panel"
        style={{
          padding: "60px 32px",
          textAlign: "center",
          marginTop: 20,
        }}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            width: 44,
            height: 44,
            color: "var(--color-brand)",
            margin: "0 auto 20px",
            display: "block",
          }}
        >
          <circle cx="12" cy="12" r="10" />
          <polyline points="12 6 12 12 16 14" />
        </svg>

        <h2 style={{ marginBottom: 10 }}>Coming in {week}</h2>
        <p
          style={{
            color: "var(--color-ink-2)",
            maxWidth: 420,
            margin: "0 auto",
            fontSize: 13,
            lineHeight: 1.7,
          }}
        >
          {sub ||
            "This module is scheduled in the development plan. The nav link works; the page itself is still being built."}
        </p>

        <div
          style={{
            marginTop: 28,
            padding: "12px 20px",
            background: "var(--color-brand-soft)",
            borderRadius: 8,
            display: "inline-block",
          }}
        >
          <span className="upper" style={{ color: "var(--color-brand)" }}>
            Sprint {week}
          </span>
        </div>
      </div>
    </>
  );
}
