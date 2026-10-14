"""
Order Fulfillment Agent tests (direct response to the owner's directive:
"if someone buys something they get what they purchase -- we can NOT have
any failures like that").

These exercise the real DB, real policy/approval engine, and the real
decide_approval -> resume_after_approval dispatch path. Only the actual
network boundary is mocked: a real Etsy OAuth token and a real Printify
production order can't be created in a test run, so `oauth_store` /
`etsy.get_listing` / `printify.submit_order` are monkeypatched -- everything
else (Order/FulfillmentEvent/Approval rows, the approval gate itself, the
resume dispatcher) runs for real.
"""
from __future__ import annotations

from app.agents import order_fulfillment as of
from app.database import SessionLocal
from app.integrations.printify import PrintifyOrderResult
from app.models.models import (
    Approval,
    FulfillmentEvent,
    MarketplaceListing,
    Order,
    ProductSpecification,
    Transaction,
)
from app.orchestration.workflow_engine import resume_after_approval
from app.policy.engine import decide_approval


def _make_listing(db, *, product_type: str, title: str, external_listing_id: str, design_brief: dict | None = None):
    product = ProductSpecification(
        title=title,
        product_type=product_type,
        target_customer="test",
        problem_solved="test",
        format="pdf" if product_type == "digital" else "tshirt",
        design_brief=design_brief or {},
        recommended_price_usd=19.99,
        estimated_cost_usd=6.0,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    listing = MarketplaceListing(
        product_id=product.id,
        storefront_channel="etsy",
        external_listing_id=external_listing_id,
        title=title,
        description="test",
        price_usd=19.99,
        status="published",
        is_simulated=False,
    )
    db.add(listing)
    db.commit()
    return product, listing


def _fake_receipt(receipt_id: str, listing_id: str, *, quantity: int = 1, product_id: int | None = None) -> dict:
    txn = {"listing_id": listing_id, "quantity": quantity}
    if product_id is not None:
        txn["product_id"] = product_id
    return {
        "receipt_id": receipt_id,
        "name": "Jane Buyer",
        "first_line": "123 Main St",
        "second_line": "",
        "city": "Springfield",
        "state": "IL",
        "zip": "62704",
        "country_iso": "US",
        "buyer_email": "jane@example.com",
        "grandtotal": {"amount": 1999, "divisor": 100},
        "transactions": [txn],
    }


def _teardown(db, *, order=None, product=None, listing=None):
    """Deletes only the rows this test itself created -- never a blanket
    table truncation, since the test DB is shared across the whole session
    and other test files' rows (e.g. test_digital_product_e2e.py's own
    Approval row) must survive untouched."""
    if order is not None:
        db.query(Transaction).filter(Transaction.order_id == order.id).delete()
        db.query(FulfillmentEvent).filter(FulfillmentEvent.order_id == order.id).delete()
        # JSON-column filtering is dialect-specific, so match in Python instead.
        stale_approval_ids = [
            a.id for a in db.query(Approval).all() if (a.payload or {}).get("order_id") == order.id
        ]
        if stale_approval_ids:
            db.query(Approval).filter(Approval.id.in_(stale_approval_ids)).delete(synchronize_session=False)
        db.query(Order).filter(Order.id == order.id).delete()
    if listing is not None:
        db.query(MarketplaceListing).filter(MarketplaceListing.id == listing.id).delete()
    if product is not None:
        db.query(ProductSpecification).filter(ProductSpecification.id == product.id).delete()
    db.commit()
    db.close()


def test_digital_order_with_real_file_is_marked_delivered(monkeypatch):
    db = SessionLocal()
    order = product = listing = None
    try:
        product, listing = _make_listing(
            db, product_type="digital", title="Test Digital Product A", external_listing_id="9001001",
        )

        monkeypatch.setattr(of.oauth_store, "get_valid_etsy_token", lambda _db: "fake-token")
        monkeypatch.setattr(
            of, "get_listing",
            lambda _listing_id, access_token: {"listing_type": "download", "file_data": "1 File"},
        )

        agent = of.OrderFulfillmentAgent(db)
        order = Order(storefront_channel="etsy", external_order_id="dig-ok-1", order_total_usd=19.99, status="received")
        db.add(order)
        db.commit()
        db.refresh(order)

        agent._fulfill(order, _fake_receipt("dig-ok-1", listing.external_listing_id))

        event = db.query(FulfillmentEvent).filter(FulfillmentEvent.order_id == order.id).order_by(FulfillmentEvent.id.desc()).first()
        assert event is not None
        assert event.status == "delivered_by_etsy"
        assert db.query(Approval).filter(Approval.action_type == "operational_concern").count() == 0
    finally:
        _teardown(db, order=order, product=product, listing=listing)


def test_digital_order_with_no_file_raises_concern_not_false_success(monkeypatch):
    """The real bug this session found live: a digital listing can exist
    without ever having had its file uploaded. This must never be marked
    delivered -- the buyer would receive nothing."""
    db = SessionLocal()
    order = product = listing = None
    try:
        product, listing = _make_listing(
            db, product_type="digital", title="Test Digital Product B", external_listing_id="9001002",
        )

        monkeypatch.setattr(of.oauth_store, "get_valid_etsy_token", lambda _db: "fake-token")
        monkeypatch.setattr(
            of, "get_listing",
            lambda _listing_id, access_token: {"listing_type": "physical", "file_data": None},
        )

        agent = of.OrderFulfillmentAgent(db)
        order = Order(storefront_channel="etsy", external_order_id="dig-fail-1", order_total_usd=19.99, status="received")
        db.add(order)
        db.commit()
        db.refresh(order)

        agent._fulfill(order, _fake_receipt("dig-fail-1", listing.external_listing_id))

        event = db.query(FulfillmentEvent).filter(FulfillmentEvent.order_id == order.id).order_by(FulfillmentEvent.id.desc()).first()
        assert event is not None and event.status == "no_file_attached"

        concern = db.query(Approval).filter(Approval.action_type == "operational_concern").order_by(Approval.id.desc()).first()
        assert concern is not None and concern.status == "pending"
        assert concern.payload.get("order_id") == order.id
    finally:
        _teardown(db, order=order, product=product, listing=listing)


def test_pod_order_requires_real_approval_before_any_printify_call(monkeypatch):
    """pod_paid_production_order is a hardcoded ALWAYS_REQUIRES_APPROVAL
    action -- this must stay true even if someone refactors this agent
    later, since skipping it means real money gets spent printing/shipping
    without owner sign-off."""
    db = SessionLocal()
    order = product = listing = None
    try:
        product, listing = _make_listing(
            db, product_type="pod", title="Faith-Based Graphic T-Shirts - test",
            external_listing_id="9001003",
            design_brief={"pod": {"printify_product_id": "fake-printify-product-id"}},
        )

        def _unexpected_submit(*_args, **_kwargs):
            raise AssertionError("submit_order() must never be called before approval is granted")

        monkeypatch.setattr(of.printify, "submit_order", _unexpected_submit)
        monkeypatch.setattr(of.settings, "printify_shop_id", "fake-shop-id")

        agent = of.OrderFulfillmentAgent(db)
        order = Order(storefront_channel="etsy", external_order_id="pod-1", order_total_usd=19.99, status="received")
        db.add(order)
        db.commit()
        db.refresh(order)

        agent._fulfill(order, _fake_receipt("pod-1", listing.external_listing_id))

        approval = db.query(Approval).filter(Approval.action_type == "pod_paid_production_order").order_by(Approval.id.desc()).first()
        assert approval is not None and approval.status == "pending"

        event = db.query(FulfillmentEvent).filter(FulfillmentEvent.order_id == order.id).order_by(FulfillmentEvent.id.desc()).first()
        assert event is not None and event.status == "awaiting_approval"
    finally:
        _teardown(db, order=order, product=product, listing=listing)


def test_pod_order_submits_to_printify_only_after_owner_approves(monkeypatch):
    db = SessionLocal()
    order = product = listing = None
    try:
        product, listing = _make_listing(
            db, product_type="pod", title="Scripture Verse Coffee Mugs - test",
            external_listing_id="9001004",
            design_brief={"pod": {"printify_product_id": "fake-printify-product-id-2"}},
        )

        calls = {}

        def _fake_submit_order(shop_id, *, external_id, product_id, variant_id, quantity, address_to):
            calls["shop_id"] = shop_id
            calls["external_id"] = external_id
            calls["product_id"] = product_id
            calls["variant_id"] = variant_id
            calls["quantity"] = quantity
            calls["address_to"] = address_to
            return PrintifyOrderResult(success=True, order_id="fake-printify-order-1", detail="ok")

        monkeypatch.setattr(of.printify, "submit_order", _fake_submit_order)
        monkeypatch.setattr(of.settings, "printify_shop_id", "fake-shop-id")

        agent = of.OrderFulfillmentAgent(db)
        order = Order(storefront_channel="etsy", external_order_id="pod-2", order_total_usd=19.99, status="received")
        db.add(order)
        db.commit()
        db.refresh(order)

        agent._fulfill(order, _fake_receipt("pod-2", listing.external_listing_id))

        approval = db.query(Approval).filter(Approval.action_type == "pod_paid_production_order").order_by(Approval.id.desc()).first()
        assert approval is not None and approval.status == "pending"
        assert "shop_id" not in calls, "must not submit before approval"

        decide_approval(db, approval.id, approve=True, decided_by="owner-test")
        resume_after_approval(db, approval.id)

        assert calls.get("product_id") == "fake-printify-product-id-2"
        assert calls.get("external_id") == str(order.id)
        assert calls.get("address_to", {}).get("first_name") == "Jane"
        assert calls.get("address_to", {}).get("email") == "jane@example.com"

        event = db.query(FulfillmentEvent).filter(FulfillmentEvent.order_id == order.id).order_by(FulfillmentEvent.id.desc()).first()
        assert event is not None and event.status == "submitted" and event.tracking_info == "fake-printify-order-1"
    finally:
        _teardown(db, order=order, product=product, listing=listing)


def test_pod_order_ships_the_real_purchased_variant_when_mapped(monkeypatch):
    """Real fix for the size/color gap: a buyer who picked Black/S must
    get Black/S, not the catalog's arbitrarily-first-listed White/L --
    this is exactly what etsy_manager.py's real variant_map (built from
    Etsy's own inventory response) exists to prevent."""
    db = SessionLocal()
    order = product = listing = None
    try:
        product, listing = _make_listing(
            db, product_type="pod", title="Faith-Based Graphic T-Shirts - test",
            external_listing_id="9001007",
            design_brief={
                "pod": {
                    "printify_product_id": "fake-printify-product-id-4",
                    "variant_map": {"555000111": 12126},  # Black / S, not the catalog's first (12100, White/L)
                },
            },
        )

        calls = {}

        def _fake_submit_order(shop_id, *, external_id, product_id, variant_id, quantity, address_to):
            calls["variant_id"] = variant_id
            return PrintifyOrderResult(success=True, order_id="fake-printify-order-2", detail="ok")

        monkeypatch.setattr(of.printify, "submit_order", _fake_submit_order)
        monkeypatch.setattr(of.settings, "printify_shop_id", "fake-shop-id")

        agent = of.OrderFulfillmentAgent(db)
        order = Order(storefront_channel="etsy", external_order_id="pod-4", order_total_usd=19.99, status="received")
        db.add(order)
        db.commit()
        db.refresh(order)

        agent._fulfill(order, _fake_receipt("pod-4", listing.external_listing_id, product_id=555000111))

        approval = db.query(Approval).filter(Approval.action_type == "pod_paid_production_order").order_by(Approval.id.desc()).first()
        decide_approval(db, approval.id, approve=True, decided_by="owner-test")
        resume_after_approval(db, approval.id)

        assert calls.get("variant_id") == 12126, "must ship the real purchased variant, not the catalog default"
        concerns = db.query(Approval).filter(Approval.action_type == "operational_concern").all()
        assert not any("wasn't found" in (c.summary or "") for c in concerns), "a correctly-mapped purchase shouldn't raise a mismatch concern"
    finally:
        _teardown(db, order=order, product=product, listing=listing)


def test_pod_order_falls_back_and_flags_concern_when_product_id_unmapped(monkeypatch):
    """A real variant_map exists for this listing, but the buyer's real
    product_id isn't in it (e.g. Etsy data drift, or a mapping built
    before a listing's inventory was last changed) -- must still ship
    something (the catalog default) rather than fail the order outright,
    but must surface the mismatch rather than silently guessing right."""
    db = SessionLocal()
    order = product = listing = None
    try:
        product, listing = _make_listing(
            db, product_type="pod", title="Faith-Based Graphic T-Shirts - test",
            external_listing_id="9001008",
            design_brief={
                "pod": {
                    "printify_product_id": "fake-printify-product-id-5",
                    "variant_map": {"111222333": 12126},
                },
            },
        )

        calls = {}

        def _fake_submit_order(shop_id, *, external_id, product_id, variant_id, quantity, address_to):
            calls["variant_id"] = variant_id
            return PrintifyOrderResult(success=True, order_id="fake-printify-order-3", detail="ok")

        monkeypatch.setattr(of.printify, "submit_order", _fake_submit_order)
        monkeypatch.setattr(of.settings, "printify_shop_id", "fake-shop-id")

        agent = of.OrderFulfillmentAgent(db)
        order = Order(storefront_channel="etsy", external_order_id="pod-5", order_total_usd=19.99, status="received")
        db.add(order)
        db.commit()
        db.refresh(order)

        agent._fulfill(order, _fake_receipt("pod-5", listing.external_listing_id, product_id=999999999))

        approval = db.query(Approval).filter(Approval.action_type == "pod_paid_production_order").order_by(Approval.id.desc()).first()
        decide_approval(db, approval.id, approve=True, decided_by="owner-test")
        resume_after_approval(db, approval.id)

        catalog_default = 12100  # first variant_id in _TSHIRT_CATALOG
        assert calls.get("variant_id") == catalog_default

        concern = db.query(Approval).filter(Approval.action_type == "operational_concern").order_by(Approval.id.desc()).first()
        assert concern is not None and "wasn't found" in concern.summary
        assert concern.payload.get("etsy_product_id") == 999999999
    finally:
        _teardown(db, order=order, product=product, listing=listing)


def test_pod_order_rejected_by_owner_never_reaches_printify(monkeypatch):
    db = SessionLocal()
    order = product = listing = None
    try:
        product, listing = _make_listing(
            db, product_type="pod", title="Christian Faith Pullover Hoodies - test",
            external_listing_id="9001005",
            design_brief={"pod": {"printify_product_id": "fake-printify-product-id-3"}},
        )

        def _unexpected_submit(*_args, **_kwargs):
            raise AssertionError("submit_order() must never be called after a rejection")

        monkeypatch.setattr(of.printify, "submit_order", _unexpected_submit)
        monkeypatch.setattr(of.settings, "printify_shop_id", "fake-shop-id")

        agent = of.OrderFulfillmentAgent(db)
        order = Order(storefront_channel="etsy", external_order_id="pod-3", order_total_usd=19.99, status="received")
        db.add(order)
        db.commit()
        db.refresh(order)

        agent._fulfill(order, _fake_receipt("pod-3", listing.external_listing_id))

        approval = db.query(Approval).filter(Approval.action_type == "pod_paid_production_order").order_by(Approval.id.desc()).first()
        assert approval is not None

        decide_approval(db, approval.id, approve=False, decided_by="owner-test", notes="not real, declining in test")
        resume_after_approval(db, approval.id)

        event = db.query(FulfillmentEvent).filter(FulfillmentEvent.order_id == order.id).order_by(FulfillmentEvent.id.desc()).first()
        assert event is not None and event.status == "awaiting_approval"
    finally:
        _teardown(db, order=order, product=product, listing=listing)


def test_check_for_new_orders_is_idempotent_on_repeat_calls(monkeypatch):
    """A scheduler re-run (or overlapping run despite max_instances=1) must
    never double-process the same real Etsy receipt into two Orders/sales."""
    db = SessionLocal()
    order = product = listing = None
    try:
        product, listing = _make_listing(
            db, product_type="digital", title="Test Digital Product C", external_listing_id="9001006",
        )

        monkeypatch.setattr(of.oauth_store, "get_valid_etsy_token", lambda _db: "fake-token")
        monkeypatch.setattr(
            of, "list_recent_paid_receipts",
            lambda access_token, limit=25: [_fake_receipt("idem-1", listing.external_listing_id)],
        )
        monkeypatch.setattr(of, "get_listing", lambda _listing_id, access_token: {"listing_type": "download", "file_data": "1 File"})

        # etsy_configured is a read-only computed property (no setter), so
        # the underlying fields it derives from are patched instead.
        from app.config import settings as real_settings
        monkeypatch.setattr(real_settings, "etsy_api_key", "fake-key")
        monkeypatch.setattr(real_settings, "etsy_api_secret", "fake-secret")
        monkeypatch.setattr(real_settings, "etsy_shop_id", "fake-shop")

        agent = of.OrderFulfillmentAgent(db)
        first = agent.check_for_new_orders()
        second = agent.check_for_new_orders()

        assert first["new_orders"] == 1
        assert second["new_orders"] == 0
        assert db.query(Order).filter(Order.external_order_id == "idem-1").count() == 1
    finally:
        created_order = db.query(Order).filter(Order.external_order_id == "idem-1").first()
        _teardown(db, order=created_order, product=product, listing=listing)
