export function Panel({
  title,
  sub,
  actions,
  children,
  footer,
  bodyPadding = true,
  className = "",
}) {
  return (
    <div className={`panel ${className}`}>
      {(title || actions) && (
        <div className="panel-head">
          <div>
            {typeof title === "string" ? <h2>{title}</h2> : title}
            {sub && (
              <div style={{ fontSize: 11, color: "var(--color-muted)", marginTop: 2 }}>{sub}</div>
            )}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {bodyPadding ? <div className="panel-body">{children}</div> : children}
      {footer && (
        <div
          className="flex items-center justify-between px-5 py-3.5 border-t"
          style={{ borderColor: "var(--color-stroke)", background: "var(--color-surface-2)" }}
        >
          {footer}
        </div>
      )}
    </div>
  );
}
