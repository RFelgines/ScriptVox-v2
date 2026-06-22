"""Échantillons d'écoute pour clore B3 (QwenTTSProvider) -- PAS une suite de régression,
aucun assert. Contrairement à spike_qwen_tts.py (qui appelait le SDK Qwen directement),
ce script appelle le vrai `QwenTTSProvider.synthesise()` de production (app/services/tts/qwen.py)
-- donc valide aussi le chemin d'intégration réel (resolve_voice/_VOICE_MAP, resampling
24000->22050 Hz, écriture WAV), pas seulement le modèle brut.

Génère 2 lots de WAV dans Ebook/qwen_b3_listening/ (gitignoré) :
  1) Mapping des 9 voice_id logiques -> presets Qwen (_VOICE_MAP), même phrase de narration
     neutre pour chacun -- à écouter pour juger si le genre/âge perçu correspond au slot
     logique (ex: female_0 doit sonner féminin).
  2) Effet de l'émotion (`instruct`) sur un seul voice_id, 4 répliques contrastées,
     chacune avec et sans instruct -- paires *_sans_instruct.wav / *_avec_instruct.wav.

Run : .venv\\Scripts\\python tests\\spike_qwen_b3_listening.py
"""
import asyncio
import subprocess
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from app.services.tts.qwen import QwenTTSProvider  # noqa: E402

OUT_DIR = ROOT / "Ebook" / "qwen_b3_listening"

_NARRATION_LINE = "Le vent soufflait doucement sur la prairie endormie."

# Mêmes 9 IDs logiques que VOICE_CATALOGUE / _VOICE_MAP (app/services/tts/qwen.py).
_VOICE_IDS = [
    "narrator", "male_0", "male_1", "male_2",
    "female_0", "female_1", "female_2", "neutral_0", "neutral_1",
]

# (étiquette, texte, instruction d'émotion FR) -- repris de spike_qwen_tts.py.
_EMOTION_LINES: list[tuple[str, str, str]] = [
    ("crie", "Mais non ! cria Harry, hors de lui.",
     "Dis cette phrase en criant, d'une voix furieuse et paniquée."),
    ("murmure", "Je crois qu'on est suivis, murmura-t-elle, apeurée.",
     "Dis cette phrase en chuchotant, d'une voix apeurée et tremblante."),
    ("calme", "Tout va bien, dit-il calmement.",
     "Dis cette phrase d'une voix calme et posée, presque monocorde."),
    ("joie", "On a gagné ! s'exclama-t-elle, débordante de joie.",
     "Dis cette phrase avec une joie débordante, enthousiaste et rieuse."),
]

# Voix utilisée pour le lot émotion (un slot féminin, arbitraire -- le but est l'effet
# de l'instruct, pas le mapping de genre, déjà couvert par le lot 1).
_EMOTION_VOICE_ID = "female_1"


def _stop_ollama_model() -> None:
    # Best-effort : libère la VRAM tenue par qwen3:8b (keep_alive Ollama ~5 min) avant de
    # charger Qwen3-TTS. Sans incidence si rien n'est chargé ou si `ollama` est absent du PATH.
    try:
        subprocess.run(
            ["ollama", "stop", "qwen3:8b"],
            capture_output=True, timeout=15, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Sortie : {OUT_DIR}\n")

    _stop_ollama_model()

    provider = QwenTTSProvider(types.SimpleNamespace())  # défauts : 1.7b / French / cuda:0 / sdpa

    print("--- Lot 1 : mapping voice_id -> preset Qwen (_VOICE_MAP) ---")
    print(f"Phrase   : {_NARRATION_LINE}\n")
    for voice_id in _VOICE_IDS:
        t0 = time.perf_counter()
        wav_bytes = await provider.synthesise(_NARRATION_LINE, voice_id)
        elapsed = time.perf_counter() - t0
        path = OUT_DIR / f"voice_{voice_id}.wav"
        path.write_bytes(wav_bytes)
        print(f"  {voice_id:<10} {elapsed:6.2f} s -> {path.name}")

    print(f"\n--- Lot 2 : effet de l'instruct (voice_id={_EMOTION_VOICE_ID}) ---")
    for i, (label, text, instruct) in enumerate(_EMOTION_LINES, start=1):
        for with_instruct in (False, True):
            tag = "avec_instruct" if with_instruct else "sans_instruct"
            t0 = time.perf_counter()
            wav_bytes = await provider.synthesise(
                text, _EMOTION_VOICE_ID, emotion=instruct if with_instruct else None,
            )
            elapsed = time.perf_counter() - t0
            path = OUT_DIR / f"emotion_{i:02d}_{label}_{tag}.wav"
            path.write_bytes(wav_bytes)
            print(f"  [{i:02d}] {label:<8} {tag:<14} {elapsed:6.2f} s -> {path.name}")

    print(f"\nTerminé. {len(_VOICE_IDS) + len(_EMOTION_LINES) * 2} fichiers dans {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
