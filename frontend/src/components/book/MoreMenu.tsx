"use client";

import type { MouseEvent, ReactNode } from "react";

// Menu déroulant sans état JS (élément natif <details>) : accessible au clavier, se referme
// au clic sur un élément. Sert à ranger les actions secondaires (audit 2026-09-25, UX-1).
export default function MoreMenu({
  label,
  children,
  ariaLabel,
}: {
  label: ReactNode;
  children: ReactNode;
  ariaLabel?: string;
}) {
  function closeOnPick(e: MouseEvent<HTMLDivElement>) {
    e.currentTarget.closest("details")?.removeAttribute("open");
  }
  return (
    <details className="relative">
      <summary
        aria-label={ariaLabel}
        className="cursor-pointer list-none rounded-control border border-border bg-surface-2 px-3 py-1.5 text-xs font-semibold text-foreground transition-colors hover:bg-surface-2/70 [&::-webkit-details-marker]:hidden"
      >
        {label}
      </summary>
      <div
        onClick={closeOnPick}
        className="absolute left-0 z-20 mt-1 min-w-56 rounded-2xl border border-border bg-surface p-1.5 shadow-lg"
      >
        {children}
      </div>
    </details>
  );
}

const ITEM_CLASS =
  "block w-full rounded-xl px-3 py-2 text-left text-sm transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50";

export function MenuItem({
  onClick,
  href,
  disabled,
  danger,
  children,
  title,
}: {
  onClick?: () => void;
  href?: string;
  disabled?: boolean;
  danger?: boolean;
  children: ReactNode;
  title?: string;
}) {
  const tone = danger ? "text-danger" : "text-foreground";
  if (href) {
    return (
      <a href={href} download title={title} className={`${ITEM_CLASS} ${tone}`}>
        {children}
      </a>
    );
  }
  return (
    <button onClick={onClick} disabled={disabled} title={title} className={`${ITEM_CLASS} ${tone}`}>
      {children}
    </button>
  );
}
