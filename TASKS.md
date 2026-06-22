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

### Étape B3 ✅ codée (2026-06-22) — `QwenTTSProvider` (4e provider) — ⚠️ NON CLOS (écoute différée)

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

**Reste à faire avant de clore B3 (TODO permanent) :** écoute réelle de l'audio Qwen3-TTS en
français (qualité + effet `instruct`) ; vérifier/corriger `_VOICE_MAP` à l'oreille (mapping
preset→genre non confirmé par la doc Qwen) — tâche utilisateur, pas automatisable.

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
