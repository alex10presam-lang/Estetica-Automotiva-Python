"""Shared validation, cost calculation and photograph storage."""

import io
import math
import warnings
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import HTTPException
from app.config import UPLOAD_DIR

MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_PHOTO_PIXELS = 20_000_000


def require_record(db, model, identifier):
    record = db.get(model, identifier)
    if record is None:
        raise HTTPException(404, "Registro não encontrado.")
    return record


def money(value):
    if not math.isfinite(value) or value < 0:
        raise HTTPException(422, "Informe um valor não negativo e finito.")
    return value


def brl(value):
    """Formata um valor no padrão brasileiro: R$ 1.234,56."""
    number = float(value or 0)
    text = f"{abs(number):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"-R$ {text}" if number < 0 else f"R$ {text}"


def whatsapp_number(phone):
    """Somente dígitos, com DDI 55 quando o número ainda não o possui."""
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if digits and not (digits.startswith("55") and len(digits) >= 12):
        digits = "55" + digits
    return digits


def dose_cost(product):
    return (
        product.preco_compra / product.ml_total * product.ml_por_uso
        if product.ml_total and product.ml_total > 0
        else 0.0
    )


def save_photos(files, folder):
    """Validate the entire batch before writing; re-encode without EXIF metadata."""
    if len(files) > 8:
        raise HTTPException(422, "Envie no máximo 8 fotos por vez.")
    prepared = []
    for file in files:
        if not file or not file.filename:
            continue
        raw = file.file.read(MAX_PHOTO_BYTES + 1)
        if len(raw) > MAX_PHOTO_BYTES:
            raise HTTPException(413, "Cada foto deve ter no máximo 8 MB.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as photo:
                    if photo.format not in {"JPEG", "PNG", "WEBP"}:
                        raise ValueError("Unsupported image format")
                    if photo.width * photo.height > MAX_PHOTO_PIXELS:
                        raise ValueError("Image too large")
                    photo = ImageOps.exif_transpose(photo).convert("RGB")
                    photo.thumbnail((2400, 2400))
                    output = io.BytesIO()
                    photo.save(output, "JPEG", quality=88)
                    prepared.append(output.getvalue())
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            raise HTTPException(
                422, "Envie uma imagem JPEG, PNG ou WebP válida, de até 20 megapixels."
            ) from None
    target = UPLOAD_DIR / folder
    target.mkdir(parents=True, exist_ok=True)
    paths = []
    try:
        for content in prepared:
            path = target / (uuid4().hex + ".jpg")
            path.write_bytes(content)
            paths.append(path)
    except OSError:
        for path in paths:
            path.unlink(missing_ok=True)
        raise
    return ["uploads/" + path.relative_to(UPLOAD_DIR).as_posix() for path in paths]
