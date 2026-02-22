import requests
import os
import sys


STEAM_DECK_URL = "https://store.steampowered.com/steamdeck"


def check_stock():
    """Fetch the Steam Deck page and look for stock indicators."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    }

    response = requests.get(STEAM_DECK_URL, headers=headers, timeout=30)
    response.raise_for_status()
    html = response.text.lower()

    # Sanity check — did we actually load the Steam Deck page?
    if "steam deck" not in html:
        print("ERROR: Page doesn't contain expected Steam Deck content.")
        print(f"Status code: {response.status_code}")
        print(f"Page length: {len(html)} characters")
        sys.exit(1)

    # Keywords that indicate OUT of stock
    oos_signals = ["out of stock", "sold out", "currently unavailable"]
    # Keywords that indicate IN stock
    is_signals = ["add to cart", "add to bag", "order now", "buy now"]

    found_oos = [s for s in oos_signals if s in html]
    found_is = [s for s in is_signals if s in html]

    print(f"Page loaded successfully: {len(html)} characters")
    print(f"Out-of-stock matches: {found_oos if found_oos else 'none'}")
    print(f"In-stock matches:     {found_is if found_is else 'none'}")

    # Alert only if we see purchase language AND no out-of-stock language
    if found_is and not found_oos:
        return True
    return False


def send_discord(webhook_url):
    """Send a notification to Discord via webhook."""
    payload = {
        "content": (
            "🚨 **STEAM DECK OLED MAY BE BACK IN STOCK!** 🚨\n\n"
            "👉 https://store.steampowered.com/steamdeck\n\n"
            "_Automated alert — verify before celebrating!_"
        ),
        "username": "Steam Deck Stock Bot",
    }
    r = requests.post(webhook_url, json=payload, timeout=10)
    r.raise_for_status()
    print("Discord notification sent!")


def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")

    try:
        in_stock = check_stock()
    except Exception as e:
        print(f"Failed to check stock: {e}")
        sys.exit(1)

    if in_stock:
        print("🟢 IN STOCK DETECTED!")
        if webhook_url:
            send_discord(webhook_url)
        else:
            print("No DISCORD_WEBHOOK_URL set — skipping notification.")
    else:
        print("🔴 Still out of stock. Will check again next run.")


if __name__ == "__main__":
    main()
