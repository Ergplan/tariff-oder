"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse } from "@tariff/contracts";
import { ErrorBanner } from "../../components";
import { call } from "../../client/actions";

export function CreateOrg() {
  const router = useRouter();
  const [v, setV] = useState({ code: "", name: "", owner_email: "" });
  const [error, setError] = useState<ErrorResponse | null>(null);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        const r = await call("organisations", "POST", v);
        if (!r.ok) return setError(r.error);
        setV({ code: "", name: "", owner_email: "" });
        router.refresh();
      }}
    >
      <div className="form-grid">
        <label>
          Code
          <input value={v.code} onChange={(e) => setV({ ...v, code: e.target.value.trim() })} required />
        </label>
        <label>
          Name
          <input value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} required />
        </label>
        <label>
          Owner email
          <input value={v.owner_email} onChange={(e) => setV({ ...v, owner_email: e.target.value.trim() })} type="email" required />
        </label>
      </div>
      <button type="submit">Create organisation</button>
      {error ? <ErrorBanner error={error} /> : null}
    </form>
  );
}

export function AddMember({ orgId }: { orgId: string }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("editor");
  const [error, setError] = useState<ErrorResponse | null>(null);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        const r = await call(`organisations/${orgId}/members`, "POST", { email, role });
        if (!r.ok) return setError(r.error);
        setEmail("");
        router.refresh();
      }}
      style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}
    >
      <input value={email} onChange={(e) => setEmail(e.target.value.trim())} type="email" placeholder="member email" required />
      <select value={role} onChange={(e) => setRole(e.target.value)}>
        <option>viewer</option>
        <option>editor</option>
        <option>owner</option>
      </select>
      <button type="submit">Add</button>
      {error ? <ErrorBanner error={error} /> : null}
    </form>
  );
}
