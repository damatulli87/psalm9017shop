"""
Real Etsy listing variation (size/color) mapping tests -- direct response
to "correct the size and color issue": a POD listing with no real
variations means a buyer can't pick a size/color, and fulfillment has to
guess. These test the pure mapping logic against Printify's real variant
option data (captured live, 2026-10-14) and Etsy's real taxonomy
property/value ids (confirmed live via get_taxonomy_properties()), with no
network calls -- printify.get_variants() is monkeypatched to the exact
real response shape, not a simplified stand-in.
"""
from __future__ import annotations

from app.agents import etsy_manager as em
from app.agents.pod_production import NICHE_CATALOG_MAP
from app.models.models import ProductSpecification

# Real captured Printify variant option data per blueprint_id (2026-10-14
# live calls to get_variants()) -- not simplified, including the real
# mangled-looking surface/size strings Printify itself returns.
_REAL_VARIANTS_BY_BLUEPRINT = {
    6: [  # t-shirt
        {"id": 12100, "options": {"color": "White", "size": "L"}},
        {"id": 12101, "options": {"color": "White", "size": "M"}},
        {"id": 12102, "options": {"color": "White", "size": "S"}},
        {"id": 12103, "options": {"color": "White", "size": "XL"}},
        {"id": 12104, "options": {"color": "White", "size": "2XL"}},
        {"id": 12124, "options": {"color": "Black", "size": "L"}},
        {"id": 12125, "options": {"color": "Black", "size": "M"}},
        {"id": 12126, "options": {"color": "Black", "size": "S"}},
        {"id": 12127, "options": {"color": "Black", "size": "XL"}},
        {"id": 12128, "options": {"color": "Black", "size": "2XL"}},
    ],
    1108: [  # cap
        {"id": 82433, "options": {"color": "Khaki", "size": "One size"}},
        {"id": 82434, "options": {"color": "White", "size": "One size"}},
        {"id": 104278, "options": {"color": "Black", "size": "One size"}},
        {"id": 104279, "options": {"color": "Dark Green", "size": "One size"}},
        {"id": 104280, "options": {"color": "Dark Navy", "size": "One size"}},
        {"id": 104282, "options": {"color": "Red", "size": "One size"}},
    ],
    1931: [  # notebook -- the real collision case: Blue/Navy/Turquoise
        {"id": 119669, "options": {"size": '5.5" x 8.5"', "color": "Black"}},
        {"id": 119670, "options": {"size": '5.5" x 8.5"', "color": "Blue"}},
        {"id": 119671, "options": {"size": '5.5" x 8.5"', "color": "Lime"}},
        {"id": 119672, "options": {"size": '5.5" x 8.5"', "color": "Navy"}},
        {"id": 119673, "options": {"size": '5.5" x 8.5"', "color": "Orange"}},
        {"id": 119674, "options": {"size": '5.5" x 8.5"', "color": "Red"}},
        {"id": 119675, "options": {"size": '5.5" x 8.5"', "color": "Silver"}},
        {"id": 119676, "options": {"size": '5.5" x 8.5"', "color": "Turquoise"}},
    ],
    68: [{"id": 33719, "options": {"size": "11oz"}}],  # mug -- single real variant
}


def _patch_get_variants(monkeypatch):
    monkeypatch.setattr(
        em.printify, "get_variants",
        lambda blueprint_id, print_provider_id: _REAL_VARIANTS_BY_BLUEPRINT.get(blueprint_id, []),
    )


def _product(title: str, fmt: str) -> ProductSpecification:
    return ProductSpecification(
        title=title, format=fmt, product_type="pod", target_customer="x", problem_solved="x", design_brief={},
    )


def test_tshirt_builds_real_color_and_normalized_size_for_every_variant(monkeypatch):
    _patch_get_variants(monkeypatch)
    catalog = NICHE_CATALOG_MAP["Faith-Based Graphic T-Shirts"]
    products = em._build_inventory_products(_product("Faith-Based Graphic T-Shirts - test", "tshirt"), catalog, 19.99)

    assert products is not None and len(products) == 10
    by_sku = {p["sku"]: p for p in products}

    # "2XL" (Printify's real name) must normalize to Etsy's real "2X" value, not match nothing.
    p = by_sku["12104"]
    size_pv = next(pv for pv in p["property_values"] if pv["property_name"] == "Size")
    assert size_pv["values"] == ["2X"]
    assert size_pv["property_id"] == em._ETSY_SHIRT_SIZE_PROPERTY_ID
    assert size_pv["scale_id"] == em._ETSY_SHIRT_SIZE_SCALE_ID

    color_pv = next(pv for pv in p["property_values"] if "color" in pv["property_name"].lower())
    assert color_pv["property_id"] == em._ETSY_COLOR_PROPERTY_ID  # real enum, no collision for t-shirt
    assert color_pv["values"] == ["White"]

    # every offering must carry a real readiness_state_id -- confirmed live
    # this is required or Etsy 400s with "All offerings need readiness state".
    assert all(off.get("readiness_state_id") is not None for prod in products for off in prod["offerings"])

    # every sku must be unique and every signature distinct (no duplicate variations).
    sigs = {tuple(sorted((pv["property_id"], tuple(pv["values"])) for pv in p["property_values"])) for p in products}
    assert len(sigs) == 10


def test_cap_colors_with_no_exact_etsy_match_fall_back_to_nearest_generic_bucket(monkeypatch):
    _patch_get_variants(monkeypatch)
    catalog = NICHE_CATALOG_MAP["Christian Faith Baseball Caps"]
    products = em._build_inventory_products(_product("Christian Faith Baseball Caps - test", "cap"), catalog, 24.99)

    assert products is not None and len(products) == 6
    colors = {p["sku"]: next(pv["values"][0] for pv in p["property_values"]) for p in products}
    # Khaki/Dark Green/Dark Navy have no exact Etsy generic-color match --
    # confirmed mapped to the nearest real bucket, not dropped.
    assert colors["82433"] == "Beige"   # Khaki -> Beige
    assert colors["104279"] == "Green"  # Dark Green -> Green
    assert colors["104280"] == "Blue"   # Dark Navy -> Blue
    assert colors["82434"] == "White"
    assert colors["104278"] == "Black"
    assert colors["104282"] == "Red"
    # cap is a single real size ("One size") -- no Size property should be sent at all.
    assert all(not any(pv["property_name"] == "Size" for pv in p["property_values"]) for p in products)


def test_notebook_color_collision_falls_back_to_real_literal_names(monkeypatch):
    """The real bug this caught before it ever reached a live listing:
    Blue/Navy/Turquoise would all collapse into Etsy's single generic
    "Blue" bucket, making 3 of 8 real distinct colors indistinguishable --
    Etsy would likely reject that as duplicate variations. Must fall back
    to the real literal Printify color name as free text for the WHOLE
    product once any collision is detected, not a per-variant mix."""
    _patch_get_variants(monkeypatch)
    catalog = NICHE_CATALOG_MAP["Daily Gratitude Journal Notebooks"]
    products = em._build_inventory_products(_product("Daily Gratitude Journal Notebooks - test", "notebook"), catalog, 15.99)

    assert products is not None and len(products) == 8
    colors = {p["sku"]: p["property_values"][0] for p in products}
    # all 8 must use the free-text Custom2 property, not the lossy enum.
    assert all(pv["property_id"] == em._ETSY_CUSTOM_COLOR_PROPERTY_ID for pv in colors.values())
    names = {sku: pv["values"][0] for sku, pv in colors.items()}
    assert names["119670"] == "Blue"
    assert names["119672"] == "Navy"
    assert names["119676"] == "Turquoise"
    assert len(set(names.values())) == 8  # every real color stays distinguishable


def test_single_real_variant_product_returns_none(monkeypatch):
    """Mug/necklace/tumbler have exactly one real Printify variant -- there
    is nothing for a buyer to choose, so no inventory call should be made
    at all (the listing's existing default price/quantity already
    correctly represents the one real option)."""
    _patch_get_variants(monkeypatch)
    catalog = NICHE_CATALOG_MAP["Scripture Verse Coffee Mugs"]
    products = em._build_inventory_products(_product("Scripture Verse Coffee Mugs - test", "mug"), catalog, 14.99)
    assert products is None


def test_sku_on_property_reflects_actual_properties_used():
    tshirt_products = [
        {"sku": "1", "property_values": [
            {"property_id": 200, "values": ["White"]},
            {"property_id": em._ETSY_SHIRT_SIZE_PROPERTY_ID, "values": ["S"]},
        ]},
    ]
    assert em._sku_on_property(tshirt_products) == sorted([200, em._ETSY_SHIRT_SIZE_PROPERTY_ID])

    custom_color_products = [
        {"sku": "1", "property_values": [{"property_id": em._ETSY_CUSTOM_COLOR_PROPERTY_ID, "values": ["Navy"]}]},
    ]
    assert em._sku_on_property(custom_color_products) == [em._ETSY_CUSTOM_COLOR_PROPERTY_ID]


def test_normalize_shirt_size_handles_plain_and_printify_style_names():
    assert em._normalize_shirt_size("S") == "S"
    assert em._normalize_shirt_size("xl") == "XL"
    assert em._normalize_shirt_size("2XL") == "2X"
    assert em._normalize_shirt_size("3XL") == "3X"
    assert em._normalize_shirt_size("not a real size") is None
