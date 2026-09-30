"""Banc LLM comparatif : vitesse, exactitude, cohérence des noms, parallélisme.

Rend les MÊMES chapitres avec plusieurs modèles et enregistre, par réplique, le locuteur choisi.
Vérité terrain partielle : les répliques dont l'incise nomme le locuteur (« dit Harry »). Le
déterminisme du parseur est coupé pendant la mesure pour voir ce que le LLM trouve seul.

    python scripts/bench_llm_compare.py run --epub Ebook/livre.epub --model qwen3:1.7b --tag 1.7b
    python scripts/bench_llm_compare.py run ... --model qwen3:1.7b --concurrency 4 --tag 1.7b-par4
    python scripts/bench_llm_compare.py report --ref 14b results/llm_compare/*.json
"""
import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

OUT_DIR = ROOT / "results" / "llm_compare"


class _Warn(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        self.count += 1


async def run(args) -> int:
    import app.services.llm.base as B
    import app.services.llm.ollama as O
    from app.config import get_settings
    from app.core.enums import SegmentType
    from app.services.epub.parser import EpubParser
    from app.services.llm.factory import get_llm_provider

    gold: dict[int, dict[int, str]] = {}  # n° de bloc -> {index de span: nom d'incise}
    orig = B._pre_segment
    counter = {"n": 0}

    def patched(text, profile=B.FR_PROFILE):
        spans = orig(text, profile)
        counter["n"] += 1
        g, pos = {}, 0
        for s in spans:
            if not B._segment_text(s):
                continue
            pos += 1
            if s.incise_character:
                g[pos] = s.incise_character
        gold[counter["n"]] = g
        return [replace(s, incise_character=None) for s in spans]

    O._pre_segment = patched

    settings = get_settings()
    options = {"model": args.model, "base_url": args.base_url}
    provider = get_llm_provider(settings, override="ollama", options=options)
    provider._num_ctx = args.num_ctx
    warn = _Warn()
    logging.getLogger("app.services.llm").addHandler(warn)

    book = EpubParser().parse(str(args.epub))
    chapters = [c for c in book.chapters if c.included and len(c.raw_text) >= 1500]
    chapters = chapters[args.skip: args.skip + args.chapters]

    jobs: list[tuple[int, int, str]] = []  # (chapitre, n° de bloc, texte)
    for ch in chapters:
        for chunk in B._chunk_text(ch.raw_text, args.budget):
            jobs.append((ch.position, len(jobs) + 1, chunk))

    results: dict[int, dict] = {}
    known: list[str] = []
    sem = asyncio.Semaphore(args.concurrency)
    started = time.perf_counter()

    async def one(chapter, block, chunk, known_snapshot):
        async with sem:
            t0 = time.perf_counter()
            counter["n"] = block - 1
            res = await provider.analyze(chunk, known_snapshot, language=book.language)
            return block, {
                "chapter": chapter, "secondes": time.perf_counter() - t0,
                "characters": [c.name for c in res.characters],
                "segments": [[s.position, s.segment_type.value, s.character_name, s.text[:60]] for s in res.segments],
            }

    if args.concurrency == 1:
        for chapter, block, chunk in jobs:
            b, r = await one(chapter, block, chunk, list(known))
            results[b] = r
            known = sorted({*known, *r["characters"]})
            print(f"  bloc {b} (ch.{chapter}) {r['secondes']:.0f} s", flush=True)
    else:
        done = await asyncio.gather(*(one(c, b, t, []) for c, b, t in jobs))
        for b, r in done:
            results[b] = r

    total = time.perf_counter() - started
    unload = getattr(provider, "unload", None)
    if callable(unload):
        unload()
    # le patch numérote les blocs dans l'ordre d'appel : en parallèle il faut rattacher l'or à chaque bloc
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"tag": args.tag, "model": args.model, "concurrency": args.concurrency,
               "num_ctx": args.num_ctx, "secondes": total, "avertissements": warn.count,
               "blocs": results, "or": {str(k): v for k, v in gold.items()}}
    (OUT_DIR / f"{args.tag}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"{args.tag}: {total:.0f} s, {len(results)} blocs, {warn.count} avertissements")
    return 0


def report(args) -> int:
    import app.services.llm.base as B

    runs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.files]
    ref = next((r for r in runs if r["tag"] == args.ref), None)
    print(f"{'tag':<14}{'modèle':<34}{'par.':>4}{'s':>7}{'répl.':>7}{'sans loc.':>10}"
          f"{'or ok':>10}{'vs réf':>9}{'persos':>8}{'warn':>6}")
    for r in runs:
        nd = unattr = gold_n = gold_ok = agree = agree_n = 0
        names: set[str] = set()
        for b, blk in r["blocs"].items():
            names.update(blk["characters"])
            known_names = set(blk["characters"])
            g = {int(k): v for k, v in (r["or"].get(b) or {}).items()}
            refblk = ref["blocs"].get(b) if ref else None
            refseg = {s[0]: s[2] for s in refblk["segments"]} if refblk else {}
            for pos, typ, name, _ in blk["segments"]:
                if typ != "DIALOGUE":
                    continue
                nd += 1
                if not name:
                    unattr += 1
                if pos in g:
                    gold_n += 1
                    if name and B._resolve_character_name(g[pos], known_names) == name:
                        gold_ok += 1
                elif refseg and pos in refseg:
                    agree_n += 1
                    if name and refseg[pos] and (name == refseg[pos] or
                                                 B._resolve_character_name(name, {refseg[pos]}) == refseg[pos]):
                        agree += 1
        gold_s = f"{gold_ok}/{gold_n}" if gold_n else "-"
        agree_s = f"{agree / agree_n:.0%}" if agree_n else "-"
        print(f"{r['tag']:<14}{r['model'][:33]:<34}{r['concurrency']:>4}{r['secondes']:>7.0f}{nd:>7}"
              f"{unattr:>10}{gold_s:>10}{agree_s:>9}{len(names):>8}{r['avertissements']:>6}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--epub", required=True, type=Path)
    r.add_argument("--model", required=True)
    r.add_argument("--tag", required=True)
    r.add_argument("--base-url", default="http://127.0.0.1:11435")
    r.add_argument("--chapters", type=int, default=4)
    r.add_argument("--skip", type=int, default=0)
    r.add_argument("--concurrency", type=int, default=1)
    r.add_argument("--num-ctx", type=int, default=20480)
    r.add_argument("--budget", type=int, default=9000, help="tokens estimés max par appel")
    p = sub.add_parser("report")
    p.add_argument("--ref")
    p.add_argument("files", nargs="+")
    args = ap.parse_args()
    return asyncio.run(run(args)) if args.cmd == "run" else report(args)


if __name__ == "__main__":
    sys.exit(main())
