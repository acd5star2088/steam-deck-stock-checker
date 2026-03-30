import requests
import os
import sys
import time
from datetime import datetime, timezone


# ─── Valve's Physical Goods Inventory API ───────────────────────────────
# This is the same API that store.steampowered.com/steamdeck calls internally.
# No HTML scraping needed — we get definitive stock data straight from Valve.
API_URL = (
    "https://api.steampowered.com/IPhysicalGoodsService"
    "/CheckInventoryAvailableByPackage/v1"
)

COUNTRY_CODE = "US"                          # North America / United States
STORE_URL = "https://store.steampowered.com/steamdeck"
REQUEST_DELAY = 1.5                          # seconds between API calls (be polite)

# ─── Known Steam Deck Packages (NA Region) ──────────────────────────────
# Source: steamdb.info/app/1675200/subs/
# To add a future model:
#   1. Go to https://steamdb.info/app/1675200/subs/
#   2. Find the new SubID for the NA variant (not "w/o PSU" — that's non-NA)
#   3. Add it below
#
PACKAGES = {
    # ── New (Retail) ─────────────────────────────────────────────────────
    946113:  {"name": "Steam Deck OLED 512GB",               "type": "New"},
    946114:  {"name": "Steam Deck OLED 1TB",                 "type": "New"},
    946453:  {"name": "Steam Deck OLED Limited Edition 1TB",  "type": "New"},

    # ── Discontinued (will not restock, but tracked for completeness) ───
    595603:  {"name": "Steam Deck LCD 64GB",                 "type": "Discontinued"},
    595604:  {"name": "Steam Deck LCD 256GB",                "type": "Discontinued"},
    595605:  {"name": "Steam Deck LCD 512GB",                "type": "Discontinued"},

    # ── Valve Certified Refurbished ──────────────────────────────────────
    903905:  {"name": "Steam Deck LCD 64GB (Refurbished)",    "type": "Refurbished"},
    903906:  {"name": "Steam Deck LCD 256GB (Refurbished)",   "type": "Refurbished"},
    903907:  {"name": "Steam Deck LCD 512GB (Refurbished)",   "type": "Refurbished"},
    1202542: {"name": "Steam Deck OLED 512GB (Refurbished)",  "type": "Refurbished"},
    1202547: {"name": "Steam Deck OLED 1TB (Refurbished)",    "type": "Refurbished"},
}

# Protobuf response when a package is NOT available
NOT_AVAILABLE = b"\x08\x00\x10\x00"


def check_package(package_id: int) -> bool:
    """Query Valve's API for a single package's availability in the US."""
    params = {
        "origin": "https://store.steampowered.com",
        "country_code": COUNTRY_CODE,
        "packageid": package_id,
    }
    resp = requests.get(API_URL, params=params, timeout=15)
    resp.raise_for_status()

    # The API returns a small protobuf blob.
    # b'\x08\x00\x10\x00' == not available; anything else == available.
    return resp.content != NOT_AVAILABLE


def check_all_packages():
    """Check every known NA Steam Deck package and return results."""
    results = []
    for pkg_id, info in PACKAGES.items():
        try:
            available = check_package(pkg_id)
            status = "IN STOCK" if available else "Out of Stock"
        except Exception as e:
            status = f"Error ({e})"

        results.append({
            "id": pkg_id,
            "name": info["name"],
            "type": info["type"],
            "status": status,
        })
        print(f"  [{pkg_id}] {info['name']}: {status}")
        time.sleep(REQUEST_DELAY)

    any_in_stock = any(r["status"] == "IN STOCK" for r in results)
    return results, any_in_stock


def build_discord_message(results, any_in_stock):
    """Build a Discord-formatted message grouped by model type."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if any_in_stock:
        header = "@everyone 🚨 **STEAM DECK IN STOCK (US)!** 🚨"
    else:
        header = "📋 **Steam Deck Stock Check (US) — No Change**"

    lines = [header, ""]

    # Group by type
    type_order = ["New", "Refurbished", "Discontinued"]
    type_labels = {
        "New": "🆕 **New (Retail)**",
        "Refurbished": "🔄 **Valve Certified Refurbished**",
        "Discontinued": "🚫 **Discontinued (LCD)**",
    }

    for t in type_order:
        group = [r for r in results if r["type"] == t]
        if not group:
            continue

        lines.append(type_labels[t])
        for m in group:
            if m["status"] == "IN STOCK":
                emoji = "🟢"
            elif m["status"] == "Out of Stock":
                emoji = "🔴"
            else:
                emoji = "🟡"
            lines.append(f"  {emoji} {m['name']}: **{m['status']}**")
        lines.append("")

    lines.append(f"🔗 {STORE_URL}")
    lines.append(f"🕐 {timestamp}")
    lines.append(f"📡 Source: Valve `IPhysicalGoodsService` API · Region: `{COUNTRY_CODE}`")

    if any_in_stock:
        lines.append("\n⚡ **GO GO GO — BUY NOW!** ⚡")

    return "\n".join(lines)


def send_discord(webhook_url, message):
    """Send a message to Discord via webhook."""
    payload = {
        "content": message,
        "username": "Steam Deck Stock Bot",
    }
    r = requests.post(webhook_url, json=payload, timeout=10)
    r.raise_for_status()
    print("Discord notification sent!")


def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")

    print(f"Steam Deck Stock Checker")
    print(f"Region: {COUNTRY_CODE}")
    print(f"API:    {API_URL}")
    print(f"Models: {len(PACKAGES)}")
    print(f"{'─' * 50}\n")

    try:
        results, any_in_stock = check_all_packages()
    except Exception as e:
        error_msg = f"Fatal error during stock check: {e}"
        print(error_msg)
        if webhook_url:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            send_discord(webhook_url, f"⚠️ **Stock check failed!**\nError: {e}\n🕐 {ts}")
        sys.exit(1)

    print(f"\n{'─' * 50}")
    in_stock_models = [r for r in results if r["status"] == "IN STOCK"]
    if in_stock_models:
        print("🟢 IN STOCK:")
        for m in in_stock_models:
            print(f"   → {m['name']}")
    else:
        print("All models out of stock.")

    if webhook_url:
        message = build_discord_message(results, any_in_stock)
        send_discord(webhook_url, message)
    else:
        print("\nNo DISCORD_WEBHOOK_URL set — skipping Discord notification.")


if __name__ == "__main__":
    main()
