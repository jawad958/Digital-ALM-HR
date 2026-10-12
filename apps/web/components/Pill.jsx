export function Pill({ children, variant = "default", plain, className = "" }) {
  const variantClass = {
    default: "",
    gold: "pill-gold",
    ok: "pill-ok",
    warn: "pill-warn",
    bad: "pill-bad",
  }[variant];
  return (
    <span className={`pill ${variantClass} ${plain ? "pill-plain" : ""} ${className}`}>
      {children}
    </span>
  );
}
