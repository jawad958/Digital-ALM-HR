"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";

import { auth } from "@/lib/api";

/**
 * Client-side auth guard. Renders nothing until the token check has run on
 * mount; if there's no token it bounces to /login carrying the current path.
 * Backend still enforces auth on every call, so this is only a UX guard.
 */
export default function AuthGate({ children }) {
  const router = useRouter();
  const pathname = usePathname();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (auth.isAuthed()) {
      setChecked(true);
    } else {
      const next = encodeURIComponent(pathname || "/");
      router.replace(`/login?next=${next}`);
    }
  }, [pathname, router]);

  if (!checked) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "grid",
          placeItems: "center",
          color: "var(--muted, #777)",
          fontSize: 14,
        }}
      >
        Loading…
      </div>
    );
  }

  return children;
}
