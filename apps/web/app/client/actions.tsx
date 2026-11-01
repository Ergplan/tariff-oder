"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse } from "@tariff/contracts";
import { networkError, readError } from "@/lib/client-errors";
import { ErrorBanner } from "../components";

/** POST/PUT/DELETE through the client proxy, then refresh or go somewhere; errors shown inline. */
export async function call(path: string, method: string, body?: unknown): Promise<{ ok: true; data: unknown } | { ok: false; error: ErrorResponse }> {
  try {
    // a path starting with "/" is a same-origin route of its own; otherwise the client proxy
    const res = await fetch(path.startsWith("/") ? path : `/api/client/${path}`, {
      method,
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) return { ok: false, error: await readError(res) };
    return { ok: true, data: res.status === 204 ? null : await res.json() };
  } catch {
    return { ok: false, error: networkError("The action") };
  }
}

export function ActionButton({
  path,
  method = "POST",
  body,
  label,
  confirm,
  then,
  tone,
}: {
  path: string;
  method?: string;
  body?: unknown;
  label: string;
  confirm?: string;
  then?: string;
  tone?: "primary" | "plain";
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);
  return (
    <span className="action">
      <button
        type="button"
        disabled={busy}
        data-tone={tone ?? "primary"}
        onClick={async () => {
          if (confirm && !window.confirm(confirm)) return;
          setBusy(true);
          setError(null);
          const r = await call(path, method, body);
          setBusy(false);
          if (!r.ok) return setError(r.error);
          if (then) router.push(then);
          else router.refresh();
        }}
      >
        {busy ? "Working…" : label}
      </button>
      {error ? <ErrorBanner error={error} /> : null}
    </span>
  );
}
