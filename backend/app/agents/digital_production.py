"""
Digital Product Production Agent (spec section 9).

Produces real files on disk -- never placeholders. Supported formats in
this MVP: PDF (printable/planner-style) and XLSX (working-formula budget
spreadsheet), plus a PNG listing preview and a customer-ready ZIP package.
DOCX/SVG are straightforward additions on top of the same pattern
(python-docx / svgwrite) once a real demand case needs them -- not built
yet (see PROGRESS.md).

Niche-specific layouts: chore charts got a real bespoke one
(generators/chore_chart_generator.py) because that's the niche that kept
winning the research scoring. Every other PDF niche used to fall back to a
single hardcoded DEFAULT_SECTIONS ruled-lines template regardless of what
the niche actually was -- the owner correctly judged this "super super
basic compared to ones selling for $5 on Etsy." Fixed the same way the POD
artwork style problem was fixed: _real_content_plan() below does real
competitive research (search_top_listings()) and asks a real AI call to
propose a concrete, niche-appropriate content plan (checklists with real
item text, tables with real column headers, trackers -- never a flat list
of blank ruled pages), which generate_pdf_product() then renders with real
fillable AcroForm fields. DEFAULT_SECTIONS is now only the fallback for
when real research isn't available (Etsy not connected, or no real AI key
configured) -- not the default experience.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from app.agents.base import BaseAgent
from app.agents.generators.chore_chart_generator import generate_chore_chart_pdf
from app.agents.generators.pdf_generator import generate_instructions_txt, generate_pdf_product
from app.agents.generators.xlsx_generator import generate_budget_spreadsheet
from app.config import settings
from app.integrations import ai_providers, oauth_store
from app.integrations.etsy import search_top_listings
from app.integrations.file_storage import product_dir, register_asset
from app.integrations.image_providers import generate_listing_image
from app.models.models import ProductSpecification

DEFAULT_SECTIONS = ["Overview", "Weekly Planning", "Tracking Grid", "Notes"]

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_VALID_LAYOUTS = {"checklist", "table", "tracker", "notes"}


def _valid_content_plan(parsed) -> list[dict] | None:
    if not isinstance(parsed, list) or not (1 <= len(parsed) <= 8):
        return None
    sections = []
    for entry in parsed:
        if not isinstance(entry, dict) or not isinstance(entry.get("heading"), str) or not entry["heading"].strip():
            return None
        layout = entry.get("layout")
        if layout not in _VALID_LAYOUTS:
            return None
        section = {"heading": entry["heading"].strip()[:60], "layout": layout}
        if layout == "checklist":
            items = entry.get("items")
            if not isinstance(items, list) or not items or not all(isinstance(i, str) for i in items):
                return None
            section["items"] = [i.strip()[:90] for i in items if i.strip()][:20]
            if not section["items"]:
                return None
        elif layout == "table":
            columns = entry.get("columns")
            if not isinstance(columns, list) or not columns or not all(isinstance(i, str) for i in columns):
                return None
            section["columns"] = [i.strip()[:24] for i in columns if i.strip()][:6]
            if not section["columns"]:
                return None
        elif layout == "tracker":
            periods = entry.get("periods", 31)
            section["periods"] = periods if isinstance(periods, int) and 1 <= periods <= 60 else 31
            label = entry.get("period_label", "Day")
            section["period_label"] = label[:12] if isinstance(label, str) and label.strip() else "Day"
        sections.append(section)
    return sections


def _real_content_plan(db, agent_key: str, product: ProductSpecification) -> list[dict] | None:
    """Real competitive research (same pattern as pod_production.py's
    _real_style_guidance(), applied to CONTENT structure instead of visual
    style): searches Etsy's real live listings for this niche, asks a real
    AI call to propose a concrete content plan grounded in common real
    patterns across the top results -- never copying one listing's exact
    content, same IP-safety framing as the POD research. Returns None
    (caller falls back to DEFAULT_SECTIONS) if Etsy isn't connected, the
    search fails, or the AI response is mock/doesn't parse as a valid plan
    -- this is a real enhancement, not a hard requirement to produce a
    product."""
    token = oauth_store.get_valid_etsy_token(db)
    if not settings.etsy_configured or not token:
        return None
    try:
        top = search_top_listings(product.title, access_token=token, sample_size=50, top_n=10)
    except Exception:  # noqa: BLE001
        return None
    if not top:
        return None

    listing_lines = "\n".join(f"- {t['title']} (tags: {', '.join(t['tags'][:6])})" for t in top)
    resp = ai_providers.complete(
        db,
        agent_key=agent_key,
        system_prompt=(
            "You design the real content structure of a printable PDF digital product, based on common "
            "patterns across real top-performing Etsy listings. Never describe or copy any single listing -- "
            "synthesize patterns across several. Propose 3-6 real, concrete, useful pages (not vague "
            "placeholders like 'Notes' or 'Overview' unless genuinely appropriate). Respond with ONLY a JSON "
            "array, each element: {\"heading\": str, \"layout\": one of \"checklist\"/\"table\"/\"tracker\"/"
            "\"notes\"}. A \"checklist\" element must also include \"items\": a list of 5-15 real, specific "
            "checklist item strings appropriate to this niche (e.g. real task names, real checklist steps -- "
            "not generic placeholders). A \"table\" element must also include \"columns\": a list of 2-6 real "
            "column header strings. A \"tracker\" element may include \"periods\" (int, e.g. 7 or 31) and "
            "\"period_label\" (e.g. \"Day\", \"Week\"). No prose, no markdown fences, ONLY the JSON array."
        ),
        user_prompt=f"Digital product title: '{product.title}'\nTarget buyer: {product.target_customer}\n\n"
                    f"These are the most-favorited real Etsy listings for this niche:\n{listing_lines}\n\n"
                    f"Propose the real content plan for this product.",
        task_hint="digital_content_plan",
        complexity="routine",
        workflow_run_id=None,
    )
    if resp.is_mock:
        return None
    try:
        parsed = json.loads(_JSON_FENCE_RE.sub("", resp.text.strip()))
    except (json.JSONDecodeError, TypeError):
        return None
    return _valid_content_plan(parsed)


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
        else:  # generic path -- see module docstring
            main_path = out_dir / f"product_{product.id}.pdf"
            content_plan = _real_content_plan(self.db, self.key, product)
            if content_plan:
                self.log(
                    "real_content_plan_used",
                    f"Product #{product.id}: real competitive-research content plan "
                    f"({len(content_plan)} sections) used instead of the generic fallback.",
                    {"product_id": product.id, "sections": [s["heading"] for s in content_plan]},
                )
            generate_pdf_product(main_path, title=product.title, palette=palette,
                                  sections=content_plan or DEFAULT_SECTIONS)
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
