# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/). L'historique fin d'avant cette date
est dans [docs/journal/2026.md](docs/journal/2026.md).

## [Unreleased] — production d'audiolivre (2026-09-26 → 2026-09-28)

### Ajouté
- **Langues** : profils espagnol, allemand, italien (segmentation, voix EdgeTTS, Qwen) ; langues non prises
  en charge signalées ; rapport multilingue `SCRIPTVOX-NIGHT-REPORT.md` (`night_langues.py`).
- **Moteur OmniVoice** (serveur local ROCm) et **voix conçues par personnage** ; moteur `command` utilisable
  sous Windows ; banc `qwen_bench.py`.
- **Production** : mastering des chapitres aux exigences ACX + contrôle de conformité, extrait avant
  rendu, reprise par segment d'un chapitre interrompu, horodatage des chapitres (.txt), lexique de
  prononciation global et par livre, titres de navigation EPUB3 > NCX > intertitres, pages liminaires.
- Idées du comparatif VoiceStudio (`docs/COMPARATIF-VOICESTUDIO.md`).
- UI : refonte visuelle des orbes, pastille de langue sur les livres, contrôle ACX, lexique, voix conçue.
- `start-tailscale.ps1` (ébauche).

### Corrigé
- Incise espagnole (séparateur = tiret) ; un segment sans rien à prononcer ne fait plus échouer le chapitre.

## [Unreleased] — audit du 2026-09-25

### Corrigé
- **Régénérer un chapitre terminé ou en échec ne faisait rien** : il était mis en file mais la pompe ne
  traitait que les chapitres `PENDING`. Il repasse maintenant `PENDING` ; la génération par chapitre est
  acceptée pour un livre `DONE` / `FAILED`.
- **Attribution au hasard d'un nom partiel** (« Weasley » → Ron, Ginny ou Molly selon le lancement de
  Python) : la résolution est déterministe, refuse l'ambigu et les mots-titres seuls.
- Le lecteur **enchaîne les chapitres** ; le routeur `/models` est branché ; la sonde d'état suit la
  préférence TTS et vérifie réellement Gemini / le serveur / les paquets Qwen (`?deep=true`).
- Voix EdgeTTS françaises : plus aucun personnage ne parle avec la voix du narrateur.
- `gemini-2.0-flash` (arrêté le 2026-06-01) remplacé dans `.env.example`.

### Ajouté
- **Modèles interchangeables** : registre de providers + **plugins** (`plugins/llm`, `plugins/tts`),
  providers génériques `openai_compatible`, `openai_tts`, `command`, checkpoint Qwen libre, réglages à chaud
  du modèle / de l'adresse dans *Paramètres* (n'importe quel nom accepté), liste des modèles installés.
  Guide : `docs/PLUGINS.md`.
- **Export M4B chapitré + couverture** (ffmpeg), téléchargement MP3 / M4B.
- **Audio** : format unique 24 kHz (fin de la dépendance à `audioop`), pauses entre répliques et chapitres,
  niveau sonore homogène, découpage des longs textes, concurrence pour les moteurs cloud, conversion
  automatique de tout format de sortie TTS.
- Modèle TTS **gardé en mémoire** d'un chapitre à l'autre (avant : rechargé à chaque chapitre), déchargé à
  l'inactivité / sur demande ; LLM local déchargé après l'analyse.
- Génération de livre **par la file de chapitres** (une tâche Huey par chapitre : les tâches courtes passent
  entre deux) ; progression par étape avec **temps restant** ; chapitres non narratifs détectés et
  excluables ; titres de chapitres issus de la table des matières EPUB.
- Aperçu d'une voix **sur une réplique du personnage** ; clonage avec transcription de l'échantillon.
- Frontend : parcours en étapes, une action principale par état, casting enregistré immédiatement, reprise de
  lecture, Media Session, raccourcis clavier, minuterie de sommeil, filtres repliés, dépôt de fichier
  partout, confirmations et annulations par toasts, police d'affichage, build de production par défaut.
- Sécurité : garde anti cross-site, `TrustedHost`, CORS restreint, contrôle des bombes de décompression
  EPUB, SQLite en WAL. `SECURITY.md`.
- Outils : `scripts/bench_llm.py`, `scripts/bench_tts.py`, `tests/run_all.py`, `scripts/doctor.py` étendu
  (ffmpeg, GPU ROCm/CUDA, providers génériques, plugins).
- CI : toutes les suites de tests, Python 3.11 – 3.13, lint, audit des dépendances ; Dependabot.

### Modifié
- Attribution des voix : les personnages les plus importants choisissent d'abord.
- `EDGETTS_LOCALE` par défaut `fr-FR` ; frontend et API liés à `127.0.0.1`.
- README, ARCHITECTURE et TASKS réécrits ; l'ancien journal archivé dans `docs/journal/`.

### Migration
- Nouvelle migration Alembic `a1c3e5f70912` (appliquée automatiquement au démarrage). Les chapitres déjà
  générés à 22 050 Hz restent lisibles et sont convertis à l'assemblage du livre.
