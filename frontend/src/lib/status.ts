export const STATUS_COLOR: Record<string, string> = {
  PENDING: "text-stone-400",
  PROCESSING: "text-blue-400",
  ANALYZED: "text-amber-400",
  GENERATING: "text-orange-400",
  DONE: "text-green-400",
  FAILED: "text-red-400",
};

export const STATUS_DOT: Record<string, string> = {
  PENDING: "bg-stone-400",
  PROCESSING: "bg-blue-400",
  ANALYZED: "bg-amber-400",
  GENERATING: "bg-orange-400",
  DONE: "bg-green-400",
  FAILED: "bg-red-400",
};

export const STATUS_LABEL: Record<string, string> = {
  PENDING: "En attente",
  PROCESSING: "Analyse…",
  ANALYZED: "Analysé",
  GENERATING: "Génération…",
  DONE: "Prêt",
  FAILED: "Échec",
};

export function statusColor(status: string): string {
  return STATUS_COLOR[status] ?? "text-stone-400";
}

export function statusDot(status: string): string {
  return STATUS_DOT[status] ?? "bg-stone-400";
}

export function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status;
}
