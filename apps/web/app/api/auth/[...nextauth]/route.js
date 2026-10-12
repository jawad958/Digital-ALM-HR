// NextAuth has been retired. These stubs return 404 so any stale client call
// doesn't crash the dev server.
import { NextResponse } from "next/server";

const gone = () =>
  NextResponse.json(
    { error: "NextAuth endpoints have been removed. Use /api/v1/auth/login." },
    { status: 404 },
  );

export const GET = gone;
export const POST = gone;
