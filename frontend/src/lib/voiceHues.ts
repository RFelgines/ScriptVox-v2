import { VoiceSummary } from "@/lib/api";

// Angle d'or (137.5077...°) : assigner la N-ième teinte = N x angle d'or
// répartit n'importe quel nombre de couleurs sur le cercle chromatique de
// façon maximalement distincte.
const GOLDEN_ANGLE = 137.5077;

// Partagé entre PlayerProvider (bandeau lecteur) et /voix (catalogue) pour
// garantir la même teinte par voix aux deux endroits — même liste triée en
// entrée, même correspondance.
export function buildHueMap(voices: VoiceSummary[]): Map<string, number> {
  const sortedIds = voices.map((v) => v.id).sort();
  const map = new Map<string, number>();
  sortedIds.forEach((id, i) => map.set(id, (i * GOLDEN_ANGLE) % 360));
  return map;
}
