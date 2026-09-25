# TASKS

État courant et feuille de route. Le journal détaillé (2 600 lignes, jusqu'au 2026-09-25) est archivé
dans [docs/journal/2026.md](docs/journal/2026.md) ; ce qui est livré est dans [CHANGELOG.md](CHANGELOG.md).

## Maintenant

- **Valider à l'oreille les moteurs TTS** sur du français avec `python scripts/bench_tts.py` :
  Qwen3-TTS (référence actuelle), Chatterbox Multilingual (esquisse `plugins/tts/_example_chatterbox.py`),
  Fish Audio S2 Pro, Higgs Audio v3. Consigner le verdict ici.
- **Comparer des LLM** sur ses propres livres avec `python scripts/bench_llm.py` (taux d'attribution,
  temps, VRAM) : `qwen3:1.7b` (référence 79 % / ~9 min sur un Harry Potter complet), un Qwen 3.x plus
  gros quantifié, `gemini-3.1-flash-lite`.
- **PyTorch ROCm sur la RX 9070 XT** : vérifier `python scripts/doctor.py` (GPU visible via ROCm) puis un
  chapitre réel avec `TTS_PROVIDER=qwen`.
- **Vérifier le frontend en conditions réelles** : `npm run lint` et `npm run build` (le lot UX de
  l'audit du 2026-09-25 a été écrit sans pouvoir compiler — voir CHANGELOG).

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
- Vrai temps réel (streaming) de la lecture pendant la génération.

## Problèmes connus

- Python 3.14 : non supporté (dépendances épinglées sans roue).
- Le lot frontend du 2026-09-25 n'a pas été compilé (proxy npm indisponible dans l'environnement de
  développement) : corriger d'éventuelles erreurs de type / lint au premier `npm run build`.

## Conventions

- Numéros de suites : le prochain est `check_phase49.py`. Réserver le numéro ici avant de créer une suite
  (une branche a déjà produit un `check_phase39.py` différent de celui de `main`).
- Toute variable d'environnement nouvelle est documentée dans `.env.example`.
