import hashlib
import io
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 20_000_000


def local_path(path, max_bytes=MAX_BYTES, roots=None):
    if not isinstance(path, (str, Path)) or "://" in str(path):
        raise ValueError("Only local file paths are supported")
    p = Path(path).expanduser().resolve(strict=True)
    if not p.is_file():
        raise ValueError("Expected a regular file")
    if roots and not any(p.is_relative_to(Path(r).expanduser().resolve()) for r in roots):
        raise PermissionError("Path is outside allowed roots")
    if p.stat().st_size > max_bytes:
        raise ValueError("Input exceeds byte limit")
    return p


def load_image(path, roots=None):
    p = local_path(path, roots=roots)
    with p.open("rb") as f:
        data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Input exceeds byte limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as im:
                if im.width * im.height > MAX_PIXELS:
                    raise ValueError("Image exceeds pixel limit")
                if getattr(im, "n_frames", 1) != 1:
                    raise ValueError("Animated images must be analyzed as video")
                im.load()
                rgb = ImageOps.exif_transpose(im).convert("RGB")
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as e:
        raise ValueError(f"Malformed or unsupported image: {p.name}") from e
    return rgb, hashlib.sha256(data).hexdigest()
