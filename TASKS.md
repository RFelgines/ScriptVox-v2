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

### Étape 1 — Fail-fast : valider l'existence du dossier `voices/` ⏳

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

### Étape 2 — README : démarrage, worker, voix, tests ⏳

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

### Étape 3 — Garde-fou format WAV dans l'assembleur ⏳

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

### Étape 4 — Test d'intégration bout-en-bout du pipeline worker ⏳

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

### Étape 5 — Polish (optionnelle, basse priorité) ⏳

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

## Décisions d'architecture figées (Phase TTS)

| Sujet | Décision |
|-------|----------|
| Piper intégration | `piper-tts` pip, modèles `.onnx` dans le repo, chemin via `PIPER_VOICES_DIR` |
| ElevenLabs intégration | `httpx` direct (0 nouvelle dépendance), sortie WAV demandée à l'API |
| Assemblage | WAV via stdlib `wave` (0 dépendance) |
| Contrat | `BaseTTSProvider.synthesise(text, voice_id) -> bytes` WAV |
| Licence Piper | GPL-3.0 — `OHF-Voice/piper1-gpl` — documentée dans ARCHITECTURE.md |
| Nommage voix | `VOICE_CATALOGUE` impose les noms de fichiers `.onnx` (voir README étape 2) |
