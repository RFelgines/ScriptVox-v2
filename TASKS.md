# TASKS

État courant et feuille de route. Le journal détaillé (2 600 lignes, jusqu'au 2026-09-25) est archivé
dans [docs/journal/2026.md](docs/journal/2026.md) ; ce qui est livré est dans [CHANGELOG.md](CHANGELOG.md).

## Maintenant

- **Écouter les sorties de la branche `feat/audiobook-production`** (jamais validées à l'oreille) : moteur
  OmniVoice (serveur ROCm local) et voix conçues par personnage, mastering ACX + contrôle de conformité,
  extrait avant rendu, reprise par segment, lexique de prononciation. Échantillons multilingues
  (EdgeTTS) du 2026-09-28 : `C:\Users\romai\Documents\ScriptVox-nuit-audio\` (rapport :
  `SCRIPTVOX-NIGHT-REPORT.md`). Consigner le verdict ici.
- **Décider de la fusion** de `feat/audiobook-production` dans `main` (11 commits d'avance) ; `main`
  porte 6 commits de langues (es / de / it) poussés le 2026-09-30.
- **Accès Tailscale** : `start-tailscale.ps1` (API sur `0.0.0.0`) est une ébauche non finie ; il reste
  `ALLOWED_HOSTS`, `FRONTEND_ORIGINS`, l'URL d'API du frontend (recompilation) et le pare-feu Windows.
- **Valider à l'oreille les moteurs TTS** sur du français avec `python scripts/bench_tts.py` :
  Qwen3-TTS (référence actuelle), Chatterbox Multilingual (esquisse `plugins/tts/_example_chatterbox.py`),
  Fish Audio S2 Pro, Higgs Audio v3. Consigner le verdict ici.
- **Bilan LLM du 2026-09-30** (`scripts/bench_llm_compare.py`, Harry Potter T1, 6 chapitres, 640 répliques,
  RX 9070 XT, Ollama 0.17.1) : 1.7b et 4b inutilisables pour l'attribution (24 à 70 % de répliques sans
  locuteur ; 19 à 42 % de bonnes réponses sur les 111 répliques dont l'incise nomme le locuteur, contre 91 %
  pour 8b et 14b). Temps : 1.7b 155-307 s (deux passages identiques, x2 d'écart), 4b 240 s, 8b 597 s,
  14b 627 s. `OLLAMA_NUM_PARALLEL=4` : débit total divisé par 4 (103 -> 24 tok/s) ; 2 à 3 instances Ollama
  séparées du 1.7b : x1,1 à x1,4 seulement. 14b-Q6 non mesuré (22 % sur CPU avec 20 k de contexte).
  Reste à faire : une vérité terrain étiquetée à la main sur les répliques sans incise (8b et 14b ne
  s'accordent qu'à 55 % dessus, on ne sait pas lequel a raison) ; passages répétés pour la variabilité.
- **Comparer des LLM** sur ses propres livres avec `python scripts/bench_llm.py` (taux d'attribution,
  temps, VRAM) : `qwen3:1.7b` (référence 79 % / ~9 min sur un Harry Potter complet), un Qwen 3.x plus
  gros quantifié, `gemini-3.1-flash-lite`.
- **PyTorch ROCm sur la RX 9070 XT** : vérifier `python scripts/doctor.py` (GPU visible via ROCm) puis un
  chapitre réel avec `TTS_PROVIDER=qwen`.
- **Tester sur la vraie machine** (RX 9070 XT, vrais modèles) tout ce que l'audit du 2026-09-25 n'a pu
  valider qu'avec des faux moteurs : Media Session sur téléphone, écoute réelle des voix, clonage avec
  transcription, déchargement VRAM réel.

## Ensuite

- Clonage « complet » Qwen3-TTS : valider à l'oreille `ref_text` + prompt de clonage réutilisé
  (API `qwen-tts` non testée avec le vrai modèle).
- Voice Design (Qwen3-TTS `VoiceDesign`) : créer une voix de personnage à partir de sa description
  (`voice_tone` / `voice_quality` / âge / genre déjà extraits par le LLM).
- Analyse en deux passes (casting complet du livre, puis attribution) quand le contexte le permet.
- Stockage : ne plus écrire une prise WAV par segment à chaque génération (extraction à la demande depuis
  le WAV du chapitre) ; supprimer `book.wav` après le MP3/M4B.
- Transcription automatique (Whisper) de l'échantillon de clonage.
- Écoute depuis le téléphone (proxy même origine + jeton) — uniquement derrière une authentification.

## Plus tard

- Migration des suites `check_phaseN.py` vers `pytest`.
- Test navigateur automatisé (Playwright) dans la CI : le parcours upload → casting → génération → écoute a été
  validé à la main le 2026-09-25 (18 vérifications) mais le script n'est pas versionné.
- Vrai temps réel (streaming) de la lecture pendant la génération.

## Problèmes connus

- Python 3.14 : non supporté (dépendances épinglées sans roue).
- Validé le 2026-09-25 avec de FAUX moteurs (serveur LLM factice, plugin TTS « bip ») : `tsc --noEmit`
  (strict), `eslint`, `next build`, un test navigateur Chromium (upload → analyse → casting → génération →
  M4B → lecteur → réglages) et `scripts/e2e_smoke.py` (vrais processus API + worker). Jamais exécuté avec
  un vrai LLM, un vrai TTS local ni un GPU.

## Conventions

- Numéros de suites : le prochain est `check_phase52.py`. Réserver le numéro ici avant de créer une suite
  (une branche a déjà produit un `check_phase39.py` différent de celui de `main`).
- Toute variable d'environnement nouvelle est documentée dans `.env.example`.
