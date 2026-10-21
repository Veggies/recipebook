"""Recipe photos uploaded from the editor, stored in the data volume next to the database."""

import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_SIDE = 1600  # plenty for a phone screen at 3x, and a hero image on desktop


class ImageError(Exception):
    pass


def save_upload(data: bytes, images_dir: Path) -> str:
    """Store an uploaded photo as a resized JPEG; returns its file name.

    The editor already shrinks photos on the phone, but anything can be posted here,
    so it's always decoded and re-encoded: that also drops EXIF (location) data.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageError("That photo is too large (20 MB max).")
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)  # phones store rotation as metadata
    except (UnidentifiedImageError, OSError) as e:
        raise ImageError("That file isn't a photo this app can read (use JPEG, PNG or WebP).") from e
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    name = f"{uuid.uuid4().hex}.jpg"
    images_dir.mkdir(parents=True, exist_ok=True)
    img.save(images_dir / name, "JPEG", quality=85, optimize=True, progressive=True)
    return name
