"""
Digital Product Production Agent (spec section 9).

Produces real files on disk -- never placeholders. Supported formats in
this MVP: PDF (printable/planner-style) and XLSX (working-formula budget
spreadsheet), plus a PNG listing preview and a customer-ready ZIP package.
DOCX/SVG are straightforward additions on top of the same pattern
(python-docx / svgwrite) once a real demand case needs them -- not built
yet (see PROGRESS.md).

Niche-specific layouts: most PDF niches still fall back to the generic
section/ruled-lines template (DEFAULT_SECTIONS), which is honestly just a
placeholder layout, not a real product design -- see PROGRESS.md for which
niches still need a real template built. Chore charts got a real one
(generators/chore_chart_generator.py) because that's the niche that kept
winning the research scoring; add further niche-specific generators here
the same way, as each one is actually needed, rather than speculatively
building templates for niches nothing has selected yet.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from app.agents.base import BaseAgent
from app.agents.generators.chore_chart_generator import generate_chore_chart_pdf
from app.agents.generators.pdf_generator import generate_instructions_txt, generate_pdf_product
from app.agents.generators.xlsx_generator import generate_budget_spreadsheet
from app.integrations.file_storage import product_dir, register_asset
from app.integrations.image_providers import generate_listing_image
from app.models.models import ProductSpecification

DEFAULT_SECTIONS = ["Overview", "Weekly Planning", "Tracking Grid", "Notes"]


def _listing_image_prompt(product: ProductSpecification) -> str:
    """Describes a styled lifestyle/product photo, never literal rendered text --
    AI image models reliably garble specific wording (tested and confirmed:
    asking for "no text" alone wasn't enough, it rendered nonsense lettering
    anyway). Instead the printed/surface area is described as deliberately
    out of focus or angled away, so nothing is legible, which also happens to
    be a common real product-photography style."""
    return (
        f"Professional e-commerce product photography for an Etsy listing. "
        f"A tastefully styled flat-lay or lifestyle scene evoking a printed "
        f"'{product.title}' in use, aimed at this buyer: {product.target_customer} "
        f"The printed page or surface itself is angled sharply away from the "
        f"camera or softly out of focus in the background, so no words or "
        f"lettering on it are legible -- the focus of the shot is the "
        f"surrounding styled scene (frame, desk, props, lighting), not the "
        f"page content. Absolutely no legible text, letters, or words "
        f"anywhere in the image. Warm natural lighting, clean modern "
        f"aesthetic, no logos or brand names, no people's faces."
    )


class DigitalProductionAgent(BaseAgent):
    key = "digital_production"

    def produce(self, product: ProductSpecification, workflow_run_id: int | None = None) -> list[Path]:
        palette = (product.design_brief or {}).get("palette", {
            "primary": "#1B4332", "secondary": "#40916C", "accent": "#D8F3DC", "text": "#081C15",
        })
        out_dir = product_dir(product.id)
        generated: list[Path] = []

        if product.format == "xlsx":
            main_path = out_dir / f"product_{product.id}.xlsx"
            generate_budget_spreadsheet(main_path, title=product.title, palette=palette)
        elif "chore chart" in product.title.lower():
            main_path = out_dir / f"product_{product.id}.pdf"
            generate_chore_chart_pdf(main_path, title=product.title, palette=palette)
        else:  # generic fallback -- see module docstring
            main_path = out_dir / f"product_{product.id}.pdf"
            generate_pdf_product(main_path, title=product.title, palette=palette, sections=DEFAULT_SECTIONS)
        generated.append(main_path)

        preview_path = out_dir / f"preview_{product.id}.png"
        image_result = generate_listing_image(
            self.db,
            agent_key=self.key,
            prompt=_listing_image_prompt(product),
            title=product.title,
            palette=palette,
            workflow_run_id=workflow_run_id,
        )
        preview_path.write_bytes(image_result.png_bytes)
        generated.append(preview_path)
        self.log(
            "listing_image_generated",
            f"Listing image for product #{product.id} via {image_result.provider}:{image_result.model}"
            f" (${image_result.cost_usd:.3f})",
            {"product_id": product.id, "is_mock": image_result.is_mock, "cost_usd": image_result.cost_usd},
        )

        instructions_path = out_dir / "INSTRUCTIONS.txt"
        generate_instructions_txt(instructions_path, title=product.title)
        generated.append(instructions_path)

        zip_path = out_dir / f"{product.title.replace(' ', '_')}_delivery.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(main_path, arcname=main_path.name)
            zf.write(instructions_path, arcname=instructions_path.name)
        generated.append(zip_path)

        for f in generated:
            asset_type = f.suffix.lstrip(".").lower()
            register_asset(self.db, product.id, asset_type, f)

        product.status = "produced"
        self.db.commit()

        self.log(
            "product_files_generated",
            f"Generated {len(generated)} files for product #{product.id}",
            {"files": [str(f) for f in generated]},
        )
        return generated
