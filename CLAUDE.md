# CLAUDE.md — ScriptVox Work Protocol

Architecture laws → [ARCHITECTURE.md](ARCHITECTURE.md) §2.1-2.6 (authoritative).
This file governs **how we work**, not what we build.

---

## Level 1 — Foundations

**Plan-First.** Before writing any file: propose plan (files touched + approach), wait for
explicit GO. Never advance to the next numbered step without "GO".

**Git.** After each validated task, propose a commit message and wait for approval.
Never commit autonomously.

**Modularity.** One task = one scope. Small files, single responsibility.
If a task touches > 5 files, stop and recut into smaller tasks first.

---

## Level 2 — Intermediate

**Tests first.** Before implementing new behaviour, write/extend the matching
`tests/check_phaseN.py` to describe the expected outcome. Run after every change —
never chain 10 changes without testing.
Runner (all suites, numeric order, one subprocess each — also what CI runs):
`python tests/run_all.py` (Windows: `.venv\Scripts\python tests\run_all.py`); one suite:
`python tests/check_phaseN.py`. Suites `check_phase1` … `check_phase48` exist; the next number is
reserved in `TASKS.md`. Tests are offline: LLM, TTS and network are mocked or served by a loopback server.

**Failing test ≠ automatic fix.** First verify whether the test expectation is stale.
Always cover the happy path AND the failure path. Never mock away a failure to hide it.

**Micro-tasks.** One deliverable per exchange. Do not "solve everything" in one turn.

**External memory.** ARCHITECTURE.md is authoritative — re-read when in doubt.
Maintain `TASKS.md` (Done / In progress / Upcoming). If stuck on a multi-session bug,
document it in a "Current problems" section of TASKS.md; the human will open a fresh session.

---

## Level 3 — Advanced

**Blast radius.** Before editing: list the exact files that will be modified and why.
List too long → recut the task.

**Signal complexity.** If a task requires architectural design or multi-layer debugging,
say so at the plan step so the human can choose the approach (and the model to use).

**Contracts require human review.** Any function signature, Pydantic schema, API route,
or SQLModel model change must be shown and approved BEFORE implementation — they propagate
everywhere.

---

## ScriptVox Guardrails

- No surprise dependencies: never add a package without justifying it and asking first.
- No mock data in production code: mocks live in `tests/` only.
- Keep `.env.example` in sync with every new environment variable.
- New LLM / TTS engines are **plugins** or generic providers (docs/PLUGINS.md), not new branches in the
  factories: register them through `app/services/registry.py`.
- Never make a runtime API setting able to execute code or carry a secret (`TTS_COMMAND` and API keys stay
  in `.env`; `llm_options` / `tts_options` accept a whitelist of keys only).
- Scope: `TASKS.md` (roadmap) and `CHANGELOG.md` (what shipped). ARCHITECTURE.md is the design reference.
