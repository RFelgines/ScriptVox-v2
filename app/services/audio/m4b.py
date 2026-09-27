"""Export M4B : livre audio standard (AAC dans MP4) avec **chapitres** et **couverture**.

C'est le format attendu par les applications de livres audio (Apple Livres, BookPlayer,
Smart AudioBook Player, VLC…) : marque-pages de chapitres, reprise de lecture, couverture.
Nécessite ffmpeg (binaire externe, non installé par pip) ; sans lui, l'application garde le
MP3 (dégradation propre, voir scripts/doctor.py).
"""
import logging
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

_COVER_SUFFIXES = {".jpg", ".jpeg", ".png"}  # formats que MP4 accepte tels quels (-c:v copy)


def find_ffmpeg(configured: str | None = None) -> str | None:
    """Chemin de ffmpeg : FFMPEG_PATH s'il est défini et valide, sinon le PATH."""
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("ffmpeg")


def _escape(value: str) -> str:
    """Échappement du format FFMETADATA : = ; # \\ et retour ligne."""
    out = value.replace("\\", "\\\\")
    for ch in ("=", ";", "#", "\n"):
        out = out.replace(ch, "\\" + ch)
    return out


def wav_file_duration_ms(path: str | Path) -> int:
    with wave.open(str(path), "rb") as w:
        return int(w.getnframes() / w.getframerate() * 1000)


def build_ffmetadata(title: str, author: str | None, chapters: list[tuple[str, int, int]]) -> str:
    """Contenu du fichier FFMETADATA1. `chapters` = [(titre, début_ms, fin_ms)]."""
    lines = [";FFMETADATA1", f"title={_escape(title)}", "genre=Audiobook"]
    if author:
        lines.append(f"artist={_escape(author)}")
        lines.append(f"album_artist={_escape(author)}")
    for name, start, end in chapters:
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={max(end, start + 1)}",
                  f"title={_escape(name)}"]
    return "\n".join(lines) + "\n"


def chapter_marks(durations_ms: list[int], titles: list[str], gap_ms: int) -> list[tuple[str, int, int]]:
    """Positions de chapitres dans le WAV assemblé (durée de chaque chapitre + silence de
    jonction, exactement comme assemble_wav_from_files(gaps_ms=...))."""
    marks, cursor = [], 0
    for i, (dur, name) in enumerate(zip(durations_ms, titles)):
        marks.append((name, cursor, cursor + dur))
        cursor += dur + (gap_ms if i < len(durations_ms) - 1 else 0)
    return marks


def _hms(ms: int) -> str:
    s = max(0, ms) // 1000
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def chapters_txt(chapters: list[tuple[str, int, int]]) -> str:
    """Horodatage des chapitres, une ligne « HH:MM:SS Titre » par chapitre : le format
    que lisent les descriptions YouTube, la plupart des hébergeurs de podcasts et les
    outils de montage. Complète le M4B, et reste disponible sans ffmpeg."""
    return "".join(f"{_hms(start)} {' '.join(name.split())}\n" for name, start, _ in chapters)


def chapters_txt_path(audio_path: str | Path) -> Path:
    return Path(audio_path).with_suffix(".chapters.txt")


def build_m4b(
    wav_path: str | Path, output_path: str | Path, *, title: str, author: str | None,
    chapters: list[tuple[str, int, int]], cover_path: str | Path | None = None,
    ffmpeg: str | None = None, bitrate: str = "64k", timeout: float = 7200.0,
) -> Path | None:
    """Encode le WAV en M4B chapitré. Retourne le chemin, ou None si ffmpeg est absent ou
    échoue (l'appelant garde alors le MP3 : jamais bloquant)."""
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        logger.warning("m4b: ffmpeg introuvable, export M4B ignoré")
        return None
    output_path = Path(output_path)
    with tempfile.TemporaryDirectory(prefix="scriptvox_m4b_") as tmp:
        meta = Path(tmp) / "meta.txt"
        meta.write_text(build_ffmetadata(title, author, chapters), encoding="utf-8")
        use_cover = cover_path is not None and Path(cover_path).suffix.lower() in _COVER_SUFFIXES \
            and Path(cover_path).is_file()
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav_path), "-i", str(meta)]
        if use_cover:
            cmd += ["-i", str(cover_path)]
        cmd += ["-map", "0:a"]
        if use_cover:
            cmd += ["-map", "2:v"]
        cmd += ["-map_metadata", "1", "-map_chapters", "1", "-c:a", "aac", "-b:a", bitrate, "-ac", "1"]
        if use_cover:
            cmd += ["-c:v", "copy", "-disposition:v", "attached_pic"]
        cmd += ["-f", "ipod", str(output_path)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                                  encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            logger.warning("m4b: ffmpeg a échoué", exc_info=True)
            return None
    if proc.returncode != 0 or not output_path.exists():
        logger.warning("m4b: ffmpeg code %s : %s", proc.returncode, proc.stderr[-500:])
        output_path.unlink(missing_ok=True)
        return None
    return output_path
