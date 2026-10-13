"""
Real AI image generation for Etsy listing preview photos, mirroring the
ai_providers.py pattern: a real call when OPENAI_API_KEY is configured,
a clearly-labeled placeholder (the plain PIL render) otherwise. Real cost
is recorded as an ACTUAL expense under the "image_gen" category, same as
ai_providers.py does for "ai_api".
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass

from PIL import Image
from sqlalchemy.orm import Session

from app.agents.generators.preview_generator import PREVIEW_SIZE, generate_preview_png
from app.budget.ledger import record_expense
from app.config import settings

IMAGE_MODEL = "gpt-image-1.5"
IMAGE_QUALITY = "medium"
GENERATED_SIZE = "1024x1024"

# Illustrative per-image cost at medium quality, 1024x1024 -- verify against
# OpenAI's current pricing page before relying on this for real financial
# reporting (token-metered pricing, so this is an approximation).
PRICE_PER_IMAGE = {
    ("gpt-image-1.5", "low"): 0.009,
    ("gpt-image-1.5", "medium"): 0.034,
    ("gpt-image-1.5", "high"): 0.133,
}


@dataclass
class ImageResponse:
    png_bytes: bytes
    provider: str
    model: str
    cost_usd: float
    is_mock: bool


def _upscale_to_preview_size(png_bytes: bytes) -> bytes:
    """Etsy listing convention / QA expects PREVIEW_SIZE (2000x2000); the
    image API's native output is smaller. Upscaling the real generated
    image preserves its actual content rather than discarding it."""
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    img = img.resize(PREVIEW_SIZE, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _generate_raw_image(db: Session, *, agent_key: str, prompt: str, workflow_run_id: int | None) -> bytes | None:
    """Real gpt-image-1.5 call, native 1024x1024 PNG bytes. Returns None on
    any failure (billing, rate limit, content policy) rather than raising --
    callers fall back to their own placeholder."""
    if not settings.openai_configured:
        return None
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        resp = client.images.generate(
            model=IMAGE_MODEL, prompt=prompt, size=GENERATED_SIZE, quality=IMAGE_QUALITY, n=1,
        )
        raw_bytes = base64.b64decode(resp.data[0].b64_json)
    except Exception:
        return None

    cost = PRICE_PER_IMAGE.get((IMAGE_MODEL, IMAGE_QUALITY), 0.04)
    record_expense(
        db,
        category="image_gen",
        amount_usd=cost,
        basis="ACTUAL",
        description=f"{agent_key} image generation via {IMAGE_MODEL} ({IMAGE_QUALITY})",
        workflow_run_id=workflow_run_id,
        agent_key=agent_key,
    )
    return raw_bytes


def generate_listing_image(
    db: Session,
    *,
    agent_key: str,
    prompt: str,
    title: str,
    palette: dict,
    workflow_run_id: int | None = None,
) -> ImageResponse:
    """Etsy listing cover photo -- upscaled to the 2000x2000 QA/Etsy convention."""
    raw_bytes = _generate_raw_image(db, agent_key=agent_key, prompt=prompt, workflow_run_id=workflow_run_id)
    if raw_bytes is None:
        buf = io.BytesIO()
        _write_placeholder(buf, title=title, palette=palette)
        return ImageResponse(buf.getvalue(), "mock", "placeholder-render", 0.0, True)
    png_bytes = _upscale_to_preview_size(raw_bytes)
    cost = PRICE_PER_IMAGE.get((IMAGE_MODEL, IMAGE_QUALITY), 0.04)
    return ImageResponse(png_bytes, "openai", IMAGE_MODEL, cost, False)


def generate_print_artwork(
    db: Session,
    *,
    agent_key: str,
    prompt: str,
    title: str,
    palette: dict,
    workflow_run_id: int | None = None,
) -> ImageResponse:
    """Print-ready POD artwork (t-shirt/mug design) -- kept at the API's
    native 1024x1024, no upscale (Printify positions/scales it onto the real
    print area itself via the placeholder x/y/scale params)."""
    raw_bytes = _generate_raw_image(db, agent_key=agent_key, prompt=prompt, workflow_run_id=workflow_run_id)
    if raw_bytes is None:
        buf = io.BytesIO()
        _write_placeholder(buf, title=title, palette=palette)
        return ImageResponse(buf.getvalue(), "mock", "placeholder-render", 0.0, True)
    cost = PRICE_PER_IMAGE.get((IMAGE_MODEL, IMAGE_QUALITY), 0.04)
    return ImageResponse(raw_bytes, "openai", IMAGE_MODEL, cost, False)


def _write_placeholder(buf: io.BytesIO, *, title: str, palette: dict) -> None:
    """Reuses the existing PIL text-render as the no-key fallback -- it
    writes to a path, so route through a temp-like in-memory approach by
    delegating to the real function against a BytesIO-compatible path."""
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        generate_preview_png(tmp_path, title=title, palette=palette)
        buf.write(tmp_path.read_bytes())
    finally:
        tmp_path.unlink(missing_ok=True)
