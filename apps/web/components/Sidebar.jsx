"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogoMark } from "./LogoMark";
import { ThemeToggle } from "./ThemeToggle";
import { auth } from "@/lib/api";

const PRIMARY_NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/hiring", label: "Hiring" },
  { href: "/candidates", label: "Candidates" },
  { href: "/interviews", label: "Interviews" },
  { href: "/offers", label: "Offers" },
  { href: "/employees", label: "Employees" },
  { href: "/approvals", label: "Approvals", alert: true },
  { href: "/forms", label: "Forms" },
  { href: "/documents", label: "Documents" },
];

const SETTINGS_NAV = [
  { href: "/settings/users", label: "Users & roles" },
  { href: "/settings/approval-chains", label: "Approval chains" },
  { href: "/settings/templates", label: "Templates" },
];

export function Sidebar({ userName = "You", userRole = "Signed in", userInitials = "U" }) {
  const path = usePathname();
  const router = useRouter();
  const isActive = (href) => path === href || path.startsWith(href + "/");

  function signOut() {
    auth.clear();
    router.replace("/login");
  }

  return (
    <aside
      style={{
        display: "flex", flexDirection: "column", gap: 18,
        borderRight: "1px solid var(--color-stroke)",
        padding: "22px 14px",
        minHeight: "100vh",
        background: "var(--sidebar-bg)",
        backdropFilter: "blur(12px) saturate(130%)",
        width: 240,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", padding: "6px 10px 18px", borderBottom: "1px solid var(--color-stroke)" }}>
        <LogoMark height={26} style={{ color: "var(--color-ink)" }} />
      </div>

      <nav style={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {PRIMARY_NAV.map((n) => <NavLink key={n.href} item={n} active={isActive(n.href)} />)}
        <div className="upper" style={{ padding: "14px 10px 6px" }}>Settings</div>
        {SETTINGS_NAV.map((n) => <NavLink key={n.href} item={n} active={isActive(n.href)} />)}
      </nav>

      <div style={{ marginTop: "auto", paddingTop: 12, display: "flex", alignItems: "center", gap: 10, borderTop: "1px solid var(--color-stroke)" }}>
        <div style={{ flexShrink: 0, width: 32, height: 32, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 600, fontSize: 12, background: "var(--color-brand-soft)", color: "var(--color-brand)" }}>
          {userInitials}
        </div>
        <div style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
          <div className="truncate-1" title={userName} style={{ fontSize: 12, fontWeight: 600, color: "var(--color-ink)" }}>
            {userName}
          </div>
          <div className="upper truncate-1" title={userRole} style={{ fontSize: 10 }}>
            {userRole}
          </div>
        </div>
        <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 2 }}>
          <ThemeToggle />
          <button
            type="button"
            onClick={signOut}
            title="Sign out"
            aria-label="Sign out"
            style={{
              appearance: "none", background: "transparent", border: 0,
              padding: 6, borderRadius: 7, cursor: "pointer",
              color: "var(--color-muted)", display: "inline-flex",
            }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
          </button>
        </div>
      </div>
    </aside>
  );
}

function NavLink({ item, active }) {
  return (
    <Link
      href={item.href}
      style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "8px 10px", borderRadius: 7,
        fontSize: 13, fontWeight: active ? 600 : 500,
        background: active ? "var(--color-brand-soft)" : "transparent",
        color: active ? "var(--color-brand)" : "var(--color-ink-2)",
        textDecoration: "none",
      }}
    >
      <span style={{ flex: 1 }}>{item.label}</span>
      {item.alert && (
        <span style={{ background: "var(--color-brand)", color: "#0A0A08", borderRadius: 99, padding: "1px 7px", fontSize: 10, fontWeight: 600 }}>
          !
        </span>
      )}
    </Link>
  );
}
