"""Validation ponctuelle — chapitre 7 forcé en plusieurs chunks plus petits, pour
vérifier l'hypothèse de troncature de sortie à num_ctx réduit.
Run: OLLAMA_CONTEXT_TOKENS=16384 .venv/Scripts/python tests/bench_ch7_chunked.py <budget_tokens>
"""
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from app.config import get_settings  # noqa: E402
from app.core.enums import SegmentType  # noqa: E402
from app.services.llm import factory as llm_factory  # noqa: E402
from app.services.llm.base import _chunk_text, _merge_chunk_results, _pre_segment  # noqa: E402

get_settings.cache_clear()
settings = get_settings()
budget = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
print(f"num_ctx={settings.ollama_context_tokens}  budget_chunk={budget}")

import tempfile, os  # noqa: E402
raw_text = Path(os.path.join(tempfile.gettempdir(), "ch7_raw.txt")).read_text(encoding="utf-8")
spans = _pre_segment(raw_text)
n_dialogue = sum(1 for s in spans if s.is_dialogue)
chunks = _chunk_text(raw_text, budget)
print(f"chapitre 7 : {len(raw_text):,} car.  spans={len(spans)} (dialogue={n_dialogue})  -> {len(chunks)} chunk(s)")


async def main() -> None:
    provider = llm_factory.get_llm_provider(settings)
    t0 = time.perf_counter()
    results = [await provider.analyze(c) for c in chunks]
    elapsed = time.perf_counter() - t0
    merged = _merge_chunk_results(results)
    dialogue_segs = [s for s in merged.segments if s.segment_type == SegmentType.DIALOGUE]
    attributed = sum(1 for s in dialogue_segs if s.character_name)
    print(f"\nTEMPS TOTAL : {elapsed:.1f}s  ({elapsed/len(chunks):.1f}s/chunk)")
    print(f"personnages : {len(merged.characters)}")
    print(f"dialogue segments : {len(dialogue_segs)}  attribués : {attributed} / {n_dialogue}")


asyncio.run(main())
