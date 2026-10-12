"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";

import { Sidebar } from "@/components/Sidebar";
import { api, auth } from "@/lib/api";

export default function AppLayout({ children }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;

    if (!auth.isAuthed()) {
      router.replace(`/login?next=${encodeURIComponent(pathname || "/")}`);
      return;
    }

    // Render immediately from the cached user, then refresh roles from the API.
    setMe({ user: auth.getUser(), roles: [] });
    setChecked(true);

    api
      .get("/api/v1/auth/me")
      .then((data) => {
        if (!cancelled) setMe(data);
      })
      .catch(() => {
        /* 401 is handled inside lib/api (clears token + redirects) */
      });

    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

  if (!checked) {
    return (
      <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", color: "var(--color-ink-2)", fontSize: 14 }}>
        Loading…
      </div>
    );
  }

  const { userName, userRole, userInitials } = sidebarIdentity(me);

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="ground" />
      <div className="grid-overlay" />
      <div className="relative z-10 grid min-h-screen" style={{ gridTemplateColumns: "240px 1fr" }}>
        <Sidebar userName={userName} userRole={userRole} userInitials={userInitials} />
        <main className="min-w-0" style={{ padding: "32px 40px 64px" }}>{children}</main>
      </div>
    </div>
  );
}

function sidebarIdentity(me) {
  const user = me?.user;
  if (!user) return { userName: "You", userRole: "Signed in", userInitials: "U" };

  const name = user.name || (user.email || "").split("@")[0] || "You";

  // Prefer the real role name ("Head of HR") over the email, which overflows.
  const roles = me?.roles || [];
  const userRole = roles.length
    ? roles.map((r) => r.name).join(" · ")
    : "No role assigned";

  const source = user.name || user.email || "U";
  const initials =
    source
      .split(/[\s@._-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((s) => s[0].toUpperCase())
      .join("") || "U";

  return { userName: name, userRole, userInitials: initials };
}
