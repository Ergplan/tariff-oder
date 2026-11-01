"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

/** A dropdown of secondary links (the regulatory desk, administration) that closes on navigation. */
export default function NavMenu({ label, links }: { label: string; links: { href: string; label: string }[] }) {
  const ref = useRef<HTMLDetailsElement>(null);
  const path = usePathname();
  useEffect(() => {
    if (ref.current) ref.current.open = false;
  }, [path]);
  useEffect(() => {
    function close(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) ref.current.open = false;
    }
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);
  return (
    <details className="navmenu" ref={ref}>
      <summary>{label}</summary>
      <div role="menu">
        {links.map((l) => (
          <Link key={l.href} href={l.href} role="menuitem">
            {l.label}
          </Link>
        ))}
      </div>
    </details>
  );
}
