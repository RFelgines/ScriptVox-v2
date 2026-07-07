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
- Étape 3 ✅ (2026-06-16) — VoiceRegistry trait-based déterministe. `_VoiceMeta`/`_CATALOGUE_META` (métadonnées
  statiques par voice_id), `_score_voice` (genre+4 / age+2 / tone+1 / quality+1), `assign_voices` réécrit avec
  tri (-score, voice_id) + wrap-around intra-tier (le top-tier évite qu'un MALE tombe sur une voix FEMALE).
  Fichiers (2) : `app/services/voice_assignment.py`, `tests/check_phase9.py` (20 sections). 8 suites sans régression.
- Étape 4 ✅ (2026-06-16) — `PATCH /characters/{id}` : override manuel de la voix. `CharacterUpdate {voice_id}`.
  Validation : voice_id doit être dans `_CATALOGUE_META` sauf `narrator` (422 sinon). 404 si personnage inconnu.
  Fichiers (4) : `app/schemas/book.py` (+CharacterUpdate), `app/api/routes/characters.py` (nouveau),
  `app/main.py`, `tests/check_phase9.py` (26 sections). 8 suites sans régression.
- Étape 5 ✅ (2026-06-20) — Fix collision de voix dans `assign_voices` (trouvé sur le run réel HP, §B-3/Étape 6).

  **Symptôme.** 3 personnages MALE différents (Dursley, Dudley, Hagrid, run HP) recevaient tous `male_0`
  alors que `male_1`/`male_2` restaient libres. Cause : le wrap-around (Étape 3) ne regardait que le
  *tier du meilleur score absolu* — si toutes ses voix étaient prises, il réutilisait `top_tier[0]` au
  lieu de descendre vers la 2ᵉ meilleure voix **libre** du même genre.

  **Fix.** `assign_voices` restreint désormais les candidats au pool de genre du personnage
  (`VOICE_CATALOGUE[effective_gender]`), les classe par score puis ne réutilise qu'en dernier recours
  (`ranked[0]`) une fois tout le pool de genre épuisé — au lieu de retomber sur le seul meilleur score.
  Le wrap-around reste strictement intra-genre (inchangé).

  **Test-first.** `check_phase9.py` Section 27 (nouvelle) : 3 personnages MALE à traits **identiques**
  (donc même meilleur score pour les trois) → confirmé en échec sur l'ancien code
  (`['male_0','male_0','male_0']`), vert après le fix (`male_0`/`male_2`/`male_1`, tous distincts).
  Sections 16/17/18/19/20 (existantes) vérifiées inchangées à la main avant le fix. 12/12 suites vertes.

  Fichiers (2) : `app/services/voice_assignment.py`, `tests/check_phase9.py` (+ Section 27).
  Pas de changement de contrat (`assign_voices(book_id, session)` inchangée).

### Phase 9 — Couverture & métadonnées
**Pourquoi.** Identité visuelle des livres (bibliothèque, lecteur).
- Étape 1 ✅ (2026-06-17) — Extraction de la couverture à l'ingestion.
  `ParsedBook.cover_image/cover_media_type` + `_extract_cover()` (3 stratégies : uid / ITEM_COVER / properties).
  `Book.cover_path` + `BookResponse.cover_path`. Worker écrit `data/{book_id}/cover.<ext>`.
  ⚠️ Supprimer `scriptvox.db` avant 1er run (nouvelle colonne). `check_phase10.py` 5/5 OK. Zéro régression sur 9 suites.
  Fichiers (5) : `app/services/epub/parser.py`, `app/models/entities.py`, `app/schemas/book.py`, `app/workers/tasks.py`, `tests/check_phase10.py`.
- Étape 2 ✅ (2026-06-17) — `GET /books/{id}/cover` (FileResponse ; 404 livre inconnu / 404 sans cover / 404 fichier absent).
  `mimetypes.guess_type` pour le Content-Type. `check_phase10.py` 8/8 OK. Zéro régression 9 suites.
  Fichiers (2) : `app/api/routes/books.py`, `tests/check_phase10.py`.
- Étape 3 ✅ (2026-06-17) — `POST /books/{id}/cover` (upload / remplacement manuel).
  Valide image/jpeg|png|gif|webp (422 sinon). Écrit `data/{id}/cover.<ext>`. Retourne `BookResponse`.
  `check_phase10.py` 11/11 OK. Zéro régression 9 suites.
  Fichiers (2) : `app/api/routes/books.py`, `tests/check_phase10.py`.

### Phase 10 — Format de diffusion audio ✅ (terminée, 2026-06-17)

- Étape 1 ✅ — `wav_to_mp3(bytes)->bytes` dans `assembler.py` (lameenc~=1.8, pur Python).
  `Book.mp3_path` + `BookResponse.mp3_path`. `check_phase11.py` 6/6 OK.
  Fichiers (5) : `requirements.txt`, `assembler.py`, `entities.py`, `schemas/book.py`, `check_phase11.py`.
- Étape 2 ✅ — Worker encode WAV→MP3 après `assemble_wav` + `GET /books/{id}/audio/mp3`.
  WAV master conservé. `check_phase11.py` 9/9 OK. Zéro régression 10 suites.
  Fichiers (3) : `workers/tasks.py`, `routes/books.py`, `check_phase11.py`.
  ⚠️ Supprimer `scriptvox.db` avant 1er run (nouvelles colonnes `mp3_path`).

### Phase 11 — Frontend (Next.js) — piste séparée
**Pourquoi.** La V1 était surtout une UI. À démarrer une fois le backend à parité (Phases 7-9).
> Nouvelle stack (Next.js / React / Tailwind) = gros périmètre. Chaque étape = sous-projet à recouper.
- Étape 1 ✅ (2026-06-17) — Scaffold + intégration API.
  - **1a** : `CORSMiddleware` + `Settings.frontend_origins` (optionnel, défaut `http://localhost:3000`). `check_phase12.py` 4/4. Commit `a48c7c2`.
  - **1b** : `frontend/` Next.js 16 App Router TypeScript Tailwind. `src/lib/api.ts` (`listBooks()`), `src/app/page.tsx` (bibliothèque + statuts colorés), `NEXT_PUBLIC_API_URL` via `.env.local`. `npm run build` vert. Commit `92e5a8b`.
- Étape 2 ✅ (2026-06-17) — Upload (drag & drop) + bibliothèque (grille).
  Frontend pur (4 fichiers, 0 backend, 0 nouvelle dépendance). `src/lib/api.ts` : `uploadBook(file)`
  (POST multipart `/books`, lit `detail` sur 422) + `coverUrl(id)`. `UploadDropzone.tsx` (nouveau) :
  drag & drop HTML5 natif + fallback `<input accept=".epub">`, validation `.epub` client, états
  upload/erreur. `BookCard.tsx` (nouveau) : carte grille, thumbnail couverture (`<img>` natif +
  fallback titre si `cover_path` nul ou erreur image), badge statut, barre de progression. `page.tsx` :
  liste → grille responsive (2→5 col.), montage du dropzone, refresh après upload. **Choix** : `<img>`
  natif (pas `next/image` → évite `images.remotePatterns`) ; `refresh()` en chaîne de promesses (la
  règle Next 16 `react-hooks/set-state-in-effect` interdit un `setState` synchrone au corps d'un effet).
  Polling du statut **différé en Étape 3** (ici refresh unique). Vérif : `npm run build` + `npm run lint`
  verts (pas de harness de test frontend).
- Étape 3 ✅ (2026-06-17) — Détail livre (chapitres, statuts, progression, polling).
  Frontend pur (3 fichiers, 0 backend, 0 nouvelle dépendance). `src/lib/api.ts` : type `ChapterStatus`
  + interface `ChapterSummary` ; `BookSummary` élargi (`author`, `error_message`) ; `getBook(id)` +
  `listChapters(id)`. `src/app/books/[id]/page.tsx` (nouveau, route dynamique) : Client Component,
  param via `use(params)` (Next 16 : `params` est une `Promise`), en-tête (couverture, titre, auteur,
  badge statut, barre de progression, `error_message` si FAILED), liste des chapitres (position, titre,
  badge statut, erreur par chapitre). **Polling** = `setTimeout` récursif (~3 s, pas de chevauchement),
  s'arrête quand le livre est terminal (DONE/FAILED) ET qu'aucun chapitre n'est PENDING/GENERATING ;
  `clearTimeout` + garde `active` au démontage. `src/components/BookCard.tsx` : carte enveloppée dans
  `<Link href="/books/{id}">`. **Bouton « Générer » différé** (vient avec le casting, Étape 4).
  Vérif : `npm run build` (route `ƒ /books/[id]` enregistrée) + `npm run lint` verts.
- Étape 4 ✅ (2026-06-17) — Modale de casting + déclencheur de génération.
  Frontend pur (3 fichiers, 0 backend, 0 nouvelle dépendance). `src/lib/api.ts` : types `Gender`,
  `VoiceSummary`, `CharacterSummary` ; `listCharacters(bookId)`, `listVoices()`,
  `patchCharacterVoice(charId, voiceId)`, `generateBook(bookId)`. `src/components/CastingModal.tsx`
  (nouveau) : overlay `fixed inset-0` (fermeture ✕ / backdrop / Esc), fetch parallèle personnages +
  voix, une ligne par personnage (nom + genre/âge + description) avec `<select>` de voix (options =
  `/voices` sans `narrator`) → `PATCH /characters/{id}` au changement (indicateur `savingId`), pied de
  modale avec bouton **« Générer l'audio »** actif uniquement si `status === ANALYZED` →
  `POST /books/{id}/generate`. `src/app/books/[id]/page.tsx` : bouton « Casting » (si statut ∈
  {ANALYZED, GENERATING, DONE}), montage de la modale, **reprise du polling** après génération via un
  `reloadNonce` ajouté aux deps de l'effet (le polling s'arrête à ANALYZED).
  **Filtre langue retiré** : `GET /voices` renvoie la même locale pour toutes les voix (le
  `edgetts_locale` serveur) → rien à filtrer ; locale affichée en info. Vérif : `npm run build` +
  `npm run lint` verts.
- Étape 5 ✅ (2026-06-17) — Lecteur audio persistant (play/pause, seek, vitesse).
  Frontend pur (5 fichiers, 0 backend, 0 nouvelle dépendance). `src/lib/api.ts` : `bookMp3Url(id)`.
  `src/components/player/PlayerProvider.tsx` (nouveau) : Context + `<audio>` caché via ref, `play/toggle/seek/setRate/close`.
  `src/components/player/PlayerBar.tsx` (nouveau) : barre fixe `bottom-0` (play/pause SVG, titre, scrub+temps, vitesse 0.5→2×, fermer). Rend `null` si pas de track.
  `src/app/layout.tsx` : wrap `<PlayerProvider>` + `<PlayerBar/>` + `pb-24`.
  `src/app/books/[id]/page.tsx` : bouton « ▶ Écouter » (status DONE && mp3_path) → `play({title, src: bookMp3Url})`.
  Vérif : `npm run build` + `npm run lint` verts.
- Étape 6 ✅ (2026-06-20) — Génération et lecture audio par chapitre. Commit `731c109`.

  **Pourquoi.** Audit de couverture API (2026-06-20) : le backend persiste un statut +
  `audio_path` par chapitre depuis Phase 7 (`POST .../chapters/{n}/generate`,
  `GET .../chapters/{n}/audio`), mais aucune UI ne les exposait — seule la génération/lecture
  du livre entier était câblée. Plus gros trou identifié dans la couverture frontend (10/14
  endpoints avant cette étape).

  Frontend pur (2 fichiers, 0 backend, 0 nouvelle dépendance). `src/lib/api.ts` :
  `chapterAudioUrl(bookId, position)` (helper URL, calqué sur `bookMp3Url`) +
  `generateChapter(bookId, position)` (POST, gestion erreur `detail` calquée sur `generateBook`).
  `src/app/books/[id]/page.tsx` : bouton « Générer » par chapitre (visible si
  `book.status === ANALYZED` et `ch.status !== DONE` ; désactivé pendant l'appel ou si déjà
  PENDING/GENERATING) → `generateChapter` puis bump `reloadNonce` (le polling existant capte
  ensuite GENERATING→DONE) ; bouton « ▶ Écouter » (visible si `ch.status === DONE`) → réutilise
  le `PlayerProvider`/`PlayerBar` existants (Étape 5), aucun nouveau composant.

  **Déviation assumée** : pas de bouton « régénérer » sur un chapitre déjà `DONE` (le backend
  l'autoriserait, mais hors périmètre de cette micro-tâche — différé).

  Vérif : `npm run build` + `npm run lint` verts.

- Étape 7 ✅ (2026-06-20) — Suppression d'un livre depuis la bibliothèque.

  **Pourquoi.** `DELETE /books/{id}` existe côté backend depuis Phase 6 mais n'avait aucune UI ;
  les livres de test s'accumulaient sans moyen de nettoyer la bibliothèque.

  Frontend pur (3 fichiers, 0 backend, 0 nouvelle dépendance). `src/lib/api.ts` :
  `deleteBook(id)` (DELETE, 204 sans body → pas de `.json()`). `src/components/BookCard.tsx` :
  restructuré — la carte (`<Link>`) et le bouton ✕ sont désormais frères dans un `<div
  className="relative">` (un `<button>` ne peut pas être enfant d'un `<a>`) ; ✕ en
  `absolute top-2 right-2`, `window.confirm` natif (KISS, pas de modale) →
  `deleteBook` → `onDeleted()` (nouvelle prop). `src/app/page.tsx` : `onDeleted={refresh}`.

  **Déviations assumées** : suppression accessible uniquement depuis la bibliothèque (pas de
  bouton sur la page détail) ; confirmation via `window.confirm` natif plutôt qu'une modale.

  **⚠️ Limite backend connue (hors périmètre, non corrigée)** : `delete_book` ([app/api/routes/books.py](app/api/routes/books.py))
  ne supprime que `source_path` — l'audio déjà généré dans `data/{id}/` (wav/mp3) reste orphelin
  sur disque. À traiter en tâche séparée si ça devient gênant.

  Vérif : `npm run build` + `npm run lint` verts.

### Phase 12 — Run réel EdgeTTS & hardening LLM parser (2026-06-17 → 2026-06-19) ✅ terminée

**Pourquoi.** Première validation bout-en-bout en conditions réelles (EdgeTTS fr-FR, vrai roman français HP). Bugs découverts et corrigés test-first pendant la tentative.

#### Étape 1 ✅ (2026-06-17) — `_coerce_enum` : parser LLM tolérant aux écarts d'enum

**Symptôme.** `qwen3:8b` retourne `"DIALOG, "` au lieu de `"DIALOGUE"` → `LLMParsingError` → book FAILED.

**Fix.** `_coerce_enum(raw, enum_cls, default)` dans `app/services/llm/base.py` : normalise casse + ponctuation (`re.sub`), table d'alias (`DIALOG→DIALOGUE`, `NARRATOR→NARRATION`, `Male→MALE`…). Fallback sur `default` + `logging.WARNING` si valeur inconnue. Zéro crash, observabilité préservée. Fichiers (2) : `app/services/llm/base.py`, `tests/check_phase3.py` (section 5 màj + section 8 nouvelle = 9 sections). 12/12 suites sans régression.

#### Étape 2 ✅ (2026-06-17) — Config EdgeTTS + gitignore Ebook/

- `.env` : `TTS_PROVIDER=edgetts`, `EDGETTS_LOCALE=fr-FR`, `OLLAMA_CONTEXT_TOKENS=32768` (était 8192 — sortie JSON tronquée sur chapitres réels avec 8K).
- `.gitignore` : `Ebook/` ajouté (épub HP copyrighté, anti-pattern V1).

#### Étape 3 ✅ (2026-06-18) — Montée edge-tts 6.1 → 7.2 + validation EdgeTTS fr-FR

**Symptôme.** `edge-tts~=6.1` retournait 403 de Microsoft (tokens Edge 130 révoqués). Test direct Python confirmé → problème lib, pas réseau.

**Fix.** `requirements.txt` : `edge-tts~=6.1` → `edge-tts~=7.2` (tokens Edge mis à jour). API edge_tts 7.x identique (`Communicate` + `.stream()`). 12/12 suites sans régression.

**Validation réelle EdgeTTS fr-FR.** Petit epub FR "Le Dernier Soir" (1 chapitre, 2 personnages) :
- LLM (`qwen3:8b`) : détecte Marie (FEMALE/female_0) + homme (MALE/male_0). Analyse instantanée.
- EdgeTTS fr-FR : `fr-FR-DeniseNeural` (Marie) + `fr-FR-HenriNeural` (homme).
- Résultat : **WAV 89,9 s — 22 050 Hz mono 16-bit — 3,9 MB — HTTP 200 ✅**
- Pipeline complet confirmé : EPUB → LLM → personnages → voix fr-FR → WAV assemblé.

#### Étape 4 ✅ (2026-06-18/19) — Protocole LLM label-based (option B retenue)

**Décision.** Option B choisie : refactoring LLM pour ne retourner que des métadonnées
(`{characters, attributions}`) ; le texte n'est jamais reproduit. Sortie O(dialogues) au lieu de
O(tokens entrée) → chapitres HP en secondes au lieu de 7-14 min.

**B-1 ✅ — Doc ARCHITECTURE.md** (commit `e2dbfd8`)
- §2.1 : signature `analyze(text: str) -> LLMChapterResult` (était stale `prompt: str`).
- §2.3 : clarification que `× 0.8` est valide uniquement avec label-based (ancien prompt laissait
  budget effectif à `context_window / 3`). **Bug §2.3 résolu.**
- §2.7 (nouveau) : spec complète du protocole — délimiteurs de pré-segmentation, schema JSON
  `{characters, attributions}`, règle de reconstruction, contrats publics préservés.

**B-2a ✅ — Pré-segmentation déterministe** (commit `b4cefde`)
- `_Span(index, text, is_dialogue)` + `_pre_segment(text) -> list[_Span]` (invariant byte-exact).
- `_build_user_prompt(spans) -> str` : formate `[i][DIALOGUE|NARRATION] texte` pour le LLM.
- `tests/check_phase3.py` : sections §9 (`_pre_segment`) et §10 (`_build_user_prompt`) ajoutées.

**B-2b ✅ — Bascule protocole label-based** (commit `aa07b50`)
- `SYSTEM_PROMPT` réécrit : LLM reçoit les spans numérotés, retourne `{characters, attributions}`,
  ne reproduit jamais le texte. Champs `age_category`/`tone`/`voice_quality` préservés (check_phase9 §13).
- `_segment_text(span) -> str` : retire les délimiteurs de dialogue pour le TTS (`«»`, `""`, `"…"`,
  tiret cadratin initial).
- `_parse_llm_json(raw, spans)` : reconstruit `SegmentData` depuis les spans + `attr_map` ;
  attributions inconnues → `None` + WARNING (jamais de crash).
- `ollama.py` + `gemini.py` câblés sur le nouveau protocole.
- `tests/check_phase3.py` §5 + `tests/check_phase9.py` §11/§12 migrés au format `{attributions}`.
- **12/12 suites vertes.**

#### Étape 5 ✅ (2026-06-19) — Run réel HP + cartographie num_ctx

**Méthode.** Nouveau script `tests/bench_hp_label_based.py` (benchmark live, **HORS** suite de
régression : nécessite Ollama + epub dans `Ebook/`, aucun assert — produit des mesures). Parse
l'epub HP réel, mesure l'analyse LLM des 3 premiers chapitres de contenu (Ch.3 « Le survivant »
82 dialogues, Ch.4, Ch.5) avec qwen3:8b + protocole label-based. Warm-up hors mesure. Cartographie
sur 3 valeurs de `OLLAMA_CONTEXT_TOKENS` + `ollama ps` après chaque run.

**Vitesse (moyenne/chapitre) & VRAM :**

| num_ctx | Ch.3 | Ch.4 | Ch.5 | moyenne | `ollama ps` |
|---------|------|------|------|---------|-------------|
| 8192    | 34,9 s | 20,9 s | 15,3 s | **23,7 s** | 100% GPU (6,6 GB) |
| 16384   | 102,3 s | 100,7 s | 107,5 s | **103,5 s** | 100% GPU (7,8 GB) |
| 32768   | 480,4 s | 263,7 s | 318,6 s | **354,2 s** | **18% CPU** / 82% GPU (10 GB) |

**Qualité d'attribution (dialogues attribués / total) :**

| num_ctx | Ch.3 (82) | Ch.4 (53) | Ch.5 (60) |
|---------|-----------|-----------|-----------|
| 8192    | 20 (+2 chunks) | 11 | **2** |
| 16384   | **0** (JSON `index:null`) | 53 | 59 |
| 32768   | **81** | 52 | 56 |

**Conclusion.** La vitesse est gouvernée par `num_ctx`, PAS par le protocole : à 32768 le cache KV
déborde la VRAM (18% CPU) → ~6 min/ch ; le plus grand contexte 100% GPU testé est 16384. **Trilemme
vitesse ↔ qualité ↔ VRAM sur qwen3:8b/ce GPU** : seul 32768 attribue correctement le plus gros
chapitre (81/82) ; 16384 est instable (Ch.3 → 82 attributions vides) ; 8192 est rapide mais
l'attribution s'effondre — et cette vitesse est en partie un artefact (peu de sortie générée car peu
d'attributions). → Le `num_ctx=32768` de l'Étape 2 est justifié par la qualité au pire cas, au prix
de la vitesse.

**Le protocole label-based est validé** (sortie O(dialogues), budget §2.3 correct, fallback narrateur
propre, zéro crash). Mais l'objectif « secondes/chapitre » (§2.3/§2.7) n'est PAS atteint sur ce
modèle/GPU — le goulot est matériel/`num_ctx`. Pistes à arbitrer : modèle plus petit/rapide ou GPU
plus gros ; chunking plus fin pour fiabiliser l'attribution à bas `num_ctx` ; retry/réparation des
attributions malformées ; ou accepter 32768 (~6 min/ch) pour la qualité. Détail : mémoire
`llm_perf_qwen3_context_tradeoff`.

**Prérequis (réunis).** Ollama lancé avec `qwen3:8b` + epub HP dans `Ebook/` (gitignored).

#### Étape 6 ✅ (2026-06-20) — Run réel pipeline complet sur Ch.3 HP (LLM + TTS)

**Pourquoi.** L'Étape 5 (B-3) ne mesurait que l'analyse LLM via le script de benchmark, qui appelle
`provider.analyze()` directement — pas le pipeline réel (`POST /books` → worker → `_generate_chapter_impl`
→ TTS). La couche TTS n'avait **jamais** été exercée à l'échelle d'un vrai chapitre HP (164 segments,
6 personnages) : seul un epub FR minuscule (1 chapitre, 2 personnages) avait validé EdgeTTS jusqu'ici.

**Méthode.** Nouveau script `tests/make_hp_chapter3_fixture.py` (hors suite de régression, aucun assert) :
isole le chapitre 3 réel (« 1LE SURVIVANT », même sélection que `bench_hp_label_based.py` —
`MIN_CONTENT_CHARS=1500`, `content[0]`) dans un epub mono-chapitre reconstruit via `ebooklib`, écrit dans
`Ebook/hp_chapter3_only.epub` (gitignored — contenu HP copyrighté). Round-trip texte vérifié byte-exact
contre l'original. **Piège rencontré** : `EpubNav` ne doit pas être ajouté au `spine` (seulement au
manifeste) sous peine d'apparaître comme un faux chapitre supplémentaire — `EpubParser` ne lit que les
items référencés par le spine. **2e piège** : `ch.raw_text` contient déjà le titre en 1res lignes (le
`<h1>` source était `"1<br/>LE SURVIVANT"`) ; ajouter un `<h1>` séparé le dupliquait.

Le fichier généré a été uploadé via `POST /books` sur l'app réellement lancée (backend + worker + frontend
démarrés pour cette session), puis suivi jusqu'à `ANALYZED`, puis `POST /books/{id}/chapters/1/generate`
jusqu'à `DONE`.

**Résultats :**
- **Analyse LLM** : `ANALYZED` en ~9,5 min (vs ~480 s mesurés en benchmark pur pour ce même chapitre —
  écart attendu : parsing EPUB + assignation de voix + aucun warm-up préalable, contrairement au script
  de benchmark).
- **6 personnages détectés**, cohérent avec B-3 (Dursley, Mrs Dursley, Dudley, Dumbledore, McGonagall,
  Hagrid). Casting plausible par genre/âge/ton. **Point relevé (non bloquant)** : 3 personnages
  masculins différents (Dursley, Dudley, Hagrid) ont tous reçu `voice_id=male_0` au lieu de se répartir
  sur `male_0/1/2` — comportement du scorer `voice_assignment.py` à creuser séparément si ça gêne à l'oreille.
- **Génération TTS (jamais testée à ce volume) : `DONE` en ~2 min 48 s, zéro erreur**, pour 164 segments
  (82 dialogues + 82 narrations) → 164 appels séquentiels EdgeTTS. Sortie `data/{id}/ch1.wav` :
  39 min 11 s, 22 050 Hz mono 16-bit (format conforme au contrat).
- Vérification UI : chapitre affiché `DONE`, bouton « ▶ Écouter » fonctionnel (Étape 6 frontend),
  lecture confirmée sans erreur console.

**Conclusion.** Le pipeline réel est validé bout-en-bout sur du contenu costaud et réel, pas seulement
sur des fixtures jouets. La couche TTS — la vraie inconnue de cette étape — fonctionne correctement et
rapidement même à 164 segments/chapitre ; ce n'est pas elle qui pose problème dans le trilemme de
l'Étape 5 (qui reste un goulot **LLM**/`num_ctx`/VRAM, pas TTS).

---

## Phase 13 — Qualité de segmentation (préalable à l'émotion par réplique)

> Découle de l'écoute du spike Qwen3-TTS : l'incise (« dit-elle froidement ») était lue par la voix
> du personnage. Voir mémoire `segmentation-incise-limitation`. Test-first, Plan-First, GO par étape.

### Étape 1 ✅ (2026-06-20) — Extraction de l'incise FR en narration

**Pourquoi.** Sur une réplique en tiret cadratin, l'incise d'attribution (« dit-elle froidement »,
« dit Harry ») n'a pas de délimiteur propre et restait collée au dialogue → lue par la voix du
personnage au lieu du narrateur. Défaut déjà présent dans la sortie EdgeTTS actuelle.

**Livré.** `_split_incise` + `_INCISE_RE` (`app/services/llm/base.py`) : peèle l'incise terminale
propre (inversion clitique `dit-elle`/`demanda-t-elle`, ou verbe d'incise curé + nom propre `dit
Harry`) en span NARRATION distinct. Borné : un dialogue *repris* (`…, répondit-il, mais je
viendrai`) n'est PAS splitté. Invariants préservés (byte-exact + index 1-based contigus).
`_segment_text` nettoie la virgule orpheline. **Aucun changement de contrat.**
Test-first : `check_phase3.py` §11 (8 asserts) ; 12 suites sans régression ; `ARCHITECTURE.md §2.7`
documenté. Fichiers (3) : `app/services/llm/base.py`, `tests/check_phase3.py`, `ARCHITECTURE.md`.

**⚠️ Bloqueur découvert (→ Étape 2).** Sur le vrai texte HP, `raw_text` contient des sauts de ligne
en milieu de phrase (~1 tous les 53 caractères) ; le regex de dialogue `[—–―][^\n]*` coupe la
réplique au 1er `\n` → **0 incise extraite sur 74 répliques réelles**, et les paroles elles-mêmes
sont mal typées narration. Le fix incise est correct mais neutralisé en amont.

### Étape 2 ✅ (2026-06-20, commit `294f60f`) — Normalisation des sauts de ligne intra-paragraphe

**Cause racine.** `soup.get_text(separator="\n", strip=True)` ne rogne que les bords des nœuds
texte ; les `\n` de hard-wrap XHTML (~80 colonnes) internes à un paragraphe restaient, coupant les
répliques em-dash au 1er `\n` et neutralisant `_split_incise` (Étape 1).

**Livré.** `_extract_text` (`app/services/epub/parser.py`) : extraction bloc par bloc (`p`, `div`,
`li`, `h1-6`, blocs feuilles uniquement — évite le double comptage `div>p`), whitespace interne
(espaces, `\n`, `\xa0`) écrasé en espace simple par bloc. Repli sur l'ancien comportement si aucun
bloc trouvé (jamais de texte perdu). **Aucune modification de `make_hp_chapter3_fixture.py`
nécessaire** — il faisait déjà la bonne chose ; c'était la source (`ch.raw_text`) qui était sale.
Test-first : `check_phase2.py` nouvelle section synthétique (zéro contenu copyrighté) ; 12 suites
sans régression. **Aucun changement de contrat.**

**Gain mesuré sur le vrai Ch.3 HP** (régénération de `Ebook/hp_chapter3_only.epub`, round-trip
byte-exact toujours OK) :

| Métrique | Avant | Après |
|---|---|---|
| Incises extraites / répliques em-dash | 0 / 74 | **19 / 74** |
| Total spans | 164 | 179 |
| Spans dialogue / narration | 82 / 82 | 80 / 99 |

**2 limites découvertes pendant la mesure — NON tranchées, à traiter en tâche séparée :**

- **Bug apostrophe.** `_INCISE_VERBS` (`base.py`) utilise l'apostrophe droite `'` pour les verbes
  réflexifs (`s'écria`, `s'exclama`, `s'étonna`, `s'enquit`), mais le texte HP réel utilise
  l'apostrophe typographique `'` → mismatch silencieux, ex. `s'exclama Mr Dursley` non détecté.
  Fix candidat : classe de caractères acceptant les deux apostrophes (1 ligne), zéro changement
  de contrat — mais portée et priorité à discuter, pas encore actées.
- **Incise qui s'étend dans du dialogue continué.** Sur `— X, dit Y avec douceur. Z.`, si `Z` est
  en réalité la suite du dialogue de Y (convention FR ambiguë sans nouveau tiret/guillemet),
  `[^,]*` l'absorbe en narration. Ambigu même à la lecture humaine sans contexte plus large.
  Corriger ou assumer comme limite bornée (cf. Étape 1) : à arbitrer.

### Étape 3 ✅ (2026-06-21) — Bug apostrophe corrigé ; bornage dialogue continué accepté

**Décision (2026-06-21).** Sur les 2 points de l'Étape 2 : **A corrigé** (bug apostrophe),
**B accepté comme limite bornée** (non corrigé — cf. Étape 1, dégradation bornée déjà assumée).

**A — Bug apostrophe (corrigé).** `app/services/llm/base.py` : nouvelle constante
`_APOS = r"['']"` (classe acceptant l'apostrophe droite ET la typographique), utilisée dans
`_INCISE_VERBS` (verbes réflexifs `s'écria`/`s'exclama`/`s'étonna`/`s'enquit`) et dans le préfixe
clitique de `_INCISE_VERB` (`s'écria-t-il`…). Avant le fix, le texte réel (apostrophe
typographique `'`) ne matchait jamais la liste codée en apostrophe droite `'` → incise non
détectée, silencieusement. Test-first : `check_phase3.py` §11, 2 nouveaux asserts (verbe réflexif
+ clitique réflexif, apostrophe typographique) — confirmés en échec sur l'ancien code
(`[True]` au lieu de `[True, False]`), verts après le fix. 12/12 suites sans régression.
**Aucun changement de contrat.** Fichiers (2) : `app/services/llm/base.py`, `tests/check_phase3.py`.

**B — Incise absorbant du dialogue continué (accepté, non corrigé).** Sur
`— X, dit Y avec douceur. Z.` où `Z` reprend en réalité la parole de Y, `[^,]*` l'absorbe en
narration. Ambigu même à la lecture humaine sans contexte plus large ; corriger risquerait des faux
positifs pires que la limite actuelle. Reste une dégradation bornée documentée (cf. Étape 1) —
aucune action prévue sauf signal contraire à l'écoute réelle.

**Phase 13 close.** Prochaine décision = arbitrage utilisateur (run HP complet 18 chapitres / spike
TTS émotion comparatif / petits défauts `error_message` stale + audio orphelin / cover upload UI).

---

## Phase 14 — Qualité multi-chapitres (persistance personnages + émotion par réplique)

> Découle de l'audit pré-run-complet HP du 2026-06-21 (mémoire `fullbook-quality-gaps`). Plan en
> 4 étapes ordonnées A → B1 → B2 → B3, un GO explicite par étape. Répartition actée : Claude
> implémente A + B1/B2/B3 ; le catalogue de voix (chantier séparé) reste à l'utilisateur.

### Étape A ✅ (2026-06-21) — Persistance des personnages entre chapitres

**Pourquoi.** Chaque chapitre était analysé indépendamment par le LLM, sans connaissance des
personnages déjà détectés dans les chapitres précédents. Risque : un même personnage nommé
différemment selon le chapitre (« Mr Dursley » puis « l'oncle Vernon ») se fragmente en plusieurs
`Character` distincts → plusieurs voix pour la même personne sur un run long (HP 18 chapitres).

**Contrat (revue humaine faite avant implémentation).**
`BaseLLMProvider.analyze(text: str, known_characters: list[str] | None = None) -> LLMChapterResult`
— paramètre optionnel, rétrocompatible. Aucun changement de schéma DB ; le dedup par nom exact
existant dans `tasks.py` (`char_map`) reste inchangé, juste mieux nourri.

**Livré.**
- `app/services/llm/base.py` — signature abstraite mise à jour ; `SYSTEM_PROMPT` += règle de
  réutilisation du nom exact pour un personnage récurrent ; `_build_user_prompt(spans,
  known_characters=None)` injecte un préambule (`"Known characters from previous chapters: ..."`)
  si la liste est non vide, sinon rendu strictement identique à avant (no-op vérifié).
- `app/services/llm/ollama.py` / `gemini.py` — passe-plat du nouveau paramètre.
- `app/workers/tasks.py` — `_analyze_book` calcule `known = list(char_map.keys())` avant les
  chunks de chaque chapitre et le transmet à `provider.analyze(chunk, known)` (vide au 1er
  chapitre, accumulé ensuite).

**Test-first.** `tests/check_phase14.py` (nouveau, 5 sections) : signature `analyze` expose le
nouveau paramètre avec défaut `None` ; `_build_user_prompt` no-op si `None`/`[]` (régression
zéro double saut de ligne re-vérifiée) et préambule correct si rempli ; `SYSTEM_PROMPT` contient
la règle ; pipeline réel `_analyze_book` avec un `FakeProvider` qui enregistre le
`known_characters` reçu — confirmé `[]` au chapitre 1 puis `['Mr Dursley']` au chapitre 2,
dedup toujours actif (1 seul `Character` créé). **13/13 suites vertes (12 existantes + nouvelle),
zéro régression.** Fichiers (5) : `app/services/llm/base.py`, `ollama.py`, `gemini.py`,
`app/workers/tasks.py`, `tests/check_phase14.py`.

**Risque résiduel assumé.** Le LLM peut quand même dériver rarement malgré la liste (dégradation
bornée) — pas de fuzzy-matching algorithmique ajouté (sur-ingénierie à ce stade).

### Étape B1 ✅ (2026-06-22) — Extraction de l'émotion par réplique de dialogue

**Pourquoi.** Premier domino vers l'intégration future de Qwen3-TTS (émotion + clonage de voix,
décidée le 2026-06-22 — voir mémoire `feature-roadmap-decisions`). Couche données pure : le LLM
décrit en langage naturel comment une réplique de dialogue doit être *dite* ; aucun changement de
comportement TTS (EdgeTTS/Piper/ElevenLabs ignorent toujours ce champ, qui n'est même pas encore
transmis aux providers).

**Contrat (revu avant implémentation).** `SegmentData.emotion: str | None = None` (dataclass,
défaut → 100% rétrocompatible) + `Segment.emotion: Optional[str] = None` (colonne nullable,
⚠️ supprimer `scriptvox.db` avant le 1er run). Émotion **dialogue uniquement** — narration reste
toujours `None`. Pas d'exposition API (`Segment` n'est exposé dans aucun schéma Pydantic).

**Livré.**
- `app/services/llm/base.py` — `SYSTEM_PROMPT` += règle `emotion` (texte libre sur
  `attributions[].emotion`) ; `_parse_llm_json` extrait l'émotion par index (indépendamment de la
  validité du `character_name`, dégradation bornée cohérente avec le reste du fichier).
- **Bug trouvé en lisant le code (pas dans le plan d'origine) :** `_merge_chunk_results`
  reconstruit chaque `SegmentData` pour renuméroter `position` à travers les chunks d'un chapitre
  découpé par `_chunk_text`, et ne propageait pas `emotion` → perte silencieuse sur tout chapitre
  chunké. Fix : `emotion=sd.emotion` ajouté à la reconstruction.
- `app/models/entities.py` — `Segment.emotion`.
- `app/workers/tasks.py` — `_analyze_book` passe `sd.emotion` au constructeur `Segment(...)`.
- `ARCHITECTURE.md §2.7` — schéma JSON + note "couche données seule, pas encore consommée par le TTS".

**Test-first.** `check_phase3.py` §5 (extraction + narration toujours `None` + rétrocompat sans le
champ) et §6 (régression `_merge_chunk_results` — rouge avant le fix, vert après) ; `check_phase14.py`
§6 (pipeline réel `_analyze_book` avec `FakeProvider`, `Segment.emotion` vérifié en base). 13/13
suites vertes, zéro régression. Fichiers (6) : `app/services/llm/base.py`, `app/models/entities.py`,
`app/workers/tasks.py`, `ARCHITECTURE.md`, `tests/check_phase3.py`, `tests/check_phase14.py`.

**Hors scope (explicite) :** pas de transmission aux providers TTS (B2), pas de `QwenTTSProvider`
(B3), pas d'exposition API, pas d'émotion sur la narration.

### Étape B2 ✅ (2026-06-22) — Contrat TTS `synthesise(..., emotion=None)` (câblage)

**Pourquoi.** Faire transiter `Segment.emotion` (livré en B1) jusqu'à la frontière des providers
TTS, **sans changer aucun comportement audio**. Prépare B3 (`QwenTTSProvider`, seul futur
consommateur de l'émotion). Pur câblage, testable sans audio.

**Contrat (revu avant implémentation).** `BaseTTSProvider.synthesise(self, text, voice_id,
emotion: str | None = None) -> bytes` — paramètre optionnel en dernière position, défaut `None`,
100% rétrocompatible. Les call-sites le passent en mot-clé (`emotion=seg.emotion`).

**Livré.**
- Les 3 providers (`piper.py`, `elevenlabs.py`, `edgetts.py`) + l'abstraite (`base.py`) acceptent
  `emotion` et l'**ignorent** (no-op — aucun n'a de levier émotion).
- **2 call-sites câblés (pas 1 comme le sketch initial le disait)** : `_synthesise_book`
  (`app/workers/tasks.py:135`, livre entier) ET `synthesise_chapter`
  (`app/services/audio/chapter.py:44`, chapitre seul) transmettent `seg.emotion`.
- `ARCHITECTURE.md §2.2` — contrat mis à jour + note "no-op, seul Qwen3-TTS le consommera".

**Test-first.** `check_phase4.py` §6b (signature `emotion=None` sur base + 3 providers) + fake
`_s21_fake_tts` mise à niveau (piège : seul mock à signature fixe du repo) ; `check_phase8.py` §12
(no-op de bout en bout sur EdgeTTS mocké) ; `check_phase6.py` §3 (forwarding `emotion` vérifié via
`call_args.kwargs` — rouge avant câblage, vert après). 13/13 suites vertes, zéro régression.
Fichiers (10) : `app/services/tts/base.py`, `piper.py`, `elevenlabs.py`, `edgetts.py`,
`app/workers/tasks.py`, `app/services/audio/chapter.py`, `ARCHITECTURE.md`,
`tests/check_phase4.py`, `tests/check_phase6.py`, `tests/check_phase8.py`.

**Prochaine étape : B3** — `QwenTTSProvider` (4e provider, dépendances lourdes torch/CUDA dans
`requirements-qwen.txt`, `emotion` → param `instruct`). Nécessite PC + écoute. GO explicite requis.

### Étape B3 ✅ CLOSE (2026-06-22 codée, écoute finale 2026-06-27) — `QwenTTSProvider` (4e provider)

**Décision actée.** B3 s'écrit et se teste **exclusivement via mocks** — le vrai modèle Qwen3-TTS
n'est jamais chargé en CI. La vérification audio réelle (qualité FR + effet `instruct` +
justesse du mapping preset→genre) est **différée à une écoute manuelle par l'utilisateur** :
B3 reste un TODO permanent tant que cette écoute n'a pas eu lieu.

**Livré.**
- `app/services/tts/qwen.py` (nouveau) : `QwenTTSProvider.synthesise(text, voice_id,
  emotion=None)`. `_VOICE_MAP` (9 ids logiques → 9 presets Qwen `Vivian/Serena/Uncle_Fu/Dylan/
  Eric/Ryan/Aiden/Ono_Anna/Sohee`, mapping **best-effort non vérifié** — Qwen ne documente pas
  le genre des presets). `_import_qwen_deps()` isole `import torch` + `from qwen_tts import
  Qwen3TTSModel` dans sa propre fonction — **rien n'est importé au niveau module**, donc
  `import app.services.tts.qwen` ne nécessite jamais torch/qwen-tts installés (seul le 1er
  appel à `synthesise()` avec `TTS_PROVIDER=qwen` les requiert réellement). `_ensure_model()`
  charge le modèle une seule fois par instance (= une fois par tâche Huey), réutilisé ensuite.
  `emotion` → kwarg `instruct` de `generate_custom_voice` **seulement si non vide** (sinon
  absent, pas de `instruct=None`). Resampling 24000→22050 Hz via stdlib `audioop.ratecv`
  (zéro nouvelle dépendance). `_float_to_pcm16` convertit les floats `[-1,1]` du modèle en
  PCM16 sans numpy (stdlib `array` pur). Erreurs `ImportError` (deps absentes) et toute
  exception du modèle → `TTSError` avec message actionnable (`pip install -r
  requirements-qwen.txt`).
- `app/services/tts/factory.py` : branche `qwen` → import paresseux de `QwenTTSProvider`
  (cohérent avec les autres providers).
- `app/config.py` : `"qwen"` ajouté à `_VALID_TTS` ; bloc `if self.tts_provider == "qwen":`
  avec 4 variables à défaut (`QWEN_MODEL=1.7b`, `QWEN_LANGUAGE=French`, `QWEN_DEVICE=cuda:0`,
  `QWEN_ATTN=sdpa`). **Déviation assumée vs §2.4 (fail-fast) :** pas de validation de la
  présence réelle de torch/CUDA au démarrage — impossible sans importer torch, ce qui
  annulerait l'intérêt de l'import paresseux/dépendance optionnelle. Le défaut applicatif
  reste fail-fast (`TTSError` actionnable) au 1er appel `synthesise()` si les deps manquent.
- `requirements-qwen.txt` (nouveau) + `.env.example` (4 nouvelles vars `QWEN_*`) + `README.md`
  (section dédiée + tableau de config + ligne `check_phase15.py`) + `ARCHITECTURE.md §2.2`.

**Test-first.** `tests/check_phase15.py` (nouveau, 13 sections, mocks uniquement) : config
(défauts + override), **import du module sans torch/qwen_tts liés au niveau module** (vérifié
via `"torch" not in vars(qwen_mod)`, pas via trafic `sys.modules` — piège rencontré, voir
ci-dessous), factory, couverture + unicité de `_VOICE_MAP`, voice_id inconnu → `TTSError` avant
tout chargement modèle, `_float_to_pcm16` (clamp inclus), `_resample_to_output` (identité +
24000→22050), deps absentes → `TTSError` actionnable, happy path (modèle mocké) → WAV 22050 Hz
mono 16-bit valide, `emotion` transmis en `instruct` ssi non vide, modèle chargé une seule fois
sur 2 appels. **14/14 suites vertes** (13 existantes + nouvelle), zéro régression.

**⚠️ Piège rencontré et documenté (pas un bug applicatif, un piège de test).** Première version
du test utilisait `unittest.mock.patch.dict(sys.modules, {"torch": None, "qwen_tts": None})`
pour simuler un import bloqué. `patch.dict` restaure **tout le dict** `sys.modules` à son état
d'avant le `with` à la sortie — pas seulement les clés explicitement passées — ce qui purgeait
aussi `app.services.tts.qwen` (et transitivement `app.core.exceptions`) du cache après le bloc.
Conséquence : tout import ultérieur du module se faisait pour de vrai (rechargement complet,
**chargement réel du modèle Qwen3-TTS** pendant le test, téléchargement HuggingFace inclus) et
créait une **2e classe `TTSError` distincte** (le `except TTSError` du test ne matchait plus
l'exception réellement levée). Fix : abandon de la manipulation `sys.modules`, remplacée par une
assertion structurelle plus simple et plus sûre (`"torch" not in vars(qwen_mod)` après un import
normal) — teste la même propriété (import paresseux) sans aucun risque d'incohérence de cache.

**Pas de changement de schéma DB.** Pas de changement de contrat (signature `synthesise`
déjà posée en B2).

**Verdict d'écoute final (2026-06-27, utilisateur).** Les 3 conditions de clôture sont réunies :
- **Mapping `_VOICE_MAP` (preset→genre) : bon** — aucun remap nécessaire.
- **Qualité FR globale : variable** — certaines voix bonnes, d'autres avec un accent « british »
  perceptible (cohérent avec le constat du 2026-06-22 sur `neutral_0`/Aiden). Jugée **limite du
  catalogue de presets Qwen en français, acceptée** — pas un bug d'intégration/architecture.
- **Effet de l'`instruct` (émotion) : pas concluant** — pas systématiquement meilleur que sans.
  Ne bloque pas le clonage (qui utilise `generate_custom_voice` avec un échantillon de référence,
  pas `instruct`) ; l'émotion par réplique reste un levier incertain, à réévaluer séparément si
  elle redevient une priorité produit.

**B3 est désormais clos.** Le chantier clonage de voix (point 8 de la roadmap,
[[feature-roadmap-decisions]]) est débloqué — nécessitera un nouveau contrat (`Voice` entité
dynamique) à valider avant tout code (CLAUDE.md Niveau 3).

---

## Hors-Phase — Petits défauts relevés en clôture de Phase 13 (2026-06-21)

### ✅ Étape 2 — `error_message` stale après un retry réussi (2026-06-21)

**Bug.** `_analyze_book_impl` / `_generate_book_impl` / `_generate_chapter_impl`
(`app/workers/tasks.py`) remettaient `status` à un état "en cours" au démarrage mais ne
réinitialisaient jamais `error_message`. Un livre/chapitre `FAILED` puis relancé avec succès
gardait l'ancien message d'erreur en base : état contradictoire (`status=DONE` +
`error_message="ancienne erreur"`).

**Chemin atteignable confirmé.** Un chapitre `FAILED` peut être régénéré via
`POST /books/{id}/chapters/{n}/generate` (la route ne garde que `book.status==ANALYZED`, pas
`chapter.status` — re-dispatch déjà autorisé depuis Phase 7 Étape 3c). Le cas livre n'est pas
atteignable via l'API actuelle (pas de route retry-analyse ; `POST /books/{id}/generate` exige
`status==ANALYZED` strict, bloqué si `FAILED`) — corrigé par cohérence (même cause, 1 ligne).
Invisible dans le frontend actuel (`error_message` affiché seulement si `status==FAILED`,
`page.tsx:144/186`), mais exposé via l'API (`BookResponse`/`ChapterResponse.error_message`).

**Fix.** `app/workers/tasks.py` : `book.error_message = None` / `chapter.error_message = None`
ajoutés aux 3 points où le statut passe à `PROCESSING`/`GENERATING`. Aucun changement de contrat.

**Test-first.** `tests/check_phase7.py` sections 24-26 (nouvelles) : pré-remplissage d'un
`error_message` "ancien" sur livre/chapitre, relance happy path → assert statut terminal correct
**et** `error_message is None`. 13/13 suites vertes (26/26 sections check_phase7), zéro régression.

Fichiers (2) : `app/workers/tasks.py`, `tests/check_phase7.py`.

### ✅ Étape 3 — Audio orphelin à la suppression d'un livre (2026-06-21)

**Bug.** `delete_book` (`app/api/routes/books.py`) ne supprimait que `book.source_path`. Deux
emplacements de fichiers générés restaient orphelins sur disque :
- WAV/MP3 du livre entier (`book.audio_path`/`book.mp3_path`) — écrits à côté de `source_path`
  (même dossier `data/`, juste une autre extension).
- `data/{book_id}/` — couverture (`cover.<ext>`) + 1 WAV par chapitre (`ch{position}.wav`).

Les lignes DB (`Chapter`/`Character`) étaient déjà nettoyées via le cascade SQLModel existant
(`cascade="all, delete-orphan"`) — seul le disque fuyait.

**Fix.** `delete_book` lit aussi `audio_path`/`mp3_path` avant le `session.delete`, les supprime
s'ils existent (même boucle que `source_path`), puis `shutil.rmtree(DATA_DIR / str(book_id),
ignore_errors=True)`. Synchrone, dans la même requête `DELETE /books/{id}` — pas de tâche de fond
ni de nettoyage différé. Aucun changement de contrat (signature/schéma).

**Test-first.** `tests/check_phase2.py` section 6 (HTTP routes) étendue : seed un livre avec
`audio_path`/`mp3_path` réels + `data/{id}/` peuplé (cover + 1 WAV chapitre) → `DELETE` → assert
les 4 chemins absents du disque (en plus du contrat HTTP existant : 204 puis 404). 13/13 suites
vertes, zéro régression.

Fichiers (2) : `app/api/routes/books.py`, `tests/check_phase2.py`.

---

## Auto-convert ✅ (2026-06-22, commit `f2d90a1`) — casting automatique après analyse

**Pourquoi.** Roadmap [[feature-roadmap-decisions]] point 2 : aujourd'hui le livre s'arrête à
`ANALYZED` et l'utilisateur doit revenir manuellement sur la page livre puis cliquer « Casting ».
Option retenue (sur 2 proposées) : **frontend pur**, pas de case « convertir automatiquement » ni
de colonne DB — un bouton/flux qui ouvre directement la confirmation après upload.

**Livré.** Frontend pur (2 fichiers, 0 backend, 0 nouvelle dépendance, 0 changement de contrat).
- `frontend/src/app/page.tsx` : après `uploadBook`, navigation directe vers
  `/books/{id}?casting=auto` (`useRouter().push`, `next/navigation`) au lieu d'un simple `refresh()`
  de la bibliothèque.
- `frontend/src/app/books/[id]/page.tsx` : `autoFlag` lu une seule fois via un **initialiseur
  paresseux de `useState`** (`new URLSearchParams(window.location.search).get("casting") ===
  "auto"`, gardé par `typeof window !== "undefined"` pour la passe SSR) — pas un effet, pour ne
  pas déclencher la règle `react-hooks/set-state-in-effect`. Un effet dépendant de
  `[autoFlag, book?.status, autoOpened, bookId]` ouvre `CastingModal` (inchangée) dès que
  `book.status === "ANALYZED"`, une seule fois (garde `autoOpened`), puis nettoie l'URL
  (`history.replaceState`). Le `setCastingOpen`/`setAutoOpened` sont différés dans
  `Promise.resolve().then(...)` (même contournement que `refresh()` ailleurs dans ce fichier) pour
  rester hors du corps synchrone de l'effet. Message « Analyse en cours — le casting s'ouvrira
  automatiquement. » affiché pendant `PENDING`/`PROCESSING` si `autoFlag`.

**Test-first.** Pas de harness de test frontend (README). Vérification : `npm run build` +
`npm run lint` verts, puis **run réel complet** (uvicorn + worker Huey + Ollama qwen3:8b réel,
`tests/fixtures/test.epub`) : upload → `ANALYZED` (~45 s) → modale ouverte automatiquement avec
casting déjà rempli (Alice → female_1) → clic « Générer l'audio » → `DONE` → rechargement de la
page sans le paramètre confirmé **sans** réouverture de la modale (comportement manuel intact).

**Hors scope (explicite) :** pas de case « convertir automatiquement » (option 1, écartée), pas de
changement du chemin manuel (bouton « Casting » inchangé), pas de gestion du cas `FAILED` (l'effet
ne se déclenche que sur `ANALYZED`, l'erreur existante s'affiche normalement).

---

## Génération de tous les chapitres en un clic ✅ (2026-06-22)

**Pourquoi.** Roadmap [[feature-roadmap-decisions]] point 4 (confirmé prioritaire par
l'utilisateur) : aujourd'hui il faut cliquer « Générer » chapitre par chapitre, manuellement, un à
la fois. Manquait un seul déclencheur pour lancer tous les chapitres d'un coup ; le polling
existant capte ensuite les `GENERATING→DONE` un par un (Huey `-w 1` les traite séquentiellement de
toute façon).

**Contrat (revu avant implémentation).** Nouvelle route `POST /books/{book_id}/chapters/generate`
→ 202 + `list[ChapterResponse]`. Gardes identiques à `POST /chapters/{position}/generate` : 404
livre inconnu, 409 si `book.status != ANALYZED`. Dispatche `generate_chapter` (task Huey existante,
inchangée) pour chaque chapitre dont `status != DONE` (re-génère les `FAILED`, saute les `DONE`).
Zéro changement de schéma DB, zéro nouvelle dépendance — réutilise entièrement la mécanique
existante (Phase 7 Étape 3b).

**Livré.**
- `app/api/routes/books.py` — `trigger_all_chapters_generate`, placée juste avant `list_chapters`.
  Pas de conflit de routage avec `/{book_id}/chapters/{position}/generate` (nombre de segments de
  chemin différent — FastAPI les distingue sans ambiguïté quel que soit l'ordre de déclaration).
- `frontend/src/lib/api.ts` — `generateAllChapters(bookId)`.
- `frontend/src/app/books/[id]/page.tsx` — bouton « Générer tout l'audio » dans l'en-tête de la
  section Chapitres, visible si `book.status === "ANALYZED"` et qu'au moins un chapitre n'est pas
  `DONE` ; désactivé pendant l'appel. Réutilise le `reloadNonce` existant pour relancer le polling
  (même pattern que `handleGenerateChapter`).

**Test-first.** `tests/check_phase7.py` sections 27-29 (nouvelles) : 404 livre inconnu · 409 si
`status != ANALYZED` · happy path (3 chapitres dont 1 `DONE` et 1 `FAILED` → `generate_chapter`
appelé uniquement pour les 2 non-`DONE`, le `DONE` est sauté). 14/14 suites vertes, zéro
régression. `npm run build` + `npm run lint` verts.

**Vérification réelle.** uvicorn + worker Huey + Ollama `qwen3:8b` + EdgeTTS réels, upload
`tests/fixtures/test.epub` → `ANALYZED` (3 chapitres `PENDING`) → clic « Générer tout l'audio » →
`POST /books/{id}/chapters/generate` → 3× `generate_chapter` dispatchés → les 3 chapitres passent à
`DONE` (synthèse EdgeTTS réelle) → bouton disparaît (plus aucun chapitre non-`DONE`) → lecture audio
chapitre 1 confirmée sans erreur console. Livre de test supprimé après vérification.

**⚠️ Piège rencontré (outil de preview, pas un bug applicatif).** `preview_click` (clic par
sélecteur CSS) ne déclenchait pas le handler React du bouton (aucune requête réseau, aucun effet) —
cause non investiguée plus avant (possible mismatch coordonnées/scroll avec le rendu Turbopack).
Contournement : `element.click()` via `preview_eval`, qui a fonctionné immédiatement et confirmé le
flux de bout en bout. Sans incidence sur le code livré — symptôme propre à l'outillage de
vérification, pas au frontend.

**Hors scope (explicite) :** pas de % de progression intra-chapitre (par segment) — discuté dans
[[feature-roadmap-decisions]] point 4 comme optionnel/plus de travail, non demandé ici ; pas de
réassemblage à la demande du WAV/MP3 livre entier depuis les chapitres (point d'archi noté pour
plus tard dans la même mémoire).

---

## Phase 16 — Fusion de personnages proposée par le LLM ✅ (2026-06-22)

**Pourquoi.** Roadmap [[feature-roadmap-decisions]] point 5 : si le LLM nomme un même
personnage différemment selon le chapitre (« Mr Dursley » / « Vernon Dursley »), malgré la
persistance inter-chapitres (Phase 14 Étape A), il peut quand même fragmenter un personnage en
plusieurs `Character` distincts. Flux UX validé : le LLM propose des fusions, l'utilisateur
confirme (humain dans la boucle, jamais de fusion automatique sans contrôle — une fusion est
destructrice : réassignation de `Segment.character_id` + suppression d'un `Character`).

**Plan en 5 étapes (1 GO chacune), repris du même découpage que Phase 14 A→B3.**

### Étape 1 — Schéma DB
`app/core/enums.py` : `MergeSuggestionStatus` (PENDING/ACCEPTED/REJECTED). `app/models/entities.py` :
`CharacterMergeSuggestion` (book_id, survivor_character_id, merged_character_id, reason, status) +
relation cascade sur `Book` (cohérente avec `chapters`/`characters`). Une **paire** (survivant,
fusionné) par ligne — un groupe de 3 doublons donne 2 lignes partageant le même survivant. ⚠️
Supprimer `scriptvox.db` avant le 1er run (nouvelle table). Test-first : `tests/check_phase16.py`
(nouveau) §1-5 — import, enum, table créée par `init_db`, round-trip, cascade delete.

### Étape 2 — Contrat LLM `suggest_merges`
`app/services/llm/base.py` : `MergeSuggestion` (dataclass), `BaseLLMProvider.suggest_merges`
(abstrait), `MERGE_SYSTEM_PROMPT`, `_build_merge_prompt`, `_parse_merge_json` (dégradation bornée :
nom inconnu ou survivant==fusionné → ignoré avec WARNING, jamais de crash — même philosophie que
`_parse_llm_json`). `app/services/llm/ollama.py`/`gemini.py` : implémentation, fast-path `< 2`
personnages → `[]` sans appel réseau. §6-9 : prompt/parsing testés en isolation + fast-path vérifié
sur les deux providers réels (settings factices, zéro appel réseau déclenché).

### Étape 3 — Câblage worker
`app/workers/tasks.py` : en fin de `_analyze_book` (après la boucle sur tous les chapitres, le LLM
encore « chaud »), si ≥2 personnages détectés sur tout le livre → `provider.suggest_merges(...)` →
persistance des `CharacterMergeSuggestion`. **Décision actée** : calcul une seule fois pour tout le
livre (pas à la volée à l'ouverture de la modale), et **non bloquant** — un échec de l'appel LLM est
loggé et le livre passe quand même à `ANALYZED` (une suggestion de fusion est un confort, pas une
condition de réussite de l'analyse). §10-12 : happy path (suggestion persistée avec les bons ids),
échec LLM non bloquant (0 suggestion, `ANALYZED` quand même), `<2` personnages → jamais appelé.

### Étape 4 — API
`app/schemas/book.py` : `MergeSuggestionResponse` (ids + reason + status — **pas de noms**, le
frontend les résout depuis `/characters` qu'il a déjà en mémoire, évite une duplication de données).
`app/api/routes/books.py` : `GET /books/{id}/merge-suggestions` (ne renvoie que les `PENDING` — pas
d'usage pour l'historique résolu actuellement). `app/api/routes/merge_suggestions.py` (nouveau
router, monté sur `/merge-suggestions`) : `POST /{id}/accept` (réassigne les segments du personnage
fusionné vers le survivant, supprime le personnage fusionné, marque `ACCEPTED`) et `POST /{id}/reject`
(marque `REJECTED`, ne touche à rien d'autre). 404 id inconnu, 409 si déjà résolu.

**Bug rencontré et corrigé (pas dans le plan initial).** Sans `session.flush()` entre la
réassignation des segments et la suppression du personnage fusionné, SQLAlchemy rechargeait la
collection `merged_char.segments` depuis la DB (encore non flushée) pendant le traitement de la
suppression et écrasait `character_id` avec `NULL` (comportement par défaut de désassociation avant
suppression, sans cascade `delete` sur la relation `Character.segments`). Confirmé en échec sur le
test §14 avant le fix, vert après.

**Décision actée pendant l'implémentation.** Accepter une suggestion rejette automatiquement les
autres suggestions `PENDING` qui référencent le personnage supprimé (cas d'un groupe de 3+
doublons) — évite qu'une suggestion pointe vers un `Character` qui n'existe plus. Testé en §17.

§13-17 : 404/filtre PENDING-only sur le GET, accept happy path (segments réassignés + personnage
supprimé), 404/409 sur accept, reject (ne touche à rien), rejet automatique des suggestions caduques
d'un groupe.

### Étape 5 — Frontend
`frontend/src/lib/api.ts` : `MergeSuggestion` (type), `listMergeSuggestions`,
`acceptMergeSuggestion`, `rejectMergeSuggestion`. `frontend/src/components/CastingModal.tsx` :
nouvelle section « Fusions de personnages suggérées » affichée **avant** la liste de
personnages/voix (ordre actée dans la roadmap — pas de dépendance technique réelle, `assign_voices`
ayant déjà tourné avant l'ouverture de la modale ; chaque personnage a déjà sa propre voix, fusionner
réassigne juste les segments et supprime le personnage fusionné avec sa voix). Bouton « Tout
accepter » (séquentiel — un 409 sur une suggestion déjà auto-rejetée par effet de bord d'un accept
précédent est attendu et ignoré silencieusement, pas une vraie erreur) + boutons « Accepter »/« Rejeter »
par suggestion. Toute action de fusion recharge personnages + suggestions (`mergeReloadNonce`).

**Vérification réelle.** uvicorn + Huey + Ollama réels, upload `tests/fixtures/test.epub` →
`ANALYZED` (1 personnage réel détecté, fixture trop petite pour que le LLM produise un doublon
organique) → **2 personnages + 1 suggestion insérés manuellement en base** pour exercer l'UI
déterministiquement → modale ouverte : section fusion affichée avant la liste de voix, clic
« Accepter » → suggestion résolue côté backend, personnage fusionné disparu de la liste de voix,
zéro erreur console. Rejoué avec 2 suggestions simultanées + clic « Tout accepter » → les deux
résolues séquentiellement, les deux personnages fusionnés supprimés. Livre de test supprimé après
vérification.

**Piège outillage (déjà noté plus haut dans ce fichier, reconfirmé) :** `preview_click` par
sélecteur ne déclenche pas toujours le handler React — `element.click()` via `preview_eval`
fonctionne de manière fiable.

**Hors scope (explicite) :** pas d'UI pour consulter l'historique des suggestions résolues
(`ACCEPTED`/`REJECTED`) — la modale n'affiche que les `PENDING`, cohérent avec le filtre côté API.

---

## Frontend — Fondations UI ✅ (2026-06-22)

**Pourquoi.** Roadmap [[feature-roadmap-decisions]] point 1 : dette concrète identifiée
(`STATUS_COLOR` dupliqué, pattern bouton réécrit ~12 fois avec incohérences, panneau d'erreur
dupliqué 3×) avant que catalogue de voix / Qwen ne remodèlent les écrans les plus exposés
(modale Casting, vue chapitre). Cadré comme **refactor d'extraction sans changement visuel**
(zéro nouvelle dépendance, zéro contrat backend) — plan détaillé approuvé en amont,
voir mémoire `frontend-foundations-plan`.

**Livré (Étapes 0-5, 1 GO chacune) :**
- **Étape 0** — Baseline : 3 screenshots de référence (accueil, détail livre `ANALYZED`, modale
  Casting avec suggestion de fusion insérée manuellement en base), lint+build verts.
- **Étape 1** — `frontend/src/lib/status.ts` (`STATUS_COLOR` + `statusColor()`), dédupliqué de
  `BookCard.tsx` / `books/[id]/page.tsx`.
- **Étape 2** — `frontend/src/components/ui/StatusBadge.tsx`. Rend toujours un `<p>` (pas un
  `<span>` comme l'imaginait le plan) : le site header de page détail appliquait `mt-2`, qui aurait
  été ignoré en layout normal sur un élément inline — sans incidence dans les 2 autres sites
  (parents `flex`, le tag racine n'y change rien pour un flex item). Préflight Tailwind confirmé
  actif (`p { margin: 0 }`), donc aucun changement visuel.
- **Étape 3** — `frontend/src/components/ui/Button.tsx` (variant `primary`/`secondary`/`warning`,
  size `sm`/`md`/`lg`, `className` override). Migration des 5 boutons de `books/[id]/page.tsx`.
- **Étape 4** — Migration des 4 boutons de `CastingModal.tsx` vers `Button`.
- **Étape 5** — `frontend/src/components/ui/Alert.tsx` (`title?`, `children`, `className?`).
  Migration des 3 panneaux d'erreur (`page.tsx`, `books/[id]/page.tsx`, `CastingModal.tsx`).

**Bug réel trouvé et corrigé pendant l'implémentation (pas un simple écart cosmétique).**
Tailwind v4 ordonne les classes générées selon son échelle interne, **pas** selon l'ordre du
`className` HTML : un override `disabled:opacity-40` (ou `p-3`) concaténé en dernier dans le
`className` ne gagnait PAS sur le `disabled:opacity-50` (ou `p-4`) de base du composant — mesuré
via `preview_inspect`/`getComputedStyle` (`opacity: 0.5` au lieu de `0.4` attendu). **Fix** :
suffixe important `!` de Tailwind v4 (`disabled:opacity-40!`, `p-3!`) — revérifié après coup.
**Implication pour tout futur composant `ui/*` de ce projet** : un override de `className` qui
partage une propriété CSS avec une classe de base du composant doit utiliser le suffixe `!`,
sinon il est silencieusement ignoré. Ajouté aux pièges durables (mémoire `project-scriptvox`).

**Étape 6 (extraction `Modal.tsx`) explicitement abandonnée.** Décision (2026-06-22, discutée
avec l'utilisateur) : un seul modal existe dans toute l'app (`CastingModal`) — extraire une
coquille « réutilisable » sans second appelant pour valider la forme de l'API est une abstraction
spéculative (contraire à CLAUDE.md « ne pas designer pour des besoins hypothétiques »). Les futurs
consommateurs (pré-écoute point 6, édition de segment point 7) sont non démarrés et conditionnés à
une session audio. À reprendre quand un 2ᵉ modal réel sera construit — même effort plus tard, avec
un vrai 2ᵉ cas d'usage pour calibrer l'API.

**Incohérences détectées et listées (non corrigées, conformément au plan) :**
- `font-medium` → `font-semibold` sur "Casting" et "Générer" (page détail) — le composant `Button`
  n'a qu'un seul poids de police, le plan acceptait cet écart par avance.
- Boutons `variant="primary"` : texte désormais `text-white` (`rgb(255,255,255)`) explicite contre
  l'ancien héritage `text-gray-100` (`rgb(243,244,246)`) du `<main>` parent. Écart de 12/255 par
  canal, imperceptible sur fond vert — vérifié via `preview_inspect`, pas seulement à l'œil.

**Vérification.** `npm run lint` + `npm run build` verts à chaque étape. Les 3 écrans baseline
revérifiés pixel-identiques après chaque étape (upload réel `tests/fixtures/test.epub`, suggestion
de fusion insérée manuellement). Les 3 panneaux d'erreur testés via leurs vrais chemins de
déclenchement : backend arrêté (accueil), id de livre inexistant (page détail), `window.fetch`
patché temporairement via `preview_eval` puis restauré (CastingModal). Console sans erreur sur
tous les scénarios.

**Piège outillage reconfirmé (déjà noté en Phase 16, pas un bug applicatif)** : `preview_screenshot`
se bloque en timeout sur un serveur frontend déjà ouvert depuis un certain temps — `preview_stop` +
`preview_start` du serveur frontend résout systématiquement le problème.

Fichiers (9) : `frontend/src/lib/status.ts`, `frontend/src/components/ui/StatusBadge.tsx`,
`frontend/src/components/ui/Button.tsx`, `frontend/src/components/ui/Alert.tsx`,
`frontend/src/components/BookCard.tsx`, `frontend/src/app/page.tsx`,
`frontend/src/app/books/[id]/page.tsx`, `frontend/src/components/CastingModal.tsx`.

---

## Phase 17 — Modernisation UI (DA ElevenLabs) — EN COURS

> Après livraison complète de la roadmap fonctionnelle + onglet Voix, l'utilisateur a jugé l'app
> « encore un peu moche » et a demandé une passe de modernisation visuelle inspirée d'ElevenLabs
> (tokens chauds, rayons généreux, accent neutre + couleur réservée aux orbes). Détail complet
> (captures de référence, forks de direction tranchés, séquençage A→D) : mémoire
> `ui_modernization_plan_2026_06_24`. Tokens d'abord (Phase A), puis correctifs tactiques (B),
> player redesign (C), polish écran par écran (D).

### Phase A — Tokens de thème clair/sombre + migration

- **A1 ✅ (2026-06-24, commit `be02b3f`)** — Tokens CSS (`--color-background/surface/surface-2/
  border/foreground/muted/primary/primary-foreground`) + toggle clair/sombre. **Bug Tailwind v4
  sérieux trouvé+corrigé** : `@theme inline` figeait les couleurs à la compilation (mode correct
  pour `next/font`, faux pour des couleurs qui changent via `[data-theme]` à l'exécution) → passé
  en `@theme` classique. **2e bug sérieux** : l'App Router retire l'attribut `data-theme` de
  `<html>` ~0-500 ms après `window.load` (reproduit en build de production, cause précise non
  confirmée) → fix par `MutationObserver` auto-réparateur (`localStorage` = seule source de vérité).
- **A2 ✅ (2026-06-24, commit `17b9690`)** — Primitives partagées (`Button`, `Alert`,
  `UploadDropzone`, `PlayerBar`) migrées vers les tokens ; accent violet entièrement retiré des
  boutons. `StatusBadge` confirmé inchangé (couleurs sémantiques par statut, indépendantes du
  thème). Bug fluidité barre de lecture corrigé au passage (`step={1}` → `step="any"` sur le
  scrubber, anticipation de B1).
- **A3 ✅ (2026-06-25)** — Migration des pages restantes vers les tokens (même méthode, aucun
  nouveau piège technique — A1/A2 avaient déjà découvert/corrigé les 2 bugs sérieux ci-dessus).
  `bg-gray-*`/`text-gray-*`/`violet-*` → `bg-background`/`bg-surface`/`bg-surface-2`/
  `text-foreground`/`text-muted`/`border-border`/`bg-primary`. Couleurs sémantiques (erreur rouge,
  favori amber) laissées intactes. Un override littéral mort (`bg-gray-700 hover:bg-gray-600` sur
  le bouton "Rejeter", page livre) supprimé plutôt que retraduit — dupliquait déjà le style par
  défaut du variant `secondary` de `Button`. Vérifié dans les deux thèmes via capture réelle
  (Bibliothèque, page livre + Casting déplié, Voix, Paramètres). `npm run lint` + `npm run build`
  verts ; 15/15 suites backend sans régression (changement purement frontend).
  Fichiers (5) : `frontend/src/app/books/[id]/page.tsx`, `frontend/src/app/page.tsx`,
  `frontend/src/app/voix/page.tsx`, `frontend/src/app/parametres/page.tsx`,
  `frontend/src/components/BookCard.tsx`.

### Phase B — Correctifs tactiques

- **B1 ✅ (2026-06-25, commit `36600c6`)** — Badges drapeau+langue + symbole sexe (♂/♀) sur le
  catalogue de voix. `localeToFlag()` (emoji depuis le code pays BCP 47, inline car seul
  consommateur) + `GENDER_SYMBOL` (MALE/FEMALE seulement, rien pour NEUTRAL/UNKNOWN/null). Pas de
  badge "ton" — décision actée avec l'utilisateur (aurait demandé une nouvelle métadonnée sur
  l'entité `Voice`, hors périmètre). 100% frontend, 0 contrat. Vérifié lint + build + capture réelle
  2 thèmes + 15/15 suites backend.
  Fichier (1) : `frontend/src/app/voix/page.tsx`.

- **B-play ✅ (2026-06-25, commit `854c458`)** — Bouton play/pause du player remodernisé.
  `frontend/src/components/player/PlayerBar.tsx` : 36px→44px, `shadow-md`, `hover:scale-105` —
  aligne sur le même langage visuel que l'orbe Voix. 100% frontend, 0 contrat. Vérifié via
  `preview_inspect` (taille/ombre/couleur) dans les 2 thèmes + lint/build verts.
  Fichier (1) : `frontend/src/components/player/PlayerBar.tsx`.

- **B-orbes ✅ (2026-06-25, commit `0952468`)** — Couleur unique par voix + grain SVG sur le
  catalogue Voix. **Déviation du plan initial** : un hash déterministe brut de `voice_id` (DJB2,
  puis DJB2+constante de Knuth, puis finalizer Murmur-style) retombait systématiquement sur des
  paires de voix à 0-9° d'écart de teinte (quasi indiscernables à l'œil) sur ce catalogue de 9 ids
  très proches (`male_0`/`male_1`/`male_2`…) — testé et confirmé en plusieurs itérations via
  `preview_eval` avant d'abandonner l'approche hash pur. **Solution retenue** : assignation par
  angle d'or (`137.5077° × rang`) sur le tri alphabétique des `voice_id` — garantit ~20°+ d'écart
  minimum pour les 9 voix actuelles, se rééquilibre automatiquement si le catalogue grossit
  (clonage futur) plutôt que de risquer une collision figée. Calculé sur le catalogue complet (pas
  le sous-ensemble filtré par "Favoris"), donc une couleur de voix ne change pas selon le filtre.
  Grain : SVG `feTurbulence` statique (pas d'animation du bruit, perf), `mix-blend-mode: overlay`,
  opacité 0.35, partagé par toutes les orbes (même data URI). 100% frontend, 0 contrat.
  Fichiers (2) : `frontend/src/app/globals.css`, `frontend/src/app/voix/page.tsx`.

**Vérification (B-play + B-orbes).** `npm run lint` + `npm run build` verts après chaque étape.
Capture réelle navigateur (via `preview_*`) dans les 2 thèmes après chaque étape. 15/15 suites
backend sans régression (changement 100% frontend).

### Phase C — Player redesign ✅ (2026-06-26)

**Pourquoi.** Restyle du player (replié + déplié) inspiré de 2 captures fournies par l'utilisateur :
référence prioritaire pour couleurs/icônes = ElevenLabs (bandeau sombre horizontal, ligne de
progression fine avec labels, cluster signet/±15s/play/±15s/vitesse) ; référence secondaire pour
layout/disposition = mockup mobile (grande couverture, transport 5 boutons, rangée vitesse/
chapitres/signet). Restyle des 2 états déjà existants (Phase 11 Étape 5/6), pas une nouvelle
architecture. 3 étapes (1 GO chacune), 100% frontend, 0 contrat, 0 nouvelle dépendance.

**Décisions actées avant implémentation (clarifications utilisateur) :**
- Durée du skip : **15 s** (pas 30 s) — la référence prioritaire (ElevenLabs, couleurs/icônes)
  montre `±15`, la référence secondaire (layout) montre `±30` ; règle de priorité de l'utilisateur
  tranche en faveur de la première.
- Barre de progression en mode replié : **ligne fine avec labels temps écoulé/restant** (recommandé
  parmi 3 options proposées) plutôt qu'aucune barre (fidélité stricte à la capture 1) ou le scrub
  complet actuel inchangé.
- "Lu par X" (avatar narrateur, capture ElevenLabs) : **abandonné** — pas de donnée équivalente
  (livres multi-voix, pas de narrateur unique nommé).
- Titre incrusté sur la couverture (mockup mobile) : **abandonné** — la couverture est une vraie
  image d'éditeur, lui superposer du texte l'aurait dégradée ; texte affiché à côté (comme le fait
  la référence ElevenLabs).
- Bouton "Chapitres" : **pas un simple placeholder** — contrairement au signet, la donnée (liste +
  navigation prev/next) existe déjà depuis Phase 11 Étape 6 ; implémenté comme un vrai toggle.
- Bouton "Ajouter un signet" : **placeholder visuel désactivé** (pas de persistance serveur du tout
  aujourd'hui) — décision explicite de l'utilisateur, fonctionnalité différée à un chantier séparé.
- Double affichage temps restant (capture mockup : "1h15m restantes" + "-6:04") : **simplifié** à
  `temps écoulé | temps total`, déjà disponible — éviter une nouvelle plomberie de durée totale
  livre pour un gain d'affichage marginal.

**Étape 1 ✅ — Boutons ±15s + restyle de l'état replié.** `seek(currentTime ± 15)` (nouvelle
fonction `skip`, réutilise `seek` existant, 0 changement de contrat `PlayerProvider`). Layout
repensé : couverture miniature (36×36) + titre à gauche (clic = déplie) ; cluster centré
`[signet placeholder] [-15s] [▶/⏸ 44×44] [+15s] [vitesse]` ; fermer à droite. Ligne de progression
fine (`h-1`) au-dessus de la rangée principale, avec labels `temps écoulé` / `-temps restant` en
petite taille (`text-[10px]`), remplace le scrub complet en mode replié.

**Étape 2 ✅ — Restyle de l'état déplié.** Grande couverture (192×192, `sm:` 192×192, image propre
sans texte incrusté) + titre livre/chapitre en dessous (`chapterLabel` calculé depuis
`chapters.find(...)`, fallback `Chapitre {position}`). Scrub complet (`temps écoulé | curseur |
temps total`) à la place de la ligne fine quand déplié. Rangée transport 5 boutons alignés
(`⏮ prev chapitre`, `↺15`, `▶/⏸` agrandi à 56×56, `15↻`, `⏭ next chapitre` — réutilise
`hasPrev`/`hasNext`/`playChapter` de Phase 11 Étape 6 inchangés). **Déviation pour éviter la
duplication visuelle** : en mode déplié, la rangée du bas (mini-barre) se réduit à
titre (replie au clic) + fermer — signet/±15/play/vitesse ne sont affichés qu'une fois, dans le
panneau déplié (plus grand), pas dupliqués dans la mini-barre en dessous.

**Étape 3 ✅ — Rangée utilitaire + toggle Chapitres.** `UtilBlock` (helper local au composant,
icône+label, 3 usages réels — pas une abstraction spéculative). `Vitesse` : bouton cyclique
(`1× → 1.25× → 1.5× → 2× → 0.5× → 1×`, `cycleRate` via `RATES.indexOf`) remplace le `<select>` du
panneau déplié. `Chapitres` : vrai toggle (`chaptersOpen`, nouvel état) — la liste des chapitres
(existante depuis Phase 11 Étape 6) est masquée par défaut en mode déplié, apparaît/disparaît au
clic, aria-label inversé. `Signet` : placeholder désactivé (`opacity-40`, `cursor-not-allowed`),
comme décidé.

**Test-first.** Pas de harness de test frontend (cf. Phase 11). Vérification : `npm run lint` +
`npm run build` verts à chaque étape ; structure/tailles/couleurs confirmées via
`preview_snapshot`/`preview_inspect`/`preview_eval` (play 44×44 replié puis 56×56 déplié, skip
±15s 32×32 puis 36×36, couverture 36×36 puis 192×192, signet désactivé, toggle chapitres 0→20
items, cycle vitesse 1.25×→1.5× sur clic isolé) dans les 2 thèmes clair/sombre — couleurs
cohérentes avec les tokens déjà validés en Phase A/B (`bg-primary`/`text-primary-foreground`/
`text-muted`/`bg-surface-2`). 15/15 suites backend vertes à chaque étape (changement 100%
frontend, attendu).

**⚠️ Piège outillage rencontré (pas un bug applicatif).** `preview_screenshot` a systématiquement
timeout toute la session (y compris après redémarrage du serveur frontend, correctif qui avait
fonctionné en Phase B) — vérification faite uniquement par inspection DOM/CSS
(`preview_snapshot`/`preview_inspect`/`preview_eval`), pas de capture visuelle directe. Distinct du
piège déjà documenté en Phase B (celui-là se corrigeait par un redémarrage du serveur).

**Autre piège outillage (déjà documenté en Phase 16, reconfirmé) :** cliquer plusieurs fois de
suite sur un bouton dans une boucle JS synchrone (`preview_eval`) ne laisse pas React re-render
entre les clics → les fermetures (`cycleRate`) restent obsolètes pendant toute la boucle, un seul
changement d'état net au lieu de N. Confirmé en isolant les clics un par un. Pas un bug du code
applicatif — un vrai utilisateur cliquant normalement laisse React re-render entre deux clics.

Fichier (1) : `frontend/src/components/player/PlayerBar.tsx`.

**Hors scope (explicite)** : persistance serveur du signet (nouvelle feature, chantier séparé) ;
durée totale du livre / temps restant agrégé multi-chapitres (simplifié à la durée de la piste
courante, cf. décisions ci-dessus).

### Hors-Phase — Clic en dehors du player déplié = repli ✅ (2026-06-26)

**Pourquoi.** Retour utilisateur après livraison de Phase C : aucune affordance évidente pour
réduire le player une fois déplié — seul un clic sur le petit bouton titre (`▾ {titre}`, barre du
bas) fonctionnait, mais ce n'était pas l'attendu (clic en dehors du bandeau, comme un panneau/sheet
classique).

**Livré.** `rootRef` (`useRef<HTMLDivElement>`) sur le conteneur racine `.fixed.bottom-0` +
`useEffect` (actif seulement si `expanded`) qui écoute `mousedown` sur `document` et appelle
`setExpanded(false)` si la cible du clic est hors de `rootRef.current` (`Node.contains`). Listener
retiré au démontage/au repli. Zéro changement de contrat, 100% frontend.

**Vérifié.** `npm run lint` + `npm run build` verts. Comportement testé via `dispatchEvent` réel
(`mousedown` bulle, pas un simple `.click()` synthétique sur un bouton) : clic en dehors du bandeau
(`<main>`) → repli confirmé ; clic dedans (sur la couverture) → reste déplié (pas de faux positif).
15/15 suites backend vertes (changement 100% frontend).

Fichier (1) : `frontend/src/components/player/PlayerBar.tsx`.

### Hors-Phase — Fix régression : cluster centré collé à droite en mode replié ✅ (2026-06-27)

**Bug.** Capture utilisateur après livraison de Phase C : le cluster `[signet][-15][play][+15]
[vitesse]` apparaissait collé contre le bord droit de la barre repliée (juste avant le bouton
fermer), au lieu d'être centré au milieu de l'écran comme prévu dans le plan initial et la
référence ElevenLabs. Plus visible avec un titre court (ex. aperçu de voix), où le décalage saute
aux yeux.

**Cause racine.** La rangée du bas utilisait `flex` avec `flex-1` sur le bouton titre : ce dernier
grossit pour occuper tout l'espace disponible, ce qui pousse mécaniquement le cluster (qui le suit
immédiatement dans le flux) contre le bord droit — un `flex-1` centre l'élément suivant *dans
l'espace restant*, pas sur la largeur totale de la barre. Le centrage visé nécessite que le cluster
soit centré indépendamment de la largeur du titre à gauche et du bouton fermer à droite.

**Fix.** Rangée du bas passée de `flex` à `grid grid-cols-[1fr_auto_1fr]` : colonne gauche (1fr,
`justify-self-start`) = couverture+titre ; colonne centrale (`auto`, `justify-self-center`) =
cluster, garantie centrée sur la largeur totale de la grille quelles que soient les largeurs des
2 autres colonnes ; colonne droite (1fr, `justify-self-end`) = fermer. **Piège évité** : la colonne
centrale doit toujours être présente dans le DOM (même vide en mode déplié, où le cluster
n'existe pas) — sinon le placement automatique de grille décale le bouton fermer en colonne 2 au
lieu de la colonne 3 quand l'élément central est complètement omis du rendu (`{cond && (...)}` au
niveau de l'élément racine plutôt qu'à l'intérieur d'un conteneur toujours rendu).

**Vérifié.** `npm run lint` + `npm run build` verts. Centrage confirmé par calcul géométrique réel
(`getBoundingClientRect`) : centre du cluster = centre exact de la barre (645px/645px sur une
largeur de 1289px), indépendamment de la longueur du titre. Capture réelle à l'appui. État déplié
revérifié sans rupture (colonne centrale vide, fermer toujours à droite). 15/15 suites backend
vertes (changement 100% frontend).

**Découverte annexe pendant le diagnostic initial (pas un bug de ce fix) :** le symptôme rapporté
en premier lieu ("curseur de progression collé à droite, durée 0:00") était en réalité dû à
`data/1/ch1.wav` corrompu (144 octets, chunk audio déclaré à 0 — reliquat d'un test antérieur),
pas à un bug du player. Régénéré via `POST /books/1/chapters/1/generate` (worker Huey démarré pour
l'occasion) pour confirmer le bon fonctionnement avec un fichier audio réel. Le VRAI bug restant
(celui corrigé ici) est apparu seulement après, sur une capture où l'utilisateur testait un aperçu
de voix (titre court, sans rapport avec ce fichier audio).

Fichier (1) : `frontend/src/components/player/PlayerBar.tsx`.

---

### Phase D — Polish écran par écran (à venir, pas encore cadrée)

Cartes Biblio, page livre, grille Voix, Paramètres.

---

## Échantillons d'écoute B3 générés (2026-06-22 soir) — verdict rendu le 2026-06-27, B3 close

**Pourquoi.** B3 (`QwenTTSProvider`, voir Phase 14 ci-dessus) restait codé mais non clos : aucune
écoute réelle n'avait validé la qualité FR, l'effet de l'`instruct`, ni le mapping `_VOICE_MAP`
(preset Qwen → genre, deviné). L'utilisateur prévoyait une vérification audio le soir même mais
n'avait pas encore accès à son PC au moment de la demande.

**Livré (préparation, pas une clôture).** `tests/spike_qwen_b3_listening.py` (nouveau, hors suite
de régression) appelle le **vrai** `QwenTTSProvider.synthesise()` de production (pas le SDK Qwen
brut comme le spike du 2026-06-20) — valide donc aussi le chemin d'intégration réel
(`resolve_voice`/`_VOICE_MAP`, resampling 24000→22050 Hz). `ollama stop qwen3:8b` appelé en
best-effort avant chargement (VRAM libre confirmée via `nvidia-smi` avant lancement : 9,4/10 Go).
17 WAV générés avec succès (exit 0) dans `Ebook/qwen_b3_listening/` (gitignoré) — 9 `voice_<id>.wav`
(même phrase neutre sur les 9 voice_id, pour juger `_VOICE_MAP`) + 8 `emotion_NN_<label>_<sans|avec>
_instruct.wav` (4 émotions × `female_1`, pour juger l'effet de l'`instruct`). Tous vérifiés
mono/16-bit/22050 Hz, 2,5-4,6 s. Modèle chargé en 89 s puis 8-13 s/réplique (cohérent avec le spike
précédent). **Envoyés directement à l'utilisateur via `SendUserFile`** pour écoute le soir même,
sans dépendre d'un nouvel accès à la machine.

**Verdict rendu (2026-06-27)** : mapping `_VOICE_MAP` bon (aucun remap) ; qualité FR variable
(accent « british » sur certaines voix, acceptée comme limite de catalogue de presets) ; `instruct`
pas concluant (n'améliore pas systématiquement, ne bloque pas le clonage). Détail → Phase 14 §B3
ci-dessus et mémoire `tts-emotion-qwen3-direction`. **B3 close** — chantier clonage (point 8
roadmap) débloqué.

---

## Piste candidate (non tranchée) — TTS expressive Qwen3-TTS local

> Spike fait (2026-06-20). Voir mémoire `tts-emotion-qwen3-direction`. Décision encore ouverte — en
> attente du ressenti d'écoute (qualité FR + effet `instruct`).

**Contexte (vérifié 2026-06-20).** Qwen3-TTS est désormais open-weights (Apache 2.0, sorti janv. 2026),
FR confirmé, émotion par réplique pilotée par un paramètre `instruct` (langage naturel) — c'est *le*
levier pour la fonctionnalité « émotion par réplique » souhaitée.

**Cadrage : AJOUTER, pas remplacer.** 4ᵉ provider `QwenTTSProvider` (`TTS_PROVIDER=qwen`) dans le
Strategy Pattern (§2.2), import paresseux de torch dans la factory. **EdgeTTS reste le défaut** (zéro
setup, pas de GPU, pas de 4,5 Go à télécharger).

### Spike de faisabilité ✅ (2026-06-20) — `tests/spike_qwen_tts.py`

Modèle 1.7B, `attn=sdpa` (pas de FlashAttention sous Windows). 8 répliques FR × 2 (avec/sans
`instruct`) = 16 WAV générés dans `Ebook/spike_qwen/` (gitignoré, à écouter). Zéro erreur.

| Métrique | Mesure |
|---|---|
| Chargement modèle | 78,1 s |
| VRAM modèle | 4,18 Go (pic génération 4,37 Go) — mieux que les 6-8 Go estimés en ligne |
| Temps moyen/réplique | 11,46 s (min 7,72 / max 17,10) |
| Repère EdgeTTS réel | ~1,02 s/réplique (164 segments / 2 min 48 s, Étape 6 ci-dessus) |
| **Ratio** | **×11,2 plus lent qu'EdgeTTS** |
| Sample rate retourné | 24 000 Hz (EdgeTTS = 22 050 Hz, voir risque ci-dessous) |

**Mise à l'échelle** : chapitre 3 HP (164 segments) → ~31 min en Qwen3-TTS vs 2 min 48 s en EdgeTTS.

**Cohabitation VRAM — tranchée par le raisonnement, pas par un test de stress.** Le pipeline est
séquentiel par construction (analyse → `ANALYZED` → action explicite « Générer » → TTS, potentiellement
minutes/heures plus tard) et Huey tourne avec `-w 1` (jamais deux tâches en parallèle). Il n'y a donc
**aucun besoin réel** que `qwen3:8b` et Qwen3-TTS soient résidents en VRAM en même temps. Le seul risque
est un accident de timing via le `keep_alive` Ollama (~5 min) si on clique Générer juste après l'analyse
— et ça se corrige en une ligne (`ollama stop qwen3:8b` ou `keep_alive=0` au début de l'étape TTS), pas
en espérant que les deux tiennent ensemble sur les 10 Go de la carte. **Pas de stress test fait ni
nécessaire.**

**Risques restants (mis à jour) :**
- **Perf ×11** confirmée ci-dessus — à peser contre le bénéfice qualité/émotion une fois l'écoute faite.
- **Sample rate 24 000 Hz ≠ 22 050 Hz EdgeTTS** : `assemble_wav` (Étape 3, Phase 5) lève `ValueError` si
  les segments d'un même livre n'ont pas le même framerate. Un `QwenTTSProvider` réel devrait resampler
  vers 22 050 Hz à la frontière du provider (comme EdgeTTS le fait déjà via `miniaudio`), pas changer
  l'assembleur.
- Dépendances lourdes (torch CUDA) — viole « no surprise dependencies » → justifié seulement si
  l'émotion est retenue après écoute.
- Contrat : exploiter l'émotion = ajouter un param `instruct`/`emotion` à `synthesise(text, voice_id)`
  (+ champ émotion sur `Segment`, + extraction côté prompt LLM). **Revue humaine obligatoire.**

**Prochaine étape** : écoute des 16 WAV par l'utilisateur (qualité FR + effet réel de l'`instruct`) →
décision go/no-go sur le chantier émotion (contrat + dépendances).

---

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

---

## Phase 18 — Clonage de voix (point 8 roadmap) — EN COURS

> B3 close (2026-06-27) → clonage débloqué. Spike Étape 0 validé : modèle Base = 4.20 Go,
> x-vector only mode, ~11 s/phrase, 4 voix FR + 1 EN. Contrat `Voice` dynamique approuvé avant
> implémentation (CLAUDE.md Niveau 3). Détail spike et décisions VRAM : mémoire
> `tts-emotion-qwen3-direction`.

### Étape 1 ✅ (2026-06-27) — Contrat Voice dynamique (schemas + base TTS)

**Livré.**
- `app/schemas/voice.py` : `VoiceResponse` + champ `has_reference_audio: bool = False` (calculé
  depuis `Voice.reference_audio_path is not None`) ; nouvelle classe `VoiceCreate(name, gender?)`.
- `app/services/tts/base.py` : `BaseTTSProvider.synthesise` += paramètre optionnel
  `reference_audio_path: str | None = None` — 100% rétrocompatible (les 4 providers existants
  n'ont pas encore été mis à jour, ils seront ajustés en Étape 2).

**Test-first.** `tests/check_phase17.py` 9/9 sections : imports, VoiceCreate validation,
`has_reference_audio` défaut/True, `from_attributes` préservé, signature `BaseTTSProvider`,
rétrocompat call-site sans/avec `reference_audio_path`. 16/16 suites sans régression.

Fichiers (3) : `app/schemas/voice.py`, `app/services/tts/base.py`,
`tests/check_phase17.py`.

### Étape 2 ✅ (2026-06-27) — Mise à jour des 4 providers TTS

**Livré.**
- `edgetts.py`, `piper.py`, `elevenlabs.py` : `reference_audio_path: str | None = None` ajouté,
  no-op (ces providers n'ont pas de levier clone).
- `qwen.py` : logique complète de clonage. Nouveau `_MODEL_IDS_BASE` (Base checkpoints) ;
  `_load_ref_audio(path)` charge MP3/WAV/FLAC via miniaudio + numpy → float32 ; `_ensure_base_model()`
  charge le checkpoint Base en déchargeant d'abord le CustomVoice (swap séquentiel VRAM) ;
  `synthesise` dispatche sur `reference_audio_path` : clone → `generate_voice_clone(...,
  x_vector_only_mode=True)` ; preset → `generate_custom_voice(...)` inchangé.
  `self._base_model` ajouté à l'état de l'instance (jamais chargé si voix catalogue uniquement).

**Test-first.** `tests/check_phase17.py` étendu à 12 sections (+3) : signature des 4 providers
(section 10) ; chemin clone WAV valide + `generate_voice_clone` appelé (section 11) ; swap
CustomVoice→Base vérifié (section 12). 16/16 suites sans régression.

Fichiers (5) : `app/services/tts/edgetts.py`, `piper.py`, `elevenlabs.py`, `qwen.py`,
`tests/check_phase17.py`.

### Étape 3 ✅ (2026-06-27) — Pipeline (call-sites)

**Livré.**
- `app/services/audio/chapter.py` : import `Voice` ajouté ; avant la boucle de synthèse, une
  requête par `voice_id` unique (`Voice.voice_id == vid`) construit `ref_path: dict[str, str | None]` ;
  `tts.synthesise` reçoit `reference_audio_path=ref_path.get(voice_id)`.
- `app/workers/tasks.py` (`_synthesise_book`) : même pattern à l'intérieur du bloc session existant ;
  `Voice` ajouté à l'import local ; `provider.synthesise` reçoit `reference_audio_path=…`.
- `tests/check_phase4.py` : `_s21_fake_tts` mis à niveau (`reference_audio_path=None`) — c'était le
  seul mock à signature fixe du repo (piège B2 déjà documenté).

**Test-first.** `tests/check_phase17.py` étendu à 14 sections (+2) : lookup réel en DB in-memory
avec `Voice.reference_audio_path` set (section 13) et absent (section 14). 16/16 suites vertes.

Fichiers (4) : `app/services/audio/chapter.py`, `app/workers/tasks.py`,
`tests/check_phase17.py`, `tests/check_phase4.py`.

### Étape 4 ✅ (2026-06-27) — API REST voix

**Livré.**
- `POST /voices` (201) : upload multipart (`file` + `name` + `gender?`) ; slug dérivé du nom via
  `_name_to_slug` ; fichier sauvé dans `data/voices/{slug}/ref.{ext}` ; `Voice(kind=CLONED,
  reference_audio_path=…)` persisté. 409 sur slug dupliqué.
- `DELETE /voices/{voice_id}` (204) : supprime le fichier de référence + dossier parent si vide +
  la ligne `Voice` en DB. 404 si inconnu, 403 si `kind=CATALOGUE` (on ne peut pas supprimer une
  voix catalogue).
- `GET /voices` : `has_reference_audio=voice.reference_audio_path is not None` maintenant peuplé.
- `GET /{voice_id}/sample` : valide désormais via la DB (plus la liste statique
  `list_catalogue_voices()`) → supporte les voix CLONED ; passe `reference_audio_path` à
  `provider.synthesise` (le clonage fonctionne avec `TTS_PROVIDER=qwen`).
- `PATCH /{voice_id}` : `has_reference_audio` ajouté à la réponse (via `_voice_to_response` helper
  qui centralise la construction de `VoiceResponse`).

**Limite connue.** L'endpoint sample sur une voix CLONED ne fonctionne que si
`TTS_PROVIDER=qwen` — les autres providers ignorent `reference_audio_path` et ne savent pas
résoudre un slug de voix clonée dans leur propre mapping.

**Test-first.** `tests/check_phase17.py` étendu à 19 sections (+5) : POST happy path (section 15) ;
POST doublon 409 (16) ; DELETE CLONED 204 (17) ; DELETE CATALOGUE 403 (18) ; GET
`has_reference_audio` (19). 16/16 suites sans régression.

Fichiers (2) : `app/api/routes/voices.py`, `tests/check_phase17.py`.

### Étape 5 ✅ (2026-06-27) — Frontend

**Livré.**
- `frontend/src/lib/api.ts` : `has_reference_audio: boolean` ajouté à `VoiceSummary` ;
  `createVoice(name, gender, file)` → `POST /voices` multipart ; `deleteVoice(voiceId)` →
  `DELETE /voices/{voiceId}`.
- `frontend/src/app/voix/page.tsx` : bouton "+ Cloner une voix" ouvre un formulaire inline
  (nom, genre optionnel, sélecteur de fichier MP3/WAV/FLAC) → appelle `createVoice`, ajoute la
  voix à la liste sans rechargement. Voix CLONED : badge "🎙 cloné" sous l'orbe + bouton ×
  (coin bas-droit de l'orbe) → `deleteVoice` avec confirmation `window.confirm`. TypeScript
  `tsc --noEmit` : 0 erreurs, HMR compilé ✓.
- `frontend/src/app/books/[id]/page.tsx` : le `<select>` de casting sépare désormais les voix
  catalogue (options plates) des voix clonées (`<optgroup label="— Voix clonées —">`) ; le label
  affiche désormais `v.name` (vs `v.id` avant, identique pour le catalogue, plus lisible pour les
  clones).

**Limite connue (inchangée).** La synthèse d'un aperçu de voix clonée n'est opérationnelle
qu'avec `TTS_PROVIDER=qwen`.

Fichiers (3) : `frontend/src/lib/api.ts`, `frontend/src/app/voix/page.tsx`,
`frontend/src/app/books/[id]/page.tsx`.

---

## Idée différée — Filtres dans le catalogue de voix

**Idée (2026-06-27).** Ajouter dans la page Voix (`/voix`) des filtres par :
- genre (`MALE` / `FEMALE` / `NEUTRAL`)
- langue / locale (ex. `fr-FR`, `en-GB`)
- type de voix (`CATALOGUE` / `CLONED`)
- éventuellement : modèle TTS (`edgetts`, `piper`, `qwen`, …)

Les données sont déjà présentes en base (`Voice.gender`, `Voice.locale`, `Voice.kind`).
À cadrer après livraison complète de Phase 18 (les voix clonées + la locale EN de David
Attenborough rendent les filtres immédiatement utiles).

---

## Phase 19 — Reprise d'analyse après arrêt/plantage ✅ (2026-06-30, commit `d3a4229`)

**Pourquoi.** Avant cette phase, ré-analyser un livre `FAILED` (arrêté volontairement via
`/stop` ou planté après les 3 retentatives LLM) effaçait systématiquement tous les chapitres,
segments et personnages déjà acquis et repartait de zéro. Sur un livre de 21 chapitres
(~43 min), perdre la progression à chaque interruption était pénalisant.

**Contrat (revue humaine faite avant implémentation, aucune migration DB).**
- `POST /books/{id}/analyze?force=true` (query param optionnel, défaut `False`).
- `analyze_book(book_id, force=False)` (tâche Huey), `_analyze_book_impl(book_id, force=False)`.
- `_analyze_book(book_id, chapter_data, engine, resume=False, already_done=0)`.

**Livré.**
- `app/workers/tasks.py` : le statut du livre *avant* l'appel (capturé avant l'écrasement en
  `PROCESSING`) détermine le mode — `FAILED` + `force=False` → **reprise** (pas de re-parse
  EPUB, saute les chapitres qui ont déjà des `Segment` en base, `char_map` reconstruit depuis
  les `Character` existants) ; `PENDING`, `ANALYZED`/`DONE`, ou `force=True` → comportement
  inchangé (purge complète + re-parse EPUB). Le marqueur "chapitre déjà fait" = "a un segment
  en base", donc **zéro nouvelle colonne**. Progression recalculée sur le total de chapitres
  (`already_done + i + 1) / total`), pas juste les chapitres restants.
- `app/api/routes/books.py` : `force: bool = False` sur `trigger_analyze`.
- `frontend/src/app/books/[id]/page.tsx` : bouton **"Reprendre l'analyse"** (au lieu
  d'"Analyser") sur un livre `FAILED`, avec icône ⚠️ (tooltip = message d'erreur réel) **sauf**
  si l'arrêt était volontaire (`error_message === "Arrêté par l'utilisateur."`, comparaison de
  chaîne — pas de nouvelle colonne booléenne).

**Test-first.** `tests/check_phase19.py` (nouveau, 4 sections) : signatures ; `_analyze_book`
préserve les `Character` existants en `resume=True` ; pipeline réel `_analyze_book_impl` en
reprise (saute le chapitre déjà segmenté, `EpubParser.parse` patché pour lever si appelé,
`known_characters` repris de la DB) ; pipeline réel `force=True` (purge tout malgré `FAILED`,
re-parse confirmé). **17/17 suites vertes, zéro régression** (fix mineur dans
`check_phase3.py` : le provider factice de la section 9 ne connaissait pas les nouveaux
paramètres `resume`/`already_done` de `_analyze_book` — alignement de signature, aucun
changement de comportement testé).

**Vérifié en conditions réelles** (preview + livre de test temporaire créé/supprimé en base) :
les deux cas (vrai plantage vs arrêt utilisateur via le vrai endpoint `/stop`) affichent
correctement le bouton et l'icône conditionnelle. `npm run build` + `npm run lint` verts.

Fichiers (5) : `app/api/routes/books.py`, `app/workers/tasks.py`,
`frontend/src/app/books/[id]/page.tsx`, `tests/check_phase3.py`, `tests/check_phase19.py`.

---

## Phase 20 — Filtres (Voix + Bibliothèque) ✅ (2026-06-30, commits `33332e2`, `595cb55`, `62531c8`)

**Pourquoi.** Lot D de la roadmap 2026-06-30 (quick win) : filtres dans l'onglet Voix, étendu
par l'utilisateur à un filtre sur la Bibliothèque (statut, modèle TTS, genre).

### D1 — Filtres Voix ✅ (commit `33332e2`)
`frontend/src/app/voix/page.tsx` : 2 sélecteurs (Genre, Type catalogue/cloné), composables avec
le filtre Favoris existant. Frontend pur.

### D2 — Champ `Book.genre` + tag manuel ✅ (commit `595cb55`)

**Constat (vérifié, 2026-06-30).** Les EPUB réels (HP T01/T02) n'ont **aucune métadonnée
`dc:subject`** exploitable (`book.get_metadata('DC', 'subject')` → `[]`) — le genre ne peut pas
être auto-extrait, seul un tag manuel est honnête.

**Contrat (revue humaine faite avant implémentation).** `Book.genre: Optional[str] = None`
(texte libre) ; `BookResponse`/`BookUpdate` += `genre`. **Migration réelle** (`ALTER TABLE book
ADD COLUMN genre VARCHAR` exécuté sur `scriptvox.db` en place) — **pas de wipe**, HP T01/T02
préservés (le projet a maintenant de vraies données, contrairement aux phases précédentes où
supprimer la DB était la norme).

**Bug latent corrigé au passage.** `patch_book` faisait `book.tts_provider = body.tts_provider`
sans distinguer "non fourni" de "explicitement null" — ajouter `genre` au même schéma aurait fait
qu'un PATCH genre-seul efface silencieusement `tts_provider` (et vice-versa). Fix :
`body.model_dump(exclude_unset=True)`, ne met à jour que les champs réellement envoyés dans le
JSON. Test-first : `tests/check_phase7.py` sections 33-35 (genre seul préserve tts_provider,
tts_provider seul préserve genre, `genre: null` explicite efface bien). 17/17 suites vertes.

Frontend : champ texte éditable inline (`defaultValue` + `onBlur`, pattern non-controlled pour
survivre au polling 3s sans clobber) à côté du badge de statut sur la page livre.

**Piège de vérification rencontré.** Les événements `blur` synthétiques dispatchés via JS
(`dispatchEvent(new FocusEvent('blur'))`) ne déclenchent PAS le handler React onBlur sans un
vrai focus préalable — confirmé par 2 tentatives échouées (fetch jamais envoyé) puis succès avec
une vraie séquence `preview_click` (focus) → `preview_fill` → `preview_click` ailleurs (blur réel).
Limite de l'outil de preview, pas un bug applicatif (un direct `fetch()` depuis la page confirmait
déjà que CORS/réseau n'étaient pas en cause).

### D3 — Filtres Bibliothèque ✅ (commit `62531c8`)
`frontend/src/app/page.tsx` : 3 sélecteurs composables (Statut — enum fixe ; Modèle TTS — depuis
`GET /settings` + option "Par défaut" pour `tts_provider=null` ; Genre — construit dynamiquement
depuis les valeurs `Book.genre` présentes, texte libre donc pas de taxonomie figée). État vide
distinct si filtres actifs ("Aucun livre ne correspond") vs bibliothèque réellement vide.
Frontend pur, dépend de D2 pour le champ `genre`.

Vérifié en conditions réelles (preview, backend redémarré pour charger le nouveau schéma,
2 vrais livres HP taggés "Fantasy jeunesse" via l'UI). `npm run build` + `npm run lint` verts
sur les 3 sous-étapes.

---

## Phase 21 — Suivi de lecture synchronisé (E0/E1/E2) ✅ (2026-06-30/07-01)

**Pourquoi.** Point E de la roadmap 2026-06-30 — le "saut produit" façon ElevenLabs : timing par
segment, bandeau "Lu par" + orbe, transcription synchronisée. Détail complet déjà documenté en
mémoire ([[player-sync-e0-e1-e2]]) — résumé ici pour combler l'absence de section TASKS.md.

- **E0** (commits `077ecaa`, `6824a3c`) — `Segment.audio_offset_ms`/`duration_ms` (migration réelle,
  pas de wipe), `GET /books/{id}/chapters/{n}/segments`, calcul dans `_synthesise_segments()`.
- **E1** (commit `1b8ae57`) — `PlayerProvider.tsx` dérive `currentSegment` (via `useMemo`, pas de
  `setState` en effet) ; `PlayerBar.tsx` affiche orbe + nom du personnage.
- **E2** (commit `ec63371`) — `ChapterTranscript.tsx` (nouveau), affiché sur `/books/{id}` dès qu'un
  chapitre du livre joue, segment courant surligné + auto-scroll.
- **E3 (mot-à-mot) : décidé explicitement PAS FAIT** — seul EdgeTTS fournit `WordBoundary`, jugé pas
  assez rentable. Ne pas reproposer sauf changement d'avis explicite sur EdgeTTS.
- Fix connexe (commit `c25e17a`) : 409 sur `.../chapters/{n}/generate` et `.../chapters/generate` si
  `chapter.status == GENERATING` (évite un double-dispatch Huey sur double-clic).

Tests : `tests/check_phase21.py` (E0) + sections ajoutées à `tests/check_phase7.py` (guard 409).

---

## Phase 22 — Refonte des orbes de voix : design retenu + mise en production ✅ (2026-07-02)

> **Contexte.** Long chantier d'exploration (2026-07-01/02, voir mémoire
> [[voice-orb-redesign-elevenlabs]] pour le fil complet des itérations) : shader WebGL (OGL/fbm)
> abandonné après plusieurs tours jugés décevants ; brainstorm de 14 designs CSS/SVG très différents ;
> **décision finale (2026-07-02) : "Glass Bubble original"** — conic-gradient qui tourne + verre en
> overlay, sans reflet. La page `frontend/src/app/orb-lab/page.tsx` est **conservée à dessein** pour
> continuer à expérimenter d'autres pistes plus tard (ne pas la supprimer sans demande explicite).
> Une évolution "nuages qui se dispersent" plaît aussi mais reste à trancher **dans le labo**, pas
> encore en prod. **4 étapes livrées dans l'ordre 1 → 4 → 2 → 3, GO explicite à chacune.**

### Étape 1 ✅ (2026-07-02) — Migrer `VoiceOrb.tsx` vers "Glass Bubble original" + prop `active`

**Pourquoi.** `VoiceOrb.tsx` (production) tourne encore sur l'ancien shader WebGL (`ogl`) + un reliquat
d'expérimentation de palettes (`palette?: "A"|...|"H"`, jamais utilisé en prod) — aucun des deux n'est
le design retenu. Contrainte de performance actée par l'utilisateur : **un orbe n'anime que lorsqu'il
est actif** (segment en cours de lecture, voix survolée/prévisualisée) ; **statique sinon** — critique
pour la transcription (jusqu'à 50-200 orbes simultanés) et le catalogue de voix.

**Fichiers (~4-5, à confirmer au moment du plan détaillé).**
- `frontend/src/components/VoiceOrb.tsx` — réécriture : structure `GlassBubbleOriginal` de
  `orb-lab/page.tsx` (conic-gradient `filter:blur(14px)` qui tourne + verre `backdrop-filter:blur(4px)
  saturate(1.3)`, bordure, ombres internes, respiration au clic) ; nouvelle prop `active?: boolean`
  (défaut `false` = statique, pas d'animation CSS déclenchée) ; suppression de `palette` et du code
  shader/`ogl`.
- `frontend/package.json` — retirer la dépendance `ogl` si plus utilisée nulle part après la migration
  (vérifier avant de la retirer).
- `frontend/src/app/voix/page.tsx`, `frontend/src/components/ChapterTranscript.tsx`,
  `frontend/src/components/player/PlayerBar.tsx` — adapter les appels (`palette` retiré, `active` câblé
  : catalogue = survol/aperçu en cours, transcription = segment en cours de lecture, bandeau = toujours
  actif tant qu'une lecture est en cours).

**Contrat.** Pas de contrat backend. Composant partagé à 3 emplacements + suppression d'une dépendance
(`ogl`) — à valider avant implémentation par prudence (CLAUDE.md Niveau 3, "changement de signature").

**Livré.** `VoiceOrb.tsx` réécrit en CSS pur (conic-gradient + verre, plus de canvas/WebGL), prop
`active` câblée (`ChapterTranscript.tsx` → segment courant, `PlayerBar.tsx` → `isPlaying`). Statique
quand `active=false` (décision explicite : pas de rotation lente au repos, contrairement à l'original
`orb-lab`, pour rester léger avec 50-200 orbes simultanées). Keyframes `orbSpinSlow`/`orbGlassBreathe`
globalisées dans `globals.css`. Dépendance `ogl` retirée de `package.json`. `voix/page.tsx` non touché
(`active` non câblé sur le survol, hors scope). Build + lint verts, vérifié visuellement en preview.

### Étape 2 ✅ (2026-07-02) — Vérifier l'unicité de la teinte par voix à la création

**Pourquoi.** Demande utilisateur : "si ce n'est pas déjà le cas". **Exploration effectuée (2026-07-02,
agent Explore)** : `buildOrbHueMap()` (`voix/page.tsx:42-46`) et `buildHueMap()`
(`PlayerProvider.tsx:26-30`, logique dupliquée) calculent `hue = (index × 137.5077°) % 360` sur les
voix **triées par id** — donc une voix nouvellement créée/clonée obtient automatiquement une teinte
distincte (le tri + angle d'or re-répartit tout l'ensemble). **A priori déjà garanti, aucun bug
identifié.** Cette étape est donc probablement une simple **vérification en conditions réelles**
(cloner une voix, confirmer visuellement une teinte différente de toutes les autres) plutôt qu'un
correctif — sauf si la vérification révèle un cas de collision non anticipé.

**Fichiers.** Aucun a priori — vérification seule.

**Vérifié (2026-07-02).** Sur les 16 voix réelles en base (`scriptvox.db`), écart minimal entre deux
teintes quelconques = 12,4° — aucune collision, largement distinct visuellement (confirmé aussi par
capture `/voix`, 16 orbes de couleurs toutes différentes). Aucun correctif nécessaire.

### Étape 3 ✅ (2026-07-02) — Paramètres : modèle TTS préféré

**Pourquoi.** Demande utilisateur : ajouter dans l'onglet Paramètres un réglage pour choisir le modèle
TTS préféré. **État actuel (vérifié)** : `GET /settings` (`app/schemas/settings.py`,
`app/api/routes/settings.py`) expose `default_tts_provider`/`available_tts_providers` en **lecture
seule** — `frontend/src/app/parametres/page.tsx` n'affiche que des cartes de statut, aucune UI
d'édition, aucune route `PATCH`.

**⚠️ Contrat — REVUE HUMAINE OBLIGATOIRE avant implémentation (CLAUDE.md Niveau 3).** Question à
trancher au moment du plan détaillé, avant tout code : `default_tts_provider` vient-il aujourd'hui
d'une variable d'environnement (process-level, donc changer la préférence nécessiterait un redémarrage
backend) ou doit-on créer une vraie persistance (nouvelle table/colonne DB) modifiable à chaud depuis
l'UI ? Ce choix détermine si c'est un simple `PATCH /settings` en mémoire ou un vrai modèle SQLModel
nouveau — à ne pas trancher sans montrer le contrat.

**Fichiers (pressentis, à confirmer).** `app/schemas/settings.py`, `app/api/routes/settings.py`,
potentiellement un nouveau modèle si persistance DB, `frontend/src/app/parametres/page.tsx` (nouveau
sélecteur).

**Décision retenue (2026-07-02) : persistance DB, affichage/édition seulement pour l'instant** (pas
encore câblée dans la génération réelle — différé, cf. "Reste à faire" ci-dessous). Nouveau modèle
singleton `AppSetting` (`id=1`, `preferred_tts_provider: str | None`) dans `app/models/entities.py`
(+ enregistrement dans `app/models/__init__.py`, oublié au 1er passage — sinon `create_all` ne crée
pas la table). `SettingsResponse` += `preferred_tts_provider` ; nouveau `SettingsUpdate` (schéma
PATCH). `GET /settings` lit/crée la ligne singleton ; `PATCH /settings` valide contre
`VALID_TTS_PROVIDERS` (422 sinon), upsert. Frontend : `api.ts` (+`preferred_tts_provider`,
+`updateAppSettings`), `parametres/page.tsx` (sélecteur avec option "Par défaut (…)", indicateur de
sauvegarde, mention explicite que ce n'est pas encore appliqué à la génération). Pas de suppression de
`scriptvox.db` nécessaire (nouvelle table, `create_all` additif). Test-first : `tests/check_phase7.py`
sections 38-40 (GET reflète `None` par défaut, PATCH persiste + 422 sur valeur invalide + remise à
`None`) — 40/40 vertes, 18 autres suites de régression sans régression. Vérifié en conditions réelles
(backend + frontend réels) : PATCH 200, persistance confirmée après rechargement, thèmes clair/sombre OK.

**Reste à faire (différé, hors périmètre de cette étape) : Étape 3b — câbler `preferred_tts_provider`
comme vrai fallback de `get_tts_provider` dans `app/workers/tasks.py` (2 call sites) quand
`book.tts_provider` est `None`, à la place de `settings.tts_provider` (.env).** Non fait ici pour
respecter le seuil de 5 fichiers du protocole — à reprendre en tâche séparée si le besoin se confirme.

### Étape 4 ✅ (2026-07-02) — Transcription déplacée dans le player déplié + surlignage de phrase + orbe active sur le segment en cours

**Pourquoi.** Demande utilisateur : ne plus afficher la transcription en direct sur la page livre,
mais dans le panneau du lecteur une fois déplié. La phrase en cours doit être surlignée (bleu foncé en
thème sombre, teinte adaptée en thème clair), et **seule l'orbe de la voix qui lit la phrase courante
doit être animée** (cf. Étape 1, prop `active`) — ex. si Harry (voix "toto") parle, seule sa bulle
s'anime pendant que les autres restent statiques.

**État actuel (vérifié)** : `ChapterTranscript.tsx` est aujourd'hui rendu directement dans
`frontend/src/app/books/[id]/page.tsx:804` (condition `track?.bookId === book.id`). `PlayerBar.tsx` a
déjà un état `expanded` (ligne 49) avec deux branches de rendu distinctes. `currentSegment` est déjà
calculé (memoïsé, pas de `setState` en effet) dans `PlayerProvider.tsx:103-110` à partir de
`currentTime` et `audio_offset_ms` — pas de nouveau calcul de timing nécessaire, seulement du
déplacement de composant + du style.

**Fichiers (~4).**
- `frontend/src/components/player/PlayerBar.tsx` — monter `<ChapterTranscript>` dans la branche
  `expanded` (au lieu de la page livre), lui passer `bookId`/`chapterPosition` depuis `track`.
- `frontend/src/app/books/[id]/page.tsx` — retirer le rendu direct de `ChapterTranscript`.
- `frontend/src/components/ChapterTranscript.tsx` — passer `active={true}` uniquement à l'orbe du
  segment courant (cf. Étape 1) ; classe de surlignage par thème.
- `frontend/src/app/globals.css` (ou classes Tailwind existantes) — couleur de surlignage adaptée au
  thème clair/sombre (le projet a déjà un mécanisme de thème, voir `layout.tsx`/`data-theme`).

**Contrat.** Pas de contrat backend — uniquement du déplacement de composant + style frontend. Dépend
de l'Étape 1 (prop `active` doit exister avant de câbler "seule l'orbe active s'anime").

**Livré.** `ChapterTranscript` retirée de `books/[id]/page.tsx` (import + `track` de `usePlayer()`
retirés, plus utilisés) ; montée dans `PlayerBar.tsx` (branche `expanded`, wrapper `w-full max-w-md`
pour la largeur). Surlignage du segment courant : nouvelles variables CSS
`--transcript-highlight-bg`/`--transcript-highlight-border` (bleu, déclinées clair/sombre dans
`globals.css`) remplaçant `bg-primary/8` (qui était un neutre, pas du bleu comme demandé). Vérifié en
conditions réelles (backend + frontend réels, livre HP T01) : transcription bien affichée dans le
player déplié, plus aucun résidu sur la page livre, thèmes clair/sombre OK.

**Ordre suivi entre les 4 étapes : 1 → 4 → 2 → 3.** L'Étape 1 (migration du composant + prop
`active`) était un prérequis direct de l'Étape 4 (qui en avait besoin). L'Étape 2 était une simple
vérification. L'Étape 3 nécessitait une décision de contrat, traitée en dernier.

**Rien de committé pour l'instant** — commit à proposer une fois la phase validée par l'utilisateur.

---

## Phase 23 — Hardening post-audit (2026-07-02)

> **Contexte.** Audit technique complet du dépôt (2026-07-02, session dédiée) : backend, worker,
> frontend, tests. Rapport structuré par sévérité (Critique/Majeur/Mineur/Note), plan de remédiation
> détaillé en mémoire ([[audit-2026-07-02-remediation-plan]]) — lots A→F, plusieurs décisions ⚖️
> encore à trancher (override TTS par livre, ElevenLabs, unification génération, sample GPU hors
> process API). Cette section ne documente que ce qui est réellement livré ; le reste du plan reste
> dans la mémoire tant qu'aucun GO n'a été donné.

### Lot A ✅ (2026-07-02) — Honorer `/stop` (Critique C1)

**Symptôme.** `POST /books/{id}/stop` posait `Book.status=FAILED` en base, mais le worker écrivait
ensuite `ANALYZED`/`DONE` sans jamais revérifier le statut — un livre stoppé en cours d'analyse ou de
génération finissait affiché comme réussi, avec des chapitres restants totalement dépourvus de
segments (générant un audiobook tronqué sans la moindre erreur visible).

**A1 — stop pendant l'analyse.**
- `_analyze_book` retourne désormais `bool` (`True` = analyse allée jusqu'au bout, `False` = abandon
  détecté). Le check de statut FAILED en boucle est désormais fait à **chaque** chapitre (avant, seul
  `i > 0` déclenchait le check, sautant le 1ᵉʳ chapitre) + un nouveau check est ajouté juste avant
  `suggest_merges` (le stop pouvait survenir après le dernier chapitre mais avant les suggestions de
  fusion).
- `_analyze_book_impl` n'écrit `ANALYZED` que si `_analyze_book` a retourné `True` **et** que le
  statut relu en DB n'est pas `FAILED` (double garde contre une course résiduelle entre les deux
  points de contrôle).

**A2 — stop pendant la génération.**
- `_synthesise_book` retourne désormais `str | None` (`None` = abandon ; `""` = livre sans segment,
  comportement préexistant inchangé ; chemin réel = chemin du WAV). Le statut est revérifié avant
  **chaque** segment synthétisé (avant : aucun check dans toute la boucle TTS).
- `_generate_book_impl` n'écrit `audio_path`/`mp3_path`/`DONE` que si `_synthesise_book` n'a pas
  retourné `None`, avec la même double garde contre une course juste avant le commit final.

**Contrat interne changé (non public — pas de revue CLAUDE.md niveau 3 requise) :** `_analyze_book`
retournait `None`, retourne maintenant `bool` ; `_synthesise_book` retournait `str`, retourne
maintenant `str | None`. Un seul call-site externe à corriger : `tests/check_phase3.py` monkeypatchait
`_analyze_book` avec un faux implicitement `-> None` — mis à jour pour retourner `True`.

**Test-first.** `tests/check_phase23.py` (nouveau, 5 sections) :
- A1a : stop simulé pendant l'analyse du chapitre 1/3 → `analyze()` appelé une seule fois, chapitres
  2 et 3 sans aucun segment, statut reste `FAILED`, `error_message` préservé, aucun `voice_id` assigné
  (confirmant qu'`assign_voices` n'a pas tourné).
- A1b : stop simulé juste après le 3ᵉ (dernier) chapitre, avant `suggest_merges` → les 3 chapitres
  sont bien analysés (3 personnages distincts), mais `suggest_merges` n'est **jamais** appelé, statut
  reste `FAILED`.
- A2 : stop simulé après le 1ᵉʳ segment synthétisé sur 4 → `synthesise()` appelé une seule fois,
  statut reste `FAILED`, `audio_path`/`mp3_path` jamais écrits.

Confirmé en échec sur le code d'avant fix (9/9 assertions rouges), vert après (5/5 sections, 18/18
assertions). **19/19 suites existantes sans régression** (`check_phase1` → `check_phase21` +
`check_phase23`) — une seule adaptation nécessaire (`check_phase3.py`, cf. ci-dessus).

Fichiers (2) : `app/workers/tasks.py`, `tests/check_phase23.py` + `tests/check_phase3.py` (fix du
fake). Aucun changement de schéma DB, aucune migration nécessaire.

**Hors périmètre de ce lot (documenté dans le plan mémoire, non traité ici) :** génération par
chapitre (`_generate_chapter_impl`) — ne touche jamais `Book.status`, donc `/stop` (qui exige
`Book.status ∈ {PROCESSING, GENERATING}`) ne s'y applique de toute façon pas ; pas une régression
introduite par ce lot.

### Lot F1b + B1a ✅ (2026-07-02) — VRAM Qwen libérée après génération + Piper overridable sans crash

**F1b — libération VRAM Qwen après une génération normale (pas seulement l'aperçu de voix, M5).**
Seuls le swap interne Base↔CustomVoice (`qwen.py`) et `_generate_voice_sample_async` appelaient
`torch.cuda.empty_cache()` ; une génération livre/chapitre normale via Qwen ne libérait jamais la VRAM
qu'elle avait chargée — elle restait réservée par l'allocateur PyTorch pour toute la durée de vie du
process worker, même après être passé à un autre provider pour le livre suivant (risque de contention
avec Ollama, cf. mémoire [[tts_emotion_qwen3_direction]]).

Nouveau helper `_release_qwen_gpu(provider)` (`app/workers/tasks.py`) : no-op pour tout provider non-
Qwen ; sur `QwenTTSProvider`, remet `_model`/`_base_model` à `None` + `gc.collect()` +
`torch.cuda.empty_cache()` (best-effort, `try/except`). Câblé en `finally` autour de l'usage du
provider dans `_synthesise_book` (génération livre) et `_synthesise_chapter_worker` (génération
chapitre) — libère la VRAM aussi bien en succès qu'en abandon (`/stop`, Lot A).

**B1a — Settings/PiperProvider tolérants à un override vers un provider non configuré (M1, option a).**
`Settings.__init__` ne créait `piper_voices_dir`/`piper_binary_path` que si Piper était le provider
**global** ; un livre overridé vers `piper` alors que le global est autre chose plantait en
`AttributeError` dans `PiperProvider.__init__` → `FAILED` cryptique. `Settings` peuple désormais ces
deux champs **toujours** (`str | None`, sans `_require`) ; le fail-fast (`ValueError`) au démarrage
reste **identique** mais ne s'applique que si `piper` est réellement le provider global.
`PiperProvider.__init__` valide lui-même ces deux champs à l'instanciation et lève une `TTSError`
explicite (« Piper is not configured: set PIPER_VOICES_DIR and PIPER_BINARY_PATH ») au lieu de planter
sur `Path(None)`. `edgetts_locale`/`qwen_*` étaient déjà safe (accès `getattr`+défaut côté provider) ;
dégagés de leur `if` pour la même raison/simplicité (aucun changement de comportement).

**Décision non traitée ici (Lot D, différé) :** le bloc `elevenlabs` de `Settings` n'a volontairement
**pas** été touché — sa suppression complète est prévue avec Lot D (ElevenLabs jamais fonctionnel), pas
encore lancé (voir raison ci-dessous).

**Test-first.** `tests/check_phase24.py` (nouveau, 11 sections) : F1b (no-op non-Qwen, libération
`_model`/`_base_model` sur un vrai `QwenTTSProvider`, intégration `_synthesise_book` en succès ET en
abandon, intégration `_synthesise_chapter_worker`) ; B1a (Settings sans crash sans vars Piper,
régression fail-fast Piper global inchangée, `PiperProvider` lève `TTSError` pas `AttributeError` sur
config absente ou chemins invalides, intégration factory bout-en-bout). **19/19 suites existantes +
check_phase24 sans régression.**

Fichiers (3) : `app/workers/tasks.py`, `app/config.py`, `app/services/tts/piper.py` +
`tests/check_phase24.py`. Aucun changement de schéma DB.

**⚠️ Note coordination (travail en parallèle sur une 2ᵉ fenêtre, 2026-07-02).** Lot D (retirer
`elevenlabs` de `VALID_TTS_PROVIDERS`) devait initialement suivre immédiatement B1a, mais touche
`tests/check_phase7.py` — fichier sur lequel une session parallèle écrivait activement au même moment
(nouvelles sections `preferred_tts_provider`, Phase 22 Étape 3b). Reporté pour éviter un conflit
d'édition en temps réel ; aucun chevauchement de fond (fonctionnalités indépendantes), juste un
chevauchement de fichier ponctuel. À reprendre une fois ce fichier stabilisé.

### Lot D ✅ (2026-07-02) — Suppression complète d'ElevenLabs (M2)

**Décision (option KISS, cf. note de coordination ci-dessus — débloqué dès que l'autre fenêtre a
committé son travail sur `check_phase7.py`).** Le provider n'a **jamais** pu fonctionner : les
voice_id logiques du catalogue (`male_0`…) étaient injectés tels quels dans l'URL de l'API
ElevenLabs (qui attend un UUID de voix réel — aucun mapping n'a jamais existé), et le modèle codé
en dur (`eleven_monolingual_v1`) était anglais-only. Aucun test ne l'exerçait en conditions réelles.
Supprimé entièrement plutôt que corrigé — pas de besoin identifié.

**Bug latent corrigé au passage.** Le factory (`get_tts_provider`) retombait **silencieusement sur
Piper** pour toute valeur de provider non reconnue (y compris, après cette migration, un
`book.tts_provider="elevenlabs"` stocké avant coup) — un livre aurait été resynthétisé avec la
mauvaise voix sans la moindre erreur. Le factory a désormais une branche explicite par provider
connu + un `else: raise ValueError` pour tout le reste.

**Fichiers (11).**
- `app/config.py` — `VALID_TTS_PROVIDERS` réduit à `{piper, edgetts, qwen}` ; bloc
  `if self.tts_provider == "elevenlabs":` retiré.
- `app/services/tts/elevenlabs.py` — **supprimé** (dead code, jamais fonctionnel).
- `app/services/tts/factory.py` — branche `piper` rendue explicite (était le fallback implicite) +
  `else: raise ValueError` pour toute valeur inconnue.
- `app/api/routes/settings.py` — branche `if p == "elevenlabs":` de `_probe_tts` retirée (code mort
  depuis le fail-fast de `Settings`, trouvé en vérifiant les résidus après la suppression).
- `.env.example`, `README.md`, `ARCHITECTURE.md` — mentions ElevenLabs retirées (nouvelle note dans
  ARCHITECTURE.md §2.2 expliquant la suppression, pour qui la chercherait). Le tableau historique
  « Phasing » (Phase 3, en bas d'ARCHITECTURE.md) volontairement **laissé inchangé** — trace
  factuelle de ce qui a été livré à l'époque, pas l'état actuel.
- `tests/check_phase4.py`, `check_phase7.py`, `check_phase9.py`, `check_phase17.py` — assertions
  ElevenLabs retirées/adaptées (ex. `check_phase7.py` : PATCH `tts_provider="elevenlabs"` remplacé
  par `"qwen"` pour continuer à tester la persistance à travers des PATCH partiels).

**Test-first.** `tests/check_phase25.py` (nouveau, 7 sections) : `elevenlabs` absent de
`VALID_TTS_PROVIDERS` ; `Settings(TTS_PROVIDER=elevenlabs)` lève `ValueError` ; le module
`elevenlabs.py` n'existe plus (`ModuleNotFoundError` à l'import) ; `get_tts_provider(override=
"elevenlabs")` lève un `ValueError` explicite (pas de repli silencieux — confirmé en échec avant le
fix : plantait en `AttributeError` brut, démontrant le bug M1 en direct) ; régression piper/edgetts/
qwen inchangés ; `PATCH /books` rejette `"elevenlabs"` en 422 ; `GET /settings` ne l'annonce plus.
**21/21 suites vertes** (`check_phase1` → `check_phase25`), zéro régression.

### Lot B ✅ CLOS (2026-07-02) — B2 + B3 : override TTS par livre, dernier volet

**B2 — `assign_voices` reçoit le provider effectif du livre (M4).** `_analyze_book_impl` passait
inconditionnellement `get_settings().tts_provider` (le provider **global**) à `assign_voices`, même
quand le livre avait son propre `tts_provider` overridé. Conséquence bidirectionnelle : un livre
overridé vers `qwen` (global ≠ qwen) ne bénéficiait jamais de la priorité aux voix clonées ; un livre
overridé **loin** de `qwen` alors que le global **est** `qwen` se voyait quand même assigner des
clones, qui échouent ensuite à la synthèse (`resolve_voice` ne les connaît que sous `qwen`). Fix :
relit `book.tts_provider` juste avant l'appel et retombe sur le global seulement si `None` — même
logique de résolution que `tts_factory.get_tts_provider(..., override=book.tts_provider)`, déjà
utilisée ailleurs dans le même fichier pour la synthèse elle-même.

**B3 — `PATCH /characters/{id}` accepte les voix clonées (M3).** La route ne validait
`body.voice_id` que contre le catalogue figé (`_CATALOGUE_META`) ; l'assignation automatique
(`assign_voices`) pouvait déjà choisir un clone pour un personnage, mais la correction manuelle
d'une voix clonée renvoyait systématiquement 422. Fix : `_is_assignable_voice_id` accepte le
catalogue **ou** un `voice_id` existant en table `Voice` avec `kind=CLONED`.

**Contrat.** Règle de validation d'API élargie (déjà montrée dans le plan mémoire avant
implémentation) — signature de route et schémas Pydantic inchangés.

**Test-first.** `tests/check_phase26.py` (nouveau, 7 sections), confirmé rouge avant / vert après par
un cycle `git stash`/`stash pop` sur les 2 fichiers concernés (4 assertions en échec exactement là où
attendu, régressions déjà vertes avant le fix) :
- B2 : override `qwen` (global `edgetts`) → clone assigné ; override `edgetts` (global `qwen`) → PAS
  de clone (catalogue à la place) ; pas d'override (global `qwen`) → clone toujours utilisé
  (régression, comportement préexistant).
- B3 : PATCH avec un `voice_id` cloné → 200 ; PATCH catalogue → 200 (régression) ; PATCH totalement
  inconnu → 422 (régression).

**22/22 suites vertes** (`check_phase1` → `check_phase26`), zéro régression.

Fichiers (3) : `app/workers/tasks.py`, `app/api/routes/characters.py`, `tests/check_phase26.py`.
Aucun changement de schéma DB.

**Lot B entièrement clos** (B1a + B2 + B3 tous livrés le 2026-07-02).

### Lot F2 ✅ (2026-07-02) — Robustesse du parseur LLM (`_parse_llm_json`)

> Chantier mené en parallèle d'une analyse de livre réelle en cours ailleurs — choisi précisément
> parce qu'il ne touche que la logique de parsing interne (aucun redémarrage de service requis pour
> l'implémenter, aucune base réelle touchée par les tests).

**Défaut 1 — index d'attribution non-entier perdu silencieusement.** Un `"index": "3"` (chaîne,
au lieu de l'entier attendu — arrive avec les petits modèles LLM) ne matchait jamais `span.index`
(int) : l'attribution était perdue **sans même le WARNING** prévu pour les autres cas malformés.
Fix : coercion `int(index)` avec `try/except`, WARNING explicite si non convertible.

**Défaut 2 — personnage sans `"name"` faisait échouer tout le chapitre.** La compréhension de
liste faisait `c["name"]` sans garde ; un dict sans cette clé levait `KeyError`, attrapé par le
`except` global de la fonction qui le transforme en `LLMParsingError` → tout le chapitre repart en
échec (3 retries puis livre `FAILED`), pour UNE seule entrée malformée sur potentiellement des
dizaines — incohérent avec la philosophie "skip + WARNING" du reste du fichier (entrées
d'attribution/personnage non-dict déjà tolérées ainsi juste au-dessus). Fix : boucle explicite avec
skip + WARNING si `name` est absent ou vide, au lieu d'une compréhension de liste qui plante.

**Test-first.** 5 nouvelles assertions dans `tests/check_phase3.py` §5 (`_parse_llm_json`), à la
suite des cas de tolérance déjà existants : index string coercé et matché ; index non convertible
ignoré proprement ; personnage sans `name` ignoré (WARNING) sans faire planter le parsing du reste.
Confirmé rouge avant / vert après par un `git stash` ciblé sur `base.py` (l'assertion sur l'index
string échouait exactement comme prévu : `got None` au lieu de `"Alice"`).

**22/22 suites vertes**, zéro régression (suites LLM/analyse en particulier revérifiées :
`check_phase1/2/3/14/16/19`).

Fichiers (2) : `app/services/llm/base.py`, `tests/check_phase3.py`. Aucun changement de contrat
(`_parse_llm_json` garde exactement sa signature et son type de retour).

### Lot C1 ✅ (2026-07-02) — Génération livre unifiée sur le chemin chapitre (M6+M7+M8)

**Décision d'architecture (⚖️ C0, GO utilisateur reçu).** `_generate_book_impl` bouclait sur TOUS
les segments du livre à plat (`_synthesise_book`, supprimée) : RAM ~3-4 Go pour un roman, aucun
timing/statut par chapitre après une génération livre (transcription synchronisée cassée), aucune
reprise après échec. Réécrit pour déléguer à la génération par chapitre (déjà propre et bornée)
puis concaténer les WAV chapitres **depuis le disque**.

**Granularité du `/stop` — décision affinée en cours de route.** Proposé initialement à la
granularité chapitre (compromis "sûr"), mais en creusant avec l'utilisateur, la granularité
**segment** s'est révélée tout aussi propre à implémenter : un chapitre interrompu jette
simplement son travail partiel (rien n'est écrit sur disque, aucun timing persisté) et repasse à
`PENDING` pour être refait en entier au prochain essai — le coût d'un stop reste borné à *un*
chapitre perdu, jamais au livre entier, mais la réactivité reste quasi-instantanée (comme avant
ce lot). `should_abort` callback threadé de `_generate_book_async` jusqu'à
`_synthesise_segments` (chapter.py).

**Reprise vs régénération complète — distinction ajoutée en implémentant.** La reprise (sauter les
chapitres déjà `DONE`) ne doit s'appliquer qu'en résumant après un échec (`Book.status == FAILED`)
— sinon un simple clic sur « Regénérer l'audio » sur un livre déjà `DONE` deviendrait un no-op
silencieux (tous les chapitres déjà `DONE`, rien à refaire). `_generate_book_impl` réinitialise
donc tous les chapitres à `PENDING` avant la boucle, SAUF si le livre reprend après un `FAILED`
(symétrique à `_analyze_book_impl`/`resume_requested`). `POST /books/{id}/generate` élargi pour
accepter `FAILED` (auparavant bloqué à ANALYZED/DONE — la reprise n'aurait jamais été
déclenchable) : contrat élargi, montré et implémenté dans la même passe.

**Nouvelles fonctions (`app/workers/tasks.py`).** `_make_book_stop_checker` (session fraîche à
chaque appel, évite le cache d'identité SQLAlchemy périmé — même piège que Lot A) ;
`_generate_chapter_async` (cœur async extrait de `_generate_chapter_impl`, réutilisable sans
`asyncio.run` imbriqué, ré-élève l'exception pour que l'appelant livre puisse faire échouer le
livre entier) ; `_generate_book_async` (boucle chapitres, reprise, stop). `_synthesise_book`
**supprimée**.

**`app/services/audio/assembler.py`** — nouvelle `assemble_wav_from_files` (concat disque→disque,
un chapitre en mémoire à la fois — pas tout le livre). **Encodage MP3 final : limite résiduelle
assumée** (relit encore tout `book.wav` en mémoire d'un coup) — différé au Lot C2, non traité ici.

**`app/services/audio/chapter.py`** — `_synthesise_segments` accepte un `should_abort` optionnel
(défaut `None`, no-op pour la génération standalone par chapitre qui ne suit pas `Book.status`).

**Test-first.** `tests/check_phase27.py` (nouveau, 10 sections) : happy path (2 chapitres → book.wav
assemblé depuis le disque, timing persisté) ; reprise après échec (chapitre déjà DONE jamais
retouché) ; régénération complète (tous les chapitres refaits, pas de no-op) ; échec partiel
(ch.1 DONE préservé, ch.2 FAILED → livre FAILED) ; stop granularité segment (abandon mi-chapitre,
rien persisté, chapitre PENDING) ; stop entre chapitres (ch.1 DONE préservé, ch.2 jamais entamé) ;
`POST /generate` accepte FAILED ; livre sans chapitre → toujours DONE ; `assemble_wav_from_files`
(concat + garde-fou format). **5 suites existantes adaptées** (`_synthesise_book` n'existe plus) :
`check_phase3.py` (fake remplacé par un mock TTS via le factory — a aussi révélé et corrigé la
même pollution `tests/fixtures/test.wav`/`.mp3` déjà rencontrée en Lot A, fixée par copie vers un
tempdir), `check_phase4.py` (§21 retirée, couverte par check_phase27 §2), `check_phase11.py`
(§7 réécrite avec un vrai chapitre au lieu d'un patch global fragile de `asyncio.run`),
`check_phase24.py` (F1b §4-5 adaptées au nouveau point d'entrée). `check_phase23.py` (A2, Lot A)
n'a nécessité **aucun changement** — il testait déjà le contrat public `_generate_book_impl`, pas
les détails internes. **22/22 suites vertes.**

Fichiers (9) : `app/workers/tasks.py`, `app/services/audio/assembler.py`,
`app/services/audio/chapter.py`, `app/api/routes/books.py`, `tests/check_phase27.py` (nouveau) +
`tests/check_phase3.py`, `check_phase4.py`, `check_phase11.py`, `check_phase24.py` (adaptées).
Aucun changement de schéma DB.

**⚠️ Follow-up frontend non traité (backend seul dans ce lot).** La reprise après un échec de
génération est maintenant possible côté API (`POST /books/{id}/generate` sur un livre `FAILED`),
mais l'UI n'a pas de bouton dédié pour ce cas — seul « Reprendre l'analyse » s'affiche sur un livre
`FAILED` (qui, pour un échec de génération, ne fait rien d'utile : tous les segments existent déjà,
la ré-analyse est un no-op qui repasse juste le livre à `ANALYZED`). Différé pour ne pas toucher
`frontend/src/app/books/[id]/page.tsx`, activement modifié par une session parallèle pendant ce lot.

### Lot C3 ✅ (2026-07-02) — Retry par segment TTS (M6 résiduel)

**Défaut.** L'analyse LLM a un retry 3× espacé de 30 s (`tasks.py` `_analyze_book`) ; la synthèse
TTS n'avait NI retry NI persistance partielle — EdgeTTS fait un appel réseau par segment (des
milliers par roman), et un flake réseau unique sur un segment faisait échouer tout le chapitre.
Avec le Lot C1 livré juste avant, ce n'est plus catastrophique (le chapitre repart de zéro, mais
les autres chapitres déjà `DONE` restent intacts) — mais ça reste un gaspillage évitable pour une
panne réseau typiquement transitoire.

**Fix.** Nouveau `_synthesise_with_retry` (`app/services/audio/chapter.py`), calqué sur le pattern
LLM existant : 3 essais, délai entre essais **plus court que le retry LLM** (3 s au lieu de 30 s —
un flake TTS est un blip réseau transitoire, pas une saturation VRAM nécessitant un temps de
récupération long). Câblé autour du seul `await tts.synthesise(...)` dans `_synthesise_segments` —
bénéficie donc uniformément à la génération standalone par chapitre ET à la génération pilotée par
le livre (Lot C1), sans duplication. `should_abort()` reste vérifié une seule fois par segment
(avant la boucle de retry), pas à chaque tentative — n'interfère pas avec la logique de `/stop`
du Lot C1.

**Test-first.** `tests/check_phase28.py` (nouveau, 6 sections) : régression happy path (aucun
retry si tout réussit) ; échec 2× puis succès → chapitre va au bout sans erreur remontée (3 appels
TTS au total) ; échec 3× → exception remonte, `_generate_chapter_impl` → chapitre `FAILED` avec
`error_message` ; aucun délai perdu après le dernier essai (ni en succès ni en échec définitif,
vérifié par comptage des appels à `asyncio.sleep` patché) ; `should_abort()` appelé exactement une
fois par segment, pas par tentative de retry. **22/22 suites vertes** (`check_phase1` → `check_phase28`,
`check_phase3.py` revérifié séparément en lecture seule car actuellement sous modification externe
non liée à ce lot).

Fichiers (2) : `app/services/audio/chapter.py`, `tests/check_phase28.py`. Aucun changement de
contrat public (`_synthesise_segments` garde exactement sa signature et son type de retour).

### Lot C2 ✅ (2026-07-02) — Encodage MP3 en flux (M8 résiduel, Lot C entièrement clos)

**Défaut.** L'assemblage WAV (`assemble_wav_from_files`, Lot C1) était déjà disque→disque, un
chapitre à la fois. Mais `_generate_book_impl` relisait ensuite **tout** `book.wav` en RAM d'un
coup (`Path.read_bytes()`) pour l'encodage MP3 — pour un roman de ~10 h, ~1,6 Go de PCM chargés
d'un bloc, exactement le pic mémoire que C1 visait à éliminer, déplacé à cette dernière étape.
Documenté comme limite résiduelle assumée dans le résumé du Lot C1.

**Fix.** Nouvelle `wav_to_mp3_streaming(wav_path, output_path, chunk_frames=1_000_000)`
(`assembler.py`) : lit le WAV par blocs de ~2 Mo (~45 s d'audio à 22050 Hz), encode chaque bloc via
`lameenc.Encoder.encode()` (encodeur en flux natif), écrit directement sur disque. **Vérifié
empiriquement** que `lameenc` produit un flux **strictement identique octet pour octet** entre un
encodage en un seul appel et un encodage en plusieurs blocs, tant que chaque bloc est aligné sur
une frontière d'échantillon — garanti par `wave.readframes()`, qui ne renvoie jamais une frame
partielle. `wav_to_mp3(bytes)` (ancienne fonction, petits buffers) conservée telle quelle — reste
utile et testée indépendamment ; seul `_generate_book_impl` bascule sur la variante en flux.

**Test-first.** `tests/check_phase29.py` (nouveau, 7 sections) : sortie identique octet pour octet
à l'ancien `wav_to_mp3(bytes)` (cas simple ET cas multi-blocs forcé avec `chunk_frames=137` sur
5000 frames, ~37 blocs — prouve que le découpage est réellement exercé, pas juste "1 bloc qui
contient tout par accident") ; WAV plus petit qu'un bloc → fonctionne (1 seul bloc interne) ;
mêmes erreurs de validation que l'ancienne fonction (8-bit, WAV vide) ; intégration
`_generate_book_impl` avec **espion** sur `wav_to_mp3_streaming` prouvant que le nouveau chemin est
réellement emprunté (pas juste que le résultat final est correct — confirmé rouge avant le câblage
dans `tasks.py` via un `git stash` ciblé : 0 appel espionné avant, 1 après). **22/22 suites vertes.**

Fichiers (3) : `app/services/audio/assembler.py`, `app/workers/tasks.py`, `tests/check_phase29.py`.
Aucun changement de contrat public.

**Pic mémoire non mesuré en test** (portabilité fiable impossible sans dépendance supplémentaire,
cf. plan) — la preuve est structurelle (chunking + `lameenc` streaming natif), à confirmer au
premier run réel sur un livre volumineux.

**Lot C entièrement clos** (C0 décision + C1 unification + C3 retry + C2 flux MP3, tous livrés le
2026-07-02).

### Lot G ✅ (2026-07-02) — Analyse LLM plus rapide sans perte de qualité (spike mesuré)

Point B de la roadmap (« moteur d'analyse plus léger/rapide ») traité comme spike mesuré,
pas comme promesse (cf. [[feature-roadmap-decisions]]). Trois changements, mesurés
ensemble sur un run complet HP T01 (18 chapitres réels) :

1. **`think=False` natif** (`app/services/llm/ollama.py`) remplace le suffixe prompt
   `/no_think` — fiable sur tous les modèles qwen3 (le suffixe était ignoré par les
   petits modèles). Dépendance `ollama` montée `~0.4.0` → `~0.6.0` (`requirements.txt`).
2. **Modèle par défaut `qwen3:1.7b`** (`ollama pull qwen3:1.7b`) au lieu de `qwen3:8b`,
   avec `OLLAMA_CONTEXT_TOKENS=32768` (tient 100% GPU, poids ~1.4 Go) et
   `OLLAMA_CHUNK_TOKENS=26000` (un chapitre HP tient en un seul chunk — éviter de
   fragmenter inutilement la liste de personnages entre appels).
3. **Réparation d'attribution déterministe** (`app/services/llm/base.py`,
   `_parse_llm_json`) : deux correctifs post-traitement, zéro appel LLM supplémentaire :
   - `_resolve_character_name` : matching flou par inclusion de mots pour les variantes
     de nom (« Percy » ⊆ « Percy Weasley », « Rogue » ⊆ « Professeur Rogue »).
   - Auto-enregistrement d'un personnage attribué mais absent de `characters[]` (incohérence
     interne du LLM observée en conditions réelles), borné par une heuristique nom-propre
     (`_looks_like_proper_noun`) pour ne pas polluer le casting avec des pseudo-personnages
     descriptifs (« boa constrictor », « tout le monde »).
   - Bonus : `_Span.incise_character` (détecté dans `_split_incise`) permet une attribution
     déterministe à 100% quand le texte source nomme explicitement le locuteur dans son
     incise (« dit Dumbledore »), prioritaire sur la réponse du LLM.

**Mesures (18 chapitres HP T01, `tests/bench_hp_label_based.py` / variante full-book) :**

| Config | Attribution | Temps total |
|---|---|---|
| qwen3:1.7b, sans réparation | 60% (1061/1764) | 445.7 s |
| qwen3:8b, sans réparation | 70% (1241/1764) | 1444.4 s |
| qwen3:8b + réparation | 76% (1337/1764) | 1442.7 s |
| **qwen3:1.7b + réparation (retenu)** | **79% (1391/1764)** | **529.2 s** |

Le petit modèle + réparations bat le gros modèle sur les deux axes (qualité ET vitesse,
~×2.7 plus rapide) — contre-intuitif, mais mesuré. Reste imparfait : quelques chapitres à
beaucoup de personnages restent faibles (ex. Ch.6 sorti à 14% dans un run) — variance
inter-chapitres réelle des deux côtés, pas une solution parfaite.

Tests : `tests/check_phase3.py` étendu (sections `_resolve_character_name` /
auto-enregistrement / `_Span.incise_character`), suite complète verte.

**Non fait / écarté par le protocole (bornes explicites du spike) :** passage à un LLM
cloud (Gemini déjà codé, jamais activé ; Claude jamais implémenté) — écarté par choix
utilisateur (« si c'est pas en local ça ne m'intéresse pas »). Split de la tâche en deux
appels LLM (lister puis attribuer) et allocation adaptative par chapitre : pistes
identifiées mais non implémentées, réservées si les réparations déterministes s'avèrent
insuffisantes en usage réel.

### Lot E ✅ (2026-07-02) — Migrations de schéma Alembic (M9)

**Défaut.** `init_db()` appelait `SQLModel.metadata.create_all(engine)` sans conditions — cette
fonction ne fait *jamais* que créer les tables manquantes, elle n'altère jamais une table
existante. Conséquence vécue plusieurs fois dans l'historique du projet : chaque changement de
modèle a nécessité de supprimer `scriptvox.db` à la main et de perdre toute la bibliothèque.

**Fix.** Adoption d'Alembic (`alembic~=1.18.0`, scaffold dans `migrations/`) :
- `migrations/env.py` — cible `SQLModel.metadata`, lit `DATABASE_URL` depuis `.env` (source
  unique avec `app/config.py`).
- `migrations/script.py.mako` édité pour toujours `import sqlmodel` — gap connu Alembic+SQLModel
  où l'autogenerate référence `sqlmodel.sql.sqltypes.AutoString(...)` sans jamais importer le
  module (aurait fait planter toute migration générée avec un `NameError`).
- Migration baseline (`migrations/versions/0a0a59b228cc_baseline.py`) générée par autogenerate
  contre une base jetable, capturant les 7 tables actuelles. **Vérifiée** : l'appliquer sur une
  base neuve puis relancer l'autogenerate dessus ne détecte plus aucun diff (`pass`/`pass`).
- `app/core/db.py` — `_ensure_schema(engine)` remplace l'appel direct à `create_all` :
  inspecte les tables existantes via `sqlalchemy.inspect` ; si des tables applicatives existent
  mais sans historique Alembic (`alembic_version` absent — l'état de **tout** `scriptvox.db`
  actuel, y compris le tien), la base est **auto-tamponnée** (`command.stamp`, qui enregistre
  seulement « cette base est déjà à la révision X », sans jamais toucher aux données) au lieu de
  tenter un `CREATE TABLE` qui planterait sur des tables déjà existantes. Sinon, `command.upgrade`
  normal.

**Bug piégé en testant (pas dans le plan initial) :** `migrations/env.py` écrasait
inconditionnellement l'URL de la base — même quand `_ensure_schema` avait déjà positionné une URL
précise sur l'objet `Config` avant d'appeler `command.upgrade`/`command.stamp` — en la remplaçant
systématiquement par `DATABASE_URL` lu depuis l'environnement. Concrètement : **toute base cible
autre que celle de l'app elle-même était silencieusement ignorée**, la migration s'appliquant
toujours sur `scriptvox.db` (ou la valeur de `DATABASE_URL` du process) au lieu de la base
réellement voulue. Repéré à l'exécution des tests : `inspect()` montrait zéro table après un
`_ensure_schema` sur une base jetable alors que les logs Alembic montraient bien une migration
appliquée — quelque part ailleurs. Fix : `env.py` ne lit `DATABASE_URL` que si aucune URL n'a déjà
été positionnée programmatiquement sur le `Config`. Sans ce correctif, le mécanisme
d'auto-tamponnement aurait été un no-op silencieux en usage réel (bien qu'inoffensif dans ce cas
précis, car la seule base ciblée en usage réel est justement `DATABASE_URL`) — mais aurait rendu
**tout test contre une base jetable invalide**, laissant croire à un mécanisme vérifié qui ne
l'était pas.

**Test-first.** `tests/check_phase30.py` (nouveau, 7 sections, exclusivement contre des fichiers
SQLite jetables en tempdir — jamais `scriptvox.db`/`data/` réels) : base neuve → schéma complet
créé ; base "pré-Alembic" simulée (tables via `create_all` brut, sans `alembic_version` — état
exact de toute base existante aujourd'hui) → auto-tamponnée sans crash ; **le plus important** :
une base pré-Alembic contenant un vrai `Book` inséré AVANT `_ensure_schema` → survit intact
(titre, statut, chemins audio) après l'opération ; idempotence (2 appels de suite sans crash) ;
intégration `init_db()` sur base neuve (schéma + catalogue de voix seedé) et sur base pré-Alembic
avec données existantes (`Voice` clonée + favorite → survit, catalogue seedé sans doublon).
**30/30 suites vertes** (régression complète).

Fichiers (6) : `requirements.txt` (ligne `alembic`), `alembic.ini`, `migrations/env.py`,
`migrations/script.py.mako`, `migrations/versions/0a0a59b228cc_baseline.py`, `app/core/db.py`,
`tests/check_phase30.py`, `README.md` (nouvelle section "Database migrations (Alembic)").

Aucune commande Alembic n'a été exécutée contre le vrai `scriptvox.db`/`data/` pendant cette
tâche — uniquement contre des bases jetables en tempdir, nettoyées après chaque test. L'auto-
tamponnement de la vraie base se déclenchera de lui-même au prochain démarrage du backend.

### Lot F1 ✅ (2026-07-02) — Génération de sample hors du process API (M5)

**Défaut.** `POST /voices/{id}/sample` appelait `_generate_voice_sample_async` **en ligne dans le
process FastAPI** : chargement du checkpoint Qwen + inférence directement dans le process API,
alors que la tâche Huey `generate_voice_sample` existait déjà pour ça mais n'était jamais
dispatchée (code mort). Risque réel : deux process distincts (API + worker) chargeant chacun un
modèle Qwen sur le même GPU sans coordination — contention/OOM potentiel si une génération de
livre tourne pendant qu'un utilisateur demande un aperçu de voix clonée.

**Fix.** `POST /voices/{id}/sample` dispatche désormais `generate_voice_sample(voice_id)` (tâche
Huey déjà existante) et répond **202 Accepted** au lieu de générer puis répondre 200 avec l'état
final. `_generate_voice_sample_async` (chemin API process) supprimé entièrement — dead code.
`_generate_voice_sample_impl` (chemin worker, jusque-là jamais exécuté puisque la tâche n'était
jamais dispatchée) corrigé pour libérer la VRAM via `_release_qwen_gpu` dans un `finally` — cette
fonction ne libérait jusqu'ici jamais rien, contrairement à la variante API qui le faisait déjà
(cleanup dupliqué inline). Aucun changement de schéma `VoiceResponse` : le corps de réponse reste
identique, seul le code HTTP (202) et le moment où il est renvoyé (immédiat, avant la fin de la
génération) changent.

**Portée volontairement limitée au backend** (décidé avec l'utilisateur avant implémentation) :
avec la génération devenue asynchrone, la réponse renvoie `has_sample: false` immédiatement — le
spinner du bouton "générer un aperçu" disparaît sans que l'aperçu soit encore prêt, il faut
recharger la page plus tard pour le voir apparaître. Un polling frontend corrigerait ça
proprement, mais `frontend/src/app/voix/page.tsx` était activement édité par une fenêtre parallèle
(refonte visuelle des orbes) pendant cette tâche — le polling est renvoyé au Lot F3 (déjà scopé
"quick wins frontend") plutôt que d'être ajouté ici pour éviter tout risque de collision de fichier
pour un gain marginal dans le même lot.

**Test-first.** `tests/check_phase31.py` (nouveau, 9 sections), confirmé rouge avant / vert après
(`git stash` ciblé sur `app/workers/tasks.py` + `app/api/routes/voices.py`) : `_generate_voice_
sample_async` absent du module ; POST sur voix CLONED → 202 + dispatch `generate_voice_sample`
appelé une fois avec le bon `voice_id` (mocké) ; aucune instanciation de `QwenTTSProvider` dans le
process API ; régressions inchangées (voix inconnue → 404, voix non-CLONED → 400, aucun dispatch
dans ces deux cas) ; `_generate_voice_sample_impl` no-op propre si `TTS_PROVIDER != qwen` ; succès
→ sample écrit sur disque + `_release_qwen_gpu` appelé ; échec de `synthesise()` → exception avalée
(loggée, ne remonte jamais) **et** VRAM quand même libérée. **27/27 suites vertes.**

Fichiers (3) : `app/workers/tasks.py`, `app/api/routes/voices.py`, `tests/check_phase31.py`.

### Lot F3 ✅ (2026-07-02) — Quick wins frontend (m2, m8) + polling sample différé de F1

**m2 — `PlayerProvider.play` relisait une vitesse périmée.** `play` était un `useCallback(..., [])`
(identité stable, volontaire) qui lisait `rate` par fermeture — capturée à 1× au montage et jamais
mise à jour puisque le tableau de dépendances est vide. Changer de vitesse mettait bien à jour
l'affichage (`rate` state, correctement propagé au `<select>`), mais tout nouvel appel à `play()`
(chapitre suivant, relecture) réappliquait 1× sur l'élément `<audio>` réel — écart invisible entre
ce que l'UI affichait et la vitesse effectivement entendue. Fix : `rateRef` (ref, pas state) tenu à
jour par `setRate`, lu par `play()` à la place de la fermeture — identité de `play()` toujours
stable, plus de valeur périmée. **Vérifié en navigateur** (voir ci-dessous) en instrumentant
`HTMLMediaElement.prototype.playbackRate` : avant le fix cet essai aurait loggé `1` après un
changement de vitesse suivi d'un replay ; après fix, loggue bien `1.5` puis `2` comme attendu.

**m8 — `buildHueMap`/`buildOrbHueMap` dupliqués à l'identique** entre `PlayerProvider.tsx` et
`voix/page.tsx` (même angle d'or, même tri, même logique). Extraits vers
`frontend/src/lib/voiceHues.ts` (nouveau), importés aux deux endroits — garantit qu'ils ne peuvent
plus diverger silencieusement.

**`.catch` manquant sur `listChapters`** dans `PlayerBar.tsx` : un échec réseau lors du dépliage du
bandeau lecteur (chargement de la liste des chapitres) produisait une rejection de promesse non
gérée, sans que `chapters` retombe à un état connu. Ajouté (aligné sur le pattern déjà utilisé pour
les segments dans `PlayerProvider`). **Vérifié en navigateur** en interceptant `fetch` pour simuler
un échec réseau : aucune rejection non gérée détectée (`window.addEventListener('unhandledrejection', ...)`),
pas de crash du bandeau.

**Polling `has_sample` (différé du Lot F1).** `POST /voices/{id}/sample` répond désormais 202
immédiatement (dispatch Huey, Lot F1) — le bouton "générer un aperçu" (`voix/page.tsx`) attendait
jusque-là la réponse finale pour effacer son spinner, ce qui ne se produisait plus jamais aussi
vite. Nouveau `pollForSample(voiceId)` : reinterroge `listVoices()` toutes les 3 s (plafonné à 20
essais, ~1 min) jusqu'à ce que `has_sample` passe à `true`, câblé sur les deux points de déclenchement
(clonage automatique + bouton manuel de régénération). Non vérifié en conditions réelles contre le
vrai worker (aurait mis en concurrence une tâche de sample avec l'analyse de livre réellement en
cours pendant cette session sur la même file Huey) — logique revue par lecture de code uniquement
pour cette partie spécifique.

**Fichier partagé avec une fenêtre parallèle.** `voix/page.tsx` contenait déjà un agrandissement
non committé des orbes (`ORB_SIZE`, composant `VoiceOrb`) fait par une autre fenêtre pendant cette
tâche — enchevêtré avec mes propres changements dans les mêmes blocs de diff (même fonction
`buildOrbHueMap` touchée par les deux, mêmes handlers de clic). Impossible à séparer proprement par
hunk (`git add -p`) contrairement à `requirements.txt` au Lot E. Décidé avec l'utilisateur : les
deux jeux de changements sont committés ensemble sur ce fichier plutôt que de laisser un état
partiellement committé.

**Vérification** (pas de harness automatisé frontend) : `npm run build` + `npm run lint` propres ;
serveur de prévisualisation (frontend seul, backend réel non redémarré) — page `/voix` sans erreur
console, couleurs d'orbe cohérentes après extraction du helper partagé ; scénario vitesse/replay
vérifié par instrumentation directe de `HTMLMediaElement.prototype` ; scénario échec réseau
`listChapters` vérifié par interception de `fetch`.

Fichiers (4) : `frontend/src/lib/voiceHues.ts` (nouveau),
`frontend/src/components/player/PlayerProvider.tsx`,
`frontend/src/components/player/PlayerBar.tsx`, `frontend/src/app/voix/page.tsx`.

### Lot F4 ✅ (2026-07-02) — Hygiène (m1 vérifié, m10, m12) + code mort (Book.updated_at)

**⚠️ Mené pendant une génération audio réellement en cours sur le livre 2** (chapitres 5-10
`GENERATING` en parallèle) — périmètre restreint aux changements sûrs sous cette contrainte :
aucun redémarrage backend/worker, aucune commande contre `scriptvox.db`/`huey.db` réels, priorité
aux fichiers dont l'édition n'affecte jamais un process déjà démarré (pas de `--reload`, voir
[[windows_zombie_process_lesson]]). `voice_tone` (colonne DB réelle, migration + `base.py`
activement édité par une fenêtre parallèle) et `synthesise_chapter` (choix de conception, pas un
bug) explicitement **différés** — décidé avec l'utilisateur avant implémentation.

**m12 — hygiène dépôt.** `.gitignore` += `*.pid`, `*.log` (fichiers de process de dev, jusque-là
non ignorés — apparaissaient en `??` à chaque `git status`). Nettoyage des `scriptvox_test_p*.db` /
`huey_test_p*.db` résiduels à la racine (déjà `*.db`-gitignorés, pur nettoyage disque — jamais
`scriptvox.db`/`huey.db` réels, vérifiés intacts après coup).

**m10 — `audioop` retiré de la stdlib en Python 3.13+ (PEP 594).** `app/services/tts/qwen.py`
important `audioop` sans garde — un upgrade futur vers 3.13 ferait planter l'import du module
entier (`ImportError` non catché) dès que `QwenTTSProvider` est référencé, même sans jamais
synthétiser. Fix : `try/except ImportError` au niveau module (`audioop = None` si absent), erreur
reportée à l'usage réel (`_resample_to_output`) sous forme de `TTSError` explicite au lieu d'un
`AttributeError` opaque sur `None.ratecv`. Aucune dépendance ajoutée (le message d'erreur mentionne
le backport `audioop-lts` comme option, sans l'installer). Sans effet sur le venv actuel (3.11.9).

**m1 — déjà corrigé, vérifié par un test de non-régression.** L'audit notait que
`EDGETTS_LOCALE` pouvait ne pas être honoré quand le provider global n'est pas `edgetts` (aperçus
catalogue parlant un texte FR avec une voix en-US). Investigation : déjà résolu par effet de bord
du Lot B1a (`Settings.edgetts_locale` toujours peuplé inconditionnellement depuis ce lot-là,
`EdgeTTSProvider.__init__` ne fait aucune vérification conditionnelle sur `tts_provider`). Aucun
code changé — un test verrouille ce comportement pour empêcher une régression silencieuse future.

**Code mort — `Book.updated_at` : écrit partout, jamais lu.** 11 sites d'écriture
(`app/workers/tasks.py` ×10, `app/api/routes/books.py` ×1) retirés — confirmé qu'aucun schéma API
(`schemas/book.py`) ni le frontend ne l'exposent. La colonne DB elle-même est **conservée**
(toujours peuplée une fois à la création via `default_factory`, aucune migration nécessaire) —
seules les réécritures redondantes à chaque mutation de statut/progression sont supprimées.
L'import `from datetime import datetime, timezone` dans `tasks.py` devenu entièrement inutile après
ce retrait a été supprimé aussi (plus aucun usage dans le fichier).

**Test-first.** `tests/check_phase15.py` étendu (2 nouvelles sections, audioop absent : no-op à
22050 Hz + `TTSError` clair si resampling requis) et `tests/check_phase24.py` étendu (1 nouvelle
section, m1 verrouillé). Confirmé rouge avant / vert après pour m10 (`git stash` ciblé sur
`qwen.py`) : le code pré-fix lève un `AttributeError: 'NoneType' object has no attribute 'ratecv'`
brut au lieu du `TTSError` propre attendu. **27/27 suites vertes**, y compris pendant que la
génération réelle du livre 2 progressait (chapitre 9 terminé pendant le run de la suite complète,
`scriptvox.db` vérifié non perturbé avant/après).

Fichiers (5) : `.gitignore`, `app/services/tts/qwen.py`, `app/workers/tasks.py`,
`app/api/routes/books.py`, `tests/check_phase15.py`, `tests/check_phase24.py`. Aucun changement de
contrat public, aucune migration de schéma.

**Reste hors de ce lot** : `voice_tone` (colonne morte, nécessite une migration Alembic — différé),
`synthesise_chapter` (garder ou virer — décision de conception non tranchée). Follow-up frontend :
bouton "Reprendre la génération" pour les livres `FAILED` (capacité livrée au Lot C1 mais jamais
exposée en UI). Détail complet : mémoire [[audit-2026-07-02-remediation-plan]].

**🏁 Plan de remédiation post-audit 2026-07-02 : tous les lots avec décision tranchée sont
maintenant livrés** (A, B, C, D, E, F1, F2, F3, F4). Il ne reste que des points explicitement
différés par choix (voice_tone, synthesise_chapter) et le follow-up frontend "reprendre
génération" — aucun n'est bloquant, tous documentés ci-dessus et dans la mémoire.

## Phase 24 — Hardening pré-publication Reddit (2026-07-07)

> **Contexte.** Le dépôt (`github.com/RFelgines/ScriptVox-v2`) est **déjà public** — Romain prépare
> un post Reddit annonçant ScriptVox comme projet perso (pas commercial). Audit dédié à cette
> publication (2026-07-07), distinct de l'audit de hardening général de la Phase 23. Rapport complet
> en mémoire ([[reddit-publication-audit]]). Rien n'est encore traité — tous les points ci-dessous
> sont 🔲 à faire.

### P0 — Bloquant avant le post

- ✅ **`LICENSE`** (2026-07-07) — [PolyForm Noncommercial 1.0.0](../LICENSE) : usage personnel/non
  commercial libre, usage commercial soumis à accord séparé avec l'auteur (demande explicite de
  Romain, plus adaptée à du code que les licences Creative Commons). Section "License" ajoutée au
  README. Fichiers (2) : `LICENSE` (nouveau), `README.md`.
- ✅ **`scripts/seed_cloned_voices.py` anonymisé** (2026-07-07) — `KNOWN_VOICES` (qui listait Macron,
  Sarkozy, Attenborough, Jancovici, Patrick Baud comme cibles de clonage vocal) vidé et remplacé par
  un commentaire d'exemple générique. Retrait simple choisi (pas de réécriture d'historique) : le
  commit `608b581` reste visible dans l'historique GitHub, mais tout nouveau clone affiche la version
  anonymisée. Chaque utilisateur repeuple localement avec ses propres enregistrements de référence
  (`data/voice_uploads/`, gitignoré). Fichier (1) : `scripts/seed_cloned_voices.py`.

### P1 — Uniquement si une *instance* (pas juste le code) est exposée à des inconnus

- 🔲 **Aucune authentification** — choix assumé pour du mono-utilisateur local, mais à documenter
  explicitement en README ("ne pas exposer sur Internet").
  - ✅ **Durcissement des uploads** (2026-07-07) — nouveau `app/core/uploads.py`
    (`read_upload_capped`) : lecture par chunks de 1 Mo, HTTP 413 dès que le plafond est dépassé
    (borne la RAM peu importe ce que le client prétend envoyer, contrairement à `await file.read()`
    seul). Appliqué à l'upload EPUB (200 Mo), couverture (20 Mo) et audio de référence voix (20 Mo).
    `books.py` : le nom de fichier client n'est plus injecté dans le chemin disque
    (`{uuid}_{filename}` → `{uuid}.epub`), conservé uniquement comme titre du livre (déjà le cas).
    `voices.py` : whitelist d'extension `{.mp3, .wav, .flac}` (ce que `_load_ref_audio` sait décoder)
    avant tout appel réseau, remplace l'extension client non filtrée.
    Suites vertes sans régression : `check_phase1/2/7/10/17`. Fichiers (3) :
    `app/core/uploads.py` (nouveau), `app/api/routes/books.py`, `app/api/routes/voices.py`.
  - 🔲 EPUB = zip + XML non fiables en entrée non contrôlée (zip bomb, quadratic blowup) — pas
    d'exploit connu ebooklib/lxml par défaut ; le plafond de 200 Mo ci-dessus atténue le pire cas
    sans l'éliminer (un zip de 200 Mo peut encore décompresser en plusieurs Go de texte).
  - 🔲 CSRF vers localhost — sans auth ni vérification d'`Origin`, un formulaire multipart externe
    peut soumettre vers `http://localhost:8000/books` (contourne CORS). Impact réel faible en usage
    perso.

### P2 — Hygiène et robustesse (non bloquant)

- 🔲 `tests/fixtures/test.epub` / `test_whitespace.epub` se régénèrent (diff binaire) à chaque run —
  soit les générer dans `data_test/`, soit ne plus les réécrire une fois committées.
- ✅ **`DELETE /voices/{id}` nullifie `Character.voice_id` orphelin** (2026-07-07) — avant de
  supprimer la `Voice`, tout `Character` dont `voice_id` pointait dessus est repassé à `None`.
  Réutilise le fallback narrateur déjà existant des deux côtés qui lisent `voice_id`
  (`books.py get_chapter_segments`, `audio/chapter.py _synthesise_segments` traitent déjà
  `voice_id=None` comme "voix narrateur") — aucun nouveau chemin de repli ajouté. Sans ce fix,
  la génération suivante levait `TTSError: Unknown voice_id`.
  Test-first : `tests/check_phase17.py` §18 (nouvelle section) — confirmé rouge avant / vert après
  (`git stash` ciblé sur `voices.py`). **20/20 sections vertes**, `check_phase9.py` sans régression.
  Fichiers (2) : `app/api/routes/voices.py`, `tests/check_phase17.py`.
- 🔲 README à compléter pour un public externe : `DATA_DIR`/`FRONTEND_ORIGINS`/timeouts manquants
  dans la table de config (présents dans `.env.example` seulement), tests listés seulement jusqu'à
  `check_phase15` (36 suites existent), version Python non indiquée (garde `audioop` ⇒ <3.13 ou
  `audioop-lts`), avertissement "local, sans auth, ne pas exposer", note de confidentialité
  (EdgeTTS envoie le texte à Microsoft, Gemini à Google).
- 🔲 Publier depuis un `main` propre — travail UI en cours sur `poc/ui-visual-refresh` (non commité)
  à merger ou laisser de côté avant le post.

**Optionnel le jour J** : `pip-audit` + `npm audit` (versions actuelles épinglées, rien d'alarmant
relevé lors de l'audit, mais bon réflexe juste avant publication).
