from fastapi import HTTPException, UploadFile

_CHUNK_SIZE = 1024 * 1024  # 1 MB


async def read_upload_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read an UploadFile's content in chunks, rejecting with 413 as soon as
    max_bytes is exceeded -- bounds worst-case memory use regardless of what the
    client claims to send, instead of trusting a single `await file.read()` to
    materialize an arbitrarily large body in RAM (audit 2026-07-07, P1)."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {max_bytes // (1024 * 1024)} MB).",
            )
        chunks.append(chunk)
    return b"".join(chunks)
