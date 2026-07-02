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


def _assemble_paths(paths: list[Path], dest) -> None:
    """Same contract as _assemble (format-mismatch guard included), but reads each
    input from disk instead of from an in-memory bytes list — only one file's
    frames are held in memory at a time, not all of them at once."""
    if not paths:
        raise ValueError("paths must not be empty")

    with wave.open(str(paths[0]), "rb") as first:
        n_channels = first.getnchannels()
        sampwidth = first.getsampwidth()
        framerate = first.getframerate()

    with wave.open(dest, "wb") as out:
        out.setnchannels(n_channels)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)
        for i, path in enumerate(paths):
            with wave.open(str(path), "rb") as seg:
                seg_ch, seg_sw, seg_fr = seg.getnchannels(), seg.getsampwidth(), seg.getframerate()
                if (seg_ch, seg_sw, seg_fr) != (n_channels, sampwidth, framerate):
                    raise ValueError(
                        f"WAV format mismatch at file {i} ({path}): "
                        f"expected ({n_channels}ch, {sampwidth}B, {framerate}Hz), "
                        f"got ({seg_ch}ch, {seg_sw}B, {seg_fr}Hz)"
                    )
                out.writeframes(seg.readframes(seg.getnframes()))


def assemble_wav_from_files(paths: list[str | Path], output_path: str | Path) -> Path:
    """Concatenate already-on-disk WAV files (one per chapter) into a single output
    WAV, streaming disk-to-disk. Companion to assemble_wav (which takes in-memory
    bytes, used for the per-chapter segment-synthesis path) — used by book-level
    generation to bound peak memory to one chapter's audio at a time instead of the
    whole book (audit 2026-07-02, Lot C / finding M8)."""
    output_path = Path(output_path)
    _assemble_paths([Path(p) for p in paths], str(output_path))
    return output_path


def wav_to_mp3(wav_bytes: bytes, bit_rate: int = 128) -> bytes:
    import lameenc  # lazy: keeps assembler importable before lameenc is installed

    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        n_channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        framerate = w.getframerate()
        n_frames = w.getnframes()
        if n_frames == 0:
            raise ValueError("WAV has no audio frames")
        if sampwidth != 2:
            raise ValueError(
                f"wav_to_mp3 requires 16-bit PCM (sampwidth=2), got sampwidth={sampwidth}"
            )
        pcm = w.readframes(n_frames)

    enc = lameenc.Encoder()
    enc.set_bit_rate(bit_rate)
    enc.set_in_sample_rate(framerate)
    enc.set_channels(n_channels)
    enc.set_quality(2)
    return bytes(enc.encode(pcm) + enc.flush())


# Frames per chunk when streaming an encode: 1,000,000 frames ≈ 2 MB of 16-bit
# mono PCM ≈ 45 s of audio at 22050 Hz — enough to keep syscall/lameenc-call
# overhead negligible on a full novel, small enough that peak memory never
# approaches the whole book (audit 2026-07-02, Lot C2 / finding M8 residual).
_MP3_STREAM_CHUNK_FRAMES = 1_000_000


def wav_to_mp3_streaming(
    wav_path: str | Path, output_path: str | Path,
    bit_rate: int = 128, chunk_frames: int = _MP3_STREAM_CHUNK_FRAMES,
) -> Path:
    """Encode a WAV file to MP3 streaming disk-to-disk, in fixed-size PCM chunks —
    at most one chunk's worth of PCM held in memory at a time, instead of the
    whole file (companion to wav_to_mp3, which is fine for small in-memory
    buffers but was the last RAM-unbounded step in book generation: C1 already
    made WAV assembly disk-to-disk, but _generate_book_impl still read the
    entire assembled book.wav into memory here — up to ~1.6 GB of PCM for a
    10-hour novel).

    lameenc.Encoder.encode() is a proper streaming encoder: calling it with N
    successive sample-aligned PCM chunks produces byte-identical output to a
    single call with the whole PCM buffer (verified empirically) — wave's
    readframes() always returns whole frames, so this chunking is always
    sample-aligned and the result is never observably different from
    wav_to_mp3(wav_bytes)."""
    import lameenc  # lazy: keeps assembler importable before lameenc is installed

    output_path = Path(output_path)
    with wave.open(str(wav_path), "rb") as w:
        n_channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        framerate = w.getframerate()
        n_frames = w.getnframes()
        if n_frames == 0:
            raise ValueError("WAV has no audio frames")
        if sampwidth != 2:
            raise ValueError(
                f"wav_to_mp3_streaming requires 16-bit PCM (sampwidth=2), got sampwidth={sampwidth}"
            )

        enc = lameenc.Encoder()
        enc.set_bit_rate(bit_rate)
        enc.set_in_sample_rate(framerate)
        enc.set_channels(n_channels)
        enc.set_quality(2)

        with open(output_path, "wb") as out:
            remaining = n_frames
            while remaining > 0:
                to_read = min(chunk_frames, remaining)
                pcm_chunk = w.readframes(to_read)
                remaining -= to_read
                out.write(bytes(enc.encode(pcm_chunk)))
            out.write(bytes(enc.flush()))

    return output_path
