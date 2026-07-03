"use client";

import { isActiveStatus, statusDot, statusLabel } from "@/lib/status";
import { useT } from "@/lib/i18n/LanguageContext";

export default function StatusBadge({
  status,
  className = "",
}: {
  status: string;
  className?: string;
}) {
  const t = useT();
  return (
    <p className={`flex items-center gap-1.5 ${className}`}>
      <span
        className={`inline-block h-2 w-2 shrink-0 rounded-full ${statusDot(status)} ${
          isActiveStatus(status) ? "animate-pulse" : ""
        }`}
      />
      <span className="font-medium text-muted">{statusLabel(status, t)}</span>
    </p>
  );
}
