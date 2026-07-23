import asyncio
import hashlib
import ipaddress
import os
import socket
import tempfile
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from uuid import UUID

import httpx
from PIL import Image, ImageFilter, ImageOps


MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MIN_IMAGE_SIDE = 500
PROCESSED_IMAGE_ROOT = Path("/app/uploads/processed")
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


@lru_cache(maxsize=1)
def get_rembg_session():
    from rembg import new_session

    return new_session("isnet-general-use")


def _remove_background(image_bytes: bytes) -> bytes:
    from rembg import remove

    return remove(
        image_bytes,
        session=get_rembg_session(),
        force_return_bytes=True,
    )


async def _validate_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Image URL must use http or https.")
    if parsed.username or parsed.password:
        raise ValueError("Image URL credentials are not allowed.")

    try:
        addresses = [ipaddress.ip_address(parsed.hostname.split("%", 1)[0])]
    except ValueError:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        loop = asyncio.get_running_loop()
        try:
            resolved = await loop.getaddrinfo(
                parsed.hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as error:
            raise ValueError("Image host could not be resolved.") from error
        addresses = list({ipaddress.ip_address(item[4][0]) for item in resolved})

    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Image URL resolves to a non-public address.")


async def download_image(url: str) -> bytes:
    current_url = url.strip()
    timeout = httpx.Timeout(15.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        for redirect_count in range(4):
            await _validate_public_url(current_url)
            async with client.stream("GET", current_url) as response:
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location or redirect_count == 3:
                        raise ValueError("Image URL has too many or invalid redirects.")
                    current_url = urljoin(current_url, location)
                    continue

                response.raise_for_status()
                mime_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if mime_type not in ALLOWED_MIME_TYPES:
                    raise ValueError("Image must be JPEG, PNG, or WebP.")
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
                    raise ValueError("Image exceeds the 20MB limit.")

                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > MAX_DOWNLOAD_BYTES:
                        raise ValueError("Image exceeds the 20MB limit.")
                return bytes(chunks)

    raise ValueError("Image download failed.")


def _validated_image(image_bytes: bytes) -> Image.Image:
    try:
        image = Image.open(BytesIO(image_bytes))
        image_format = image.format
        width, height = image.size
        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise ValueError("Image must be JPEG, PNG, or WebP.")
        if width * height > MAX_IMAGE_PIXELS:
            raise ValueError("Image exceeds the 40MP limit.")
        if min(width, height) < MIN_IMAGE_SIDE:
            raise ValueError("The shortest image side must be at least 500px.")
        image.load()
        return ImageOps.exif_transpose(image).convert("RGBA")
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("Image could not be decoded.") from error


def _studio_background(preset: int) -> Image.Image:
    colors = (
        ("#ffffff", "#edf0f4"),
        ("#fffdf9", "#eee4d8"),
        ("#fbfdff", "#e1eaf2"),
    )
    gradient = Image.linear_gradient("L").resize((1000, 1000))
    return ImageOps.colorize(gradient, *colors[preset]).convert("RGBA")


def process_main_image(image_bytes: bytes, product_id: UUID | str) -> bytes:
    source = _validated_image(image_bytes)
    normalized = BytesIO()
    source.save(normalized, format="PNG")

    try:
        foreground = Image.open(BytesIO(_remove_background(normalized.getvalue()))).convert("RGBA")
        foreground.load()
    except Exception as error:
        raise ValueError("Background removal failed.") from error

    alpha = foreground.getchannel("A")
    visible_mask = alpha.point(lambda value: 255 if value >= 8 else 0)
    foreground_ratio = sum(visible_mask.histogram()[1:]) / (foreground.width * foreground.height)
    bbox = visible_mask.getbbox()
    if bbox is None or not 0.05 <= foreground_ratio <= 0.95:
        raise ValueError("Foreground mask failed the 5%-95% quality gate.")

    foreground = foreground.crop(bbox)
    foreground.thumbnail((820, 820), Image.Resampling.LANCZOS)
    x = (1000 - foreground.width) // 2
    y = max(60, (1000 - foreground.height) // 2 - 15)

    preset = hashlib.sha256(str(product_id).encode()).digest()[0] % 3
    canvas = _studio_background(preset)
    shadow_mask = Image.new("L", canvas.size)
    shadow_mask.paste(foreground.getchannel("A"), (x, y + 24))
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(20)).point(lambda value: value * 28 // 100)
    shadow = Image.new("RGBA", canvas.size, (25, 30, 38, 0))
    shadow.putalpha(shadow_mask)
    canvas = Image.alpha_composite(canvas, shadow)
    canvas.alpha_composite(foreground, (x, y))

    output = BytesIO()
    canvas.convert("RGB").save(
        output,
        format="JPEG",
        quality=90,
        progressive=True,
        subsampling=0,
    )
    return output.getvalue()


def processed_image_path(user_id: UUID | str, product_id: UUID | str) -> Path:
    safe_user_id = UUID(str(user_id))
    safe_product_id = UUID(str(product_id))
    return PROCESSED_IMAGE_ROOT / str(safe_user_id) / f"{safe_product_id}.jpg"


def save_processed_image(image_bytes: bytes, user_id: UUID | str, product_id: UUID | str) -> Path:
    target = processed_image_path(user_id, product_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.stem}-", delete=False) as file:
            temp_path = Path(file.name)
            file.write(image_bytes)
        os.replace(temp_path, target)
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)
    return target


def delete_processed_image(user_id: UUID | str, product_id: UUID | str) -> None:
    try:
        processed_image_path(user_id, product_id).unlink(missing_ok=True)
    except OSError:
        pass


def processed_main_image_url(product) -> str | None:
    if not has_processed_image(product):
        return None
    updated_at = getattr(product, "updated_at", None)
    version = int(updated_at.timestamp() * 1_000_000) if updated_at else 0
    return f"/api/processor/products/{product.id}/processed-main-image?v={version}"


def has_processed_image(product) -> bool:
    if getattr(product, "image_processing_status", "not_started") != "completed":
        return False
    expected = processed_image_path(product.user_id, product.id)
    return getattr(product, "processed_image_path", None) == str(expected) and expected.is_file()
