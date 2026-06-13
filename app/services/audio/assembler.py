import io
import wave
from pathlib import Path


def assemble_wav(audio_segments: list[bytes], output_path: str | Path) -> Path:
    if not audio_segments:
        raise ValueError("audio_segments must not be empty")

    output_path = Path(output_path)

    with wave.open(io.BytesIO(audio_segments[0]), "rb") as first:
        n_channels = first.getnchannels()
        sampwidth = first.getsampwidth()
        framerate = first.getframerate()

    with wave.open(str(output_path), "wb") as out:
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

    return output_path
