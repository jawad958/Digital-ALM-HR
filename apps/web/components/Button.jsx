export function Button({ variant = "default", className = "", children, ...rest }) {
  const variantClass = {
    default: "btn",
    primary: "btn btn-primary",
    ghost: "btn btn-ghost",
  }[variant];
  return (
    <button className={`${variantClass} ${className}`} {...rest}>
      {children}
    </button>
  );
}
