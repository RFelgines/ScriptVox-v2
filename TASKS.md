# TASKS.md — ScriptVox

## Fait

- Phase 1 : config fail-fast + modèles SQLModel (commit 9f9360c)
- Phase 2 : FastAPI skeleton, EPUB ingestion, Huey worker (commit 6e1b600)
- Phase 3 : pipeline LLM — BaseLLMProvider, Gemini, Ollama, token budgeting (commit 83b086b)
- CLAUDE.md — protocole de travail permanent (commit 6286920)

## En cours

### Phase TTS & audio (ARCHITECTURE.md § Phase 3)

**Sous-tâche 1 — Scaffold Strategy TTS + stubs + fail-fast** ✅
- [x] TASKS.md (ce fichier)
- [x] app/services/tts/base.py
- [x] app/services/tts/piper.py (stub)
- [x] app/services/tts/elevenlabs.py (stub)
- [x] app/services/tts/factory.py
- [x] app/core/exceptions.py (+ TTSError)
- [x] app/config.py (+ fail-fast ELEVENLABS_API_KEY)
- [x] tests/check_phase4.py

**Sous-tâche 2 — Catalogue de voix + service d'assignation** ✅
- [x] app/services/voice_assignment.py : assignation déterministe par genre, voix narrateur dédiée
- [x] Character.voice_id peuplé en base (champ déjà présent en Phase 3)

**3a — Config & variables d'env** ✅
- [x] app/config.py : fail-fast PIPER_VOICES_DIR quand TTS_PROVIDER=piper
- [x] .env.example : + PIPER_VOICES_DIR
- [x] tests/check_phase1/2/3/4.py : + PIPER_VOICES_DIR dans os.environ

## À venir

**3b — Schéma + assembleur audio** ✅
- [x] app/models/entities.py : Book.audio_path
- [x] app/services/audio/__init__.py (nouveau)
- [x] app/services/audio/assembler.py (nouveau) : concaténation WAV stdlib wave
- [x] tests/check_phase4.py : sections 16-19 (assembler + Book.audio_path)

**3c — Implémentations TTS réelles** ✅
- [x] requirements.txt : + piper-tts~=1.2.0 (GPL-3.0)
- [x] ARCHITECTURE.md : note licence Piper GPL-3.0
- [x] app/services/tts/piper.py : impl réelle (lazy import, run_in_executor, TTSError)
- [x] app/services/tts/elevenlabs.py : impl réelle via httpx, PCM->WAV
- [x] tests/check_phase4.py : sections 5/6 mis à jour + section 20 (mock HTTP 200)

**3d — Câblage worker** ✅
- [x] app/workers/tasks.py : _synthesise_book + assign_voices dans _process_book_impl, Book.audio_path
- [x] tests/check_phase4.py : section 21 (_synthesise_book avec mock TTS)
- [x] tests/check_phase3.py : section 7 mise à jour (mock _synthesise_book pour éviter régression)

**Sous-tâche 4 — Exposition API**
- [ ] api/routes/books.py : GET /books/{id}/audio (FileResponse)
- [ ] schemas/book.py : audio_path dans BookResponse

---

## Décisions d'architecture figées (Phase TTS)

| Sujet | Décision |
|-------|----------|
| Piper intégration | `piper-tts` pip, modèles `.onnx` dans le repo, chemin via `PIPER_VOICES_DIR` |
| ElevenLabs intégration | `httpx` direct (0 nouvelle dépendance), sortie WAV demandée à l'API |
| Assemblage | WAV via stdlib `wave` (0 dépendance) |
| Contrat | `BaseTTSProvider.synthesise(text, voice_id) -> bytes` WAV |
| Licence Piper | GPL-3.0 — `OHF-Voice/piper1-gpl` — à documenter dans ARCHITECTURE.md |
