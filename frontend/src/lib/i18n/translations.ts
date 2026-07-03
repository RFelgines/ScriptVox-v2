// Dictionnaire FR/EN maison (pas de next-intl/i18next — décision du chantier
// i18n, voir mémoire projet). `Dictionary` fixe la forme exacte des clés :
// tout écart entre `fr` et `en` est une erreur de compilation TS.
export type Locale = "fr" | "en";

export const LOCALE_STORAGE_KEY = "language";

export interface Dictionary {
  nav: {
    library: string;
    voices: string;
    generation: string;
    settings: string;
  };
  status: Record<"PENDING" | "PROCESSING" | "ANALYZED" | "GENERATING" | "DONE" | "FAILED", string>;
  errors: {
    upload: (detail: string) => string;
    fieldChange: (field: string, detail: string) => string;
    fields: {
      ttsProvider: string;
      genre: string;
      language: string;
      publishedAt: string;
    };
    voiceCreate: (detail: string) => string;
    voiceDelete: (detail: string) => string;
    voiceOverride: (detail: string) => string;
    bookAction: (action: string, detail: string) => string;
    actions: {
      analyze: string;
      generate: string;
      stop: string;
    };
    bookDelete: (detail: string) => string;
    chapterGenerate: (detail: string) => string;
    mergeResolve: (action: "accept" | "reject", detail: string) => string;
    chapterStop: (detail: string) => string;
    chapterPriority: (detail: string) => string;
    allChaptersGenerate: (detail: string) => string;
  };
}

const fr: Dictionary = {
  nav: {
    library: "Bibliothèque",
    voices: "Voix",
    generation: "Génération",
    settings: "Paramètres",
  },
  status: {
    PENDING: "En attente",
    PROCESSING: "Analyse…",
    ANALYZED: "Analysé",
    GENERATING: "Génération…",
    DONE: "Prêt",
    FAILED: "Échec",
  },
  errors: {
    upload: (detail) => `Upload échoué : ${detail}`,
    fieldChange: (field, detail) => `${field} échoué : ${detail}`,
    fields: {
      ttsProvider: "Changement de provider",
      genre: "Changement de genre",
      language: "Changement de langue",
      publishedAt: "Changement de date de publication",
    },
    voiceCreate: (detail) => `Création de voix échouée : ${detail}`,
    voiceDelete: (detail) => `Suppression de voix échouée : ${detail}`,
    voiceOverride: (detail) => `Override voix échoué : ${detail}`,
    bookAction: (action, detail) => `${action} : ${detail}`,
    actions: {
      analyze: "Analyse échouée",
      generate: "Génération échouée",
      stop: "Arrêt échoué",
    },
    bookDelete: (detail) => `Suppression échouée : ${detail}`,
    chapterGenerate: (detail) => `Génération du chapitre échouée : ${detail}`,
    mergeResolve: (action, detail) => `Fusion (${action}) échouée : ${detail}`,
    chapterStop: (detail) => `Arrêt du chapitre échoué : ${detail}`,
    chapterPriority: (detail) => `Changement de priorité échoué : ${detail}`,
    allChaptersGenerate: (detail) => `Génération de tous les chapitres échouée : ${detail}`,
  },
};

const en: Dictionary = {
  nav: {
    library: "Library",
    voices: "Voices",
    generation: "Generation",
    settings: "Settings",
  },
  status: {
    PENDING: "Pending",
    PROCESSING: "Analysing…",
    ANALYZED: "Analysed",
    GENERATING: "Generating…",
    DONE: "Ready",
    FAILED: "Failed",
  },
  errors: {
    upload: (detail) => `Upload failed: ${detail}`,
    fieldChange: (field, detail) => `${field} failed: ${detail}`,
    fields: {
      ttsProvider: "Provider change",
      genre: "Genre change",
      language: "Language change",
      publishedAt: "Publication date change",
    },
    voiceCreate: (detail) => `Voice creation failed: ${detail}`,
    voiceDelete: (detail) => `Voice deletion failed: ${detail}`,
    voiceOverride: (detail) => `Voice override failed: ${detail}`,
    bookAction: (action, detail) => `${action}: ${detail}`,
    actions: {
      analyze: "Analysis failed",
      generate: "Generation failed",
      stop: "Stop failed",
    },
    bookDelete: (detail) => `Deletion failed: ${detail}`,
    chapterGenerate: (detail) => `Chapter generation failed: ${detail}`,
    mergeResolve: (action, detail) => `Merge (${action}) failed: ${detail}`,
    chapterStop: (detail) => `Chapter stop failed: ${detail}`,
    chapterPriority: (detail) => `Priority change failed: ${detail}`,
    allChaptersGenerate: (detail) => `Generation of all chapters failed: ${detail}`,
  },
};

export const translations: Record<Locale, Dictionary> = { fr, en };

// Lecture directe (hors React) pour du code impératif comme lib/api.ts, qui
// n'a pas accès aux hooks -- même clé que LanguageContext.tsx.
export function getStoredLocale(): Locale {
  if (typeof window === "undefined") return "fr";
  return localStorage.getItem(LOCALE_STORAGE_KEY) === "en" ? "en" : "fr";
}
