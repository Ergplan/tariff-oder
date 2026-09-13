"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Polls job progress by refreshing server data.  A dropped connection never marks the job
 * failed; the next successful refresh shows the backend's state. */
export function AutoRefresh({ seconds }: { seconds: number }) {
  const router = useRouter();
  useEffect(() => {
    const t = setInterval(() => router.refresh(), seconds * 1000);
    return () => clearInterval(t);
  }, [router, seconds]);
  return (
    <p className="muted" aria-live="polite">
      Job in progress — refreshing every {seconds}s.
    </p>
  );
}
