# TASKS.md — ScriptVox

## Fait

- Phase 1 : config fail-fast + modèles SQLModel (commit 9f9360c)
- Phase 2 : FastAPI skeleton, EPUB ingestion, Huey worker (commit 6e1b600)
- Phase 3 : pipeline LLM — BaseLLMProvider, Gemini, Ollama, token budgeting (commit 83b086b)
- CLAUDE.md — protocole de travail permanent (commit 6286920)

## En cours

### Phase TTS & audio (ARCHITECTURE.md § Phase 3)

**Sous-tâche 1 — Scaffold Strategy TTS + stubs + fail-fast**
- [x] TASKS.md (ce fichier)
- [x] app/services/tts/base.py
- [x] app/services/tts/piper.py (stub)
- [x] app/services/tts/elevenlabs.py (stub)
- [x] app/services/tts/factory.py
- [x] app/core/exceptions.py (+ TTSError)
- [x] app/config.py (+ fail-fast ELEVENLABS_API_KEY)
- [x] tests/check_phase4.py

## À venir

**Sous-tâche 2 — Catalogue de voix + service d'assignation**
- services/voice_assignment.py : assignation déterministe par genre, voix narrateur dédiée
- Peuple Character.voice_id en base

**Sous-tâche 3 — Assemblage audio + implémentation réelle + câblage worker**
- requirements.txt : ajouter piper-tts (épinglé), noter licence GPL-3.0 (OHF-Voice/piper1-gpl)
- ARCHITECTURE.md : note licence Piper
- models/entities.py : Book.audio_path
- services/audio/assembler.py : concaténation WAV via stdlib wave
- tts/piper.py + tts/elevenlabs.py : implémentation réelle (httpx pour ElevenLabs)
- workers/tasks.py : appel TTS après LLM analysis, mise à jour statut
- config.py : PIPER_VOICES_DIR requis quand TTS_PROVIDER=piper
- .env.example : ajouter PIPER_VOICES_DIR
- check_phase1/2/3 : ajouter PIPER_VOICES_DIR aux os.environ de chaque test

**Sous-tâche 4 — Exposition API**
- api/routes/books.py : GET /books/{id}/audio (FileResponse)
- schemas/book.py : audio_path dans BookResponse

---

## Décisions d'architecture figées (Phase TTS)

| Sujet | Décision |
|-------|----------|
| Piper intégration | `piper-tts` pip, modèles `.onnx` dans le repo, chemin via `PIPER_VOICES_DIR` |
| ElevenLabs intégration | `httpx` direct (0 nouvelle dépendance), sortie WAV demandée à l'API |
| Assemblage | WAV via stdlib `wave` (0 dépendance) |
| Contrat | `BaseTTSProvider.synthesise(text, voice_id) -> bytes` WAV |
| Licence Piper | GPL-3.0 — `OHF-Voice/piper1-gpl` — à documenter dans ARCHITECTURE.md |
