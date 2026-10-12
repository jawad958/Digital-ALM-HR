"use client";

/** Simple right-side drawer for create/edit forms. */
export function Drawer({ open, onClose, title, children, actions }) {
  if (!open) return null;
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 100,
        background: "rgba(0,0,0,0.4)",
        display: "flex", justifyContent: "flex-end",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(520px, 95vw)",
          background: "var(--color-bg)",
          borderLeft: "1px solid var(--color-stroke)",
          display: "flex", flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "20px 24px", borderBottom: "1px solid var(--color-stroke)" }}>
          <h2>{title}</h2>
          <button onClick={onClose} aria-label="Close" className="btn btn-ghost btn-sm">✕</button>
        </div>
        <div style={{ flex: 1, overflow: "auto", padding: 24 }}>{children}</div>
        {actions && (
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", padding: 16, borderTop: "1px solid var(--color-stroke)", background: "var(--color-surface-2)" }}>
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}
