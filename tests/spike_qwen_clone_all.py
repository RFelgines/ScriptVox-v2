"""Spike clonage multi-voix -- charge le modèle Base une seule fois, itère sur
tous les fichiers audio présents dans tests/refs/ et génère 3 phrases clonées
par voix dans Ebook/spike_qwen_clone/<nom_voix>/.

Run :
    .venv\\Scripts\\python tests/spike_qwen_clone_all.py

Options :
    --trim N      Durée max de l'audio de réf en secondes [défaut : 10]
    --model       1.7b (défaut) | 0.6b
    --attn        sdpa (défaut) | flash_attention_2
    --language    [défaut : French]
    --outdir      [défaut : Ebook/spike_qwen_clone]
    --refs-dir    [défaut : tests/refs]
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
_OUTPUT_SAMPLE_RATE = 22050

_TEST_PHRASES = [
    "Le vent soufflait doucement sur la prairie endormie.",
    "Mais non ! Il faut absolument partir maintenant.",
    "Elle prit le livre et l'ouvrit à la première page.",
]

_EDGETTS_S_PER_SEG = (2 * 60 + 48) / 164
_AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}


def _fail(msg: str) -> None:
    print(f"\nERREUR: {msg}\n", file=sys.stderr, flush=True)
    sys.exit(1)


def _load_deps():
    try:
        import torch
    except ImportError:
        _fail("torch manquant : pip install torch --index-url https://download.pytorch.org/whl/cu128")
    try:
        from qwen_tts import Qwen3TTSModel
    except ImportError:
        _fail("qwen-tts manquant : pip install qwen-tts")
    try:
        import miniaudio
    except ImportError:
        _fail("miniaudio manquant : pip install -r requirements.txt")
    if not torch.cuda.is_available():
        _fail("Aucun GPU CUDA détecté.")
    return torch, Qwen3TTSModel, miniaudio


def _load_ref_audio(path: Path, trim_s: float, miniaudio):
    import numpy as np
    ext = path.suffix.lower()
    if ext == ".mp3":
        native_sr = miniaudio.mp3_get_file_info(str(path)).sample_rate
    elif ext == ".flac":
        native_sr = miniaudio.flac_get_file_info(str(path)).sample_rate
    else:
        native_sr = miniaudio.wav_get_file_info(str(path)).sample_rate
    decoded = miniaudio.decode_file(
        str(path),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=native_sr,
    )
    samples_i16 = np.frombuffer(bytes(decoded.samples), dtype=np.int16)
    samples_i16 = samples_i16[: int(trim_s * native_sr)]
    samples_f32 = samples_i16.astype(np.float32) / 32768.0
    duration = len(samples_f32) / native_sr
    return samples_f32, native_sr, duration


def _to_wav_bytes(wavs_out, sr_from_model: int) -> bytes:
    ints = [int(max(-1.0, min(1.0, float(s))) * 32767) for s in wavs_out[0]]
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trim", type=float, default=10.0)
    parser.add_argument("--model", choices=sorted(_BASE_MODEL_IDS), default="1.7b")
    parser.add_argument("--attn", choices=["sdpa", "flash_attention_2"], default="sdpa")
    parser.add_argument("--language", default="French")
    parser.add_argument("--outdir", default=str(ROOT / "Ebook" / "spike_qwen_clone"))
    parser.add_argument("--refs-dir", default=str(ROOT / "tests" / "refs"))
    args = parser.parse_args()

    torch, Qwen3TTSModel, miniaudio = _load_deps()

    refs_dir = Path(args.refs_dir)
    ref_files = sorted(p for p in refs_dir.iterdir() if p.suffix.lower() in _AUDIO_EXTS)
    if not ref_files:
        _fail(f"Aucun fichier audio trouvé dans {refs_dir}")

    out_root = Path(args.outdir)
    model_id = _BASE_MODEL_IDS[args.model]

    print(f"\nModèle : {model_id}", flush=True)
    print(f"Langue : {args.language} | attn : {args.attn}", flush=True)
    print(f"Voix   : {[p.stem for p in ref_files]}", flush=True)
    print(f"Sortie : {out_root}\n", flush=True)

    # --- Chargement modèle (une seule fois) ---
    torch.cuda.reset_peak_memory_stats()
    vram_before = torch.cuda.memory_allocated() / 1e9
    print(f"Chargement {model_id} ...", flush=True)
    t0 = time.perf_counter()
    model = Qwen3TTSModel.from_pretrained(
        model_id,
        device_map="cuda:0",
        dtype=torch.bfloat16,
        attn_implementation=args.attn,
    )
    load_s = time.perf_counter() - t0
    vram_loaded = torch.cuda.memory_allocated() / 1e9
    print(f"  chargé en {load_s:.1f} s — VRAM : {vram_loaded:.2f} Go\n", flush=True)

    # --- Boucle sur les voix ---
    all_times: list[float] = []
    sr_seen: int | None = None

    for ref_path in ref_files:
        voice_name = ref_path.stem
        print(f"{'='*60}", flush=True)
        print(f"Voix : {voice_name}", flush=True)

        samples_f32, ref_sr, ref_dur = _load_ref_audio(ref_path, args.trim, miniaudio)
        print(f"  ref : {ref_dur:.2f} s / {ref_sr} Hz mono", flush=True)

        out_dir = out_root / voice_name
        out_dir.mkdir(parents=True, exist_ok=True)

        for i, phrase in enumerate(_TEST_PHRASES, start=1):
            print(f"  [{i:02d}] {phrase[:55]}", flush=True)
            t0 = time.perf_counter()
            wavs, sr = model.generate_voice_clone(
                text=phrase,
                language=args.language,
                ref_audio=(samples_f32, ref_sr),
                x_vector_only_mode=True,
            )
            elapsed = time.perf_counter() - t0
            sr_seen = sr
            fname = out_dir / f"{i:02d}_xvec.wav"
            fname.write_bytes(_to_wav_bytes(wavs, sr))
            print(f"       {elapsed:.2f} s -> {fname.name}", flush=True)
            all_times.append(elapsed)

        print(f"  -> {out_dir}", flush=True)

    # --- Résumé global ---
    peak_vram = torch.cuda.max_memory_allocated() / 1e9
    avg = sum(all_times) / len(all_times)

    print(f"\n{'='*60}")
    print("RÉSUMÉ GLOBAL")
    print(f"  Voix traitées        : {len(ref_files)}")
    print(f"  WAVs générés         : {len(all_times)}")
    print(f"  sample rate modèle   : {sr_seen} Hz → {_OUTPUT_SAMPLE_RATE} Hz")
    print(f"  chargement modèle    : {load_s:.1f} s (une seule fois)")
    print(f"  VRAM modèle          : {vram_loaded - vram_before:.2f} Go")
    print(f"  VRAM pic             : {peak_vram:.2f} Go")
    print(f"  temps moyen / phrase : {avg:.2f} s (min {min(all_times):.2f} / max {max(all_times):.2f})")
    print(f"  -> Qwen clone ≈ x{avg / _EDGETTS_S_PER_SEG:.1f} le temps d'EdgeTTS")
    print(f"\nFichiers dans : {out_root}/<voix>/01_xvec.wav … 03_xvec.wav")


if __name__ == "__main__":
    main()
