from __future__ import annotations

"""Simple image uploads: store on disk and serve via /uploads.

POST /api/uploads?scope=user|event&owner_id=<int>
Body: multipart/form-data with file field name "file"
Response: { url: "/uploads/<scope>/<owner_id>/<filename>", size: int, content_type: str }

Notes:
- Validates content type and enforces a size limit.
- Stores files as SHA1-hash-named with the correct extension under var/uploads.
"""

import hashlib
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile, File, Query, status


router = APIRouter(prefix="/api/uploads", tags=["uploads"])

UPLOAD_ROOT = Path("var/uploads")
ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _max_bytes() -> int:
    # Size limit in MiB (default 10)
    try:
        mib = int(os.getenv("MAX_UPLOAD_SIZE_MIB", "10"))
    except Exception:
        mib = 10
    return mib * 1024 * 1024


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_image(
    scope: Literal["user", "event"] = Query(..., description="Who this image belongs to"),
    owner_id: str = Query(..., description="User or Event ID (string or number)"),
    file: UploadFile = File(..., description="Image file"),
):
    # Validate content type
    ext = ALLOWED_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(status_code=415, detail="Unsupported media type")

    # Ensure base directory exists
    target_dir = UPLOAD_ROOT / scope / str(owner_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Stream to hash then write to temp file atomically
    sha1 = hashlib.sha1()
    size = 0
    max_len = _max_bytes()
    tmp_path = target_dir / (".tmp_" + os.urandom(8).hex())
    with tmp_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_len:
                out.close()
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File too large")
            sha1.update(chunk)
            out.write(chunk)

    digest = sha1.hexdigest()
    final_name = f"{digest}{ext}"
    final_path = target_dir / final_name
    if final_path.exists():
        # Same content already stored; remove temp file.
        tmp_path.unlink(missing_ok=True)
    else:
        tmp_path.replace(final_path)

    url = f"/uploads/{scope}/{owner_id}/{final_name}"
    return {"url": url, "size": size, "content_type": file.content_type}
