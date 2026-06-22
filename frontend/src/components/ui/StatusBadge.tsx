import { statusColor } from "@/lib/status";

export default function StatusBadge({
  status,
  className = "",
}: {
  status: string;
  className?: string;
}) {
  return (
    <p className={`font-semibold ${statusColor(status)} ${className}`}>
      {status}
    </p>
  );
}
