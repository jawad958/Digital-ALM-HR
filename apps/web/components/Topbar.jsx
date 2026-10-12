export function Topbar({ crumb, title, sub, actions }) {
  return (
    <div className="flex items-end justify-between gap-6 mb-7">
      <div className="flex flex-col gap-1.5">
        <div className="upper">{crumb}</div>
        <h1>{title}</h1>
        {sub && (
          <div style={{ color: "var(--color-muted)", fontSize: 13, marginTop: 2 }}>{sub}</div>
        )}
      </div>
      {actions && <div className="flex items-center gap-2.5">{actions}</div>}
    </div>
  );
}
