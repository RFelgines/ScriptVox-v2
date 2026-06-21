"""Spike de faisabilité -- Qwen3-TTS local (émotion par réplique).

PAS une suite de régression : aucun assert. Dépendances installées à la main
(PAS dans requirements.txt -- rien n'est tranché). Sert à mesurer, avant tout
engagement, la qualité FR, l'effet réel du paramètre `instruct` (émotion par
réplique) et le coût VRAM/temps sur cette machine.

Pré-requis (à exécuter manuellement dans la venv) :
    .venv\\Scripts\\pip install torch --index-url https://download.pytorch.org/whl/cu128
    .venv\\Scripts\\pip install qwen-tts soundfile

Run :
    .venv/Scripts/python tests/spike_qwen_tts.py [--model 1.7b|0.6b] [--speaker Vivian]
                                                  [--language French] [--attn sdpa|flash_attention_2]

Sortie : Ebook/spike_qwen/<NN>_<sans|avec>_instruct.wav (gitignoré) + résumé console
(temps de chargement, VRAM pic, temps/réplique, comparaison au repère EdgeTTS réel :
164 segments / 2 min 48 s, TASKS.md Phase 12 Étape 6).

Test de cohabitation VRAM (manuel, 2 runs) :
    1) `ollama ps` doit montrer qwen3:8b chargé -> lancer ce script -> noter VRAM/erreurs.
    2) `ollama stop qwen3:8b` -> relancer ce script -> comparer.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Console Windows (cp1252) : la sortie ci-dessous contient des accents français.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

_MODEL_IDS = {
    "1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
}

# (verbe, texte, instruction d'émotion FR)
_LINES: list[tuple[str, str, str]] = [
    ("cria", "Mais non ! cria Harry, hors de lui.",
     "Dis cette phrase en criant, d'une voix furieuse et paniquée."),
    ("murmura", "Je crois qu'on est suivis, murmura-t-elle, apeurée.",
     "Dis cette phrase en chuchotant, d'une voix apeurée et tremblante."),
    ("dit calmement", "Tout va bien, dit-il calmement.",
     "Dis cette phrase d'une voix calme et posée, presque monocorde."),
    ("hurla de rage", "Sors de cette maison immédiatement ! hurla-t-il de rage.",
     "Dis cette phrase en hurlant de rage, voix tendue et agressive."),
    ("s'exclama joyeusement", "On a gagné ! s'exclama-t-elle, débordante de joie.",
     "Dis cette phrase avec une joie débordante, enthousiaste et rieuse."),
    ("demanda timidement", "Est-ce que je peux venir avec vous ? demanda-t-il timidement.",
     "Dis cette phrase timidement, d'une voix hésitante et peu sûre de soi."),
    ("dit froidement", "Je ne te crois pas, dit-elle froidement.",
     "Dis cette phrase d'un ton froid, détaché et méprisant."),
    ("narration", "La pluie tombait sans bruit sur les pavés de la vieille ville.",
     "Lis cette phrase d'une voix de narrateur neutre, posée et fluide."),
]

# Repère réel EdgeTTS (TASKS.md Phase 12 Étape 6) : 164 segments / 2 min 48 s.
_EDGETTS_S_PER_SEGMENT = (2 * 60 + 48) / 164


def _fail(msg: str) -> None:
    print(f"\nERREUR: {msg}\n", file=sys.stderr)
    sys.exit(1)


def _load_deps():
    try:
        import torch
    except ImportError:
        _fail(
            "torch manquant. Installer manuellement (PAS dans requirements.txt) :\n"
            "  .venv\\Scripts\\pip install torch --index-url https://download.pytorch.org/whl/cu128"
        )
    try:
        import soundfile as sf
    except ImportError:
        _fail("soundfile manquant : .venv\\Scripts\\pip install soundfile")
    try:
        from qwen_tts import Qwen3TTSModel
    except ImportError:
        _fail("qwen-tts manquant : .venv\\Scripts\\pip install qwen-tts")
    if not torch.cuda.is_available():
        _fail("Aucun GPU CUDA détecté (torch.cuda.is_available() == False).")
    return torch, sf, Qwen3TTSModel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=sorted(_MODEL_IDS), default="1.7b")
    parser.add_argument(
        "--speaker", default="Vivian",
        help="Preset : Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee",
    )
    parser.add_argument("--language", default="French")
    parser.add_argument(
        "--attn", choices=["sdpa", "flash_attention_2"], default="sdpa",
        help="sdpa = sans FlashAttention 2 (recommandé sous Windows)",
    )
    parser.add_argument("--outdir", default=str(ROOT / "Ebook" / "spike_qwen"))
    args = parser.parse_args()

    torch, sf, Qwen3TTSModel = _load_deps()
    model_id = _MODEL_IDS[args.model]
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Modèle    : {model_id}")
    print(f"Speaker   : {args.speaker}  |  Langue : {args.language}  |  attn : {args.attn}")
    print(f"Sortie    : {out_dir}\n")

    torch.cuda.reset_peak_memory_stats()
    vram_before = torch.cuda.memory_allocated() / 1e9

    print("Chargement du modèle...")
    t0 = time.perf_counter()
    model = Qwen3TTSModel.from_pretrained(
        model_id, device_map="cuda:0", dtype=torch.bfloat16, attn_implementation=args.attn,
    )
    load_s = time.perf_counter() - t0
    vram_after_load = torch.cuda.memory_allocated() / 1e9
    print(
        f"  chargé en {load_s:.1f} s -- VRAM allouée : {vram_after_load:.2f} Go "
        f"(delta {vram_after_load - vram_before:.2f} Go)\n"
    )

    rows: list[tuple[str, bool, float]] = []
    sr_seen: int | None = None

    for i, (verb, text, instruct) in enumerate(_LINES, start=1):
        for with_instruct in (False, True):
            kwargs = dict(text=text, language=args.language, speaker=args.speaker)
            if with_instruct:
                kwargs["instruct"] = instruct
            tag = "avec_instruct" if with_instruct else "sans_instruct"

            t0 = time.perf_counter()
            wavs, sr = model.generate_custom_voice(**kwargs)
            elapsed = time.perf_counter() - t0
            sr_seen = sr

            wav_path = out_dir / f"{i:02d}_{tag}.wav"
            sf.write(str(wav_path), wavs[0], sr)

            print(f"[{i:02d}] {verb:<24} {tag:<14} {elapsed:6.2f} s  -> {wav_path.name}")
            rows.append((verb, with_instruct, elapsed))

    peak_vram = torch.cuda.max_memory_allocated() / 1e9
    times = [r[2] for r in rows]
    avg = sum(times) / len(times)

    print("\n" + "-" * 64)
    print("RÉSUMÉ")
    print(f"  sample rate retourné       : {sr_seen} Hz")
    print(f"  chargement modèle          : {load_s:.1f} s")
    print(f"  VRAM allouée (modèle seul) : {vram_after_load - vram_before:.2f} Go")
    print(f"  VRAM pic (génération)      : {peak_vram:.2f} Go")
    print(
        f"  temps moyen / réplique     : {avg:.2f} s   (min {min(times):.2f} / max {max(times):.2f})"
    )
    print(
        f"  repère EdgeTTS réel        : ~{_EDGETTS_S_PER_SEGMENT:.2f} s / segment "
        "(164 segments / 2 min 48 s, TASKS.md Phase 12 Étape 6)"
    )
    if avg > 0:
        ratio = avg / _EDGETTS_S_PER_SEGMENT
        print(f"  -> Qwen3-TTS est environ x{ratio:.1f} le temps d'EdgeTTS par réplique")
    print(
        "\nÉcouter les paires *_sans_instruct.wav / *_avec_instruct.wav dans "
        f"{out_dir} pour juger l'effet de l'émotion."
    )
    print(
        "\nPour le test de cohabitation VRAM : relancer après `ollama stop qwen3:8b` "
        "et comparer le pic VRAM ci-dessus."
    )


if __name__ == "__main__":
    main()
