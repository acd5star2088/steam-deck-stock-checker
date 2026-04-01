import requests
import os
import sys
import time
from datetime import datetime, timezone


# ─── Valve's Physical Goods Inventory API ───────────────────────────────
API_URL = (
    "https://api.steampowered.com/IPhysicalGoodsService"
    "/CheckInventoryAvailableByPackage/v1"
)

COUNTRY_CODE = "US"
STORE_URL = "https://store.steampowered.com/steamdeck"
REQUEST_DELAY = 1.5

# ─── Known Steam Deck Packages (NA Region) ──────────────────────────────
# Source: steamdb.info/app/1675200/subs/
# To add a future model:
#   1. Go to https://steamdb.info/app/1675200/subs/
#   2. Find the new SubID for the NA variant
#   3. Add it below
#
PACKAGES = {
    # ── New (Retail) ─────────────────────────────────────────────────────
    946113:  {"name": "Steam Deck OLED 512GB",                "type": "New"},
    946114:  {"name": "Steam Deck OLED 1TB",                  "type": "New"},
    946453:  {"name": "Steam Deck OLED Limited Edition 1TB",  "type": "New"},

    # ── Discontinued (will not restock, tracked for completeness) ────────
    595603:  {"name": "Steam Deck LCD 64GB",                  "type": "Discontinued"},
    595604:  {"name": "Steam Deck LCD 256GB",                 "type": "Discontinued"},

    # ── Valve Certified Refurbished ──────────────────────────────────────
    903905:  {"name": "Steam Deck LCD 64GB (Refurbished)",    "type": "Refurbished"},
    903906:  {"name": "Steam Deck LCD 256GB (Refurbished)",   "type": "Refurbished"},
    903907:  {"name": "Steam Deck LCD 512GB (Refurbished)",   "type": "Refurbished"},
    1202542: {"name": "Steam Deck OLED 512GB (Refurbished)",  "type": "Refurbished"},
    1202547: {"name": "Steam Deck OLED 1TB (Refurbished)",    "type": "Refurbished"},
}

DEBUG = "--debug" in sys.argv


def debug(msg):
    if DEBUG:
        print(f"  [DEBUG] {msg}")


def check_package(package_id: int) -> bool:
    """Query Valve's API for a single package's availability in the US."""
    params = {
        "origin": "https://store.steampowered.com",
        "country_code": COUNTRY_CODE,
        "packageid": package_id,
    }
    resp = requests.get(API_URL, params=params, timeout=15)
    resp.raise_for_status()

    debug(f"Package {package_id} — HTTP {resp.status_code}")
    debug(f"  Content-Type: {resp.headers.get('Content-Type', 'unknown')}")
    debug(f"  Raw bytes ({len(resp.content)}): {resp.content[:200]}")

    content_type = resp.headers.get("Content-Type", "")

    # ── Try JSON first ───────────────────────────────────────────────────
    if "json" in content_type or resp.content.startswith(b"{"):
        try:
            data = resp.json()
            debug(f"  Parsed JSON: {data}")
            response = data.get("response", {})

            # When unavailable, Valve returns {"response": {}} (empty obj)
            # When available: {"response": {"inventory_available": 1, ...}}
            inventory = response.get("inventory_available")
            if inventory is None:
                debug(f"  'inventory_available' key MISSING → Out of Stock")
                return False

            result = bool(int(inventory))
            debug(f"  inventory_available={inventory} → {'IN STOCK' if result else 'Out of Stock'}")
            return result

        except (ValueError, KeyError, TypeError) as e:
            debug(f"  JSON parse error: {e}")
            # Fall through to protobuf check

    # ── Protobuf fallback ────────────────────────────────────────────────
    # In protobuf, field 1 (inventory_available) as varint:
    #   \x08\x01 = true (available)
    #   \x08\x00 = false (not available)
    # An empty response body also means not available.
    debug(f"  Trying protobuf parse...")
    raw = resp.content

    if len(raw) == 0:
        debug(f"  Empty response → Out of Stock")
        return False

    # Look for field 1 = 1 (available)
    if b"\x08\x01" in raw:
        debug(f"  Found \\x08\\x01 in protobuf → IN STOCK")
        return True

    debug(f"  No availability signal in protobuf → Out of Stock")
    return False


def check_all_packages():
    """Check every known NA Steam Deck package and return results."""
    results = []
    for pkg_id, info in PACKAGES.items():
        try:
            available = check_package(pkg_id)
            status = "IN STOCK" if available else "Out of Stock"
        except requests.exceptions.HTTPError as e:
            status = f"HTTP Error ({e.response.status_code})"
            debug(f"  HTTP error for {pkg_id}: {e}")
        except Exception as e:
            status = f"Error ({e})"
            debug(f"  Exception for {pkg_id}: {e}")

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
        header = "📋 **Steam Deck Stock Check (US) — All Out of Stock**"

    lines = [header, ""]

    type_order = ["New", "Refurbished", "Discontinued"]
    type_labels = {
        "New":          "🆕 **New (Retail)**",
        "Refurbished":  "🔄 **Valve Certified Refurbished**",
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
    print(f"Debug:  {'ON' if DEBUG else 'OFF (use --debug to enable)'}")
    print(f"{'─' * 60}\n")

    try:
        results, any_in_stock = check_all_packages()
    except Exception as e:
        error_msg = f"Fatal error during stock check: {e}"
        print(error_msg)
        if webhook_url:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            send_discord(webhook_url, f"⚠️ **Stock check failed!**\nError: {e}\n🕐 {ts}")
        sys.exit(1)

    print(f"\n{'─' * 60}")
    in_stock = [r for r in results if r["status"] == "IN STOCK"]
    out_of_stock = [r for r in results if r["status"] == "Out of Stock"]
    errors = [r for r in results if r["status"] not in ("IN STOCK", "Out of Stock")]

    print(f"Summary: {len(in_stock)} in stock, {len(out_of_stock)} out of stock, {len(errors)} errors")

    if in_stock:
        print("\n🟢 IN STOCK:")
        for m in in_stock:
            print(f"   → {m['name']}")
    else:
        print("\n🔴 All models out of stock.")

    if errors:
        print("\n🟡 ERRORS:")
        for m in errors:
            print(f"   → {m['name']}: {m['status']}")

    if webhook_url:
        message = build_discord_message(results, any_in_stock)
        send_discord(webhook_url, message)
    else:
        print("\nNo DISCORD_WEBHOOK_URL set — skipping Discord notification.")


if __name__ == "__main__":
    main()
