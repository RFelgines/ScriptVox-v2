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
  library: {
    title: string;
    bookCount: (n: number) => string;
    filteredOf: (total: number) => string;
    searchPlaceholder: string;
    searchAriaLabel: string;
    filterStatusAriaLabel: string;
    allStatuses: string;
    statusLabels: Record<"PENDING" | "PROCESSING" | "ANALYZED" | "GENERATING" | "DONE" | "FAILED", string>;
    filterProviderAriaLabel: string;
    allProviders: string;
    defaultProvider: (name: string) => string;
    filterGenreAriaLabel: string;
    allGenres: string;
    filterAuthorAriaLabel: string;
    allAuthors: string;
    filterLanguageAriaLabel: string;
    allLanguages: string;
    sortAriaLabel: string;
    sortLabels: Record<
      "NONE" | "TITLE_ASC" | "ADDED_DESC" | "ADDED_ASC" | "PUBLISHED_DESC" | "PUBLISHED_ASC",
      string
    >;
    apiUnreachableTitle: string;
    apiUnreachableHint: string;
    emptyTitle: string;
    emptyHint: string;
    noMatchTitle: string;
    noMatchHint: string;
  };
  generation: {
    title: string;
    subtitle: string;
    errorTitle: string;
    inProgress: string;
    noneInProgress: string;
    stopping: string;
    stop: string;
    chapterFallback: (position: number) => string;
    coverAlt: (title: string) => string;
    pending: (n: number) => string;
    queueEmpty: string;
    dragToReorder: string;
    moveUp: string;
    moveDown: string;
  };
  settings: {
    title: string;
    subtitle: string;
    apiUnreachableTitle: string;
    llmLabel: string;
    ttsLabel: string;
    statusLevels: Record<"ok" | "warning" | "error", string>;
    preferredProviderLabel: string;
    defaultOption: (name: string) => string;
    saving: string;
    preferredHint: string;
    clonedVoicesLabel: string;
    clonedVoicesAvailable: (n: number) => string;
    clonedVoicesNone: string;
    clonedVoicesHintAvailable: string;
    clonedVoicesHintNone: string;
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
  library: {
    title: "Bibliothèque",
    bookCount: (n) => `${n} livre${n > 1 ? "s" : ""}`,
    filteredOf: (total) => ` sur ${total}`,
    searchPlaceholder: "Rechercher un titre ou un auteur…",
    searchAriaLabel: "Rechercher un livre",
    filterStatusAriaLabel: "Filtrer par statut",
    allStatuses: "Tous statuts",
    statusLabels: {
      PENDING: "En attente",
      PROCESSING: "Analyse en cours",
      ANALYZED: "Analysé",
      GENERATING: "Génération en cours",
      DONE: "Terminé",
      FAILED: "Échec",
    },
    filterProviderAriaLabel: "Filtrer par modèle TTS",
    allProviders: "Tous moteurs TTS",
    defaultProvider: (name) => `Par défaut (${name})`,
    filterGenreAriaLabel: "Filtrer par genre",
    allGenres: "Tous genres",
    filterAuthorAriaLabel: "Filtrer par auteur",
    allAuthors: "Tous auteurs",
    filterLanguageAriaLabel: "Filtrer par langue",
    allLanguages: "Toutes langues",
    sortAriaLabel: "Trier par",
    sortLabels: {
      NONE: "Tri par défaut",
      TITLE_ASC: "Titre (A→Z)",
      ADDED_DESC: "Date d'ajout (récent d'abord)",
      ADDED_ASC: "Date d'ajout (ancien d'abord)",
      PUBLISHED_DESC: "Date de publication (récent d'abord)",
      PUBLISHED_ASC: "Date de publication (ancien d'abord)",
    },
    apiUnreachableTitle: "Impossible de joindre l'API",
    apiUnreachableHint: "Vérifiez que l'API tourne sur",
    emptyTitle: "Bibliothèque vide",
    emptyHint: "Glissez un fichier EPUB ci-dessus pour commencer.",
    noMatchTitle: "Aucun livre ne correspond",
    noMatchHint: "Essayez d'élargir les filtres ci-dessus.",
  },
  generation: {
    title: "Génération",
    subtitle: "File d'attente de génération audio, tous livres confondus.",
    errorTitle: "Erreur",
    inProgress: "En cours",
    noneInProgress: "Aucune génération en cours.",
    stopping: "Arrêt…",
    stop: "Arrêter",
    chapterFallback: (position) => `Chapitre ${position}`,
    coverAlt: (title) => `Couverture de ${title}`,
    pending: (n) => `En attente (${n})`,
    queueEmpty: "La file d'attente est vide.",
    dragToReorder: "Glisser pour réordonner",
    moveUp: "Monter dans la file",
    moveDown: "Descendre dans la file",
  },
  settings: {
    title: "Paramètres",
    subtitle: "État des services. Le moteur de synthèse par livre se choisit dans la page Casting.",
    apiUnreachableTitle: "Impossible de joindre l'API",
    llmLabel: "Analyse LLM",
    ttsLabel: "Synthèse vocale TTS",
    statusLevels: {
      ok: "Opérationnel",
      warning: "Attention",
      error: "Erreur",
    },
    preferredProviderLabel: "Modèle TTS préféré",
    defaultOption: (name) => `Par défaut (${name})`,
    saving: "Enregistrement…",
    preferredHint:
      "Préférence enregistrée, pas encore appliquée à la génération — le moteur réel reste " +
      "celui choisi par livre (page Casting) ou la valeur par défaut du serveur.",
    clonedVoicesLabel: "Voix clonées",
    clonedVoicesAvailable: (n) => `${n} voix clonée${n > 1 ? "s" : ""} disponible${n > 1 ? "s" : ""}`,
    clonedVoicesNone: "Aucune voix clonée",
    clonedVoicesHintAvailable: "Utilisables avec Qwen3-TTS uniquement — assignées en priorité lors de l'analyse.",
    clonedVoicesHintNone: "Ajoutez des voix depuis l'onglet Voix pour activer le clonage.",
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
  library: {
    title: "Library",
    bookCount: (n) => `${n} book${n > 1 ? "s" : ""}`,
    filteredOf: (total) => ` of ${total}`,
    searchPlaceholder: "Search by title or author…",
    searchAriaLabel: "Search for a book",
    filterStatusAriaLabel: "Filter by status",
    allStatuses: "All statuses",
    statusLabels: {
      PENDING: "Pending",
      PROCESSING: "Analysing",
      ANALYZED: "Analysed",
      GENERATING: "Generating",
      DONE: "Done",
      FAILED: "Failed",
    },
    filterProviderAriaLabel: "Filter by TTS engine",
    allProviders: "All TTS engines",
    defaultProvider: (name) => `Default (${name})`,
    filterGenreAriaLabel: "Filter by genre",
    allGenres: "All genres",
    filterAuthorAriaLabel: "Filter by author",
    allAuthors: "All authors",
    filterLanguageAriaLabel: "Filter by language",
    allLanguages: "All languages",
    sortAriaLabel: "Sort by",
    sortLabels: {
      NONE: "Default order",
      TITLE_ASC: "Title (A→Z)",
      ADDED_DESC: "Date added (newest first)",
      ADDED_ASC: "Date added (oldest first)",
      PUBLISHED_DESC: "Publication date (newest first)",
      PUBLISHED_ASC: "Publication date (oldest first)",
    },
    apiUnreachableTitle: "Cannot reach the API",
    apiUnreachableHint: "Check that the API is running on",
    emptyTitle: "Library is empty",
    emptyHint: "Drop an EPUB file above to get started.",
    noMatchTitle: "No book matches",
    noMatchHint: "Try widening the filters above.",
  },
  generation: {
    title: "Generation",
    subtitle: "Audio generation queue, across all books.",
    errorTitle: "Error",
    inProgress: "In progress",
    noneInProgress: "No generation in progress.",
    stopping: "Stopping…",
    stop: "Stop",
    chapterFallback: (position) => `Chapter ${position}`,
    coverAlt: (title) => `Cover of ${title}`,
    pending: (n) => `Pending (${n})`,
    queueEmpty: "The queue is empty.",
    dragToReorder: "Drag to reorder",
    moveUp: "Move up in the queue",
    moveDown: "Move down in the queue",
  },
  settings: {
    title: "Settings",
    subtitle: "Service status. The per-book synthesis engine is chosen from the Casting page.",
    apiUnreachableTitle: "Cannot reach the API",
    llmLabel: "LLM analysis",
    ttsLabel: "TTS voice synthesis",
    statusLevels: {
      ok: "Operational",
      warning: "Warning",
      error: "Error",
    },
    preferredProviderLabel: "Preferred TTS model",
    defaultOption: (name) => `Default (${name})`,
    saving: "Saving…",
    preferredHint:
      "Preference saved, not yet applied to generation — the actual engine remains " +
      "the one chosen per book (Casting page) or the server's default value.",
    clonedVoicesLabel: "Cloned voices",
    clonedVoicesAvailable: (n) => `${n} cloned voice${n > 1 ? "s" : ""} available`,
    clonedVoicesNone: "No cloned voice",
    clonedVoicesHintAvailable: "Usable with Qwen3-TTS only — assigned as priority during analysis.",
    clonedVoicesHintNone: "Add voices from the Voices tab to enable cloning.",
  },
};

export const translations: Record<Locale, Dictionary> = { fr, en };

// Lecture directe (hors React) pour du code impératif comme lib/api.ts, qui
// n'a pas accès aux hooks -- même clé que LanguageContext.tsx.
export function getStoredLocale(): Locale {
  if (typeof window === "undefined") return "fr";
  return localStorage.getItem(LOCALE_STORAGE_KEY) === "en" ? "en" : "fr";
}
