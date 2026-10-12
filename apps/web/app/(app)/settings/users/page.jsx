"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/Button";
import { Drawer } from "@/components/Drawer";
import { Panel } from "@/components/Panel";
import { Pill } from "@/components/Pill";
import { Topbar } from "@/components/Topbar";
import { EmptyState, ErrorBanner, Loading, formatWhen } from "@/components/Shared";
import { api } from "@/lib/api";

const STATUS_PILL = {
  active: ["ok", "Active"],
  invited: ["warn", "Invited"],
  suspended: ["bad", "Suspended"],
};

export default function UsersSettingsPage() {
  const [users, setUsers] = useState(null);
  const [roles, setRoles] = useState(null);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [u, r] = await Promise.all([
        api.get("/api/v1/auth/users"),
        api.get("/api/v1/auth/roles"),
      ]);
      setUsers(u);
      setRoles(r);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Which roles nobody holds — these are what stall approval chains
  const held = new Set((users ?? []).flatMap((u) => u.roles.map((r) => r.key)));
  const unheld = (roles ?? []).filter((r) => !held.has(r.key));

  return (
    <>
      <Topbar
        crumb="Settings · Access control"
        title="Users &amp; roles"
        sub={users === null ? "Loading…" : `${users.length} accounts · ${roles?.length ?? 0} roles`}
        actions={<Button onClick={load}>Refresh</Button>}
      />

      <ErrorBanner message={error} />

      {unheld.length > 0 && (
        <div style={{
          padding: "11px 14px", borderRadius: 10, marginBottom: 16,
          background: "var(--color-warn-soft)", border: "1px solid var(--color-warn)",
          color: "var(--color-warn)", fontSize: 13,
        }}>
          No user holds: <strong>{unheld.map((r) => r.name).join(", ")}</strong>.
          Any approval step routed to these roles will stall.
        </div>
      )}

      <Panel bodyPadding={false} title="Accounts">
        {users === null ? (
          <Loading />
        ) : users.length === 0 ? (
          <EmptyState>No users yet. Run <code>python seed_demo.py</code> to create them.</EmptyState>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th><th>Email</th><th>Roles</th>
                <th>Last sign-in</th><th>Status</th><th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const [v, l] = STATUS_PILL[u.status] || ["default", u.status];
                return (
                  <tr key={u.id}>
                    <td style={{ fontWeight: 600, color: "var(--color-ink)" }}>{u.name || "—"}</td>
                    <td style={{ fontSize: 12 }}>{u.email}</td>
                    <td>
                      <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                        {u.roles.length === 0
                          ? <Pill variant="bad">No role</Pill>
                          : u.roles.map((r) => <Pill key={r.id} variant="gold">{r.name}</Pill>)}
                      </div>
                    </td>
                    <td style={{ fontSize: 11, color: "var(--color-muted)" }}>
                      {u.last_login_at ? formatWhen(u.last_login_at) : "Never"}
                    </td>
                    <td><Pill variant={v}>{l}</Pill></td>
                    <td style={{ textAlign: "right" }}>
                      <button type="button" className="btn btn-sm" onClick={() => setEditing(u)}>
                        Edit roles
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>

      <div style={{ marginTop: 20 }}>
        <Panel bodyPadding={false} title="Role catalogue">
          {roles === null ? <Loading /> : (
            <table className="data-table">
              <thead><tr><th>Role</th><th>Key</th><th>Description</th><th>Holders</th></tr></thead>
              <tbody>
                {roles.map((r) => {
                  const holders = (users ?? []).filter((u) => u.roles.some((x) => x.key === r.key));
                  return (
                    <tr key={r.id}>
                      <td style={{ fontWeight: 600, color: "var(--color-ink)" }}>{r.name}</td>
                      <td className="num" style={{ fontSize: 11 }}>{r.key}</td>
                      <td style={{ fontSize: 12 }}>{r.description || "—"}</td>
                      <td>
                        {holders.length === 0
                          ? <Pill variant="bad">Nobody</Pill>
                          : <span style={{ fontSize: 12 }}>{holders.map((h) => h.name).join(", ")}</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      <EditRolesDrawer
        user={editing}
        allRoles={roles ?? []}
        onClose={() => setEditing(null)}
        onSaved={() => { setEditing(null); load(); }}
      />
    </>
  );
}

function EditRolesDrawer({ user, allRoles, onClose, onSaved }) {
  const [selected, setSelected] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setSelected(user ? user.roles.map((r) => r.key) : []);
    setError(null);
  }, [user]);

  function toggle(key) {
    setSelected((s) => (s.includes(key) ? s.filter((k) => k !== key) : [...s, key]));
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.put(`/api/v1/auth/users/${user.id}/roles`, { role_keys: selected });
      onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={!!user}
      onClose={onClose}
      title={user ? `Roles — ${user.name || user.email}` : "Roles"}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save roles"}
          </Button>
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <ErrorBanner message={error} />

        <p style={{ fontSize: 12, color: "var(--color-muted)", lineHeight: 1.6, margin: 0 }}>
          Roles decide what someone can see and which approval steps route to them.
          Changing them takes effect the next time they load a page.
        </p>

        {allRoles.map((r) => (
          <label
            key={r.id}
            style={{
              display: "flex", alignItems: "flex-start", gap: 10,
              padding: "10px 12px", borderRadius: 9, cursor: "pointer",
              border: `1px solid ${selected.includes(r.key) ? "var(--color-brand)" : "var(--color-stroke)"}`,
              background: selected.includes(r.key) ? "var(--color-brand-soft)" : "transparent",
            }}
          >
            <input
              type="checkbox"
              style={{ width: "auto", marginTop: 2, flexShrink: 0 }}
              checked={selected.includes(r.key)}
              onChange={() => toggle(r.key)}
            />
            <span style={{ minWidth: 0 }}>
              <span style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--color-ink)" }}>
                {r.name}
              </span>
              {r.description && (
                <span style={{ display: "block", fontSize: 11, color: "var(--color-muted)", marginTop: 2 }}>
                  {r.description}
                </span>
              )}
            </span>
          </label>
        ))}
      </div>
    </Drawer>
  );
}
