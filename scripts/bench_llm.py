"""Banc d'essai LLM : compare des modèles sur les MÊMES chapitres d'un EPUB (protocole du projet).

Pour chaque chapitre : pré-segmentation, appel au moteur choisi, puis mesure
  - le taux d'attribution : répliques attribuées à un personnage / répliques détectées ;
  - la durée ; le nombre de personnages détectés ; les avertissements de réparation du parseur.
Une ligne CSV par exécution (results/llm_bench.csv) : lancer le script une fois par modèle, puis
comparer. Aucun modèle n'est privilégié : le meilleur est celui qui attribue le mieux SUR VOS
livres, dans un temps acceptable.

Exemples :
    python scripts/bench_llm.py --epub Ebook/livre.epub --chapters 3 --provider ollama --model qwen3:1.7b
    python scripts/bench_llm.py --epub Ebook/livre.epub --provider ollama --model qwen3.8:27b
    python scripts/bench_llm.py --epub Ebook/livre.epub --provider openai_compatible \\
        --model qwen3.8-27b --base-url http://localhost:1234/v1
    python scripts/bench_llm.py --epub Ebook/livre.epub --provider gemini --model gemini-3.1-flash-lite

Astuce VRAM : `ollama ps` pendant l'exécution montre si le modèle déborde sur le CPU (« 31 % CPU »),
ce qui ruine la vitesse : réduire OLLAMA_CONTEXT_TOKENS / OLLAMA_CHUNK_TOKENS ou la quantification.
"""
import argparse
import asyncio
import csv
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

MIN_CONTENT_CHARS = 1500  # ignore pages de garde / sommaire


class _WarnCounter(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        self.count += 1


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--epub", required=True, type=Path)
    ap.add_argument("--chapters", type=int, default=3, help="nombre de chapitres de contenu à mesurer")
    ap.add_argument("--provider", help="ollama | gemini | openai_compatible | <plugin> (défaut : .env)")
    ap.add_argument("--model", help="modèle (réglage à chaud, comme dans Paramètres)")
    ap.add_argument("--base-url", help="adresse du serveur")
    ap.add_argument("--csv", type=Path, default=ROOT / "results" / "llm_bench.csv")
    args = ap.parse_args()

    from app.config import get_settings
    from app.core.enums import SegmentType
    from app.services.epub.parser import EpubParser
    from app.services.llm.base import _chunk_text, _merge_chunk_results
    from app.services.llm.factory import get_llm_provider

    settings = get_settings()
    options = {k: v for k, v in (("model", args.model), ("base_url", args.base_url)) if v}
    provider = get_llm_provider(settings, override=args.provider, options=options)
    provider_name = args.provider or settings.llm_provider
    model_name = args.model or "(défaut .env)"
    budget = getattr(provider, "chunk_tokens", 12000)

    book = EpubParser().parse(str(args.epub))
    chapters = [c for c in book.chapters if c.included and len(c.raw_text) >= MIN_CONTENT_CHARS][: args.chapters]
    if not chapters:
        raise SystemExit("Aucun chapitre de contenu exploitable dans cet EPUB.")

    counter = _WarnCounter()
    logging.getLogger("app.services.llm").addHandler(counter)
    known: list[str] = []
    dialogues = attributed = 0
    started = time.perf_counter()
    for ch in chapters:
        t0 = time.perf_counter()
        results = [await provider.analyze(chunk, known, language=book.language) for chunk in _chunk_text(ch.raw_text, budget)]
        merged = _merge_chunk_results(results)
        d = [s for s in merged.segments if s.segment_type == SegmentType.DIALOGUE]
        a = [s for s in d if s.character_name]
        dialogues += len(d)
        attributed += len(a)
        known = sorted({*known, *(c.name for c in merged.characters)})
        print(f"  ch.{ch.position:<3} {len(a)}/{len(d)} répliques attribuées  {time.perf_counter() - t0:6.1f} s")
    total = time.perf_counter() - started
    unload = getattr(provider, "unload", None)
    if callable(unload):
        unload()

    rate = attributed / dialogues if dialogues else 0.0
    print(f"\n{provider_name} / {model_name} : attribution {rate:.0%} ({attributed}/{dialogues}), "
          f"{len(known)} personnages, {total:.0f} s, {counter.count} avertissements du parseur")
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    new = not args.csv.exists()
    with args.csv.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["date", "epub", "provider", "model", "chapitres", "repliques", "attribuees",
                        "taux_attribution", "personnages", "secondes", "avertissements"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), args.epub.name, provider_name, model_name,
                    len(chapters), dialogues, attributed, f"{rate:.3f}", len(known), f"{total:.1f}", counter.count])
    print(f"Ligne ajoutée à {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
