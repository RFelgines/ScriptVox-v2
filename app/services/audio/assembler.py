import io
import wave
from pathlib import Path


def _assemble(audio_segments: list[bytes], dest) -> None:
    """Concatenate WAV segments into ``dest`` (a path string or a binary file-like
    accepted by ``wave.open``). All segments must share the format of the first;
    a mismatch raises ValueError rather than silently producing skewed audio."""
    if not audio_segments:
        raise ValueError("audio_segments must not be empty")

    with wave.open(io.BytesIO(audio_segments[0]), "rb") as first:
        n_channels = first.getnchannels()
        sampwidth = first.getsampwidth()
        framerate = first.getframerate()

    with wave.open(dest, "wb") as out:
        out.setnchannels(n_channels)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)
        for i, segment_bytes in enumerate(audio_segments):
            with wave.open(io.BytesIO(segment_bytes), "rb") as seg:
                seg_ch, seg_sw, seg_fr = seg.getnchannels(), seg.getsampwidth(), seg.getframerate()
                if (seg_ch, seg_sw, seg_fr) != (n_channels, sampwidth, framerate):
                    raise ValueError(
                        f"WAV format mismatch at segment {i}: "
                        f"expected ({n_channels}ch, {sampwidth}B, {framerate}Hz), "
                        f"got ({seg_ch}ch, {seg_sw}B, {seg_fr}Hz)"
                    )
                out.writeframes(seg.readframes(seg.getnframes()))


def assemble_wav(audio_segments: list[bytes], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    _assemble(audio_segments, str(output_path))
    return output_path


def assemble_wav_bytes(audio_segments: list[bytes]) -> bytes:
    buf = io.BytesIO()
    _assemble(audio_segments, buf)
    return buf.getvalue()
