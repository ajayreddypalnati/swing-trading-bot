import json
import re
import time
import pandas as pd
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

MOMO_HEALTH_URL = "https://momoindiascreener.in/market-health"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def scrape_nifty_total_market_breadth():
    print("\n📊 STEP 1: Starting Momo India Screener Test Scraper...")

    series_names = {
        "aboveMa200": "% Above 200-day MA",
        "aboveMa100": "% Above 100-day MA",
        "aboveMa50": "% Above 50-day MA",
        "aboveMa20": "% Above 20-day MA",
        "returnsAboveZero": "% 1Y Return > 0%",
        "returnsAboveTen": "% 1Y Return > 10%",
        "returnsAboveHundred": "% 1Y Return > 100%",
        "withinTenOfAth": "% Within 10% of ATH",
        "withinTwentyOfAth": "% Within 20% of ATH",
        "withinThirtyOfAth": "% Within 30% of ATH",
    }

    try:
        # NEW V2 SYNTAX: Wrap sync_playwright with Stealth().use_sync()
        with Stealth().use_sync(sync_playwright()) as p:
            print("🤖 Launching Chromium browser with headless stealth settings...")
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox"
                ]
            )
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1920, "height": 1080}
            )
            
            # Stealth is now automatically applied to this page context
            page = context.new_page()

            captured_responses = []

            def handle_response(response):
                try:
                    text = response.text()
                    if ("aboveMa200" in text and "aboveMa100" in text and "returnsAboveZero" in text):
                        captured_responses.append(text)
                except Exception:
                    pass

            page.on("response", handle_response)
            print(f"🌐 Navigating to {MOMO_HEALTH_URL}...")
            page.goto(MOMO_HEALTH_URL, wait_until="domcontentloaded", timeout=120000)
            time.sleep(5)

            selectors = [
                'text="nifty-allcap"',
                '[href*="nifty-allcap"]',
                'button:has-text("nifty-allcap")',
                'a:has-text("nifty-allcap")',
            ]

            clicked = False
            print("🖱️ Attempting to click 'nifty-allcap' button...")
            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if element.count() > 0:
                        element.click()
                        clicked = True
                        print(f"   ✅ Clicked using selector: {selector}")
                        break
                except Exception:
                    pass

            if not clicked:
                browser.close()
                raise Exception("Could not find or select 'nifty-allcap' button.")

            time.sleep(5)
            browser.close()

            if not captured_responses:
                raise Exception("No Market Health response captured from network traffic.")

            print("📦 Parsing captured network response JSON...")
            json_text = captured_responses[-1]

            all_data = {}
            for json_key, excel_name in series_names.items():
                pattern = rf'"{json_key}"\s*:\s*(\[[\s\S]*?\])'
                match = re.search(pattern, json_text)
                if not match:
                    continue

                try:
                    data = json.loads(match.group(1))
                    for item in data:
                        date = item.get("time")
                        value = item.get("value")
                        if not date:
                            continue
                        if date not in all_data:
                            all_data[date] = {}
                        all_data[date][excel_name] = value
                except Exception as e:
                    print(f"   ⚠️ ERROR parsing key {json_key}: {e}")

            if not all_data:
                raise Exception("No historical data records could be parsed.")

            rows = []
            for date, values in all_data.items():
                row = {"Date": date}
                row.update(values)
                rows.append(row)

            df = pd.DataFrame(rows)
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"]).sort_values("Date", ascending=False)

            columns = [
                "Date",
                "% Above 200-day MA",
                "% Above 100-day MA",
                "% Above 50-day MA",
                "% Above 20-day MA",
                "% 1Y Return > 0%",
                "% 1Y Return > 10%",
                "% 1Y Return > 100%",
                "% Within 10% of ATH",
                "% Within 20% of ATH",
                "% Within 30% of ATH",
            ]

            for col in columns:
                if col not in df.columns:
                    df[col] = None

            df = df[columns]
            df["Date"] = df["Date"].dt.strftime('%Y-%m-%d')

            print("\n" + "="*60)
            print("🎉 SUCCESS! Momo India Screener extracted successfully:")
            print("="*60)
            print(df.head(10).to_string(index=False))
            print(f"\nTotal Records Extracted: {len(df)}")
            return df

    except Exception as e:
        print(f"\n❌ FATAL SCRAPER ERROR: {e}")
        raise e

if __name__ == "__main__":
    scrape_nifty_total_market_breadth()
