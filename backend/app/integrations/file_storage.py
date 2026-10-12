"""Local persistent storage for generated product files (spec section 9, step 8).

Swap-in point for real object storage (S3-compatible) later: everything here
is routed through `product_dir()` / `register_asset()` so only this module
needs to change.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import STORAGE_DIR
from app.models.models import ProductAsset


def product_dir(product_id: int) -> Path:
    d = STORAGE_DIR / "products" / str(product_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def register_asset(db: Session, product_id: int, asset_type: str, path: Path) -> ProductAsset:
    asset = ProductAsset(
        product_id=product_id,
        asset_type=asset_type,
        file_path=str(path),
        file_size_bytes=path.stat().st_size,
        checksum_sha256=_sha256(path),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset
