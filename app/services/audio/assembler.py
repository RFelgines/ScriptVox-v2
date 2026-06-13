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
        for segment_bytes in audio_segments:
            with wave.open(io.BytesIO(segment_bytes), "rb") as seg:
                out.writeframes(seg.readframes(seg.getnframes()))

    return output_path
