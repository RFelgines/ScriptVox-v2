"""Mastering des chapitres aux exigences ACX (Audible / ACX Audio Submission Requirements).

ACX exige, pour CHAQUE fichier (un par chapitre) :
  - RMS entre -23 et -18 dBFS ;
  - crête (peak) inférieure ou égale à -3 dBFS ;
  - bruit de fond inférieur ou égal à -60 dBFS RMS.

Le niveau par segment (format.adjust_level, -20 dBFS avec plafond -1) homogénéise les voix
entre elles, mais ne garantit rien pour le fichier du chapitre : sa crête peut atteindre
-1 dBFS, et les pauses font baisser le RMS global. master() règle donc le chapitre ENTIER :
gain vers le RMS cible, puis limiteur doux sous le plafond de crête, puis réajustement du
gain si le limiteur a fait retomber le RMS hors de la plage.

Le bruit de fond d'une voix de synthèse est un silence numérique (zéro) : il est très en
dessous de -60 dBFS, donc conforme ; loudness_report() le signale pour information, car
certains contrôles humains d'ACX préfèrent un « room tone » discret à un silence absolu.
"""
import io
import wave

import numpy as np

ACX_RMS_MIN = -23.0
ACX_RMS_MAX = -18.0
ACX_PEAK_MAX = -3.0
ACX_NOISE_MAX = -60.0

TARGET_RMS = -20.0     # milieu de la plage ACX
PEAK_CEILING = -3.5    # marge de 0,5 dB sous l'exigence (conversions MP3/AAC)
_KNEE_DB = 6.0         # le limiteur commence à agir 6 dB sous le plafond
_FULL = 32768.0


def _read(wav_bytes: bytes) -> tuple[np.ndarray, wave._wave_params]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        params = w.getparams()
        frames = w.readframes(w.getnframes())
    if params.sampwidth != 2:
        raise ValueError("mastering: PCM 16 bits attendu")
    return np.frombuffer(frames, dtype="<i2").astype(np.float64), params


def _write(samples: np.ndarray, params) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(2)
        w.setframerate(params.framerate)
        w.writeframes(np.clip(np.round(samples), -32768, 32767).astype("<i2").tobytes())
    return buf.getvalue()


def _db(x: float) -> float:
    return 20 * np.log10(x / _FULL) if x > 0 else float("-inf")


def _rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(samples ** 2))) if samples.size else 0.0


def _noise_floor(samples: np.ndarray, rate: int) -> float:
    """RMS (dBFS) des fenêtres de 50 ms les plus calmes (10e centile)."""
    n = max(1, int(rate * 0.05))
    windows = samples[: samples.size // n * n].reshape(-1, n) if samples.size >= n else samples[None, :]
    rms = np.sqrt(np.mean(windows ** 2, axis=1))
    return _db(float(np.percentile(rms, 10))) if rms.size else float("-inf")


def loudness_report(wav_bytes: bytes) -> dict:
    samples, params = _read(wav_bytes)
    rms_db = _db(_rms(samples))
    peak_db = _db(float(np.max(np.abs(samples)))) if samples.size else float("-inf")
    noise_db = _noise_floor(samples, params.framerate)

    def r(x):
        return None if x == float("-inf") else round(float(x), 1)

    checks = {  # bool() : des numpy.bool ne se sérialisent pas en JSON
        "rms": bool(ACX_RMS_MIN <= rms_db <= ACX_RMS_MAX),
        "peak": bool(peak_db <= ACX_PEAK_MAX),
        "noise_floor": bool(noise_db <= ACX_NOISE_MAX),
    }
    return {
        "rms_dbfs": r(rms_db), "peak_dbfs": r(peak_db), "noise_floor_dbfs": r(noise_db),
        "digital_silence": bool(noise_db == float("-inf")),
        "duration_s": round(samples.size / params.nchannels / params.framerate, 1),
        "checks": checks, "acx_compliant": all(checks.values()),
        "requirements": {"rms_dbfs": [ACX_RMS_MIN, ACX_RMS_MAX], "peak_dbfs_max": ACX_PEAK_MAX,
                         "noise_floor_dbfs_max": ACX_NOISE_MAX},
    }


def _limit(samples: np.ndarray, ceiling_db: float) -> np.ndarray:
    """Limiteur doux sans anticipation : transparent sous le genou, courbe tanh au-dessus,
    ne dépasse jamais le plafond."""
    ceil = _FULL * 10 ** (ceiling_db / 20)
    knee = ceil * 10 ** (-_KNEE_DB / 20)
    mag = np.abs(samples)
    over = mag > knee
    out = samples.copy()
    out[over] = np.sign(samples[over]) * (knee + (ceil - knee) * np.tanh((mag[over] - knee) / (ceil - knee)))
    return out


def master(wav_bytes: bytes, target_rms: float = TARGET_RMS, ceiling: float = PEAK_CEILING) -> bytes:
    """Chapitre conforme ACX (RMS dans la plage, crête sous le plafond). Un fichier muet est
    rendu tel quel."""
    samples, params = _read(wav_bytes)
    if _rms(samples) < 1.0:
        return wav_bytes
    out = samples
    for _ in range(4):
        gain_db = target_rms - _db(_rms(out))
        out = _limit(out * 10 ** (gain_db / 20), ceiling)
        if abs(_db(_rms(out)) - target_rms) < 0.5:
            break
    return _write(out, params)
