/**
 * Thin fetch wrapper for the Alpago API.
 * All requests go through /api/v1/* which Next.js rewrites to the backend.
 *
 * Auth: JWT lives in localStorage. We attach it as `Authorization: Bearer <jwt>`
 * on every request. On a 401 we clear the token and send the user to /login.
 */

const TOKEN_KEY = "alpago.token";
const USER_KEY = "alpago.user";

export const auth = {
  getToken() {
    if (typeof window === "undefined") return null;
    try { return window.localStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  getUser() {
    if (typeof window === "undefined") return null;
    try {
      const raw = window.localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  },
  setSession(token, user) {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(TOKEN_KEY, token);
      window.localStorage.setItem(USER_KEY, JSON.stringify(user));
    } catch {}
  },
  clear() {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.removeItem(TOKEN_KEY);
      window.localStorage.removeItem(USER_KEY);
    } catch {}
  },
  isAuthed() { return !!this.getToken(); },
};

function withAuth(headers = {}) {
  const token = auth.getToken();
  return token ? { ...headers, Authorization: `Bearer ${token}` } : headers;
}

function handleUnauth(res) {
  if (res.status === 401 && typeof window !== "undefined") {
    auth.clear();
    const here = window.location.pathname + window.location.search;
    if (!here.startsWith("/login")) {
      window.location.href = `/login?next=${encodeURIComponent(here)}`;
    }
  }
}

async function request(path, init = {}) {
  const res = await fetch(path, {
    ...init,
    headers: withAuth({
      "Content-Type": "application/json",
      ...(init.headers || {}),
    }),
  });
  handleUnauth(res);
  if (!res.ok) {
    const body = await res.text();
    let message = `${res.status} ${res.statusText}`;
    try {
      const parsed = JSON.parse(body);
      message = parsed.detail || parsed.title || message;
    } catch {}
    const err = new Error(message);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return await res.json();
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body: JSON.stringify(body) }),
  put: (path, body) => request(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: (path, body) => request(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: (path) => request(path, { method: "DELETE" }),
  upload: async (path, formData) => {
    const res = await fetch(path, {
      method: "POST",
      body: formData,
      // Note: no Content-Type here — the browser sets the multipart boundary
      headers: withAuth(),
    });
    handleUnauth(res);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return await res.json();
  },
};
