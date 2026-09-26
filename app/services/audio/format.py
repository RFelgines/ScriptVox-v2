"""Format audio commun à tout le pipeline + conversions.

Toute sortie de provider TTS est normalisée ici en **WAV mono 16 bits à OUTPUT_SAMPLE_RATE**
avant assemblage. Conséquence pratique : un provider (officiel, plugin, serveur HTTP, commande
externe) peut renvoyer du WAV/MP3/FLAC/OGG à n'importe quelle fréquence ; le pipeline s'en
accommode via `normalize_audio`.

24 kHz : fréquence native d'EdgeTTS et de Qwen3-TTS (audit 2026-09-25, AUD-3) — plus de
rééchantillonnage vers le bas, et plus de dépendance au module `audioop` (retiré de Python 3.13+).
Dépendances : `miniaudio` (déjà requis) pour décoder/rééchantillonner ; `numpy` pour les opérations
vectorielles (silences, niveau sonore, conversion float -> PCM).
"""
import array
import io
import wave

import miniaudio

OUTPUT_SAMPLE_RATE = 24000
_SAMPLE_WIDTH = 2  # 16 bits

_RIFF = b"RIFF"


def pcm16_to_wav(pcm: bytes, sample_rate: int = OUTPUT_SAMPLE_RATE, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(_SAMPLE_WIDTH)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def float_to_pcm16(samples) -> bytes:
    """Échantillons float32 dans [-1, 1] -> PCM 16 bits little-endian (vectorisé)."""
    try:
        import numpy as np
    except ImportError:  # pragma: no cover — numpy est une dépendance de requirements.txt
        ints = [int(max(-1.0, min(1.0, float(s))) * 32767) for s in samples]
        return array.array("h", ints).tobytes()
    a = np.asarray(samples, dtype=np.float32).reshape(-1)
    return (np.clip(a, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def resample_pcm16(pcm: bytes, src_rate: int, dst_rate: int = OUTPUT_SAMPLE_RATE,
                   channels: int = 1) -> bytes:
    """Rééchantillonne du PCM 16 bits (miniaudio : filtre passe-bas, pas d'interpolation naïve)."""
    if src_rate == dst_rate or not pcm:
        return pcm
    out = miniaudio.convert_frames(
        miniaudio.SampleFormat.SIGNED16, channels, src_rate, pcm,
        miniaudio.SampleFormat.SIGNED16, channels, dst_rate,
    )
    return bytes(out)


def wav_info(wav_bytes: bytes) -> tuple[int, int, int]:
    """(canaux, largeur d'échantillon en octets, fréquence) d'un WAV en mémoire."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        return w.getnchannels(), w.getsampwidth(), w.getframerate()


def wav_duration_ms(wav_bytes: bytes) -> int:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        return int(w.getnframes() / w.getframerate() * 1000)


def silence_wav(ms: int, sample_rate: int = OUTPUT_SAMPLE_RATE, channels: int = 1) -> bytes:
    n_frames = int(sample_rate * ms / 1000)
    return pcm16_to_wav(b"\x00\x00" * n_frames * channels, sample_rate, channels)


def _is_standard_wav(data: bytes) -> bool:
    if not data.startswith(_RIFF):
        return False
    try:
        return wav_info(data) == (1, _SAMPLE_WIDTH, OUTPUT_SAMPLE_RATE)
    except (wave.Error, EOFError):
        return False


def normalize_audio(data: bytes) -> bytes:
    """Convertit n'importe quel audio décodable (WAV/MP3/FLAC/OGG, toute fréquence, mono ou
    stéréo, 8/16/24/32 bits) en WAV mono 16 bits à OUTPUT_SAMPLE_RATE. No-op si déjà conforme."""
    if _is_standard_wav(data):
        return data
    try:
        decoded = miniaudio.decode(
            data,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
            sample_rate=OUTPUT_SAMPLE_RATE,
        )
    except Exception as exc:
        raise ValueError(
            f"Audio illisible ({len(data)} octets, début {data[:12]!r}) : {exc}"
        ) from exc
    return pcm16_to_wav(decoded.samples.tobytes(), OUTPUT_SAMPLE_RATE)


def adjust_level(wav_bytes: bytes, target_dbfs: float = -20.0, max_gain_db: float = 6.0,
                 peak_ceiling_dbfs: float = -1.0) -> bytes:
    """Ramène le niveau RMS vers `target_dbfs` (gain borné à ±max_gain_db, plafonné pour que le
    pic reste sous `peak_ceiling_dbfs`). Homogénéise le volume entre voix/providers sans écraser
    la dynamique (le gain est borné, ce n'est pas un compresseur). WAV mono 16 bits attendu ;
    un silence complet est renvoyé tel quel."""
    import numpy as np

    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        if w.getsampwidth() != _SAMPLE_WIDTH:
            return wav_bytes
        channels, rate, frames = w.getnchannels(), w.getframerate(), w.readframes(w.getnframes())
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32)
    if samples.size == 0:
        return wav_bytes
    rms = float(np.sqrt(np.mean(samples ** 2)))
    peak = float(np.max(np.abs(samples)))
    if rms < 1.0 or peak < 1.0:
        return wav_bytes
    gain_db = target_dbfs - 20 * np.log10(rms / 32768.0)
    gain_db = max(-max_gain_db, min(max_gain_db, gain_db))
    ceiling = 32768.0 * (10 ** (peak_ceiling_dbfs / 20))
    gain = min(10 ** (gain_db / 20), ceiling / peak)
    out = np.clip(samples * gain, -32768, 32767).astype("<i2").tobytes()
    return pcm16_to_wav(out, rate, channels)


def split_sentences(text: str, max_chars: int) -> list[str]:
    """Découpe `text` en morceaux <= max_chars aux fins de phrase (jamais au milieu d'un mot).
    Sans effet si le texte tient déjà. Un « mot » plus long que max_chars est coupé net."""
    text = text.strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return [text] if text else []
    import re

    pieces = re.split(r"(?<=[.!?…])[\"”»)]*\s+", text)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        candidate = f"{current} {piece}".strip() if current else piece
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(piece) > max_chars:
            cut = piece.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            chunks.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        current = piece
    if current:
        chunks.append(current)
    return chunks
