export const STATUS_COLOR: Record<string, string> = {
  PENDING: "text-gray-400",
  PROCESSING: "text-blue-400",
  ANALYZED: "text-yellow-400",
  GENERATING: "text-orange-400",
  DONE: "text-green-400",
  FAILED: "text-red-400",
};

export function statusColor(status: string): string {
  return STATUS_COLOR[status] ?? "text-gray-400";
}
