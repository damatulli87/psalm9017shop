from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models.models import MarketplaceListing, ProductAsset, ProductSpecification, QAResult

router = APIRouter(prefix="/products", tags=["products"])


@router.get("")
def list_products(db: Session = Depends(get_db), user=Depends(get_current_user)):
    products = db.query(ProductSpecification).order_by(ProductSpecification.id.desc()).limit(200).all()
    return [
        {
            "id": p.id, "title": p.title, "product_type": p.product_type, "format": p.format,
            "status": p.status, "recommended_price_usd": p.recommended_price_usd,
            "estimated_margin_usd": p.estimated_margin_usd, "created_at": p.created_at,
        }
        for p in products
    ]


@router.get("/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    product = db.query(ProductSpecification).filter(ProductSpecification.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    assets = db.query(ProductAsset).filter(ProductAsset.product_id == product_id).all()
    qa = db.query(QAResult).filter(QAResult.product_id == product_id).all()
    listing = db.query(MarketplaceListing).filter(MarketplaceListing.product_id == product_id).first()
    return {
        "id": product.id, "title": product.title, "product_type": product.product_type,
        "format": product.format, "status": product.status, "target_customer": product.target_customer,
        "problem_solved": product.problem_solved, "design_brief": product.design_brief,
        "recommended_price_usd": product.recommended_price_usd,
        "estimated_cost_usd": product.estimated_cost_usd, "estimated_margin_usd": product.estimated_margin_usd,
        "assets": [
            {"id": a.id, "asset_type": a.asset_type, "file_size_bytes": a.file_size_bytes,
             "checksum_sha256": a.checksum_sha256}
            for a in assets
        ],
        "qa_results": [{"check_name": r.check_name, "passed": r.passed, "details": r.details} for r in qa],
        "listing": (
            {
                "id": listing.id, "status": listing.status, "title": listing.title,
                "description": listing.description, "price_usd": listing.price_usd, "tags": listing.tags,
                "is_simulated": listing.is_simulated,
            }
            if listing else None
        ),
    }


@router.get("/{product_id}/assets/{asset_id}/download")
def download_asset(product_id: int, asset_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    asset = db.query(ProductAsset).filter(ProductAsset.id == asset_id, ProductAsset.product_id == product_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(asset.file_path)
