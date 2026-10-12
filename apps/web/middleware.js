// Auth is enforced client-side via AuthGate (components/AuthGate.jsx) and on the
// backend via JWT. No Next.js middleware needed, so we export a passthrough and
// a matcher that doesn't match anything (keeps the file a no-op without the
// runtime loading `lib/auth` from the retired NextAuth setup).

import { NextResponse } from "next/server";

export function middleware() {
  return NextResponse.next();
}

export const config = {
  // Match a path that doesn't exist, so middleware never actually runs.
  matcher: ["/_never_matches__"],
};
