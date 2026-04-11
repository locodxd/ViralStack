"""
Export TikTok cookies for automation.
Run: python scripts/export_cookies.py

How to get TikTok cookies:
1. Install the "EditThisCookie" or "Cookie-Editor" browser extension
2. Log into TikTok on your browser
3. Export cookies as JSON using the extension
4. Paste the JSON when prompted by this script

Alternatively, use the manual method:
1. Open DevTools (F12) > Application > Cookies
2. Copy the relevant cookies (sessionid, sid_tt, etc.)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

COOKIES_DIR = Path(__file__).resolve().parent.parent / "storage" / "cookies"
ACCOUNTS = ["terror", "historias", "dinero"]


def export_cookies():
    print("=" * 50)
    print("TikTok Cookie Export")
    print("=" * 50)
    print("\nThis script helps you save TikTok login cookies for each account.")
    print("You need to log into each TikTok account in your browser,")
    print("export the cookies using a browser extension, and paste them here.\n")

    COOKIES_DIR.mkdir(parents=True, exist_ok=True)

    for account in ACCOUNTS:
        cookie_file = COOKIES_DIR / f"{account}_cookies.txt"

        if cookie_file.exists():
            overwrite = input(f"Cookies for '{account}' already exist. Overwrite? (y/n): ")
            if overwrite.lower() != "y":
                continue

        print(f"\n--- Account: {account.upper()} ---")
        print("1. Log into the TikTok account for this niche in your browser")
        print("2. Use a cookie extension to export cookies as JSON")
        print("3. Paste the JSON below (then press Enter twice):")

        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)

        if not lines:
            print(f"Skipped {account}")
            continue

        cookie_text = "\n".join(lines)

        try:
            # Validate it's proper JSON
            cookies = json.loads(cookie_text)

            # Convert to Netscape cookie format for tiktok-uploader
            netscape_lines = ["# Netscape HTTP Cookie File"]
            for cookie in cookies:
                domain = cookie.get("domain", ".tiktok.com")
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                path = cookie.get("path", "/")
                secure = "TRUE" if cookie.get("secure", False) else "FALSE"
                expiry = str(int(cookie.get("expirationDate", 0)))
                name = cookie.get("name", "")
                value = cookie.get("value", "")

                netscape_lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")

            cookie_file.write_text("\n".join(netscape_lines), encoding="utf-8")
            print(f"Saved {len(cookies)} cookies to: {cookie_file}")

        except json.JSONDecodeError:
            # Might already be in Netscape format
            cookie_file.write_text(cookie_text, encoding="utf-8")
            print(f"Saved raw cookies to: {cookie_file}")

    print("\nDone! Cookies saved for TikTok automation.")
    print("Note: Cookies expire periodically. Re-run this script when uploads fail due to auth.")


if __name__ == "__main__":
    export_cookies()
