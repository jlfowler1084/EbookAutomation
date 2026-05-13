"""One-shot Stripe bootstrap script — create Products and Prices for Leafbind token packs.

Idempotent: searches for existing Products by name and Prices by unit_amount before
creating. Safe to run multiple times. Prints resulting Price IDs in .env-paste-ready
format.

Usage:
    STRIPE_SECRET_KEY=sk_test_xxx python deploy/stripe_bootstrap.py
    STRIPE_SECRET_KEY=sk_live_xxx python deploy/stripe_bootstrap.py --dry-run

Compatible with Stripe SDK v12.x (stripe~=12.5).

Pack definitions:
    - Starter:  $2.99  /  3 credits  (300 cents)
    - Standard: $7.99  / 10 credits  (799 cents)
    - Power:    $14.99 / 25 credits  (1499 cents)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pack definitions
# ---------------------------------------------------------------------------

_PACKS = [
    {
        "env_key": "STRIPE_PRICE_STARTER",
        "product_name": "Leafbind Starter Pack",
        "product_description": "3 premium ebook conversion credits (KFX output).",
        "unit_amount": 299,      # $2.99 in cents
        "currency": "usd",
        "credits": 3,
    },
    {
        "env_key": "STRIPE_PRICE_STANDARD",
        "product_name": "Leafbind Standard Pack",
        "product_description": "10 premium ebook conversion credits (KFX output).",
        "unit_amount": 799,      # $7.99 in cents
        "currency": "usd",
        "credits": 10,
    },
    {
        "env_key": "STRIPE_PRICE_POWER",
        "product_name": "Leafbind Power Pack",
        "product_description": "25 premium ebook conversion credits (KFX output).",
        "unit_amount": 1499,     # $14.99 in cents
        "currency": "usd",
        "credits": 25,
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_product(stripe_mod, name: str):
    """Return the first active Stripe Product matching *name*, or None."""
    page = stripe_mod.Product.list(limit=100)
    for product in page.auto_paging_iter():
        if product.name == name and product.active:
            log.debug("Found existing product: %s (id=%s)", name, product.id)
            return product
    return None


def _find_price(stripe_mod, product_id: str, unit_amount: int, currency: str):
    """Return the first active Stripe Price matching product + amount + currency, or None."""
    page = stripe_mod.Price.list(product=product_id, limit=100)
    for price in page.auto_paging_iter():
        if (
            price.unit_amount == unit_amount
            and price.currency == currency
            and price.active
        ):
            log.debug(
                "Found existing price: %s/%s cents (id=%s)",
                currency,
                unit_amount,
                price.id,
            )
            return price
    return None


def _bootstrap_pack(stripe_mod, pack: dict, dry_run: bool) -> str:
    """Ensure Product + Price exist for *pack*. Returns the Price ID."""
    name = pack["product_name"]
    unit_amount = pack["unit_amount"]
    currency = pack["currency"]

    # --- Product ---
    product = _find_product(stripe_mod, name)
    if product is None:
        if dry_run:
            log.info("[DRY RUN] Would create Product: %r", name)
            return "price_DRY_RUN"
        product = stripe_mod.Product.create(
            name=name,
            description=pack["product_description"],
        )
        log.info("Created Product: %r (id=%s)", name, product.id)
    else:
        log.info("Product already exists: %r (id=%s)", name, product.id)

    # --- Price ---
    price = _find_price(stripe_mod, product.id, unit_amount, currency)
    if price is None:
        if dry_run:
            log.info(
                "[DRY RUN] Would create Price: %s %s cents for product %s",
                currency,
                unit_amount,
                product.id,
            )
            return "price_DRY_RUN"
        price = stripe_mod.Price.create(
            product=product.id,
            unit_amount=unit_amount,
            currency=currency,
            # tax_behavior=exclusive: operator adds tax on top. Can be changed
            # to "inclusive" via the Stripe Dashboard after bootstrap.
            tax_behavior="exclusive",
        )
        log.info(
            "Created Price: %s %s cents (id=%s) for %r",
            currency,
            unit_amount,
            price.id,
            name,
        )
    else:
        log.info(
            "Price already exists: %s %s cents (id=%s) for %r",
            currency,
            unit_amount,
            price.id,
            name,
        )

    return price.id


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Bootstrap Stripe Products and Prices for Leafbind token packs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print what would be created without making any Stripe API calls. "
            "Products/Prices are still listed to detect existing resources."
        ),
    )
    args = parser.parse_args()

    secret_key = os.environ.get("STRIPE_SECRET_KEY")
    if not secret_key:
        log.error("STRIPE_SECRET_KEY environment variable is not set.")
        return 1

    try:
        import stripe as stripe_mod
    except ImportError:
        log.error("stripe package is not installed. Run: pip install stripe~=12.5")
        return 1

    stripe_mod.api_key = secret_key

    if args.dry_run:
        log.info("--- DRY RUN MODE: no Stripe API write calls will be made ---")

    results: dict[str, str] = {}
    for pack in _PACKS:
        try:
            price_id = _bootstrap_pack(stripe_mod, pack, dry_run=args.dry_run)
            results[pack["env_key"]] = price_id
        except stripe_mod.error.StripeError as exc:
            log.error("Stripe API error for pack %r: %s", pack["product_name"], exc)
            return 1

    # Print .env-paste-ready output
    print()
    print("# --- Paste the following into your .env file ---")
    for env_key, price_id in results.items():
        print(f"{env_key}={price_id}")
    print("# ------------------------------------------------")

    return 0


if __name__ == "__main__":
    sys.exit(main())
