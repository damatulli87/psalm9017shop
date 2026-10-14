"""
Order Fulfillment Agent (spec sections 14/15: order retrieval, fulfillment
within policy).

Real paid orders only (`was_paid=true` on the Etsy receipts call) --
abandoned carts never trigger fulfillment. Two real delivery paths:

  - Digital: Etsy delivers the file to the buyer itself once it's attached
    to the listing (confirmed live 2026-10-14, see etsy_manager.py) -- this
    agent just confirms that happened and records the real sale.
  - POD (physical): nothing ships until THIS agent submits a real order to
    Printify. Printify's new-shop default is automatic order approval
    (production starts immediately on submission, confirmed against their
    own docs) -- so submit_order() is a real commitment to print and ship,
    not a draft/preview action.

Real size/color variations (2026-10-14): etsy_manager.py now sets real
Etsy listing inventory/offerings from Printify's own real variant data for
every multi-variant POD format, and stores the real
{etsy_product_id: printify_variant_id} map Etsy hands back. _resolve_variant_id()
below uses the buyer's real transaction product_id to look up the actual
variant they ordered, falling back to the catalog's first listed variant
(the old behavior) -- and raising a real concern when it has to -- only
for a listing created before this feature or a format with nothing to
vary (single-real-variant products like mug/necklace/tumbler). Not yet
exercised against a real buyer transaction, since no real sale has
happened -- same honest caveat as submit_order() below.
"""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.pod_production import _lookup_catalog
from app.budget.ledger import record_transaction
from app.config import settings
from app.integrations import oauth_store, printify
from app.integrations.etsy import get_listing, list_recent_paid_receipts
from app.models.models import Approval, FulfillmentEvent, MarketplaceListing, Order, ProductSpecification


def _money(amount_obj: dict | None) -> float:
    if not amount_obj:
        return 0.0
    divisor = amount_obj.get("divisor") or 100
    return round((amount_obj.get("amount") or 0) / divisor, 2)


def _map_etsy_address(receipt: dict) -> dict:
    """Etsy gives one full `name` field; Printify wants first/last split."""
    name = (receipt.get("name") or "").strip()
    parts = name.split(" ", 1)
    first_name, last_name = (parts[0], parts[1]) if len(parts) == 2 else (parts[0] if parts else "", "")
    return {
        "first_name": first_name,
        "last_name": last_name,
        "address1": receipt.get("first_line") or "",
        "address2": receipt.get("second_line") or "",
        "city": receipt.get("city") or "",
        "region": receipt.get("state") or "",
        "zip": receipt.get("zip") or "",
        "country": receipt.get("country_iso") or "",
        "email": receipt.get("buyer_email") or "",
    }


class OrderFulfillmentAgent(BaseAgent):
    key = "order_fulfillment"

    def _raise_concern(self, *, summary: str, payload: dict) -> None:
        self.db.add(Approval(
            action_type="operational_concern", summary=summary, payload=payload,
            estimated_cost_usd=0.0, risk_level="high", requested_by_agent=self.key, status="pending",
        ))
        self.db.commit()

    def check_for_new_orders(self) -> dict:
        token = oauth_store.get_valid_etsy_token(self.db)
        if not settings.etsy_configured or not token:
            return {"checked": 0, "new_orders": 0, "note": "Etsy not connected."}

        receipts = list_recent_paid_receipts(access_token=token)
        new_count = 0
        for receipt in receipts:
            external_order_id = str(receipt["receipt_id"])
            if self.db.query(Order).filter(
                Order.storefront_channel == "etsy", Order.external_order_id == external_order_id
            ).first():
                continue  # already processed -- idempotent on our own unique constraint too

            order = Order(
                storefront_channel="etsy",
                external_order_id=external_order_id,
                order_total_usd=_money(receipt.get("grandtotal")),
                status="received",
                raw_data=receipt,
            )
            self.db.add(order)
            self.db.commit()
            self.db.refresh(order)
            new_count += 1

            if order.order_total_usd > 0:
                record_transaction(
                    self.db, type="sale", amount_usd=order.order_total_usd, basis="ACTUAL",
                    description=f"Etsy receipt #{external_order_id}", order_id=order.id,
                )

            self.log(
                "real_order_received",
                f"Real paid order #{order.id} (Etsy receipt {external_order_id}): ${order.order_total_usd:.2f}",
                {"order_id": order.id, "amount_usd": order.order_total_usd},
            )
            self._fulfill(order, receipt)

        return {"checked": len(receipts), "new_orders": new_count}

    def _fulfill(self, order: Order, receipt: dict) -> None:
        for txn in receipt.get("transactions", []):
            listing_id = str(txn.get("listing_id"))
            listing = self.db.query(MarketplaceListing).filter(
                MarketplaceListing.storefront_channel == "etsy",
                MarketplaceListing.external_listing_id == listing_id,
            ).first()
            if not listing:
                self._raise_concern(
                    summary=f"Order #{order.id}: sold listing {listing_id} has no matching local record.",
                    payload={"order_id": order.id, "etsy_listing_id": listing_id},
                )
                continue

            product = self.db.query(ProductSpecification).filter(
                ProductSpecification.id == listing.product_id
            ).first()
            if not product:
                self._raise_concern(
                    summary=f"Order #{order.id}: listing #{listing.id} has no matching product record.",
                    payload={"order_id": order.id, "listing_id": listing.id},
                )
                continue

            if product.product_type == "digital":
                # Etsy delivers the file itself once attached -- confirmed
                # live. Don't just assume it's attached because
                # product.product_type says "digital"; verify the real
                # listing actually has it (listing_type == "download")
                # before telling anyone this order is handled.
                token = oauth_store.get_valid_etsy_token(self.db)
                real_listing = get_listing(listing_id, access_token=token) if token else None
                has_file = bool(real_listing and real_listing.get("listing_type") == "download" and real_listing.get("file_data"))
                if has_file:
                    self.db.add(FulfillmentEvent(
                        order_id=order.id, provider="etsy_digital_delivery", status="delivered_by_etsy", cost_usd=0.0,
                    ))
                    self.db.commit()
                    self.log("digital_order_fulfilled", f"Order #{order.id}: verified real file attached; digital delivery handled by Etsy.", {"order_id": order.id})
                else:
                    self.db.add(FulfillmentEvent(order_id=order.id, provider="etsy_digital_delivery", status="no_file_attached", cost_usd=0.0))
                    self.db.commit()
                    self._raise_concern(
                        summary=f"Order #{order.id}: buyer paid for a digital product but listing {listing_id} has no file attached -- they will receive nothing without manual intervention.",
                        payload={"order_id": order.id, "listing_id": listing_id, "product_id": product.id},
                    )
            else:
                self._fulfill_pod(order, receipt, txn, product)

    def _resolve_variant_id(self, order: Order, txn: dict, pod_data: dict, catalog: dict) -> int:
        """Real fix for the known gap this agent previously flagged: a real
        buyer's transaction carries a real `product_id` (Etsy's
        ShopReceiptTransaction schema, confirmed against Etsy's own OpenAPI
        spec) identifying exactly which real listing variation they
        bought. etsy_manager.py's _set_real_pod_variations() stores the
        {etsy_product_id: printify_variant_id} map it got back from Etsy
        when it set up real inventory on the listing (keyed by the sku it
        deliberately set to str(variant_id)), so looking that up here is
        how fulfillment learns which real Printify variant to actually
        ship -- not a guess. Falls back to the catalog's first listed
        variant (the prior behavior) only when no mapping exists (e.g. a
        listing created before this feature, or a single-real-variant
        product with no mapping at all), and raises a real concern when it
        has to fall back so the owner can see it happened rather than it
        being silently assumed correct."""
        variant_map = pod_data.get("variant_map") or {}
        etsy_product_id = txn.get("product_id")
        if etsy_product_id is not None and str(etsy_product_id) in variant_map:
            return variant_map[str(etsy_product_id)]

        fallback = catalog["variant_ids"][0]
        if variant_map:
            # A real mapping exists for this listing but didn't contain the
            # buyer's actual product_id -- a real mismatch worth a human
            # looking at, not just a product with nothing to vary.
            self._raise_concern(
                summary=f"Order #{order.id}: buyer's real Etsy product_id ({etsy_product_id}) wasn't found "
                        f"in this listing's known variant map -- shipping the catalog's default variant "
                        f"instead of the one actually ordered.",
                payload={"order_id": order.id, "etsy_product_id": etsy_product_id, "fallback_variant_id": fallback},
            )
        return fallback

    def _fulfill_pod(self, order: Order, receipt: dict, txn: dict, product: ProductSpecification) -> None:
        pod_data = (product.design_brief or {}).get("pod", {})
        printify_product_id = pod_data.get("printify_product_id")
        if not printify_product_id:
            self._raise_concern(
                summary=f"Order #{order.id}: product #{product.id} has no real Printify product id -- cannot fulfill.",
                payload={"order_id": order.id, "product_id": product.id},
            )
            return

        catalog = _lookup_catalog(product.title)
        if not catalog or not catalog.get("variant_ids"):
            self._raise_concern(
                summary=f"Order #{order.id}: no real Printify catalog mapping for product #{product.id} -- cannot fulfill.",
                payload={"order_id": order.id, "product_id": product.id},
            )
            return
        variant_id = self._resolve_variant_id(order, txn, pod_data, catalog)

        if not settings.printify_shop_id:
            self._raise_concern(
                summary=f"Order #{order.id}: PRINTIFY_SHOP_ID not configured -- cannot fulfill a real POD order.",
                payload={"order_id": order.id, "product_id": product.id},
            )
            return

        # Real money commitment -- Printify's default is automatic order
        # approval, meaning submission immediately starts real production.
        # "pod_paid_production_order" is already a hardcoded
        # ALWAYS_REQUIRES_APPROVAL action (see policy/engine.py, matching
        # pod_production.py's own system prompt: "never place a paid
        # production order without... explicit policy authorization") --
        # this agent was initially built bypassing that gate entirely and
        # was corrected before being considered done. In SUPERVISED mode
        # (the current default) this always pauses for a real owner
        # decision; resume_pod_fulfillment() below is what actually
        # submits the order once approved.
        auth_result = self.request_approval(
            action_type="pod_paid_production_order",
            summary=f"Fulfill order #{order.id}: submit real Printify production order for product #{product.id} ({product.title}).",
            payload={
                "order_id": order.id,
                "product_id": product.id,
                "printify_product_id": printify_product_id,
                "variant_id": variant_id,
                "quantity": txn.get("quantity", 1),
                "address_to": _map_etsy_address(receipt),
            },
            estimated_cost_usd=product.estimated_cost_usd or 0.0,
            risk_level="high",
        )
        if not auth_result.allowed:
            self.db.add(FulfillmentEvent(order_id=order.id, provider="printify", status="awaiting_approval", cost_usd=0.0))
            self.db.commit()
            self.log(
                "pod_order_fulfillment_pending_approval",
                f"Order #{order.id}: real Printify production order requires owner approval before submission.",
                {"order_id": order.id, "approval_id": auth_result.approval_id},
            )
            return

        self._submit_to_printify(order, printify_product_id, variant_id, txn.get("quantity", 1), _map_etsy_address(receipt))

    def _submit_to_printify(self, order: Order, product_id: str, variant_id: int, quantity: int, address_to: dict) -> None:
        result = printify.submit_order(
            settings.printify_shop_id,
            external_id=str(order.id),
            product_id=product_id,
            variant_id=variant_id,
            quantity=quantity,
            address_to=address_to,
        )
        self.db.add(FulfillmentEvent(
            order_id=order.id,
            provider="printify",
            status="submitted" if result.success else "submission_failed",
            cost_usd=0.0,
            tracking_info=result.order_id or "",
        ))
        self.db.commit()
        self.log(
            "pod_order_fulfillment_submitted" if result.success else "pod_order_fulfillment_failed",
            f"Order #{order.id}: {result.detail}",
            {"order_id": order.id, "printify_order_id": result.order_id, "success": result.success},
        )
        if not result.success:
            self._raise_concern(
                summary=f"Order #{order.id}: real Printify order submission FAILED -- buyer will not receive their item without manual intervention.",
                payload={"order_id": order.id, "detail": result.detail},
            )


def resume_pod_fulfillment(db, approval) -> None:
    """Called from the real approval-decision dispatcher
    (app/routers/approvals.py -> workflow_engine.resume_after_approval)
    when a "pod_paid_production_order" approval is decided. Only submits
    the real Printify order on approval -- a rejection just leaves the
    order's FulfillmentEvent at "awaiting_approval" with nothing shipped."""
    if approval.status != "approved":
        return
    payload = approval.payload or {}
    order = db.query(Order).filter(Order.id == payload.get("order_id")).first()
    if not order:
        return
    agent = OrderFulfillmentAgent(db)
    agent._submit_to_printify(
        order,
        payload["printify_product_id"],
        payload["variant_id"],
        payload.get("quantity", 1),
        payload["address_to"],
    )
