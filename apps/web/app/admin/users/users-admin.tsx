"use client";

import { useState } from "react";
import type { ErrorResponse, UserOut } from "@tariff/contracts";
import { networkError, readError } from "@/lib/client-errors";

type Role = "analyst" | "reviewer" | "administrator";

export function UsersAdmin({ initial, me }: { initial: UserOut[]; me: string }) {
  const [users, setUsers] = useState<UserOut[]>(initial);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("reviewer");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);

  async function upsert(body: { email: string; display_name?: string | null; role: Role; active: boolean }) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/users", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
      if (!res.ok) {
        setError(await readError(res));
        return;
      }
      const u = (await res.json()) as UserOut;
      setUsers((list) => {
        const rest = list.filter((x) => x.email !== u.email);
        return [...rest, u].sort((a, b) => a.email.localeCompare(b.email));
      });
      setEmail("");
      setName("");
    } catch {
      setError(networkError("The user change"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form
        className="card users-add"
        onSubmit={(e) => {
          e.preventDefault();
          if (email.trim()) void upsert({ email: email.trim().toLowerCase(), display_name: name.trim() || null, role, active: true });
        }}
      >
        <label>
          Google email <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="name@company.com" />
        </label>
        <label>
          Name <input value={name} onChange={(e) => setName(e.target.value)} placeholder="optional" />
        </label>
        <label>
          Role{" "}
          <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="analyst">analyst (read)</option>
            <option value="reviewer">reviewer (decide)</option>
            <option value="administrator">administrator</option>
          </select>
        </label>
        <button type="submit" disabled={busy}>
          Add or update
        </button>
      </form>
      {error ? (
        <div className="banner" data-tone="bad" role="alert">
          <strong>{error.message}</strong> {error.next_step} {error.detail ? <span className="muted">{error.detail}</span> : null}
        </div>
      ) : null}
      <table className="compact">
        <thead>
          <tr>
            <th>Email</th>
            <th>Name</th>
            <th>Role</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>
                {u.email}
                {u.email === me ? <span className="muted"> (you)</span> : null}
              </td>
              <td>{u.display_name ?? <span className="muted">—</span>}</td>
              <td>
                <select
                  value={u.role}
                  disabled={busy || u.email === me}
                  onChange={(e) => void upsert({ email: u.email, display_name: u.display_name, role: e.target.value as Role, active: u.active })}
                  aria-label={`role of ${u.email}`}
                >
                  <option value="analyst">analyst</option>
                  <option value="reviewer">reviewer</option>
                  <option value="administrator">administrator</option>
                </select>
              </td>
              <td>
                <span className="badge" data-tone={u.active ? "ok" : "bad"}>
                  {u.active ? "active" : "disabled"}
                </span>
              </td>
              <td>
                {u.email !== me ? (
                  <button type="button" className="tt-btn" disabled={busy} onClick={() => void upsert({ email: u.email, display_name: u.display_name, role: u.role, active: !u.active })}>
                    {u.active ? "Disable" : "Enable"}
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
