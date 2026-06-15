# TASKS.md — ScriptVox

## Fait

- Phase 1 : config fail-fast + modèles SQLModel (commit 9f9360c)
- Phase 2 : FastAPI skeleton, EPUB ingestion, Huey worker (commit 6e1b600)
- Phase 3 : pipeline LLM — BaseLLMProvider, Gemini, Ollama, token budgeting (commit 83b086b)
- CLAUDE.md — protocole de travail permanent (commit 6286920)
- **Phase TTS & audio (ARCHITECTURE.md § Phase 3) — COMPLÈTE :**
  - Sous-tâche 1 — Scaffold Strategy TTS + stubs + fail-fast ✅
  - Sous-tâche 2 — Catalogue de voix + service d'assignation ✅
  - Sous-tâche 3a — Config & variables d'env (PIPER_VOICES_DIR) ✅
  - Sous-tâche 3b — Schéma + assembleur audio (Book.audio_path, assemble_wav) ✅
  - Sous-tâche 3c — Implémentations TTS réelles (Piper lazy-import, ElevenLabs httpx) ✅
  - Sous-tâche 3d — Câblage worker (_synthesise_book dans _process_book_impl) ✅
  - Sous-tâche 4 — Exposition API (GET /books/{id}/audio, audio_path dans BookResponse) ✅
    (test phase4 : 23/23 sections OK)

---

## À venir — Phase 5 : Run & Hardening

> **Constat de revue (2026-06-13).** Le code des 4 phases est complet et propre, mais le
> projet n'a jamais été exécuté de bout en bout. Cette phase rend ScriptVox réellement
> lançable (mode local Piper) puis durcit les points fragiles. Étapes ordonnées par
> valeur × faisabilité. **Une étape = un échange. Test-first. Attendre GO avant chaque étape.**

### Étape 1 — Fail-fast : valider l'existence du dossier `voices/` ✅

**Pourquoi.** `config.py` ne vérifie que la présence de la variable `PIPER_VOICES_DIR`,
pas que le dossier existe. ARCHITECTURE.md §2.4 : « never start in a silently degraded state ».

**Fichiers (≤5).**
- `app/config.py` — dans le bloc `if self.tts_provider == "piper":`, après `_require`,
  ajouter une validation : si `Path(self.piper_voices_dir)` n'est pas un dossier existant,
  `raise ValueError(f"PIPER_VOICES_DIR does not exist or is not a directory: {...}")`.
- `voices/.gitkeep` — **créer le dossier** (nouveau fichier vide), sinon l'étape casse les
  4 suites de tests existantes qui fixent `PIPER_VOICES_DIR=./voices`.
- `tests/check_phase4.py` — nouvelle section : ValueError quand `PIPER_VOICES_DIR` pointe
  vers un chemin inexistant ; pas d'erreur quand il pointe vers `./voices`.

**Dépendance critique.** `check_phase1/2/3/4.py` font tous `get_settings()` avec
`PIPER_VOICES_DIR=./voices`. Créer `voices/.gitkeep` AVANT de valider, puis relancer
**les 4 suites** (`check_phase1` → `check_phase4`) pour confirmer zéro régression.

**Contrat.** Non — pas de changement de signature ni de schéma.

---

### Étape 2 — README : démarrage, worker, voix, tests ✅

**Pourquoi.** Aucun README. Rien ne documente comment lancer l'app, le consumer Huey,
installer les voix Piper, ni faire correspondre `VOICE_CATALOGUE` aux fichiers `.onnx`.

**Fichiers (1).**
- `README.md` (nouveau) — sections :
  1. **Setup** : `python -m venv .venv`, `pip install -r requirements.txt`,
     copier `.env.example` → `.env`.
  2. **Lancement** : API = `uvicorn app.main:app --reload` ;
     worker = `huey_consumer app.workers.tasks.huey` (les deux process en parallèle).
  3. **Voix Piper (CRITIQUE)** : `PiperProvider` charge `{PIPER_VOICES_DIR}/{voice_id}.onnx`.
     `VOICE_CATALOGUE` exige donc ces fichiers exacts dans `voices/` :
     `narrator.onnx`, `male_0.onnx`, `male_1.onnx`, `male_2.onnx`,
     `female_0.onnx`, `female_1.onnx`, `female_2.onnx`, `neutral_0.onnx`, `neutral_1.onnx`
     (+ les `.onnx.json` associés). Expliquer : télécharger des voix sur
     huggingface.co/rhasspy/piper-voices et les **renommer** selon ces IDs.
  4. **Tests** : `.venv/Scripts/python tests/check_phaseN.py` (N = 1..4).
  5. **Flux API** : `POST /books` (upload .epub) → polling `GET /books/{id}` →
     `GET /books/{id}/audio` quand `status=DONE`.

**Contrat.** Non — documentation pure, zéro risque.

---

### Étape 3 — Garde-fou format WAV dans l'assembleur ✅

**Pourquoi.** `assemble_wav` lit (nchannels, sampwidth, framerate) du **1er segment seulement**
et concatène les suivants sans vérifier. Deux voix à sample-rates différents (Piper natif vs
ElevenLabs 22050) → audio à vitesse faussée, silencieusement.

**Fichiers (2).**
- `app/services/audio/assembler.py` — avant `out.writeframes`, comparer les params de chaque
  segment à ceux du 1er ; si différents,
  `raise ValueError(f"WAV format mismatch at segment {i}: ...")`.
- `tests/check_phase4.py` — nouvelle section : 2 segments de framerates différents (ex. 22050
  et 16000) → ValueError ; happy path inchangé (section 19 doit toujours passer).

**Contrat.** Non — `assemble_wav` garde sa signature.

---

### Étape 4 — Test d'intégration bout-en-bout du pipeline worker ✅

**Pourquoi.** Aucun test ne valide `_process_book_impl` en entier. `check_phase3` mocke
`_synthesise_book` ; `check_phase4` teste `_synthesise_book` isolé. Les coutures
EPUB → LLM → voix → TTS → audio ne sont jamais testées ensemble.

**Fichiers (1).**
- `tests/check_phase5.py` (nouveau) — appeler `_process_book_impl(book_id)` sur
  `tests/fixtures/test.epub` avec **deux mocks** :
  - LLM : patcher `get_llm_provider` pour renvoyer un provider dont `analyze` retourne
    un petit `LLMChapterResult` (1-2 personnages, quelques segments NARRATION + DIALOGUE).
  - TTS : patcher `get_tts_provider` pour renvoyer un mock dont `synthesise` retourne un
    WAV minuscule (réutiliser le helper `_make_wav_bytes` de check_phase4).
  - Utiliser un engine SQLite (`StaticPool` mémoire ou fichier temp) injecté via
    `app.core.db.get_engine` (patcher) pour que le worker et le test partagent la base.
  - Asserts : `Book.status == DONE`, `progress == 100.0`, `audio_path` non nul + fichier WAV
    valide sur disque, tous les `Character.voice_id` peuplés.
  - Couvrir aussi le chemin d'échec : si `synthesise` lève `TTSError`, `Book.status == FAILED`
    et `error_message` renseigné.

**Contrat.** Non — test uniquement.

---

### Étape 5 — Polish (optionnelle, basse priorité) ✅

**Pourquoi.** Confort et exactitude, pas bloquant.

**Fichiers (≤3).**
- `.env.example` — `GEMINI_MODEL=gemini-1.5-pro` → un modèle courant (ex. `gemini-2.0-flash`).
- `app/api/routes/books.py` + `app/schemas/book.py` — exposer un résumé d'analyse
  (ex. `chapter_count`, `character_count` dans `BookResponse`, ou un endpoint
  `GET /books/{id}/characters`).

**⚠️ Contrat — REVUE HUMAINE OBLIGATOIRE.** Toute modification de `BookResponse` (schéma
Pydantic) se propage. Montrer le nouveau schéma et attendre validation AVANT implémentation
(CLAUDE.md Niveau 3).

---

### Étape 6 — Pivot Piper pip → binaire + 1er run réel ✅ (2026-06-14, commit 07aff3e)

**Constat.** Au premier lancement bout-en-bout réel, `piper-tts` s'avère impossible à
installer sous Windows (`piper-phonemize` sans wheel). Pivot vers le binaire `piper.exe`
appelé en subprocess.

- `app/services/tts/piper.py` — réécrit en subprocess (`--model`, `--output_file`, stdin=texte).
- `app/config.py` — nouvelle var `PIPER_BINARY_PATH`, validée comme fichier existant.
- `requirements.txt` — `piper-tts` retiré (plus importé).
- `.gitignore` — exclut `piper/`, `voices/*` (sauf `.gitkeep`), `*.db-shm/-wal`.
- `README.md` — download binaire + nommage `.onnx.json`.
- 5 suites de tests mises à jour (`PIPER_BINARY_PATH`) + 2 sections fail-fast (check_phase4).

**Run réel validé** : EPUB Alice → Ollama `qwen3:8b` → 2 personnages → Piper → WAV 47,9 s.
`GET /books/{id}/audio` et `GET /books/{id}/characters` OK. **App utilisable en local.**

---

---

## Phase 6 — Audio par chapitre ✅ (terminée)

### Étape 1 — `GET /books/{id}/chapters/{n}/audio` ✅ (2026-06-14)

**Livré.** Endpoint `GET /books/{book_id}/chapters/{position}/audio` (position 1-indexée),
synthèse à la volée → `audio/wav`. Codes : 404 book / 409 book non `DONE` / 404 chapitre
inexistant / 404 chapitre sans segment. Fichiers (4) :
- `app/services/audio/assembler.py` — cœur partagé `_assemble(segments, dest)` + nouveau
  `assemble_wav_bytes(list[bytes]) -> bytes` (`assemble_wav` inchangé, garde-fou format centralisé).
- `app/services/audio/chapter.py` (nouveau) — `async synthesise_chapter(chapter_id, session, tts) -> bytes`
  (`ValueError` si aucun segment). **Déviation assumée** : signature par `chapter_id` (la route
  résout déjà le chapitre → 404), pas par `(book_id, position)`. `_synthesise_book` non touché.
- `app/api/routes/books.py` — endpoint `async get_chapter_audio`.
- `tests/check_phase6.py` (nouveau) — 8 sections vertes ; 5 suites existantes sans régression.

**Pourquoi.** Le pipeline génère un WAV du livre entier (30-90 min pour un roman). Un
endpoint par chapitre permet de tester rapidement, d'écouter au fil de l'analyse,
et d'ouvrir la voie à une parallélisation future.

---

## Roadmap V2 — parité fonctionnelle avec la V1

> **Contexte.** L'ancien repo `RFelgines/ScriptVox` (V1, abandonnée car trop buggée) est un
> **blueprint de features**, pas du code à reprendre (voir mémoire `old_repo_feature_reference.md`).
> Cette roadmap porte les **idées** de la V1 dans l'archi propre de la V2. Règles : **test-first,
> Plan-First, attendre GO avant chaque étape**. Le détail fichier-par-fichier se fait au moment du
> plan, PAS ici (cette roadmap fixe le quoi et l'ordre, pas le comment).

### ⚖️ Décisions tranchées (2026-06-14)

- **D1 ✅ — EdgeTTS devient le moteur TTS par défaut.** Nouveau provider EdgeTTS (gratuit, sans GPU,
  sans clé, multilingue) dans le pattern Strategy ; Piper = option 100 % offline, ElevenLabs = premium.
  **Implémenté (2026-06-15)** — stratégie MP3→WAV choisie : `miniaudio` décode le MP3 en PCM dans le
  provider, `_pcm_to_wav` (stdlib `wave`) produit du WAV 22050 Hz mono 16-bit compatible avec l'assembleur.
  Zéro changement à la couche audio (Phase 10 toujours différée).

  - **D1a ✅** Scaffold : `edgetts` dans `_VALID_TTS`, `EdgeTTSProvider` (stub), `_VOICE_MAP` en-US/fr-FR,
    factory câblée, `.env.example` mis à jour. `check_phase8.py` sections 1-7.
  - **D1b ✅** Implémentation : `edge-tts~=6.1` + `miniaudio~=1.2` dans `requirements.txt`,
    `synthesise` réelle (stream MP3 → decode → WAV). `check_phase8.py` sections 8-11 (offline, mocks).
  - **D1c ✅** Doc : README section EdgeTTS, table config mise à jour, API reference Phase 7, tests à jour.
    `TASKS.md` + mémoire mis à jour. `TTS_PROVIDER=edgetts` est le nouveau défaut dans `.env.example`.
- **D2 ✅ — Le pipeline sera découplé.** Upload = parse + analyse seulement ; la génération audio
  devient une étape explicite déclenchée après le casting. Change `BookStatus` (contrat). → Phase 7.

### Phase 7 — Découplage du pipeline & déclencheurs de génération
**Pourquoi.** Laisser l'utilisateur ajuster le casting AVANT la synthèse (longue). Meilleure UX,
économise du calcul. *Dépend de D2.*

- Étape 1 ✅ (2026-06-14) — Pipeline découplé. Nouveaux statuts `ANALYZED` et `GENERATING` dans
  `BookStatus`. Worker splitté : `_analyze_book_impl` (EPUB + LLM + voix → `ANALYZED`) +
  `_generate_book_impl` (TTS → `DONE`). `_process_book_impl` conservé comme chaîne pour
  rétrocompabilité des tests. Tasks Huey : `analyze_book`, `generate_book`. `POST /books`
  déclenche désormais `analyze_book` (plus `process_book`). Garde de `GET /books/{id}/chapters/{n}/audio`
  relâchée à `{ANALYZED, GENERATING, DONE}`. `ARCHITECTURE.md §2.6` mis à jour.
  `tests/check_phase7.py` — 10 sections OK. Zéro régression sur les 6 suites existantes.
  Fichiers (6) : `app/core/enums.py`, `app/workers/tasks.py`, `app/api/routes/books.py`,
  `ARCHITECTURE.md`, `tests/check_phase7.py`, `tests/check_phase2.py`.

- Étape 2 ✅ (2026-06-14) — `POST /books/{id}/generate` : dispatch `generate_book` Huey.
  Garde : 404 livre inexistant · 409 si statut ≠ `ANALYZED`. Retourne 202 + `BookResponse`.
  `POST /books/{id}/chapters/{n}/generate` différé en Étape 3 (sans `Chapter.audio_path`,
  le résultat serait inaccessible). `check_phase7.py` — 13 sections OK.
  Fichiers (2) : `app/api/routes/books.py`, `tests/check_phase7.py`.
- Étape 3 ✅ (2026-06-14) — Persistance audio chapitre + statut par chapitre + régénération.

  **3a ✅** `ChapterStatus` enum (PENDING/GENERATING/DONE/FAILED) + `Chapter.audio_path/status/error_message`
  + `ChapterResponse` (id, position, title, status, error_message). check_phase7 sections 14-16. Commit `d1776c5`.
  ⚠️ Migration : supprimer `scriptvox.db` avant le 1er run (`create_all` n'ALTER pas).

  **3b ✅** `_synthesise_chapter_worker` (async) + `_generate_chapter_impl` (GENERATING→WAV sur disque→DONE/FAILED)
  + task Huey `generate_chapter` + `POST /books/{id}/chapters/{n}/generate` (202 ; 404 book/ch ; 409 si non ANALYZED).
  check_phase7 sections 17-20. Commit `42b6ec6`.

  **3c ✅** `GET /books/{id}/chapters/{n}/audio` sert le fichier persisté (FileResponse ; 409 si chapitre pas DONE) —
  suppression de la synthèse à la volée. `GET /books/{id}/chapters` → `list[ChapterResponse]`. Re-dispatch autorisé si
  chapitre DONE. Sections 9-10 de check_phase7 mises à jour (stale). check_phase6 section 5 mise à jour.
  check_phase7 sections 21-23. 23/23 OK. 7 suites sans régression. Commit `284e303`.

### Phase 8 — Casting & attribution intelligente des voix
**Pourquoi.** Cœur de la promesse « multi-voix » ; donne le contrôle des voix à l'utilisateur.
*D1 livré — Phase 8 débloquée.*
- Étape 1 ✅ (2026-06-15) — `GET /voices` : liste les 9 voix logiques du catalogue
  (`narrator` + `male_0..2` / `female_0..2` / `neutral_0..1`) avec `gender` (`narrator`→null)
  et `locale` (= `edgetts_locale` si provider `edgetts`, sinon `null`). **KISS** : lit le
  catalogue + la locale depuis `Settings`, n'instancie PAS le provider TTS (répond même sans
  binaire Piper / sans réseau). Fichiers (5) : `app/services/voice_assignment.py`
  (`list_catalogue_voices()` déterministe/dédupliqué), `app/schemas/voice.py` (`VoiceResponse`),
  `app/api/routes/voices.py` (router monté `/voices` dans `main.py`), `app/main.py`,
  `tests/check_phase9.py` (6 sections OK). 8 suites existantes sans régression.
- Étape 2 ✅ (2026-06-16) — Traits de personnage enrichis : `AgeCategory` enum (CHILD/YOUNG_ADULT/ADULT/ELDER/UNKNOWN)
  + 3 nouveaux champs sur `Character`/`CharacterData`/`CharacterResponse` : `age_category`, `tone` (libre), `voice_quality` (libre).
  `voice_tone` conservé (rétrocompat). `SYSTEM_PROMPT` étendu (âge, ton, qualité). `_parse_llm_json` lit les 3 champs avec fallback.
  Worker `tasks.py` propage vers BDD. Fichiers (6) : `app/core/enums.py`, `app/models/entities.py`, `app/schemas/book.py`,
  `app/services/llm/base.py`, `app/workers/tasks.py`, `tests/check_phase9.py` (13 sections). ⚠️ Supprimer `scriptvox.db` avant 1er run.
- Étape 3 — VoiceRegistry trait-based **déterministe** (score genre/âge/ton/qualité/locale), testé.
  Remplace le round-robin genre-only.
- Étape 4 — `PATCH /characters/{id}` : override manuel de la voix. ⚠️ **Contrat** : nouvelle route + schéma.

### Phase 9 — Couverture & métadonnées
**Pourquoi.** Identité visuelle des livres (bibliothèque, lecteur).
- Étape 1 — Extraction de la couverture à l'ingestion. ⚠️ **Contrat** : `Book.cover_path` + `BookResponse`.
- Étape 2 — `GET /books/{id}/cover` (servir l'image).
- Étape 3 — `POST /books/{id}/cover` (upload / remplacement manuel).

### Phase 10 — Format de diffusion audio
**Pourquoi.** Un WAV de livre entier est énorme ; le MP3 convient au streaming web.
- Étape 1 — Sortie MP3 pour la diffusion (master WAV conservé). ⚠️ **Dépendance** à justifier
  avant ajout (ex. `ffmpeg` / `lameenc`). *Dépend de D1 (EdgeTTS produit déjà du MP3).*

### Phase 11 — Frontend (Next.js) — piste séparée
**Pourquoi.** La V1 était surtout une UI. À démarrer une fois le backend à parité (Phases 7-9).
> Nouvelle stack (Next.js / React / Tailwind) = gros périmètre. Chaque étape = sous-projet à recouper.
- Étape 1 — Scaffold + intégration API (URL configurable, zéro hardcode).
- Étape 2 — Upload (drag & drop) + bibliothèque (grille).
- Étape 3 — Détail livre (chapitres, statuts, progression, polling).
- Étape 4 — Modale de casting (auto + override, filtre langue).
- Étape 5 — Lecteur audio persistant (play/pause, seek, vitesse).

### Différé / à NE PAS refaire
- **Voice Studio** (clonage de voix, contrôle d'émotion) — vaporware V1.
- **Lyrics / texte synchronisé** — faisable plus tard via timestamps de segments.
- **Switch de mode qui réécrit le `.env`** au runtime — anti-pattern, éviter (la V2 est fail-fast au démarrage).
- **Fichiers audio par segment séparés** — le WAV assemblé de la V2 est meilleur.

---

## Décisions d'architecture figées (Phase TTS)

| Sujet | Décision |
|-------|----------|
| Piper intégration | **Binaire `piper.exe` en subprocess** (PAS le pip `piper-tts` : `piper-phonemize` sans wheel Windows). Chemin via `PIPER_BINARY_PATH` ; modèles `.onnx` via `PIPER_VOICES_DIR` (gitignorés, hors repo) |
| ElevenLabs intégration | `httpx` direct (0 nouvelle dépendance), sortie WAV demandée à l'API |
| Assemblage | WAV via stdlib `wave` (0 dépendance) |
| Contrat | `BaseTTSProvider.synthesise(text, voice_id) -> bytes` WAV |
| Licence Piper | GPL-3.0 — `OHF-Voice/piper1-gpl` — documentée dans ARCHITECTURE.md |
| Nommage voix | `VOICE_CATALOGUE` impose les noms `.onnx` ; chaque voix exige un `<voice>.onnx.json` à côté (sinon crash silencieux) |
