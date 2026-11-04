"""Bounded reads for uploaded files."""
from fastapi import HTTPException, UploadFile

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
_CHUNK = 1024 * 1024


async def read_upload(file: UploadFile, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
    """Read an upload, answering 413 as soon as it exceeds max_bytes."""
    buf = bytearray()
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: the limit is {max_bytes // (1024 * 1024)} MB.",
            )
    return bytes(buf)
