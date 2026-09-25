"""Banc d'écoute TTS : rend le même script français avec un moteur donné, pour COMPARER À L'OREILLE.

Aucun score automatique : la qualité d'une voix (naturel, accent, émotion) ne se mesure qu'à
l'écoute. Ce script produit un WAV par ligne du script + un WAV assemblé + les temps de synthèse,
dans data_test/listening/<moteur>[-<modèle>]/, pour écouter deux moteurs l'un après l'autre.

Exemples :
    python scripts/bench_tts.py --provider edgetts
    python scripts/bench_tts.py --provider qwen --model 1.7b
    python scripts/bench_tts.py --provider openai_tts --model kokoro --base-url http://localhost:8880/v1
    python scripts/bench_tts.py --provider mon_plugin            # un plugin de plugins/tts/
    python scripts/bench_tts.py --provider qwen --script mon_texte.txt --language fr

Le script (tests/listening/fr_script.txt par défaut) : une ligne « voix | émotion | texte ».
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")


def parse_script(path: Path) -> list[tuple[str, str | None, str]]:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        parts = [p.strip() for p in raw.split("|", 2)]
        if len(parts) != 3:
            raise SystemExit(f"Ligne invalide (attendu « voix | émotion | texte ») : {raw!r}")
        voice, emotion, text = parts
        lines.append((voice, None if emotion.lower() in ("", "neutral", "none") else emotion, text))
    return lines


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", required=True, help="edgetts | piper | qwen | openai_tts | command | <plugin>")
    ap.add_argument("--model", help="modèle / checkpoint (réglage à chaud, comme dans Paramètres)")
    ap.add_argument("--base-url", help="adresse du serveur (openai_tts…)")
    ap.add_argument("--locale", help="locale EdgeTTS (fr-FR…)")
    ap.add_argument("--language", default="fr", help="langue du livre simulée (fr | en)")
    ap.add_argument("--script", type=Path, default=ROOT / "tests" / "listening" / "fr_script.txt")
    ap.add_argument("--out", type=Path, default=ROOT / "data_test" / "listening")
    args = ap.parse_args()

    from app.config import get_settings
    from app.services.audio.assembler import assemble_wav_bytes
    from app.services.audio.format import normalize_audio, silence_wav, wav_duration_ms
    from app.services.tts.factory import get_tts_provider

    options = {k: v for k, v in (("model", args.model), ("base_url", args.base_url), ("locale", args.locale)) if v}
    settings = get_settings()
    provider = get_tts_provider(settings, override=args.provider, language=args.language, options=options)
    tag = args.provider + (f"-{args.model.replace('/', '_')}" if args.model else "")
    out_dir = args.out / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    parts: list[bytes] = []
    total_audio = total_wall = 0.0
    print(f"Moteur : {tag}  ->  {out_dir}")
    for i, (voice, emotion, text) in enumerate(parse_script(args.script), start=1):
        t0 = time.perf_counter()
        try:
            wav = normalize_audio(await provider.synthesise(text, voice, emotion=emotion))
        except Exception as exc:  # noqa: BLE001
            print(f"  {i:02d} {voice:<10} ÉCHEC : {exc}")
            continue
        wall = time.perf_counter() - t0
        dur = wav_duration_ms(wav) / 1000
        total_audio += dur
        total_wall += wall
        (out_dir / f"{i:02d}_{voice}.wav").write_bytes(wav)
        parts += [wav, silence_wav(400)]
        print(f"  {i:02d} {voice:<10} {dur:5.1f} s d'audio en {wall:5.1f} s  (x{dur / wall:4.1f} temps réel)")
    if parts:
        (out_dir / "_tout.wav").write_bytes(assemble_wav_bytes(parts[:-1]))
        print(f"Total : {total_audio:.0f} s d'audio en {total_wall:.0f} s  ->  {out_dir / '_tout.wav'}")
    unload = getattr(provider, "unload", None)
    if callable(unload):
        unload()
    return 0 if parts else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
