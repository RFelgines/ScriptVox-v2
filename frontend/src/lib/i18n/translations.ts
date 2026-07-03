// Dictionnaire FR/EN maison (pas de next-intl/i18next — décision du chantier
// i18n, voir mémoire projet). `Dictionary` fixe la forme exacte des clés :
// tout écart entre `fr` et `en` est une erreur de compilation TS.
export type Locale = "fr" | "en";

export interface Dictionary {
  nav: {
    library: string;
    voices: string;
    generation: string;
    settings: string;
  };
}

const fr: Dictionary = {
  nav: {
    library: "Bibliothèque",
    voices: "Voix",
    generation: "Génération",
    settings: "Paramètres",
  },
};

const en: Dictionary = {
  nav: {
    library: "Library",
    voices: "Voices",
    generation: "Generation",
    settings: "Settings",
  },
};

export const translations: Record<Locale, Dictionary> = { fr, en };
