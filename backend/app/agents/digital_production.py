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
from app.agents.generators.preview_generator import generate_preview_png
from app.agents.generators.xlsx_generator import generate_budget_spreadsheet
from app.integrations.file_storage import product_dir, register_asset
from app.models.models import ProductSpecification

DEFAULT_SECTIONS = ["Overview", "Weekly Planning", "Tracking Grid", "Notes"]


class DigitalProductionAgent(BaseAgent):
    key = "digital_production"

    def produce(self, product: ProductSpecification) -> list[Path]:
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
        generate_preview_png(preview_path, title=product.title, palette=palette)
        generated.append(preview_path)

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
