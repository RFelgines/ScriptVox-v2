"""Validation ponctuelle (pas une suite de régression) — chapitre 7 (le plus dense,
42 900 car.) avec /no_think + num_ctx réduit, pour valider avant un run complet.
Run: OLLAMA_CONTEXT_TOKENS=16384 .venv/Scripts/python tests/bench_ch7_no_think.py
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
from app.services.llm.base import _pre_segment  # noqa: E402

get_settings.cache_clear()
settings = get_settings()
print(f"num_ctx={settings.ollama_context_tokens}  model={settings.ollama_model}")

import tempfile, os  # noqa: E402
raw_text = Path(os.path.join(tempfile.gettempdir(), "ch7_raw.txt")).read_text(encoding="utf-8")
print(f"chapitre 7 : {len(raw_text):,} car.")

spans = _pre_segment(raw_text)
n_dialogue = sum(1 for s in spans if s.is_dialogue)
print(f"spans : {len(spans)} (dialogue={n_dialogue})")


async def main() -> None:
    provider = llm_factory.get_llm_provider(settings)
    t0 = time.perf_counter()
    result = await provider.analyze(raw_text)
    elapsed = time.perf_counter() - t0
    dialogue_segs = [s for s in result.segments if s.segment_type == SegmentType.DIALOGUE]
    attributed = sum(1 for s in dialogue_segs if s.character_name)
    print(f"\nTEMPS : {elapsed:.1f}s")
    print(f"personnages : {len(result.characters)}")
    print(f"dialogue segments : {len(dialogue_segs)}  attribués : {attributed} / {n_dialogue}")


asyncio.run(main())
