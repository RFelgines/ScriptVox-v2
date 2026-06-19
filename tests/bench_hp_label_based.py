"""Benchmark réel — protocole LLM label-based (Phase 12 Étape 5 / B-3).

Mesure le coût de l'analyse LLM **par chapitre** sur un epub HP réel, avec le
protocole label-based (ARCHITECTURE.md §2.7) et le provider configuré dans `.env`
(Ollama qwen3:8b par défaut).

Ce n'est PAS une suite de régression : il nécessite Ollama lancé + un epub dans
`Ebook/`, et ne contient aucun assert — il produit des mesures à consigner.

Run: .venv/Scripts/python tests/bench_hp_label_based.py [n_chapitres]
     (n_chapitres = nombre de chapitres de contenu à mesurer, défaut 3)
"""
import asyncio
import math
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")  # vraie config (Ollama qwen3:8b), indépendant du CWD

# Console Windows (cp1252) : les titres/noms de fichiers peuvent contenir des
# accents combinants (forme NFD) non encodables → forcer UTF-8 sur les flux.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from app.config import get_settings  # noqa: E402
from app.core.enums import SegmentType  # noqa: E402
from app.services.epub.parser import EpubParser  # noqa: E402
from app.services.llm import factory as llm_factory  # noqa: E402
from app.services.llm.base import (  # noqa: E402
    GEMINI_MAX_TOKENS,
    _chunk_text,
    _estimate_tokens,
    _merge_chunk_results,
    _pre_segment,
)

# Filtre les pages de garde / sommaire / dédicace (chapitres sans contenu réel)
MIN_CONTENT_CHARS = 1500

# Baseline de l'ancien prompt « reproduis chaque mot » (TASKS.md Phase 12 Étape 5)
BASELINE_MIN_S = 7 * 60
BASELINE_MAX_S = 14 * 60


async def run_bench(settings, selected, budget) -> None:
    provider = llm_factory.get_llm_provider(settings)

    # Warm-up : charge le modèle en VRAM HORS mesure (sinon le 1er chapitre
    # porterait le cold-start et fausserait le temps/chapitre).
    print("Warm-up (chargement du modèle, hors mesure)…")
    t0 = time.perf_counter()
    try:
        await provider.analyze("Bonjour, ceci est un échauffement.")
        print(f"  warm-up OK : {time.perf_counter() - t0:.1f} s\n")
    except Exception as exc:  # noqa: BLE001 — le warm-up ne doit jamais tuer le bench
        print(f"  warm-up : réponse ignorée ({type(exc).__name__}) — modèle chargé quand même\n")

    rows: list[tuple] = []
    for ch in selected:
        spans = _pre_segment(ch.raw_text)
        n_dialogue_spans = sum(1 for s in spans if s.is_dialogue)
        chunks = _chunk_text(ch.raw_text, budget)
        tokens = _estimate_tokens(ch.raw_text)

        t0 = time.perf_counter()
        results = []
        for c in chunks:
            results.append(await provider.analyze(c))
        elapsed = time.perf_counter() - t0

        merged = _merge_chunk_results(results)
        dialogue_segs = [s for s in merged.segments if s.segment_type == SegmentType.DIALOGUE]
        attributed = sum(1 for s in dialogue_segs if s.character_name)

        title = (ch.title or "?").strip()[:48]
        print(f"Ch.{ch.position:>2}  « {title} »")
        print(f"    {len(ch.raw_text):>7,} car.   ~{tokens:>6,} tok.   {len(chunks)} chunk(s)")
        print(f"    spans : {len(spans):>5}  (dialogue {n_dialogue_spans} / narration {len(spans) - n_dialogue_spans})")
        print(f"    LLM   : {elapsed:7.1f} s")
        print(f"    →  {len(merged.characters)} personnages   "
              f"{len(dialogue_segs)} segments dialogue   {attributed} attribués\n")
        rows.append((ch.position, elapsed, len(spans), n_dialogue_spans,
                     len(merged.characters), len(dialogue_segs), attributed))

    if not rows:
        return

    times = [r[1] for r in rows]
    total = sum(times)
    avg = total / len(times)
    print("─" * 60)
    print(f"RÉSUMÉ — {len(rows)} chapitre(s) mesuré(s)")
    print(f"  temps total           : {total:7.1f} s")
    print(f"  temps moyen / chapitre : {avg:7.1f} s")
    print(f"  min / max             : {min(times):.1f} s / {max(times):.1f} s")
    print(f"  baseline ancien prompt : ~7-14 min/chapitre ({BASELINE_MIN_S}-{BASELINE_MAX_S} s)")
    if avg > 0:
        print(f"  gain ≈ ×{BASELINE_MIN_S / avg:.0f} à ×{BASELINE_MAX_S / avg:.0f}")


def main() -> None:
    n_target = int(sys.argv[1]) if len(sys.argv) > 1 else 3

    settings = get_settings()
    print(f"LLM_PROVIDER={settings.llm_provider}   model={getattr(settings, 'ollama_model', '?')}   "
          f"num_ctx={getattr(settings, 'ollama_context_tokens', '?')}")

    budget = (
        math.floor(settings.ollama_context_tokens * 0.8)
        if settings.llm_provider == "ollama"
        else GEMINI_MAX_TOKENS
    )
    print(f"budget de contenu = {budget:,} tokens (×0.8)\n")

    epubs = sorted((ROOT / "Ebook").glob("*.epub"))
    if not epubs:
        print("Aucun epub dans Ebook/ — abandon.")
        sys.exit(1)
    epub_path = epubs[0]
    print(f"EPUB : {epub_path.name}")

    parsed = EpubParser().parse(str(epub_path))
    print(f"Titre : {parsed.title}  |  Auteur : {parsed.author}  |  "
          f"{len(parsed.chapters)} chapitres parsés")

    content = [ch for ch in parsed.chapters if len(ch.raw_text) >= MIN_CONTENT_CHARS]
    selected = content[:n_target]
    print(f"{len(content)} chapitres ≥ {MIN_CONTENT_CHARS} car. ; "
          f"mesure sur les {len(selected)} premiers.\n")

    if not selected:
        print("Aucun chapitre de contenu — abandon.")
        sys.exit(1)

    asyncio.run(run_bench(settings, selected, budget))


if __name__ == "__main__":
    main()
