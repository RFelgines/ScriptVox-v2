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
    voiceSample: (detail: string) => string;
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
    deleteConfirm: (title: string) => string;
    deleteAriaLabel: string;
  };
  upload: {
    invalidFile: string;
    uploading: string;
    dropHint: string;
    clickHint: string;
  };
  // Chaînes partagées par PlayerBar et ChapterTranscript (bandeau lecteur +
  // panneau déplié).
  player: {
    narrator: string;
    transcript: {
      title: (position: number) => string;
      loading: string;
      empty: string;
      syncUnavailable: string;
      seekAriaLabel: (label: string) => string;
    };
    progressAriaLabel: string;
    prevChapterAriaLabel: string;
    rewind15AriaLabel: string;
    pauseAriaLabel: string;
    playAriaLabel: string;
    forward15AriaLabel: string;
    nextChapterAriaLabel: string;
    rateAriaLabel: string;
    rateLabel: string;
    showChaptersAriaLabel: string;
    hideChaptersAriaLabel: string;
    chaptersLabel: string;
    bookmarkAriaLabel: string;
    bookmarkTitle: string;
    bookmarkLabel: string;
    rateSelectAriaLabel: string;
    readByLabel: string;
    closePlayerAriaLabel: string;
    audioError: string;
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
    preferredLanguageLabel: string;
    languageOptionNone: string;
    languageNames: Record<string, string>;
    preferredLanguageHint: string;
    clonedVoicesLabel: string;
    clonedVoicesAvailable: (n: number) => string;
    clonedVoicesNone: string;
    clonedVoicesHintAvailable: string;
    clonedVoicesHintNone: string;
    preferredLlmLabel: string;
    preferredLlmHint: string;
    privacyBadgeLocal: string;
    privacyBadgeCloud: string;
    testConnection: string;
    testConnectionTesting: string;
  };
  book: {
    backToLibrary: string;
    errorTitle: string;
    coverAlt: (title: string) => string;
    languageUnsupported: (language: string) => string;
    genrePlaceholder: string;
    genreAriaLabel: string;
    languagePlaceholder: string;
    languageAriaLabel: string;
    publishedAtLabel: string;
    analysisInProgressHint: string;
    launching: string;
    analyze: string;
    resumeAnalysis: string;
    analysisFailedAriaLabel: string;
    analysisFailedTitle: (detail: string) => string;
    reanalyze: string;
    reanalyzeConfirm: string;
    generateAudio: string;
    regenerateAudio: string;
    resumeGeneration: string;
    regenerateAudioConfirm: string;
    stopping: string;
    stop: string;
    stopConfirm: string;
    casting: string;
    listen: string;
    loadingCasting: string;
    castingUnavailableTitle: string;
    castingUnavailableBody: (status: string) => string;
    mergeSuggestionsTitle: string;
    acceptAll: string;
    accept: string;
    reject: string;
    noCharactersDetected: string;
    searchCharacterPlaceholder: string;
    noCharacterMatches: string;
    secondaryCharacters: (n: number) => string;
    localeKnown: (locale: string) => string;
    localeUnknown: string;
    engineLabel: string;
    defaultProvider: (name: string) => string;
    generateOnlyWhenAnalyzed: string;
    segmentCount: (n: number) => string;
    clonedVoiceIncompatible: (provider: string) => string;
    clonedBadge: string;
    chooseVoice: string;
    clonedVoicesGroup: string;
    previewVoice: string;
    previewTitle: (id: string) => string;
    confirmVoice: string;
    chaptersTitle: (n: number) => string;
    generateAllAudio: string;
    noChaptersYet: string;
    chapterFallback: (position: number) => string;
    generateChapter: string;
    regenerateChapter: string;
  };
  voices: {
    title: string;
    searchPlaceholder: string;
    searchAriaLabel: string;
    genderFilterAriaLabel: string;
    allGenders: string;
    genderLabels: Record<"MALE" | "FEMALE" | "NEUTRAL", string>;
    kindFilterAriaLabel: string;
    allKinds: string;
    catalogueKind: string;
    clonedKind: string;
    sampleFilterAriaLabel: string;
    allSamples: string;
    sampleAvailable: string;
    sampleMissing: string;
    favoritesOnly: string;
    cancelClone: string;
    startClone: string;
    subtitle: string;
    cloneFormTitle: string;
    nameLabel: string;
    namePlaceholder: string;
    genderLabel: string;
    genderUnspecified: string;
    referenceAudioLabel: string;
    chooseFile: string;
    creating: string;
    createClonedVoice: string;
    nameRequired: string;
    referenceAudioRequired: string;
    apiUnreachableTitle: string;
    noMatchTitle: string;
    noneAvailableTitle: string;
    noMatchHint: string;
    catalogueEmptyHint: string;
    deleteClonedConfirm: (name: string) => string;
    deleteCatalogueConfirm: (name: string) => string;
    generateSampleAriaLabel: (name: string) => string;
    sampleUnavailableTitle: string;
    previewAriaLabel: (name: string) => string;
    removeFavorite: string;
    addFavorite: string;
    deleteVoiceAriaLabel: (name: string) => string;
    deleteClonedTitle: string;
    removeFromCatalogueTitle: string;
    clonedBadge: string;
  };
  // ── Audit 2026-09-25 ─────────────────────────────────────────────────────────
  models: {
    sectionTitle: string;
    sectionHint: string;
    llmTitle: string;
    ttsTitle: string;
    providerLabel: string;
    modelLabel: string;
    modelPlaceholder: string;
    modelHint: string;
    baseModelLabel: string;
    baseUrlLabel: string;
    baseUrlHint: string;
    localeLabel: string;
    envDefault: string;
    saveButton: string;
    savingButton: string;
    savedToast: string;
    refreshList: string;
    listError: (detail: string) => string;
    effectiveModel: (model: string) => string;
    testButton: string;
    testingButton: string;
    pluginErrorsTitle: string;
    pluginHint: string;
    presetsTitle: string;
    presetLocal: string;
    presetCloud: string;
    presetLocalNote: string;
    presetCloudNote: string;
    freeGpu: string;
    freeGpuDone: string;
  };
  flow: {
    stepAnalysis: string;
    stepCasting: string;
    stepGeneration: string;
    stepListen: string;
    generateBook: string;
    regenerate: string;
    resume: string;
    restart: string;
    listen: string;
    resumeListening: (chapter: string, time: string) => string;
    more: string;
    details: string;
    download: string;
    downloadM4b: string;
    downloadMp3: string;
    m4bMissing: string;
    stageAnalysis: string;
    stageGeneration: string;
    stageAssembly: string;
    chapterProgress: (current: number, total: number) => string;
    etaLessThanMinute: string;
    etaMinutes: (minutes: number) => string;
    etaHours: (hours: number, minutes: number) => string;
    includeChapter: string;
    excludeChapter: string;
    chapterExcluded: string;
    voiceSaved: (character: string, voice: string) => string;
    previewOnLine: string;
    previewLoading: string;
    previewFailed: string;
    privacyCloudLlm: string;
    privacyCloudTts: string;
    languageAuto: string;
    languageFr: string;
    languageEn: string;
  };
  feedback: {
    confirm: string;
    cancel: string;
    undo: string;
    close: string;
    bookDeleted: (title: string) => string;
    deleteConfirmTitle: string;
  };
  player2: {
    sleepLabel: string;
    sleepOff: string;
    sleepEndOfChapter: string;
    sleepMinutes: (minutes: number) => string;
    sleepRemaining: (mmss: string) => string;
    shortcutsHint: string;
  };
  library2: {
    filters: string;
    filtersActive: (count: number) => string;
    resetFilters: string;
    importEpub: string;
    dropOverlay: string;
    continueListening: string;
    generationBadge: (count: number) => string;
  };
  voices2: {
    referenceTextLabel: string;
    referenceTextPlaceholder: string;
    referenceTextHint: string;
  };
  production: {
    excerpt: string;
    excerptTitle: string;
    excerptLoading: string;
    acxCheck: string;
    acxTitle: (rms: string, peak: string) => string;
    acxOk: string;
    acxKo: string;
    downloadChaptersTxt: string;
    lexiconTitle: string;
    lexiconGlobalTitle: string;
    lexiconHint: string;
    lexiconTerm: string;
    lexiconReplacement: string;
    lexiconWholeWord: string;
    lexiconCaseSensitive: string;
    lexiconAdd: string;
    lexiconEmpty: string;
    lexiconGlobalBadge: string;
    lexiconTest: string;
    lexiconTestPlaceholder: string;
    lexiconSpoken: string;
    designVoice: string;
    designVoiceTitle: string;
    designPromptLabel: string;
    designPromptHint: string;
    designLaunch: string;
    designRunning: string;
    designDone: string;
    designNeedsServer: string;
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
    voiceSample: (detail) => `Aperçu de voix échoué : ${detail}`,
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
    deleteConfirm: (title) => `Supprimer « ${title} » ?`,
    deleteAriaLabel: "Supprimer",
  },
  upload: {
    invalidFile: "Seuls les fichiers .epub sont acceptés.",
    uploading: "Upload en cours…",
    dropHint: "Glissez un EPUB ici",
    clickHint: "ou cliquez pour choisir un fichier .epub",
  },
  player: {
    narrator: "Narrateur",
    transcript: {
      title: (position) => `Transcription — Chapitre ${position}`,
      loading: "Chargement de la transcription…",
      empty: "Aucun segment disponible pour ce chapitre.",
      syncUnavailable: "Synchronisation indisponible — regénérez ce chapitre",
      seekAriaLabel: (label) => `Aller à ce passage — ${label}`,
    },
    progressAriaLabel: "Progression",
    prevChapterAriaLabel: "Chapitre précédent",
    rewind15AriaLabel: "Reculer de 15 secondes",
    pauseAriaLabel: "Pause",
    playAriaLabel: "Lire",
    forward15AriaLabel: "Avancer de 15 secondes",
    nextChapterAriaLabel: "Chapitre suivant",
    rateAriaLabel: "Changer la vitesse de lecture",
    rateLabel: "Vitesse",
    showChaptersAriaLabel: "Afficher les chapitres",
    hideChaptersAriaLabel: "Masquer les chapitres",
    chaptersLabel: "Chapitres",
    bookmarkAriaLabel: "Signet (bientôt disponible)",
    bookmarkTitle: "Signet — bientôt disponible",
    bookmarkLabel: "Signet",
    rateSelectAriaLabel: "Vitesse de lecture",
    readByLabel: "Lu par",
    closePlayerAriaLabel: "Fermer le lecteur",
    audioError: "Lecture impossible",
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
      "Utilisé quand aucun moteur n'est choisi pour ce livre (page Casting) — sinon, " +
      "l'override par livre reste prioritaire.",
    preferredLanguageLabel: "Langue de préférence (repli de détection)",
    languageOptionNone: "Aucune (repli historique : français)",
    languageNames: { fr: "Français", en: "English" },
    preferredLanguageHint:
      "Utilisée uniquement quand la langue d'un livre ne peut pas être détectée à l'import " +
      "— n'affecte jamais un livre déjà identifié ou modifié manuellement. Distincte de la " +
      "langue d'affichage de l'interface (sélecteur en haut de l'écran).",
    clonedVoicesLabel: "Voix clonées",
    clonedVoicesAvailable: (n) => `${n} voix clonée${n > 1 ? "s" : ""} disponible${n > 1 ? "s" : ""}`,
    clonedVoicesNone: "Aucune voix clonée",
    clonedVoicesHintAvailable: "Utilisables avec Qwen3-TTS uniquement — assignées en priorité lors de l'analyse.",
    clonedVoicesHintNone: "Ajoutez des voix depuis l'onglet Voix pour activer le clonage.",
    preferredLlmLabel: "Moteur LLM préféré",
    preferredLlmHint: "Détermine quel modèle analyse vos textes à chaque run. Pris en compte au prochain lancement d'analyse.",
    privacyBadgeLocal: "🔒 Local — aucune donnée envoyée",
    privacyBadgeCloud: "☁️ Cloud — textes envoyés à Google",
    testConnection: "Tester la connexion",
    testConnectionTesting: "Test en cours…",
  },
  book: {
    backToLibrary: "← Bibliothèque",
    errorTitle: "Erreur",
    coverAlt: (title) => `Couverture de ${title}`,
    languageUnsupported: (language) =>
      `${language} — langue non prise en charge par le moteur actuel : l’audio utilisera le profil français`,
    genrePlaceholder: "Genre (ex. Fantasy)",
    genreAriaLabel: "Genre du livre",
    languagePlaceholder: "Langue (ex. fr)",
    languageAriaLabel: "Langue du livre",
    publishedAtLabel: "Date de publication",
    analysisInProgressHint: "Analyse en cours — le casting s'ouvrira automatiquement.",
    launching: "Lancement…",
    analyze: "Analyser",
    resumeAnalysis: "Reprendre l'analyse",
    analysisFailedAriaLabel: "L'analyse a échoué suite à une erreur",
    analysisFailedTitle: (detail) => `Échec : ${detail}`,
    reanalyze: "Ré-analyser",
    reanalyzeConfirm:
      "Ré-analyser ce livre effacera les personnages, segments et suggestions de fusion existants. Continuer ?",
    generateAudio: "Générer l'audio",
    resumeGeneration: "Reprendre la génération",
    regenerateAudio: "Regénérer l'audio",
    regenerateAudioConfirm: "Regénérer l'audio effacera l'export existant. Continuer ?",
    stopping: "Arrêt…",
    stop: "Arrêter",
    stopConfirm: "Arrêter la tâche en cours ? Le livre passera en échec.",
    casting: "Casting",
    listen: "Écouter",
    loadingCasting: "Chargement du casting…",
    castingUnavailableTitle: "Casting indisponible",
    castingUnavailableBody: (status) =>
      `Le casting n'est disponible qu'une fois le livre analysé (statut actuel : ${status}).`,
    mergeSuggestionsTitle: "Fusions de personnages suggérées",
    acceptAll: "Tout accepter",
    accept: "Accepter",
    reject: "Rejeter",
    noCharactersDetected: "Aucun personnage détecté.",
    searchCharacterPlaceholder: "Rechercher un personnage…",
    noCharacterMatches: "Aucun personnage ne correspond.",
    secondaryCharacters: (n) => `Personnages secondaires sans réplique (${n})`,
    localeKnown: (locale) => `Langue : ${locale}`,
    localeUnknown: "Langue : selon le provider TTS",
    engineLabel: "Moteur :",
    defaultProvider: (name) => `Par défaut (${name})`,
    generateOnlyWhenAnalyzed: "Génération possible uniquement quand le livre est ANALYZED",
    segmentCount: (n) => `${n} réplique${n > 1 ? "s" : ""}`,
    clonedVoiceIncompatible: (provider) =>
      `Le moteur "${provider}" ne clone pas : une voix du catalogue du même genre sera utilisée. Passer sur Qwen ou OmniVoice pour cette voix.`,
    clonedBadge: "Clone",
    chooseVoice: "Choisir…",
    clonedVoicesGroup: "— Voix clonées —",
    previewVoice: "Écouter un aperçu de cette voix",
    previewTitle: (id) => `Aperçu — ${id}`,
    confirmVoice: "Confirmer cette voix",
    chaptersTitle: (n) => `Chapitres (${n})`,
    generateAllAudio: "Générer tout l'audio",
    noChaptersYet: "Aucun chapitre pour l'instant.",
    chapterFallback: (position) => `Chapitre ${position}`,
    generateChapter: "Générer",
    regenerateChapter: "Regénérer ce chapitre",
  },
  voices: {
    title: "Voix",
    searchPlaceholder: "Rechercher par nom…",
    searchAriaLabel: "Rechercher une voix",
    genderFilterAriaLabel: "Filtrer par genre",
    allGenders: "Tous genres",
    genderLabels: {
      MALE: "Masculin",
      FEMALE: "Féminin",
      NEUTRAL: "Neutre",
    },
    kindFilterAriaLabel: "Filtrer par type",
    allKinds: "Tous types",
    catalogueKind: "Catalogue",
    clonedKind: "Clonées",
    sampleFilterAriaLabel: "Filtrer par aperçu",
    allSamples: "Tous aperçus",
    sampleAvailable: "Aperçu disponible",
    sampleMissing: "Sans aperçu",
    favoritesOnly: "★ Favoris",
    cancelClone: "✕ Annuler",
    startClone: "+ Cloner une voix",
    subtitle: "Le catalogue de voix disponibles. Cliquez sur un cercle pour écouter un aperçu.",
    cloneFormTitle: "Cloner une voix",
    nameLabel: "Nom *",
    namePlaceholder: "ex. Patrick Baud",
    genderLabel: "Genre",
    genderUnspecified: "— Non précisé —",
    referenceAudioLabel: "Audio de référence * (MP3 / WAV / FLAC)",
    chooseFile: "Choisir un fichier…",
    creating: "Création en cours…",
    createClonedVoice: "Créer la voix clonée",
    nameRequired: "Le nom est requis.",
    referenceAudioRequired: "Un fichier audio de référence est requis.",
    apiUnreachableTitle: "Impossible de joindre l'API",
    noMatchTitle: "Aucune voix ne correspond",
    noneAvailableTitle: "Aucune voix disponible",
    noMatchHint: "Essayez d'élargir les filtres ci-dessus.",
    catalogueEmptyHint: "Le catalogue de voix est vide.",
    deleteClonedConfirm: (name) => `Supprimer la voix « ${name} » ? Cette action est irréversible.`,
    deleteCatalogueConfirm: (name) =>
      `Retirer « ${name} » du catalogue ? Elle sera restaurée au prochain redémarrage du serveur.`,
    generateSampleAriaLabel: (name) => `Générer un aperçu pour ${name}`,
    sampleUnavailableTitle: "Sample non disponible — cliquer pour générer",
    previewAriaLabel: (name) => `Écouter un aperçu de ${name}`,
    removeFavorite: "Retirer des favoris",
    addFavorite: "Ajouter aux favoris",
    deleteVoiceAriaLabel: (name) => `Supprimer la voix ${name}`,
    deleteClonedTitle: "Supprimer cette voix clonée",
    removeFromCatalogueTitle: "Retirer du catalogue",
    clonedBadge: "🎙 cloné",
  },
  models: {
    sectionTitle: "Modèles",
    sectionHint:
      "Choisissez le moteur et le modèle. La liste propose ce qui est installé, mais vous pouvez saisir n'importe quel nom : un modèle absent de la liste fonctionne s'il est servi par le moteur.",
    llmTitle: "Analyse du texte (LLM)",
    ttsTitle: "Voix (synthèse vocale)",
    providerLabel: "Moteur",
    modelLabel: "Modèle",
    modelPlaceholder: "Nom du modèle (ex. qwen3.8:27b)",
    modelHint: "Vide = valeur du fichier .env",
    baseModelLabel: "Modèle de clonage de voix",
    baseUrlLabel: "Adresse du serveur",
    baseUrlHint: "Vide = valeur du fichier .env",
    localeLabel: "Langue des voix",
    envDefault: "Défaut (.env)",
    saveButton: "Enregistrer",
    savingButton: "Enregistrement…",
    savedToast: "Réglages enregistrés",
    refreshList: "Actualiser la liste",
    listError: (detail) => `Liste indisponible : ${detail}`,
    effectiveModel: (model) => `Modèle utilisé : ${model}`,
    testButton: "Tester la connexion",
    testingButton: "Test…",
    pluginErrorsTitle: "Plugins non chargés",
    pluginHint: "Ajoutez vos propres moteurs dans le dossier plugins/ (voir docs/PLUGINS.md).",
    presetsTitle: "Profil rapide",
    presetLocal: "100 % local",
    presetCloud: "Rapide (cloud)",
    presetLocalNote: "Rien ne quitte votre machine.",
    presetCloudNote: "Le texte du livre est envoyé à Google et Microsoft.",
    freeGpu: "Libérer la mémoire GPU",
    freeGpuDone: "Déchargement demandé au worker",
  },
  flow: {
    stepAnalysis: "Analyse",
    stepCasting: "Casting",
    stepGeneration: "Génération",
    stepListen: "Écoute",
    generateBook: "Générer le livre audio",
    regenerate: "Régénérer",
    resume: "Reprendre",
    restart: "Recommencer à zéro",
    listen: "Écouter",
    resumeListening: (chapter, time) => `Reprendre · ${chapter}, ${time}`,
    more: "Plus d'actions",
    details: "Détails du livre",
    download: "Télécharger",
    downloadM4b: "Livre audio (M4B, chapitres)",
    downloadMp3: "MP3",
    m4bMissing: "M4B indisponible (ffmpeg absent à la génération)",
    stageAnalysis: "Analyse",
    stageGeneration: "Génération",
    stageAssembly: "Assemblage",
    chapterProgress: (current, total) => `chapitre ${current}/${total}`,
    etaLessThanMinute: "moins d'une minute restante",
    etaMinutes: (minutes) => `environ ${minutes} min restantes`,
    etaHours: (hours, minutes) => `environ ${hours} h ${minutes} min restantes`,
    includeChapter: "Inclure ce chapitre",
    excludeChapter: "Exclure ce chapitre (page non narrative)",
    chapterExcluded: "Exclu",
    voiceSaved: (character, voice) => `Voix de ${character} : ${voice}`,
    previewOnLine: "Écouter sur une réplique du personnage",
    previewLoading: "Génération de l'aperçu…",
    previewFailed: "Aperçu indisponible",
    privacyCloudLlm: "L'analyse envoie le texte du livre à Google (Gemini).",
    privacyCloudTts: "La synthèse envoie le texte du livre à Microsoft (EdgeTTS).",
    languageAuto: "Auto",
    languageFr: "Français",
    languageEn: "Anglais",
  },
  feedback: {
    confirm: "Confirmer",
    cancel: "Annuler",
    undo: "Annuler",
    close: "Fermer",
    bookDeleted: (title) => `« ${title} » supprimé`,
    deleteConfirmTitle: "Supprimer ce livre ?",
  },
  player2: {
    sleepLabel: "Minuterie",
    sleepOff: "Désactivée",
    sleepEndOfChapter: "Fin du chapitre",
    sleepMinutes: (minutes) => `${minutes} min`,
    sleepRemaining: (mmss) => `Veille dans ${mmss}`,
    shortcutsHint: "Espace : lecture · ← → : −15 s / +30 s · [ ] : vitesse",
  },
  library2: {
    filters: "Filtres",
    filtersActive: (count) => `Filtres (${count})`,
    resetFilters: "Réinitialiser",
    importEpub: "Importer un EPUB",
    dropOverlay: "Déposez votre EPUB pour l'importer",
    continueListening: "Reprendre l'écoute",
    generationBadge: (count) => `${count} en cours`,
  },
  voices2: {
    referenceTextLabel: "Transcription de l'échantillon (facultatif)",
    referenceTextPlaceholder: "Ce qui est dit dans l'enregistrement, mot pour mot",
    referenceTextHint:
      "Avec la transcription, le clonage reproduit aussi la manière de parler (Qwen3-TTS) ; sans, seul le timbre est copié.",
  },
  production: {
    excerpt: "Extrait",
    excerptTitle: "Écouter environ une minute du début, rendue comme le chapitre final, avant de lancer le rendu complet",
    excerptLoading: "Rendu de l'extrait…",
    acxCheck: "ACX",
    acxTitle: (rms, peak) => `RMS ${rms} dBFS · crête ${peak} dBFS (ACX : RMS -23 à -18, crête ≤ -3)`,
    acxOk: "Conforme ACX",
    acxKo: "Non conforme ACX",
    downloadChaptersTxt: "Horodatage des chapitres (.txt)",
    lexiconTitle: "Lexique de prononciation",
    lexiconGlobalTitle: "Lexique de prononciation (tous les livres)",
    lexiconHint:
      "Remplace un mot dans le texte envoyé à la voix de synthèse, jamais dans le texte affiché : noms propres, mots étrangers, sigles (« SNCF » → « S N C F »), abréviations (« M. » → « Monsieur »). Une entrée du livre prime sur l'entrée globale du même mot.",
    lexiconTerm: "Mot ou expression",
    lexiconReplacement: "Se prononce",
    lexiconWholeWord: "Mot entier",
    lexiconCaseSensitive: "Respecter la casse",
    lexiconAdd: "Ajouter",
    lexiconEmpty: "Aucune entrée.",
    lexiconGlobalBadge: "global",
    lexiconTest: "Tester",
    lexiconTestPlaceholder: "Une phrase du livre…",
    lexiconSpoken: "Prononcé :",
    designVoice: "Voix conçue",
    designVoiceTitle: "Concevoir une voix propre à ce personnage (OmniVoice), gardée tout le livre",
    designPromptLabel: "Description de la voix",
    designPromptHint:
      "Déduite de la fiche du personnage. Une valeur par catégorie : genre (male, female), âge (child, teenager, young adult, middle-aged, elderly), hauteur (very low … very high pitch) ou whisper. La voix est conçue une fois puis clonée à chaque réplique : elle reste la même tout le livre. Moteur OmniVoice requis (poids CC-BY-NC : usage non commercial).",
    designLaunch: "Concevoir",
    designRunning: "Conception…",
    designDone: "Voix conçue et attribuée",
    designNeedsServer: "Le serveur OmniVoice ne répond pas (scripts/omnivoice_server.py).",
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
    voiceSample: (detail) => `Voice preview failed: ${detail}`,
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
    deleteConfirm: (title) => `Delete "${title}"?`,
    deleteAriaLabel: "Delete",
  },
  upload: {
    invalidFile: "Only .epub files are accepted.",
    uploading: "Uploading…",
    dropHint: "Drop an EPUB here",
    clickHint: "or click to choose an .epub file",
  },
  player: {
    narrator: "Narrator",
    transcript: {
      title: (position) => `Transcript — Chapter ${position}`,
      loading: "Loading transcript…",
      empty: "No segment available for this chapter.",
      syncUnavailable: "Sync unavailable — regenerate this chapter",
      seekAriaLabel: (label) => `Jump to this passage — ${label}`,
    },
    progressAriaLabel: "Progress",
    prevChapterAriaLabel: "Previous chapter",
    rewind15AriaLabel: "Rewind 15 seconds",
    pauseAriaLabel: "Pause",
    playAriaLabel: "Play",
    forward15AriaLabel: "Forward 15 seconds",
    nextChapterAriaLabel: "Next chapter",
    rateAriaLabel: "Change playback speed",
    rateLabel: "Speed",
    showChaptersAriaLabel: "Show chapters",
    hideChaptersAriaLabel: "Hide chapters",
    chaptersLabel: "Chapters",
    bookmarkAriaLabel: "Bookmark (coming soon)",
    bookmarkTitle: "Bookmark — coming soon",
    bookmarkLabel: "Bookmark",
    rateSelectAriaLabel: "Playback speed",
    readByLabel: "Read by",
    closePlayerAriaLabel: "Close player",
    audioError: "Playback error",
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
      "Used when no engine is chosen for this book (Casting page) — otherwise, " +
      "the per-book override still takes priority.",
    preferredLanguageLabel: "Preferred language (detection fallback)",
    languageOptionNone: "None (historical fallback: French)",
    languageNames: { fr: "Français", en: "English" },
    preferredLanguageHint:
      "Only used when a book's language can't be detected at import time — never " +
      "affects a book that was already identified or manually edited. Distinct from " +
      "the UI display language (selector at the top of the screen).",
    clonedVoicesLabel: "Cloned voices",
    clonedVoicesAvailable: (n) => `${n} cloned voice${n > 1 ? "s" : ""} available`,
    clonedVoicesNone: "No cloned voice",
    clonedVoicesHintAvailable: "Usable with Qwen3-TTS only — assigned as priority during analysis.",
    clonedVoicesHintNone: "Add voices from the Voices tab to enable cloning.",
    preferredLlmLabel: "Preferred LLM engine",
    preferredLlmHint: "Determines which model analyses your texts each run. Applied at the next analysis launch.",
    privacyBadgeLocal: "🔒 Local — no data sent",
    privacyBadgeCloud: "☁️ Cloud — texts sent to Google",
    testConnection: "Test connection",
    testConnectionTesting: "Testing…",
  },
  book: {
    backToLibrary: "← Library",
    errorTitle: "Error",
    coverAlt: (title) => `Cover of ${title}`,
    languageUnsupported: (language) =>
      `${language} — not supported by the current engine: audio will fall back to the French profile`,
    genrePlaceholder: "Genre (e.g. Fantasy)",
    genreAriaLabel: "Book genre",
    languagePlaceholder: "Language (e.g. en)",
    languageAriaLabel: "Book language",
    publishedAtLabel: "Publication date",
    analysisInProgressHint: "Analysis in progress — casting will open automatically.",
    launching: "Starting…",
    analyze: "Analyse",
    resumeAnalysis: "Resume analysis",
    analysisFailedAriaLabel: "Analysis failed due to an error",
    analysisFailedTitle: (detail) => `Failed: ${detail}`,
    reanalyze: "Re-analyse",
    reanalyzeConfirm:
      "Re-analysing this book will erase existing characters, segments and merge suggestions. Continue?",
    generateAudio: "Generate audio",
    resumeGeneration: "Resume generation",
    regenerateAudio: "Regenerate audio",
    regenerateAudioConfirm: "Regenerating audio will erase the existing export. Continue?",
    stopping: "Stopping…",
    stop: "Stop",
    stopConfirm: "Stop the current task? The book will be marked as failed.",
    casting: "Casting",
    listen: "Listen",
    loadingCasting: "Loading casting…",
    castingUnavailableTitle: "Casting unavailable",
    castingUnavailableBody: (status) =>
      `Casting is only available once the book is analysed (current status: ${status}).`,
    mergeSuggestionsTitle: "Suggested character merges",
    acceptAll: "Accept all",
    accept: "Accept",
    reject: "Reject",
    noCharactersDetected: "No character detected.",
    searchCharacterPlaceholder: "Search for a character…",
    noCharacterMatches: "No character matches.",
    secondaryCharacters: (n) => `Secondary characters with no lines (${n})`,
    localeKnown: (locale) => `Language: ${locale}`,
    localeUnknown: "Language: depends on the TTS provider",
    engineLabel: "Engine:",
    defaultProvider: (name) => `Default (${name})`,
    generateOnlyWhenAnalyzed: "Generation only possible once the book is ANALYZED",
    segmentCount: (n) => `${n} line${n > 1 ? "s" : ""}`,
    clonedVoiceIncompatible: (provider) =>
      `Engine "${provider}" cannot clone: a catalogue voice of the same gender will be used. Switch to Qwen or OmniVoice for this voice.`,
    clonedBadge: "Clone",
    chooseVoice: "Choose…",
    clonedVoicesGroup: "— Cloned voices —",
    previewVoice: "Listen to a preview of this voice",
    previewTitle: (id) => `Preview — ${id}`,
    confirmVoice: "Confirm this voice",
    chaptersTitle: (n) => `Chapters (${n})`,
    generateAllAudio: "Generate all audio",
    noChaptersYet: "No chapters yet.",
    chapterFallback: (position) => `Chapter ${position}`,
    generateChapter: "Generate",
    regenerateChapter: "Regenerate this chapter",
  },
  voices: {
    title: "Voices",
    searchPlaceholder: "Search by name…",
    searchAriaLabel: "Search for a voice",
    genderFilterAriaLabel: "Filter by gender",
    allGenders: "All genders",
    genderLabels: {
      MALE: "Male",
      FEMALE: "Female",
      NEUTRAL: "Neutral",
    },
    kindFilterAriaLabel: "Filter by type",
    allKinds: "All types",
    catalogueKind: "Catalogue",
    clonedKind: "Cloned",
    sampleFilterAriaLabel: "Filter by preview",
    allSamples: "All previews",
    sampleAvailable: "Preview available",
    sampleMissing: "No preview",
    favoritesOnly: "★ Favourites",
    cancelClone: "✕ Cancel",
    startClone: "+ Clone a voice",
    subtitle: "The catalogue of available voices. Click a circle to hear a preview.",
    cloneFormTitle: "Clone a voice",
    nameLabel: "Name *",
    namePlaceholder: "e.g. Patrick Baud",
    genderLabel: "Gender",
    genderUnspecified: "— Unspecified —",
    referenceAudioLabel: "Reference audio * (MP3 / WAV / FLAC)",
    chooseFile: "Choose a file…",
    creating: "Creating…",
    createClonedVoice: "Create cloned voice",
    nameRequired: "Name is required.",
    referenceAudioRequired: "A reference audio file is required.",
    apiUnreachableTitle: "Cannot reach the API",
    noMatchTitle: "No voice matches",
    noneAvailableTitle: "No voice available",
    noMatchHint: "Try widening the filters above.",
    catalogueEmptyHint: "The voice catalogue is empty.",
    deleteClonedConfirm: (name) => `Delete voice "${name}"? This action is irreversible.`,
    deleteCatalogueConfirm: (name) =>
      `Remove "${name}" from the catalogue? It will be restored on the next server restart.`,
    generateSampleAriaLabel: (name) => `Generate a preview for ${name}`,
    sampleUnavailableTitle: "Sample not available — click to generate",
    previewAriaLabel: (name) => `Listen to a preview of ${name}`,
    removeFavorite: "Remove from favourites",
    addFavorite: "Add to favourites",
    deleteVoiceAriaLabel: (name) => `Delete voice ${name}`,
    deleteClonedTitle: "Delete this cloned voice",
    removeFromCatalogueTitle: "Remove from catalogue",
    clonedBadge: "🎙 cloned",
  },
  models: {
    sectionTitle: "Models",
    sectionHint:
      "Pick the engine and the model. The list shows what is installed, but you can type any name: a model missing from the list works as long as the engine serves it.",
    llmTitle: "Text analysis (LLM)",
    ttsTitle: "Voices (text-to-speech)",
    providerLabel: "Engine",
    modelLabel: "Model",
    modelPlaceholder: "Model name (e.g. qwen3.8:27b)",
    modelHint: "Empty = value from the .env file",
    baseModelLabel: "Voice-cloning model",
    baseUrlLabel: "Server address",
    baseUrlHint: "Empty = value from the .env file",
    localeLabel: "Voice language",
    envDefault: "Default (.env)",
    saveButton: "Save",
    savingButton: "Saving…",
    savedToast: "Settings saved",
    refreshList: "Refresh list",
    listError: (detail) => `List unavailable: ${detail}`,
    effectiveModel: (model) => `Model in use: ${model}`,
    testButton: "Test connection",
    testingButton: "Testing…",
    pluginErrorsTitle: "Plugins that failed to load",
    pluginHint: "Add your own engines in the plugins/ folder (see docs/PLUGINS.md).",
    presetsTitle: "Quick profile",
    presetLocal: "100% local",
    presetCloud: "Fast (cloud)",
    presetLocalNote: "Nothing leaves your machine.",
    presetCloudNote: "The book's text is sent to Google and Microsoft.",
    freeGpu: "Free GPU memory",
    freeGpuDone: "Unload requested from the worker",
  },
  flow: {
    stepAnalysis: "Analysis",
    stepCasting: "Casting",
    stepGeneration: "Generation",
    stepListen: "Listen",
    generateBook: "Generate the audiobook",
    regenerate: "Regenerate",
    resume: "Resume",
    restart: "Start over",
    listen: "Listen",
    resumeListening: (chapter, time) => `Resume · ${chapter}, ${time}`,
    more: "More actions",
    details: "Book details",
    download: "Download",
    downloadM4b: "Audiobook (M4B, chapters)",
    downloadMp3: "MP3",
    m4bMissing: "M4B unavailable (ffmpeg was missing at generation)",
    stageAnalysis: "Analysis",
    stageGeneration: "Generation",
    stageAssembly: "Assembly",
    chapterProgress: (current, total) => `chapter ${current}/${total}`,
    etaLessThanMinute: "less than a minute left",
    etaMinutes: (minutes) => `about ${minutes} min left`,
    etaHours: (hours, minutes) => `about ${hours} h ${minutes} min left`,
    includeChapter: "Include this chapter",
    excludeChapter: "Exclude this chapter (non-narrative page)",
    chapterExcluded: "Excluded",
    voiceSaved: (character, voice) => `${character}'s voice: ${voice}`,
    previewOnLine: "Listen on one of the character's lines",
    previewLoading: "Generating the preview…",
    previewFailed: "Preview unavailable",
    privacyCloudLlm: "Analysis sends the book's text to Google (Gemini).",
    privacyCloudTts: "Synthesis sends the book's text to Microsoft (EdgeTTS).",
    languageAuto: "Auto",
    languageFr: "French",
    languageEn: "English",
  },
  feedback: {
    confirm: "Confirm",
    cancel: "Cancel",
    undo: "Undo",
    close: "Close",
    bookDeleted: (title) => `"${title}" deleted`,
    deleteConfirmTitle: "Delete this book?",
  },
  player2: {
    sleepLabel: "Sleep timer",
    sleepOff: "Off",
    sleepEndOfChapter: "End of chapter",
    sleepMinutes: (minutes) => `${minutes} min`,
    sleepRemaining: (mmss) => `Sleeping in ${mmss}`,
    shortcutsHint: "Space: play · ← →: −15 s / +30 s · [ ]: speed",
  },
  library2: {
    filters: "Filters",
    filtersActive: (count) => `Filters (${count})`,
    resetFilters: "Reset",
    importEpub: "Import an EPUB",
    dropOverlay: "Drop your EPUB to import it",
    continueListening: "Continue listening",
    generationBadge: (count) => `${count} running`,
  },
  voices2: {
    referenceTextLabel: "Sample transcript (optional)",
    referenceTextPlaceholder: "What is said in the recording, word for word",
    referenceTextHint:
      "With the transcript, cloning also reproduces the speaking style (Qwen3-TTS); without it, only the timbre is copied.",
  },
  production: {
    excerpt: "Excerpt",
    excerptTitle: "Listen to about one minute of the beginning, rendered like the final chapter, before the full render",
    excerptLoading: "Rendering excerpt…",
    acxCheck: "ACX",
    acxTitle: (rms, peak) => `RMS ${rms} dBFS · peak ${peak} dBFS (ACX: RMS -23 to -18, peak ≤ -3)`,
    acxOk: "ACX compliant",
    acxKo: "Not ACX compliant",
    downloadChaptersTxt: "Chapter timestamps (.txt)",
    lexiconTitle: "Pronunciation lexicon",
    lexiconGlobalTitle: "Pronunciation lexicon (all books)",
    lexiconHint:
      "Replaces a word in the text sent to the synthetic voice, never in the displayed text: proper names, foreign words, acronyms, abbreviations. A book entry overrides the global entry for the same word.",
    lexiconTerm: "Word or phrase",
    lexiconReplacement: "Pronounced",
    lexiconWholeWord: "Whole word",
    lexiconCaseSensitive: "Match case",
    lexiconAdd: "Add",
    lexiconEmpty: "No entries.",
    lexiconGlobalBadge: "global",
    lexiconTest: "Test",
    lexiconTestPlaceholder: "A sentence from the book…",
    lexiconSpoken: "Spoken:",
    designVoice: "Designed voice",
    designVoiceTitle: "Design a voice of its own for this character (OmniVoice), kept for the whole book",
    designPromptLabel: "Voice description",
    designPromptHint:
      "Derived from the character sheet. One value per category: gender (male, female), age (child, teenager, young adult, middle-aged, elderly), pitch (very low … very high pitch) or whisper. The voice is designed once then cloned for every line, so it stays the same throughout the book. Requires the OmniVoice engine (CC-BY-NC weights: non-commercial use).",
    designLaunch: "Design",
    designRunning: "Designing…",
    designDone: "Voice designed and assigned",
    designNeedsServer: "The OmniVoice server is not responding (scripts/omnivoice_server.py).",
  },
};

export const translations: Record<Locale, Dictionary> = { fr, en };

// Lecture directe (hors React) pour du code impératif comme lib/api.ts, qui
// n'a pas accès aux hooks -- même clé que LanguageContext.tsx.
export function getStoredLocale(): Locale {
  if (typeof window === "undefined") return "fr";
  return localStorage.getItem(LOCALE_STORAGE_KEY) === "en" ? "en" : "fr";
}
