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

export function statusDot(status: string): string {
  return STATUS_DOT[status] ?? "bg-stone-400";
}

export function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status;
}

// "En cours" seulement (PROCESSING/GENERATING) -- PENDING est une file
// d'attente statique, pas un travail en cours, donc ne doit pas clignoter
// (une liste de 30+ chapitres PENDING pulserait tous en même temps sinon).
export function isActiveStatus(status: string): boolean {
  return status === "PROCESSING" || status === "GENERATING";
}
