"""Spike de faisabilité -- clonage de voix Qwen3-TTS (étape 0, chantier clonage).

PAS une suite de régression : aucun assert. Dépendances : requirements-qwen.txt
(torch/qwen-tts déjà installés depuis B3).

NOTE ARCHITECTURE (validée par lecture du package installé, 2026-06-27) :
  - generate_voice_clone n'existe que sur le checkpoint "Base" (Qwen3-TTS-12Hz-1.7B-Base).
  - Les modèles "CustomVoice" (presets/émotion) et "Base" (clonage) sont DISTINCTS :
    deux chargements séparés, ~4,2 Go VRAM chacun.
  - generate_voice_clone N'A PAS de paramètre `instruct` → émotion et clonage sont
    mutuellement exclusifs au niveau modèle. À acter avant le Plan-First contrat.

⚠  Avant de lancer :
    ollama stop qwen3:8b        # libérer VRAM avant chargement
    nvidia-smi en parallèle     # surveiller pics VRAM en temps réel
    Event Viewer prêt           # crash natif backend non diagnostiqué : si ce process
                                # meurt sans message Python, c'est un crash CUDA/natif

Run :
    .venv\\Scripts\\python tests/spike_qwen_clone.py

Options :
    --ref PATH       Audio de référence WAV ou MP3, 3-30 s
                     [défaut : tests/refs/ref_voice.mp3]
    --trim N         Secondes max à conserver du fichier de réf [défaut : 10]
    --ref-text TEXT  Transcript de l'audio de référence (requis pour ICL mode).
                     Si absent, seul x_vector_only est testé.
    --model          1.7b (défaut) | 0.6b
    --attn           sdpa (défaut, recommandé Windows) | flash_attention_2
    --language       [défaut : French]
    --vram-dual      ⚠ Risque OOM. Charge Base+CustomVoice simultanément pour
                     mesurer la cohabitation VRAM → tranche Décision 2 du Plan-First.
    --outdir         [défaut : Ebook/spike_qwen_clone]

Décisions tranchées par ce spike :
    Décision 2 (VRAM)  : mesure Base seul + opt-in Base+CustomVoice ensemble
    Décision 3 (mode)  : fidélité x_vector_only vs ICL → verdict à l'écoute des paires
"""
import argparse
import array
import audioop
import io
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

_BASE_MODEL_IDS = {
    "1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
}
_CUSTOM_VOICE_MODEL_IDS = {
    "1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
}
_OUTPUT_SAMPLE_RATE = 22050  # format partagé ScriptVox

_TEST_PHRASES = [
    "Le vent soufflait doucement sur la prairie endormie.",
    "Mais non ! Il faut absolument partir maintenant.",
    "Elle prit le livre et l'ouvrit à la première page.",
]

# Repère EdgeTTS réel : 164 segments en 2 min 48 s (TASKS.md Phase 12 Étape 6)
_EDGETTS_S_PER_SEG = (2 * 60 + 48) / 164


def _fail(msg: str) -> None:
    print(f"\nERREUR: {msg}\n", file=sys.stderr, flush=True)
    sys.exit(1)


def _load_deps():
    try:
        import torch
    except ImportError:
        _fail(
            "torch manquant :\n"
            "  .venv\\Scripts\\pip install torch --index-url https://download.pytorch.org/whl/cu128"
        )
    try:
        from qwen_tts import Qwen3TTSModel
    except ImportError:
        _fail("qwen-tts manquant : .venv\\Scripts\\pip install qwen-tts")
    try:
        import miniaudio
    except ImportError:
        _fail("miniaudio manquant : pip install -r requirements.txt")
    if not torch.cuda.is_available():
        _fail("Aucun GPU CUDA détecté (torch.cuda.is_available() == False).")
    return torch, Qwen3TTSModel, miniaudio


def _load_ref_audio(path: str, trim_s: float, miniaudio):
    """Charge MP3/WAV → numpy float32 mono, tronqué à trim_s secondes."""
    import numpy as np
    p = Path(path)
    if not p.exists():
        _fail(
            f"Fichier de référence introuvable : {p}\n"
            "  Placer l'audio de référence dans tests/refs/ref_voice.mp3\n"
            "  ou passer --ref <chemin>"
        )
    print(f"  Ref audio : {p.name}", flush=True)
    # Récupérer le sample rate natif avant decode (decode_file exige un entier > 0)
    ext = p.suffix.lower()
    if ext == ".mp3":
        native_sr = miniaudio.mp3_get_file_info(str(p)).sample_rate
    elif ext == ".flac":
        native_sr = miniaudio.flac_get_file_info(str(p)).sample_rate
    else:
        native_sr = miniaudio.wav_get_file_info(str(p)).sample_rate
    decoded = miniaudio.decode_file(
        str(p),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,          # stéréo → mono automatiquement
        sample_rate=native_sr,
    )
    sr = decoded.sample_rate
    samples_i16 = np.frombuffer(bytes(decoded.samples), dtype=np.int16)
    max_frames = int(trim_s * sr)
    samples_i16 = samples_i16[:max_frames]
    samples_f32 = samples_i16.astype(np.float32) / 32768.0
    duration = len(samples_f32) / sr
    print(f"  -> {duration:.2f} s / {sr} Hz mono ({len(samples_f32)} frames)", flush=True)
    return samples_f32, sr


def _to_wav_bytes(wavs_out, sr_from_model: int) -> bytes:
    """numpy float32 → PCM16 → resample vers 22050 → WAV bytes (pipeline production)."""
    samples = wavs_out[0]
    ints = [int(max(-1.0, min(1.0, float(s))) * 32767) for s in samples]
    pcm16 = array.array("h", ints).tobytes()
    if sr_from_model != _OUTPUT_SAMPLE_RATE:
        pcm16, _ = audioop.ratecv(pcm16, 2, 1, sr_from_model, _OUTPUT_SAMPLE_RATE, None)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_OUTPUT_SAMPLE_RATE)
        w.writeframes(pcm16)
    return buf.getvalue()


def _load_model(model_id: str, attn: str, torch):
    print(f"\nChargement {model_id} ...", flush=True)
    from qwen_tts import Qwen3TTSModel
    t0 = time.perf_counter()
    model = Qwen3TTSModel.from_pretrained(
        model_id,
        device_map="cuda:0",
        dtype=torch.bfloat16,
        attn_implementation=attn,
    )
    return model, time.perf_counter() - t0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--ref",
        default=str(ROOT / "tests" / "refs" / "ref_voice.mp3"),
        help="Audio de référence (WAV ou MP3)",
    )
    parser.add_argument(
        "--trim", type=float, default=10.0,
        help="Durée max de l'audio de réf en secondes (défaut : 10)",
    )
    parser.add_argument(
        "--ref-text", default=None,
        help="Transcript de l'audio de référence pour le mode ICL",
    )
    parser.add_argument("--model", choices=sorted(_BASE_MODEL_IDS), default="1.7b")
    parser.add_argument("--attn", choices=["sdpa", "flash_attention_2"], default="sdpa")
    parser.add_argument("--language", default="French")
    parser.add_argument(
        "--vram-dual", action="store_true",
        help="⚠ Risque OOM : charge Base+CustomVoice simultanément (Décision 2)",
    )
    parser.add_argument("--outdir", default=str(ROOT / "Ebook" / "spike_qwen_clone"))
    args = parser.parse_args()

    torch, Qwen3TTSModel, miniaudio = _load_deps()
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nBase model  : {_BASE_MODEL_IDS[args.model]}", flush=True)
    print(f"Langue      : {args.language} | attn : {args.attn}", flush=True)
    print(f"Sortie      : {out_dir}\n", flush=True)

    # --- Chargement audio de référence ---
    ref_samples, ref_sr = _load_ref_audio(args.ref, args.trim, miniaudio)
    ref_audio_arg = (ref_samples, ref_sr)  # format (np.ndarray, sr) accepté par Qwen

    # Modes à tester : x_vector toujours, ICL seulement si --ref-text fourni
    modes: list[tuple[str, bool, str | None]] = [("xvec", True, None)]
    if args.ref_text:
        modes.append(("icl", False, args.ref_text))
    else:
        print("  [ICL mode non activé : --ref-text absent → uniquement x_vector_only testé]", flush=True)

    # --- Chargement modèle Base ---
    torch.cuda.reset_peak_memory_stats()
    vram_before = torch.cuda.memory_allocated() / 1e9
    base_model, load_s = _load_model(_BASE_MODEL_IDS[args.model], args.attn, torch)
    vram_after_load = torch.cuda.memory_allocated() / 1e9
    print(
        f"  chargé en {load_s:.1f} s — VRAM : {vram_after_load:.2f} Go "
        f"(delta {vram_after_load - vram_before:.2f} Go)",
        flush=True,
    )

    # --- Génération clonée ---
    rows: list[tuple[str, str, float]] = []
    sr_seen: int | None = None

    for i, phrase in enumerate(_TEST_PHRASES, start=1):
        for tag, xvec_only, ref_text in modes:
            label = f"[{i:02d}] {tag}"
            print(f"\n{label} | {phrase[:50]}", flush=True)
            t0 = time.perf_counter()
            wavs, sr = base_model.generate_voice_clone(
                text=phrase,
                language=args.language,
                ref_audio=ref_audio_arg,
                ref_text=ref_text,
                x_vector_only_mode=xvec_only,
            )
            elapsed = time.perf_counter() - t0
            sr_seen = sr
            fname = out_dir / f"{i:02d}_{tag}.wav"
            fname.write_bytes(_to_wav_bytes(wavs, sr))
            print(f"  {elapsed:.2f} s -> {fname.name}", flush=True)
            rows.append((phrase[:30], tag, elapsed))

    peak_vram = torch.cuda.max_memory_allocated() / 1e9

    # --- Cohabitation Base+CustomVoice (opt-in, risque OOM) ---
    vram_dual: float | None = None
    if args.vram_dual:
        print(
            f"\n⚠  --vram-dual : chargement CustomVoice ({_CUSTOM_VOICE_MODEL_IDS[args.model]}) "
            "en plus du Base déjà résidant...",
            flush=True,
        )
        try:
            custom_model, _ = _load_model(_CUSTOM_VOICE_MODEL_IDS[args.model], args.attn, torch)
            vram_dual = torch.cuda.memory_allocated() / 1e9
            print(f"  VRAM Base+CustomVoice résidents : {vram_dual:.2f} Go", flush=True)
            del custom_model
            torch.cuda.empty_cache()
        except Exception as exc:
            print(f"  ÉCHEC (probablement OOM) : {exc}", flush=True)

    # --- Résumé ---
    times = [r[2] for r in rows]
    avg = sum(times) / len(times)

    print("\n" + "-" * 64)
    print("RÉSUMÉ")
    print(f"  sample rate retourné (modèle)  : {sr_seen} Hz → resampleé vers {_OUTPUT_SAMPLE_RATE} Hz")
    print(f"  chargement Base                : {load_s:.1f} s")
    print(f"  VRAM Base seul                 : {vram_after_load - vram_before:.2f} Go")
    print(f"  VRAM pic (génération)          : {peak_vram:.2f} Go")
    if vram_dual is not None:
        print(f"  VRAM Base+CustomVoice ensemble : {vram_dual:.2f} Go  ← Décision 2")
    print(f"  temps moyen / phrase           : {avg:.2f} s (min {min(times):.2f} / max {max(times):.2f})")
    print(f"  repère EdgeTTS                 : ~{_EDGETTS_S_PER_SEG:.2f} s/segment")
    if avg > 0:
        print(f"  -> Qwen clone ≈ x{avg / _EDGETTS_S_PER_SEG:.1f} le temps d'EdgeTTS par réplique")

    print(f"\nFichiers générés dans : {out_dir}")
    for i, phrase in enumerate(_TEST_PHRASES, start=1):
        for tag, _, _ in modes:
            print(f"  {i:02d}_{tag}.wav  ← {phrase[:55]}")
    if len(modes) > 1:
        print("\nÉcouter les paires *_xvec.wav / *_icl.wav pour juger la fidélité  ← Décision 3")

    print(
        "\n⚠  Si ce process est mort avant ce message : crash natif CUDA (non diagnostiqué).\n"
        "   Consulter Event Viewer → Windows Logs → Application et nvidia-smi."
    )


if __name__ == "__main__":
    main()
