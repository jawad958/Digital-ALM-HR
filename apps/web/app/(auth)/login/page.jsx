"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { LogoMark } from "@/components/LogoMark";
import { api, auth } from "@/lib/api";

export const dynamic = "force-dynamic";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const res = await api.post("/api/v1/auth/login", { email, password });
      auth.setSession(res.access_token, res.user);
      router.replace(next);
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="mt-8 flex flex-col gap-4" noValidate>
      <div className="flex flex-col gap-2">
        <label htmlFor="email" className="upper">Email</label>
        <input
          id="email"
          type="email"
          name="email"
          required
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@alpagomanufacturing.com"
        />
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor="password" className="upper">Password</label>
        <div style={{ position: "relative" }}>
          <input
            id="password"
            type={showPw ? "text" : "password"}
            name="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            style={{ paddingRight: 64, width: "100%" }}
          />
          <button
            type="button"
            onClick={() => setShowPw((s) => !s)}
            aria-label={showPw ? "Hide password" : "Show password"}
            className="upper"
            style={{
              position: "absolute",
              right: 10,
              top: "50%",
              transform: "translateY(-50%)",
              background: "transparent",
              border: 0,
              color: "var(--color-ink-2)",
              fontSize: 10,
              cursor: "pointer",
              padding: "4px 6px",
            }}
          >
            {showPw ? "Hide" : "Show"}
          </button>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          style={{
            padding: "10px 14px",
            fontSize: 13,
            color: "#C0392B",
            background: "rgba(192, 57, 43, 0.08)",
            border: "1px solid rgba(192, 57, 43, 0.25)",
            borderRadius: 8,
          }}
        >
          {error}
        </div>
      )}

      <button
        type="submit"
        className="btn btn-primary w-full justify-center"
        style={{ padding: 14, marginTop: 4 }}
        disabled={submitting}
      >
        {submitting ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div
      className="min-h-screen"
      style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", background: "var(--color-bg)" }}
    >
      {/* Brand panel */}
      <div
        className="relative overflow-hidden flex flex-col items-center justify-center"
        style={{ background: "#0A0A08", padding: "48px 60px" }}
      >
        <GoldWaves />
        <GoldWaves flipped />
        <div className="relative z-10 flex flex-col items-center">
          <LogoMark variant="white" height={74} />
        </div>
      </div>

      {/* Form panel */}
      <div
        className="relative flex flex-col items-center justify-center"
        style={{ padding: "60px 80px" }}
      >
        <div className="ground opacity-50" />
        <div className="relative" style={{ maxWidth: 400, width: "100%" }}>
          <div className="upper">Sign in</div>
          <h1 className="mt-2.5">Welcome back.</h1>
          <p className="mt-2.5 text-sm" style={{ color: "var(--color-ink-2)", lineHeight: 1.6 }}>
            Use your Alpago email and password to continue.
          </p>

          <Suspense
            fallback={
              <div className="mt-8" style={{ color: "var(--color-ink-2)", fontSize: 14 }}>
                Loading…
              </div>
            }
          >
            <LoginForm />
          </Suspense>

          <div
            className="mt-8 pt-6 border-t text-xs"
            style={{
              borderColor: "var(--color-stroke)",
              color: "var(--color-muted)",
              lineHeight: 1.7,
            }}
          >
            <strong style={{ color: "var(--color-ink-2)", fontWeight: 600 }}>Candidate?</strong>{" "}
            Open the sign-in link in the email we sent you to view your offer or upload documents
            — no account required.
          </div>
        </div>
      </div>
    </div>
  );
}

function GoldWaves({ flipped }) {
  const style = flipped
    ? {
        position: "absolute",
        bottom: 0,
        left: 0,
        right: 0,
        height: "50%",
        opacity: 0.6,
        transform: "scaleY(-1)",
      }
    : { position: "absolute", top: 0, left: 0, right: 0, height: "50%", opacity: 0.6 };
  return (
    <svg style={style} viewBox="0 0 1200 400" preserveAspectRatio="none" aria-hidden="true">
      <g fill="none" stroke="#C9A961" strokeWidth="0.6">
        <path d="M0,40 Q300,15 600,38 T1200,30" />
        <path d="M0,80 Q300,55 600,76 T1200,70" />
        <path d="M0,120 Q300,98 600,118 T1200,112" />
        <path d="M0,160 Q300,138 600,158 T1200,152" />
        <path d="M0,200 Q300,180 600,198 T1200,192" />
        <path d="M0,240 Q300,218 600,238 T1200,232" />
        <path d="M0,280 Q300,258 600,278 T1200,272" />
        <path d="M0,320 Q300,298 600,316 T1200,312" />
      </g>
    </svg>
  );
}
