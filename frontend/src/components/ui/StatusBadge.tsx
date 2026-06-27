import { statusDot, statusLabel } from "@/lib/status";

export default function StatusBadge({
  status,
  className = "",
}: {
  status: string;
  className?: string;
}) {
  return (
    <p className={`flex items-center gap-1.5 ${className}`}>
      <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${statusDot(status)}`} />
      <span className="font-medium text-muted">{statusLabel(status)}</span>
    </p>
  );
}
