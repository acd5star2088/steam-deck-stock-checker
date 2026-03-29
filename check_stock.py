import requests
import os
import sys
from datetime import datetime, timezone


STEAM_DECK_URL = "https://store.steampowered.com/steamdeck"

# Models to look for on the page — add or remove as Valve updates the lineup
KNOWN_MODELS = [
    "Steam Deck OLED 512GB",
    "Steam Deck OLED 1TB",
    "Steam Deck OLED Limited Edition",
    "Steam Deck LCD",
    "Steam Deck 256GB",
    "Steam Deck 512GB",
    "Steam Deck 64GB",
]

OOS_SIGNALS = ["out of stock", "sold out", "currently unavailable"]
IS_SIGNALS = ["add to cart", "add to bag", "order now", "buy now"]


def fetch_page():
    """Fetch the Steam Deck store page."""
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
    html = response.text
    html_lower = html.lower()

    if "steam deck" not in html_lower:
        raise Exception(
            f"Page doesn't contain expected Steam Deck content. "
            f"Status: {response.status_code}, Length: {len(html)}"
        )

    print(f"Page loaded successfully: {len(html)} characters")
    return html, html_lower


def determine_model_status(html_lower, model_name):
    """Check surrounding context around a model name to guess its stock status."""
    model_lower = model_name.lower()
    idx = html_lower.find(model_lower)
    if idx == -1:
        return None  # Model not found on page

    # Grab a window of text around the model name for context
    context = html_lower[max(0, idx - 500): idx + 500]

    has_oos = any(s in context for s in OOS_SIGNALS)
    has_is = any(s in context for s in IS_SIGNALS)

    if has_is and not has_oos:
        return "IN STOCK"
    elif has_oos:
        return "Out of Stock"
    else:
        return "Unknown"


def check_stock():
    """Analyze stock status for all detectable Steam Deck models."""
    html, html_lower = fetch_page()

    # Page-wide signal detection for logging
    found_oos = [s for s in OOS_SIGNALS if s in html_lower]
    found_is = [s for s in IS_SIGNALS if s in html_lower]
    print(f"Page-wide out-of-stock signals: {found_oos if found_oos else 'none'}")
    print(f"Page-wide in-stock signals:     {found_is if found_is else 'none'}")

    # Per-model detection
    models = []
    for model_name in KNOWN_MODELS:
        status = determine_model_status(html_lower, model_name)
        if status is not None:
            models.append({"name": model_name, "status": status})

    # Fallback: if no individual models were found, report on the page as a whole
    if not models:
        if found_is and not found_oos:
            fallback_status = "IN STOCK"
        elif found_oos:
            fallback_status = "Out of Stock"
        else:
            fallback_status = "Unknown"
        models.append({"name": "Steam Deck (all models)", "status": fallback_status})

    any_in_stock = any(m["status"] == "IN STOCK" for m in models)
    return models, any_in_stock


def build_discord_message(models, any_in_stock):
    """Build the Discord message body."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if any_in_stock:
        header = "@everyone 🚨 **STEAM DECK IN STOCK ALERT!** 🚨"
    else:
        header = "📋 **Steam Deck Stock Check — No Changes**"

    lines = [header, ""]

    for m in models:
        if m["status"] == "IN STOCK":
            emoji = "🟢"
        elif m["status"] == "Out of Stock":
            emoji = "🔴"
        else:
            emoji = "🟡"
        lines.append(f"{emoji} **{m['name']}**: {m['status']}")

    lines.append("")
    lines.append(f"🔗 https://store.steampowered.com/steamdeck")
    lines.append(f"🕐 {timestamp}")

    if any_in_stock:
        lines.append("\n⚡ **GO GO GO!**")

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

    try:
        models, any_in_stock = check_stock()
    except Exception as e:
        error_msg = f"Failed to check stock: {e}"
        print(error_msg)
        if webhook_url:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            error_discord = (
                f"⚠️ **Stock check failed!**\n"
                f"Error: {e}\n"
                f"🕐 {timestamp}"
            )
            try:
                send_discord(webhook_url, error_discord)
            except Exception as de:
                print(f"Also failed to send error to Discord: {de}")
        sys.exit(1)

    print("\n--- Results ---")
    for m in models:
        print(f"  {m['name']}: {m['status']}")
    print(f"  Any in stock: {any_in_stock}")

    if webhook_url:
        message = build_discord_message(models, any_in_stock)
        send_discord(webhook_url, message)
    else:
        print("No DISCORD_WEBHOOK_URL set — skipping Discord notification.")


if __name__ == "__main__":
    main()
