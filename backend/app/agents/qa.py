"""
Quality Assurance Agent (spec section 11).

Runs real checks against the files the Digital Production Agent wrote to
disk: does the PDF actually open and have the right page size/count, does
the XLSX actually contain live formulas (not just static numbers), does
the preview image actually have the right dimensions, is the ZIP valid and
non-empty. A product that fails any mandatory check is NOT marked
publishable. These are technical checks only -- not legal/IP clearance.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from PIL import Image
from pypdf import PdfReader

from app.agents.base import BaseAgent
from app.models.models import ProductAsset, ProductSpecification, QAResult

EXPECTED_PDF_SIZE_PT = (612, 792)  # US Letter
EXPECTED_PREVIEW_SIZE = (2000, 2000)


class QAAgent(BaseAgent):
    key = "qa"

    def _record(self, product_id: int, check_name: str, passed: bool, details: str) -> QAResult:
        result = QAResult(product_id=product_id, check_name=check_name, passed=passed, details=details)
        self.db.add(result)
        self.db.commit()
        return result

    def run_checks(self, product: ProductSpecification) -> bool:
        if product.product_type != "digital":
            return self._run_pod_checks(product)

        assets = self.db.query(ProductAsset).filter(ProductAsset.product_id == product.id).all()
        asset_by_type = {a.asset_type: Path(a.file_path) for a in assets}
        all_passed = True

        # --- Mandatory: main deliverable exists and is non-empty ---
        main_type = "xlsx" if product.format == "xlsx" else "pdf"
        main_path = asset_by_type.get(main_type)
        if not main_path or not main_path.exists() or main_path.stat().st_size == 0:
            self._record(product.id, "main_file_exists", False, f"Missing or empty {main_type} file.")
            all_passed = False
        else:
            self._record(product.id, "main_file_exists", True, f"{main_path.name} ({main_path.stat().st_size} bytes)")

            if main_type == "pdf":
                try:
                    reader = PdfReader(str(main_path))
                    page_count = len(reader.pages)
                    first_page = reader.pages[0]
                    size = (round(float(first_page.mediabox.width)), round(float(first_page.mediabox.height)))
                    passed = page_count > 0 and size == EXPECTED_PDF_SIZE_PT
                    self._record(
                        product.id, "pdf_opens_and_dimensions_correct", passed,
                        f"{page_count} page(s), size {size}, expected {EXPECTED_PDF_SIZE_PT}",
                    )
                    all_passed = all_passed and passed
                except Exception as exc:  # noqa: BLE001
                    self._record(product.id, "pdf_opens_and_dimensions_correct", False, f"PDF failed to open: {exc}")
                    all_passed = False
            else:  # xlsx
                try:
                    wb = load_workbook(main_path)
                    ws = wb.active
                    formula_cells = [
                        cell.coordinate
                        for row in ws.iter_rows()
                        for cell in row
                        if isinstance(cell.value, str) and cell.value.startswith("=")
                    ]
                    passed = len(formula_cells) > 0
                    self._record(
                        product.id, "xlsx_has_working_formulas", passed,
                        f"Found {len(formula_cells)} formula cells: {formula_cells[:5]}",
                    )
                    all_passed = all_passed and passed
                except Exception as exc:  # noqa: BLE001
                    self._record(product.id, "xlsx_has_working_formulas", False, f"XLSX failed to open: {exc}")
                    all_passed = False

        # --- Mandatory: preview image exists with correct dimensions ---
        preview_path = asset_by_type.get("png")
        if preview_path and preview_path.exists():
            try:
                with Image.open(preview_path) as img:
                    passed = img.size == EXPECTED_PREVIEW_SIZE and img.format == "PNG"
                    self._record(
                        product.id, "preview_image_valid", passed,
                        f"size={img.size}, format={img.format}, expected {EXPECTED_PREVIEW_SIZE}",
                    )
                    all_passed = all_passed and passed
            except Exception as exc:  # noqa: BLE001
                self._record(product.id, "preview_image_valid", False, f"Preview image failed to open: {exc}")
                all_passed = False
        else:
            self._record(product.id, "preview_image_valid", False, "Preview PNG missing.")
            all_passed = False

        # --- Mandatory: delivery ZIP is valid and contains the main file + instructions ---
        zip_path = asset_by_type.get("zip")
        if zip_path and zip_path.exists():
            import zipfile

            try:
                with zipfile.ZipFile(zip_path) as zf:
                    bad_file = zf.testzip()
                    names = zf.namelist()
                    passed = bad_file is None and main_path is not None and main_path.name in names
                    self._record(product.id, "zip_package_valid", passed, f"Contains: {names}")
                    all_passed = all_passed and passed
            except Exception as exc:  # noqa: BLE001
                self._record(product.id, "zip_package_valid", False, f"ZIP failed validation: {exc}")
                all_passed = False
        else:
            self._record(product.id, "zip_package_valid", False, "Delivery ZIP missing.")
            all_passed = False

        # NOTE: AI-disclosure accuracy is NOT checked here -- QA runs before
        # listing_creation, so there's no listing description yet to check
        # against. That check runs post-hoc in UltronSupervisorAgent
        # (verify_ai_disclosure_accuracy), where the actual listing text and
        # the product's real AI-involvement flag both exist to compare.

        product.status = "qa_passed" if all_passed else "qa_failed"
        self.db.commit()

        self.log(
            "qa_completed",
            f"Product #{product.id} QA {'PASSED' if all_passed else 'FAILED'}",
            {"product_id": product.id, "passed": all_passed},
        )
        return all_passed

    def _run_pod_checks(self, product: ProductSpecification) -> bool:
        """POD products have no PDF/XLSX/ZIP -- real checks instead verify
        the real artwork file, the real Printify product, and that the real
        quoted cost actually supports a positive margin at the listed price."""
        all_passed = True
        pod_data = (product.design_brief or {}).get("pod", {})

        assets = self.db.query(ProductAsset).filter(ProductAsset.product_id == product.id).all()
        artwork_path = next((Path(a.file_path) for a in assets if a.asset_type == "png"), None)
        if artwork_path and artwork_path.exists():
            try:
                with Image.open(artwork_path) as img:
                    passed = img.format == "PNG" and img.size[0] > 0 and img.size[1] > 0
                    self._record(product.id, "pod_artwork_exists", passed, f"size={img.size}, format={img.format}")
                    all_passed = all_passed and passed
            except Exception as exc:  # noqa: BLE001
                self._record(product.id, "pod_artwork_exists", False, f"Artwork image failed to open: {exc}")
                all_passed = False
        else:
            self._record(product.id, "pod_artwork_exists", False, "Print artwork PNG missing.")
            all_passed = False

        printify_product_id = pod_data.get("printify_product_id")
        passed = bool(printify_product_id)
        self._record(
            product.id, "printify_product_created", passed,
            f"printify_product_id={printify_product_id}" if passed else "No Printify product id recorded.",
        )
        all_passed = all_passed and passed

        real_cost = pod_data.get("real_cost_usd")
        passed = isinstance(real_cost, (int, float)) and real_cost > 0 and product.recommended_price_usd > real_cost
        detail = (
            f"real_cost=${real_cost}, price=${product.recommended_price_usd}"
            if real_cost is not None
            else "No real cost recorded."
        )
        self._record(product.id, "real_cost_recorded", passed, detail)
        all_passed = all_passed and passed

        product.status = "qa_passed" if all_passed else "qa_failed"
        self.db.commit()

        self.log(
            "qa_completed",
            f"Product #{product.id} (POD) QA {'PASSED' if all_passed else 'FAILED'}",
            {"product_id": product.id, "passed": all_passed},
        )
        return all_passed
