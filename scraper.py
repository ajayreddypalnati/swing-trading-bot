import requests
import time
import random
import re
import pandas as pd
import numpy as np
import io  
import os
import sys
import warnings
from bs4 import BeautifulSoup
from sqlalchemy import create_engine
from sqlalchemy import text
from playwright.sync_api import sync_playwright
from tvDatafeed import TvDatafeed, Interval

# Force unbuffered output so execution logs write instantly to Windows command prompt
sys.stdout.reconfigure(line_buffering=True)
warnings.simplefilter(action='ignore', category=FutureWarning)

# ==========================================
# 0. CREDENTIALS & DATABASE CONFIG
# ==========================================
SCREENER_EMAIL = "ajayreddypalnati@gmail.com"
SCREENER_PASSWORD = "sunnyreddi999@AA"

# Microcap Screener Credentials
MICROCAP_EMAIL = "ajayreddy5654@gmail.com"
MICROCAP_PASSWORD = "ajayreddi999@AA"

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("\n❌ FATAL ERROR: DATABASE_URL environment variable is missing on this machine.")
    sys.exit(1)

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

if "?pgbouncer=true" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("?pgbouncer=true", "")

try:
    print("\n🔌 SYSTEM: Connecting to Supabase Cloud Database...")
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)
    print("✅ SYSTEM: Database connection established successfully.")
except Exception as e:
    print(f"❌ FATAL ERROR: Could not connect to database: {e}")
    sys.exit(1)

SCREENER_URL = "https://www.screener.in/screens/3299871/all-screener-stocks/"
MICROCAP_URL = "https://www.screener.in/company/NFMICRO250/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def random_sleep(min_ms=800, max_ms=2000):
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

def fetch_with_retry(session, url, referer_url=None, retries=3):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Cookie": getattr(session, 'screener_cookies', '')
    }
    if referer_url: headers["Referer"] = referer_url
        
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=headers, timeout=15)
            if resp.status_code == 200: return resp.text
            elif resp.status_code == 429:
                print(f"   ⚠️ WARNING: Rate limited by Screener (429). Pausing for 15 seconds...")
                time.sleep(15)
        except Exception:
            pass
        random_sleep(1500, 3500)
    return None

def save_db_with_retry(df, table_name, engine, if_exists="replace", index=False, chunksize=None, method=None):
    """Saves DataFrame to Supabase with an automatic 3-attempt retry loop."""
    for attempt in range(1, 4):
        try:
            df.to_sql(table_name, engine, if_exists=if_exists, index=index, chunksize=chunksize, method=method)
            return True
        except Exception as e:
            print(f"   ⚠️ Database write failed for {table_name} (Attempt {attempt}/3): {e}")
            if attempt < 3: time.sleep(5)
    raise Exception(f"Failed to save {table_name} to database after 3 attempts.")

def log_sync_status(engine, status="SUCCESS", failed_module="None"):
    """Logs the script status and failing module to the sync_log table."""
    timestamp_string = pd.Timestamp.now(tz='Asia/Kolkata').strftime('%d %b %Y, %I:%M %p')
    sync_df = pd.DataFrame([{
        "last_sync": timestamp_string,
        "status": status,
        "failed_module": failed_module
    }])
    try:
        for _ in range(3):
            try:
                sync_df.to_sql("sync_log", engine, if_exists="replace", index=False)
                break
            except Exception:
                time.sleep(3)
    except Exception:
        print("   ⚠️ WARNING: Could not update sync_log table.")

# ==========================================
# 1. AUTO-LOGIN FUNCTION (PLAYWRIGHT)
# ==========================================
def get_fresh_screener_cookies(email, password):
    print(f"\n🤖 AUTO-LOGIN: Authenticating with Screener as {email}...")
    
    for attempt in range(1, 4):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=USER_AGENT)
                page = context.new_page()

                page.goto("https://www.screener.in/login/")
                page.fill("input[name='username']", email)
                page.fill("input[name='password']", password)
                page.click("button[type='submit']")

                page.wait_for_timeout(8000)
                
                cookies = context.cookies()
                cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
                csrf = cookie_dict.get('csrftoken', '')
                session = cookie_dict.get('sessionid', '')
                
                if session:
                    print("   ✅ Login successful! Extracted fresh session tokens.")
                    browser.close()
                    return f"csrftoken={csrf}; sessionid={session}"
                else:
                    raise Exception("Could not find 'sessionid'. Login likely failed.")
                
        except Exception as e:
            print(f"   ⚠️ Auto-login attempt {attempt}/3 failed: {e}")
            if attempt < 3: time.sleep(5)
            
    raise Exception("Playwright Login Module completely failed after 3 attempts.")

# ==========================================
# NEW: NIFTY MICROCAP 250 SCRAPER
# ==========================================
def scrape_nifty_microcap_250(engine, stock_master_df):
    print("\n🔬 STEP: Scraping Nifty Microcap 250 Index (Alternate Account)...")
    try:
        fresh_cookies = get_fresh_screener_cookies(MICROCAP_EMAIL, MICROCAP_PASSWORD)
        session = requests.Session()
        session.screener_cookies = fresh_cookies
        
        first_page = fetch_with_retry(session, MICROCAP_URL)
        if not first_page:
            print("   ❌ ERROR: Failed to fetch Microcap page.")
            return

        page_match = re.search(r'Showing page \d+ of (\d+)', first_page)
        total_pages = int(page_match.group(1)) if page_match else 1
        print(f"   📋 Found {total_pages} pages for Nifty Microcap 250. Downloading...")
        
        all_dfs = []
        for page in range(1, total_pages + 1):
            page_url = MICROCAP_URL if page == 1 else f"{MICROCAP_URL}?page={page}"
            html_content = first_page if page == 1 else fetch_with_retry(session, page_url)
            
            if html_content:
                try:
                    tables = pd.read_html(io.StringIO(html_content), thousands=',')
                    if tables:
                        df = tables[0]
                        # Remove redundant headers
                        df = df[df['Name'] != 'Name'].copy()
                        df['Name'] = df['Name'].astype(str).str.strip()
                        all_dfs.append(df)
                except Exception as e:
                    print(f"     ⚠️ ERROR parsing microcap page {page}: {e}")
            random_sleep(800, 1500)
            
        if all_dfs:
            microcap_df = pd.concat(all_dfs, ignore_index=True)
            print(f"   ✅ Collected {len(microcap_df)} Microcap companies.")
            
            # Map required columns from stock_master_df
            cols_to_pull = ['Name', 'Sector', 'Broad Industry', 'Band', 'Down %_ATH', 'Turnover']
            existing_cols = [c for c in cols_to_pull if c in stock_master_df.columns]
            
            microcap_df = pd.merge(microcap_df, stock_master_df[existing_cols], on='Name', how='left')
            print("   ✅ VLOOKUP completed for Microcap data.")
            
            save_db_with_retry(microcap_df, "Nifty_Microcap_250_Index", engine, if_exists="replace", index=False)
            print("   ☁️ Successfully pushed 'Nifty_Microcap_250_Index' to Supabase.")
            
    except Exception as e:
        print(f"   ❌ Failed to scrape Nifty Microcap 250: {e}")

# ==========================================
# ETF ENGINES
# ==========================================
def download_and_rank_etfs():
    print("\n📈 STEP: Fetching and Ranking NSE ETFs...")
    url = "https://scanner.tradingview.com/india/scan"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json"
    }

    payload = {
        "columns": [
            "name", "description", "close", "change", 
            "Perf.W", "Perf.1M", "Perf.3M", "Perf.6M", "Perf.Y", "exchange",
            "EMA21", "average_volume_30d_calc", "expense_ratio"
        ],
        "filter": [
            {"left": "exchange", "operation": "equal", "right": "NSE"},
            {"left": "type", "operation": "equal", "right": "fund"}
        ],
        "ignore_unknown_fields": False,
        "markets": ["india"],
        "options": {"lang": "en"},
        "range": [0, 500],  
        "sort": {"sortBy": "Perf.10Y", "sortOrder": "desc"}
    }
    
    response = None
    for attempt in range(1, 4):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            resp.raise_for_status()
            response = resp
            break
        except Exception as e:
            print(f"   ⚠️ ETF Fetch attempt {attempt}/3 failed: {e}")
            if attempt < 3: time.sleep(5)
            
    if not response:
        raise Exception("Failed to fetch ETF data from TradingView after 3 attempts.")
        
    data = response.json()
    rows = [item['d'] for item in data.get('data', [])]

    if not rows:
        raise Exception("No ETF data returned from TradingView payload.")

    df = pd.DataFrame(rows, columns=payload["columns"])
    df.columns = [
        "Symbol", "Name", "Price (INR)", "Chg %", 
        "Perf 1W %", "Perf 1M %", "Perf 3M %", "Perf 6M %", "Perf 1Y %", "Exchange",
        "EMA 21", "Avg Vol 30D", "Expense Ratio"
    ]

    df['EMA 21 Status'] = df.apply(
        lambda row: "Above 21 Ema" if pd.notnull(row['Price (INR)']) and pd.notnull(row['EMA 21']) and row['Price (INR)'] > row['EMA 21'] 
        else ("Below 21 Ema" if pd.notnull(row['Price (INR)']) and pd.notnull(row['EMA 21']) else "N/A"), 
        axis=1
    )

    df['Turnover (Cr)'] = ((df['Price (INR)'] * df['Avg Vol 30D']) / 10000000).round(2)

    print("   🧮 Calculating relative scores and ranks for ETFs...")
    rank_1m = df['Perf 1M %'].rank(ascending=False, method='min', na_option='bottom')
    rank_3m = df['Perf 3M %'].rank(ascending=False, method='min', na_option='bottom')
    rank_6m = df['Perf 6M %'].rank(ascending=False, method='min', na_option='bottom')

    df['Relative Score'] = (rank_1m * 2) + (rank_3m * 4) + (rank_6m * 4)
    df['Final Rank'] = df['Relative Score'].rank(ascending=True, method='min').astype('Int64')

    cols = [
        "Final Rank", "Relative Score", "Symbol", "Name", "Exchange", 
        "Price (INR)", "EMA 21", "EMA 21 Status", "Chg %", "Turnover (Cr)", "Avg Vol 30D", "Expense Ratio",
        "Perf 1W %", "Perf 1M %", "Perf 3M %", "Perf 6M %", "Perf 1Y %"
    ]
    
    df = df[cols].sort_values('Final Rank')

    print("   🔗 VLOOKUP: Mapping ETF Categories from Supabase 'ETF Category' table...")
    try:
        with engine.connect() as conn:
            category_df = pd.read_sql(text('SELECT "Symbol", "Catergory" FROM "ETF Category"'), conn)
        df = pd.merge(df, category_df, on='Symbol', how='left')
        df.rename(columns={'Catergory': 'Category'}, inplace=True)
        print("   ✅ Categories successfully mapped and appended.")
    except Exception as e:
        print(f"   ⚠️ WARNING: Could not fetch or merge ETF Category map: {e}")
        df['Category'] = np.nan

    print(f"   ☁️ Saving {len(df)} ranked ETFs directly to Supabase...")
    save_db_with_retry(df, "ETF Screener", engine, if_exists="replace", index=False, chunksize=500, method='multi')
    print("   ✅ 'ETF Screener' table overwritten successfully.")


def download_usa_etfs(engine):
    print("\n🇺🇸 STEP: Fetching and Ranking USA ETFs...")
    url = "https://scanner.tradingview.com/america/scan"
    payload = {
        "columns": [
            "name", "close", "change", 
            "Perf.W", "Perf.1M", "Perf.3M", "Perf.6M", "Perf.Y", 
            "exchange", "average_volume_30d_calc", "EMA21", "expense_ratio"
        ],
        "filter": [
            {"left": "type", "operation": "equal", "right": "fund"},
            {"left": "Value.Traded", "operation": "greater", "right": 5000000}
        ],
        "markets": ["america"],
        "options": {"lang": "en"},
        "range": [0, 4000], 
        "sort": {"sortBy": "Perf.10Y", "sortOrder": "desc"}
    }

    try:
        response = requests.post(url, headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"}, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        rows = [item["d"] for item in data.get("data", [])]
        df = pd.DataFrame(rows, columns=[
            "Symbol", "Price (USD)", "Chg %", 
            "Perf 1W %", "Perf 1M %", "Perf 3M %", "Perf 6M %", 
            "Perf 1Y %", "Exchange", "Avg Vol 30D", "EMA 21", "Expense Ratio"
        ])
        df["Symbol"] = df["Symbol"].str.upper().str.strip()
        print(f"   📋 Retrieved {len(df)} USA ETFs from TradingView.")

        # VLOOKUP Logic from USA_ETF_Catagory
        with engine.connect() as conn:
            cat_df = pd.read_sql(text('SELECT "Symbol", "Category", "Index" FROM "USA_ETF_Catagory"'), conn)
        
        cat_df["Symbol"] = cat_df["Symbol"].astype(str).str.upper().str.strip()
        df = df.merge(cat_df, on="Symbol", how="inner")
        print(f"   🔗 Matched {len(df)} USA ETFs against Supabase category map.")

        df["EMA 21 Status"] = df.apply(
            lambda r: "Above 21 EMA" if pd.notna(r["Price (USD)"]) and pd.notna(r["EMA 21"]) and r["Price (USD)"] > r["EMA 21"]
            else ("Below 21 EMA" if pd.notna(r["Price (USD)"]) and pd.notna(r["EMA 21"]) else "N/A"), axis=1
        )
        df["Turnover (M USD)"] = (df["Price (USD)"] * df["Avg Vol 30D"] / 1_000_000).round(2)

        r1 = df["Perf 1M %"].rank(ascending=False, method="min", na_option="bottom")
        r3 = df["Perf 3M %"].rank(ascending=False, method="min", na_option="bottom")
        r6 = df["Perf 6M %"].rank(ascending=False, method="min", na_option="bottom")
        df["Relative Score"] = r1 * 2 + r3 * 4 + r6 * 4
        df["Final Rank"] = df["Relative Score"].rank(ascending=True, method="min").astype(int)
        
        cols = [
            "Final Rank", "Relative Score", "Symbol", "Category", "Index",
            "Exchange", "Price (USD)", "EMA 21", "EMA 21 Status", "Chg %", 
            "Turnover (M USD)", "Avg Vol 30D", "Expense Ratio",
            "Perf 1W %", "Perf 1M %", "Perf 3M %", "Perf 6M %", "Perf 1Y %"
        ]
        df = df[[c for c in cols if c in df.columns]].sort_values("Final Rank")
        
        save_db_with_retry(df, "USA_ETF_Screener", engine, if_exists="replace", index=False)
        print("   ☁️ Successfully pushed 'USA_ETF_Screener' to Supabase.")

    except Exception as e:
        print(f"   ❌ Failed to scrape and rank USA ETFs: {e}")

# ==========================================
# MAIN PIPELINE
# ==========================================
def run_daily_scraper():
    print("\n" + "="*60)
    print("🚀 STARTING: Cloud-Native Market Scraper & Trend Engine")
    print("="*60)
    
    current_module = "Initialization & Login"
    try:
        fresh_cookies = get_fresh_screener_cookies(SCREENER_EMAIL, SCREENER_PASSWORD)
        session = requests.Session()
        session.screener_cookies = fresh_cookies
        
        # ==========================================
        # STEP 1: FETCH STATIC DB MAP & CACHE
        # ==========================================
        current_module = "Database Cache Check"
        print("\n📚 STEP 1: Checking database for companies we already know...")
        try:
            static_df = pd.read_sql("SELECT * FROM sector_master", engine)
            
            col_n = next((c for c in static_df.columns if str(c).strip().lower() == 'name'), 'Name')
            col_t = next((c for c in static_df.columns if str(c).strip().lower() == 'ticker'), 'Ticker')
            col_s = next((c for c in static_df.columns if str(c).strip().lower() == 'sector'), 'Sector')
            col_i = next((c for c in static_df.columns if 'industry' in str(c).lower()), 'Broad Industry')
            col_e = next((c for c in static_df.columns if 'exchange' in str(c).lower()), 'Exchange')
            
            unknown_mask = (static_df[col_s] == 'Unknown') | (static_df[col_i] == 'Unknown')
            if unknown_mask.any():
                print(f"   🧹 Found {unknown_mask.sum()} incomplete profiles. Forcing a re-scrape for them...")
                with engine.begin() as conn:
                    conn.execute(text(f'DELETE FROM sector_master WHERE "{col_s}" = \'Unknown\' OR "{col_i}" = \'Unknown\''))
                static_df = static_df[~unknown_mask]
            
            cols_to_keep = [c for c in [col_n, col_t, col_s, col_i, col_e] if c in static_df.columns]
            static_subset = static_df[cols_to_keep].copy()
            static_subset.columns = ['Name', 'Ticker', 'Sector', 'Broad Industry', 'Exchange']
            static_subset['Name'] = static_subset['Name'].astype(str).str.strip()
            
            known_names = set(static_subset['Name'].tolist())
            print(f"   ✅ Cache Loaded: We currently have {len(known_names)} companies saved in Supabase.")
        except Exception as e:
            print(f"   ⚠️ Could not load database cache. Starting fresh. ({e})")
            known_names = set()
            static_subset = pd.DataFrame(columns=['Name', 'Ticker', 'Sector', 'Broad Industry', 'Exchange'])

        if 'Exchange' not in static_subset.columns:
            static_subset['Exchange'] = "NSE"

        # ==========================================
        # STEP 2: FAST LIVE SCRAPE (MAIN TABLES)
        # ==========================================
        current_module = "Live Market Scrape"
        print("\n📡 STEP 2: Scanning Screener.in for live market prices...")
        first_page = fetch_with_retry(session, SCREENER_URL)
        if not first_page: 
            raise Exception("Cannot reach Screener.in. Check internet connection.")
            
        page_match = re.search(r'Showing page \d+ of (\d+)', first_page)
        total_pages = int(page_match.group(1)) if page_match else 1
        print(f"   📋 Found {total_pages} pages of live market data. Downloading now...")
        
        all_dataframes = []
        
        for page in range(1, total_pages + 1):
            page_url = SCREENER_URL if page == 1 else f"{SCREENER_URL}?page={page}"
            referer_url = None if page == 1 else (SCREENER_URL if page == 2 else f"{SCREENER_URL}?page={page-1}")
            
            html_content = first_page if page == 1 else fetch_with_retry(session, page_url, referer_url=referer_url)
            if not html_content: continue
            
            try:
                tables = pd.read_html(io.StringIO(html_content), thousands=',')
                if tables:
                    df = tables[0]
                    df = df[df['Name'] != 'Name'].copy()
                    df['Name'] = df['Name'].astype(str).str.strip()
                    
                    soup = BeautifulSoup(html_content, 'html.parser')
                    table = soup.find('table')
                    codes = []
                    if table and table.find('tbody'):
                        for tr in table.find('tbody').find_all('tr'):
                            if tr.find('th'): continue
                            a_tag = tr.find('a', href=re.compile(r'/company/([A-Za-z0-9_\-&]+)/'))
                            if a_tag:
                                code = re.search(r'/company/([A-Za-z0-9_\-&]+)/', a_tag['href']).group(1)
                                codes.append(code.upper())
                    
                    if len(codes) == len(df):
                        df['live_ticker_slug'] = codes 
                        all_dataframes.append(df)
                    else:
                        print(f"     ⚠️ WARNING: Data mismatch on page {page}. Dropping page.")
                        
            except Exception as e:
                print(f"     ⚠️ ERROR parsing page {page}: {e}")
                
            if page % 10 == 0 or page == total_pages:
                print(f"     -> Processed {page}/{total_pages} pages...")
                
            if page < total_pages: random_sleep(800, 1500)

        if not all_dataframes: 
            raise Exception("No live market data was successfully scraped.")
            
        live_df = pd.concat(all_dataframes, ignore_index=True)
        print(f"   ✅ Done! Collected live data for {len(live_df)} active companies.")
        
        # ==========================================
        # STEP 3: DEEP SCRAPE MISSING NAMES ONLY
        # ==========================================
        current_module = "Deep Scrape Missing Companies"
        print("\n🕵️‍♂️ STEP 3: Checking for brand new companies (IPOs, name changes)...")
        live_names = set(live_df['Name'].tolist())
        missing_names = [n for n in live_names if n not in known_names]
        
        if missing_names:
            missing_df = live_df[live_df['Name'].isin(missing_names)].drop_duplicates(subset=['Name'])
            total_missing = len(missing_df)
            print(f"   🚨 Found {total_missing} NEW companies! Fetching their sector details...")
            new_records = []
            
            current_count = 0
            for idx, row in missing_df.iterrows():
                current_count += 1
                stock_name = row['Name']
                code = row['live_ticker_slug']
                url = f"https://www.screener.in/company/{code}/"
                
                if current_count > 1 and current_count % 25 == 0:
                    cooldown = random.randint(6, 12)
                    print(f"     💤 Anti-Block Trigger: Taking a {cooldown}-second stealth pause...")
                    time.sleep(cooldown)

                print(f"     -> [{current_count}/{total_missing}] Investigating: {stock_name}")
                page_html = fetch_with_retry(session, url, referer_url=SCREENER_URL)
                
                sector, industry, exchange_class = "Unknown", "Unknown", ""
                if page_html:
                    soup = BeautifulSoup(page_html, 'html.parser')
                    sec_tag = soup.find('a', title='Sector')
                    ind_tag = soup.find('a', title='Broad Industry')
                    if sec_tag: sector = sec_tag.text.strip()
                    if ind_tag: industry = ind_tag.text.strip()

                    nse_link = soup.find('a', href=re.compile(r'nseindia\.com/get-quotes/equity\?symbol='))
                    bse_link = soup.find('a', href=re.compile(r'bseindia\.com/stock-share-price/'))

                    if nse_link:
                        span_tag = nse_link.find('span')
                        exchange_class = "NSE SME" if (span_tag and 'SME' in span_tag.text.upper()) else "NSE"
                    elif bse_link:
                        span_tag = bse_link.find('span')
                        exchange_class = "BSE SME" if (span_tag and 'SME' in span_tag.text.upper()) else "BSE"
                    else:
                        exchange_class = "BSE" if code.isdigit() else "NSE"
                else:
                    exchange_class = "BSE" if code.isdigit() else "NSE"
                    
                try:
                    original_col_t = next((c for c in static_df.columns if str(c).strip().lower() == 'ticker'), 'Ticker')
                    original_col_n = next((c for c in static_df.columns if str(c).strip().lower() == 'name'), 'Name')
                    original_col_s = next((c for c in static_df.columns if str(c).strip().lower() == 'sector'), 'Sector')
                    original_col_i = next((c for c in static_df.columns if 'industry' in str(c).lower()), 'Broad Industry')
                    original_col_e = next((c for c in static_df.columns if 'exchange' in str(c).lower()), 'Exchange')
                    
                    new_records.append({
                        original_col_n: stock_name,
                        original_col_t: code, 
                        original_col_s: sector, 
                        original_col_i: industry, 
                        original_col_e: exchange_class
                    })
                except Exception:
                    pass
                random_sleep(800, 1500)
                
            if new_records:
                new_static_df = pd.DataFrame(new_records)
                print(f"   ☁️ Saving {len(new_records)} new companies permanently to database...")
                save_db_with_retry(new_static_df, "sector_master", engine, if_exists="append", index=False)
                new_static_mapped = pd.DataFrame({
                    'Name': [r.get(original_col_n) for r in new_records],
                    'Ticker': [r.get(original_col_t) for r in new_records],
                    'Sector': [r.get(original_col_s) for r in new_records],
                    'Broad Industry': [r.get(original_col_i) for r in new_records],
                    'Exchange': [r.get(original_col_e) for r in new_records]
                })
                static_subset = pd.concat([static_subset, new_static_mapped], ignore_index=True)
                print("   ✅ New companies saved successfully.")
        else:
            print("   ✅ No new companies today. Existing database is perfectly up to date.")

        # ==========================================
        # STEP 4: MERGE, CLEAN, & CALCULATE MOMENTUM
        # ==========================================
        current_module = "Momentum & Price Bands"
        print("\n🧮 STEP 4: Calculating cross-sectional momentum scores...")
        ret_1m = next((c for c in live_df.columns if '1m' in c.lower() and 'return' in c.lower()), None)
        ret_3m = next((c for c in live_df.columns if '3m' in c.lower() and 'return' in c.lower()), None)
        ret_6m = next((c for c in live_df.columns if '6m' in c.lower() and 'return' in c.lower()), None)

        if ret_1m and ret_3m and ret_6m:
            live_df[ret_1m] = pd.to_numeric(live_df[ret_1m], errors='coerce')
            live_df[ret_3m] = pd.to_numeric(live_df[ret_3m], errors='coerce')
            live_df[ret_6m] = pd.to_numeric(live_df[ret_6m], errors='coerce')

            rank_1m = live_df[ret_1m].rank(ascending=False, method='min')
            rank_3m = live_df[ret_3m].rank(ascending=False, method='min')
            rank_6m = live_df[ret_6m].rank(ascending=False, method='min')
            
            momentum_score = (rank_1m * 2) + (rank_3m * 4) + (rank_6m * 4)
            valid_mask = live_df[[ret_1m, ret_3m, ret_6m]].notna().all(axis=1)
            
            final_rank = momentum_score.rank(ascending=True, method='min')
            
            live_df['Relative score'] = final_rank.where(valid_mask, np.nan)
            print("   ✅ Momentum rank calculated (1 = Highest Momentum) and assigned.")
        else:
            print("   ⚠️ WARNING: 1M/3M/6M return columns are missing. Cannot calculate momentum.")
            live_df['Relative score'] = np.nan

        live_df = live_df.drop(columns=['live_ticker_slug'])
        merged_df = pd.merge(live_df, static_subset, on='Name', how='left')
        merged_df = merged_df.loc[:, ~merged_df.columns.duplicated()].copy()
        
        cmp_col = next((c for c in merged_df.columns if 'cmp' in str(c).lower()), None)
        ath_col = next((c for c in merged_df.columns if 'all time high' in str(c).lower() or 'alltime' in str(c).lower()), None)
        vol_col = next((c for c in merged_df.columns if 'avg vol' in str(c).lower()), None)
        
        if cmp_col and ath_col:
            print(f"\n📉 STEP 4.1a: Calculating Down %_ATH using [{ath_col}] and [{cmp_col}]...")
            merged_df[ath_col] = pd.to_numeric(merged_df[ath_col], errors='coerce')
            merged_df[cmp_col] = pd.to_numeric(merged_df[cmp_col], errors='coerce')
            merged_df['Down %_ATH'] = (((merged_df[ath_col] - merged_df[cmp_col]) / merged_df[ath_col]) * 100).clip(lower=0).round(2)
            print("   ✅ 'Down %_ATH' column successfully calculated and appended.")
        else:
            print(f"\n   ⚠️ WARNING: Cannot calculate Down %_ATH. Found CMP Col: {cmp_col}, Found ATH Col: {ath_col}")

        if cmp_col and vol_col:
            print(f"🔄 STEP 4.1b: Calculating Turnover using [{cmp_col}] and [{vol_col}]...")
            merged_df[vol_col] = pd.to_numeric(merged_df[vol_col], errors='coerce')
            merged_df['Turnover'] = ((merged_df[cmp_col] * merged_df[vol_col]) / 10000000).round(2)
            print("   ✅ 'Turnover' column successfully calculated in Crores.")
        else:
            print(f"   ⚠️ WARNING: Cannot calculate Turnover. Found CMP Col: {cmp_col}, Found Vol Col: {vol_col}")


        print("\n🏷️ STEP 4.2: Fetching NSE Price Bands (sec_list.csv)...")
        file_url = "https://archives.nseindia.com/content/equities/sec_list.csv"
        band_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }
        band_df = pd.DataFrame()
        for attempt in range(1, 4):
            try:
                time.sleep(random.uniform(1, 3))
                resp = requests.get(file_url, headers=band_headers, timeout=10)
                if resp.status_code == 200:
                    band_df = pd.read_csv(io.StringIO(resp.text))
                    break
            except Exception as e:
                print(f"   ⚠️ Attempt {attempt} failed: {e}")
                
        if not band_df.empty and len(band_df.columns) >= 4:
            band_df.columns = [str(c).strip() for c in band_df.columns]
            if 'Symbol' in band_df.columns and 'Band' in band_df.columns:
                band_subset = band_df[['Symbol', 'Band']].drop_duplicates(subset=['Symbol'])
                band_subset['Symbol'] = band_subset['Symbol'].astype(str).str.strip().str.upper()
                
                merged_df['temp_ticker'] = merged_df['Ticker'].astype(str).str.strip().str.upper()
                merged_df = pd.merge(merged_df, band_subset, left_on='temp_ticker', right_on='Symbol', how='left')
                
                valid_exchanges = ['NSE', 'NSE SME']
                is_nse_mask = merged_df['Exchange'].astype(str).str.strip().str.upper().isin(valid_exchanges)
                merged_df.loc[~is_nse_mask, 'Band'] = np.nan
                
                merged_df.drop(columns=['temp_ticker', 'Symbol'], inplace=True)
                print("   ✅ Price Bands successfully merged for NSE/NSE SME stocks.")
            else:
                print("   ⚠️ WARNING: 'Symbol' or 'Band' columns missing from downloaded CSV.")
        else:
            print("   ❌ ERROR: Failed to download or parse sec_list.csv.")


        # ==========================================
        # STEP 5.1: SCRAPE ATH DATA & RANK SECTORS
        # ==========================================
        current_module = "ATH Sector Scrape"
        print("\n📊 STEP 5.1: Scraping true ATH data & Generating Sector Rankings...")
        sector_summary_df = pd.DataFrame()
        industry_summary_df = pd.DataFrame()
        ath_df = pd.DataFrame()
        ath_names = set()
        
        ath_screener_url = "https://www.screener.in/screens/3315507/ath-sector-analysis/"
        first_ath_page = fetch_with_retry(session, ath_screener_url)
        
        if first_ath_page:
            page_match = re.search(r'Showing page \d+ of (\d+)', first_ath_page)
            ath_total_pages = int(page_match.group(1)) if page_match else 1
            print(f"   📋 Found {ath_total_pages} pages of live ATH stocks. Downloading...")
            
            ath_dataframes = []
            
            for p in range(1, ath_total_pages + 1):
                p_url = ath_screener_url if p == 1 else f"{ath_screener_url}?page={p}"
                p_html = first_ath_page if p == 1 else fetch_with_retry(session, p_url)
                
                if p_html:
                    try:
                        tables = pd.read_html(io.StringIO(p_html), thousands=',')
                        if tables:
                            df = tables[0]
                            df = df[df['Name'] != 'Name'].copy() 
                            df['Name'] = df['Name'].astype(str).str.strip()
                            ath_dataframes.append(df)
                    except Exception as e:
                        print(f"     ⚠️ ERROR parsing page {p}: {e}")
                        
                if p % 5 == 0 or p == ath_total_pages:
                    print(f"     -> Scraped {p}/{ath_total_pages} ATH pages...")
                    
                if p < ath_total_pages:
                    random_sleep(800, 1500)
                    
            if ath_dataframes:
                ath_df = pd.concat(ath_dataframes, ignore_index=True)
                if 'Is not SME' in ath_df.columns:
                    ath_df = ath_df.drop(columns=['Is not SME'])
                    
                print(f"   ✅ Collected detailed data for {len(ath_df)} ATH companies.")
                
                cols_to_pull = ['Name', 'Ticker', 'Sector', 'Broad Industry', 'Exchange']
                existing_cols = [c for c in cols_to_pull if c in merged_df.columns]
                
                ath_df = pd.merge(ath_df, merged_df[existing_cols], on='Name', how='left')
                print("   ✅ Performed VLOOKUP to add Sector, Industry, Ticker, and Exchange to ATH_Analysis.")
                
                ath_names = set(ath_df['Name'].tolist())
        else:
            print("   ❌ Failed to fetch ATH Screener. Sector analysis will be empty.")

        sme_col = next((c for c in merged_df.columns if str(c).strip().lower() == 'is sme'), None)
        
        if sme_col:
            analysis_df = merged_df[merged_df[sme_col].astype(str).str.strip() != '1'].copy()
            print(f"   🧹 Filtered out SMEs using '{sme_col}' column.")
        else:
            print("   ⚠️ WARNING: 'Is SME' column not found! Proceeding without SME filtering.")
            analysis_df = merged_df.copy()
        
        analysis_df['is_ath'] = analysis_df['Name'].astype(str).str.strip().isin(ath_names)

        def build_summary_table(df, group_col):
            valid_df = df[(df[group_col] != "Unknown") & (df[group_col].notna())]
            if valid_df.empty: return pd.DataFrame()
            summary = valid_df.groupby(group_col).agg(Total_Stocks=('is_ath', 'count'), ATH_Stocks=('is_ath', 'sum')).reset_index()
            summary['ATH %'] = (summary['ATH_Stocks'] / summary['Total_Stocks'] * 100).round(2)
            summary = summary.sort_values(by='ATH %', ascending=False).reset_index(drop=True)
            summary['Rank'] = summary.index + 1
            return summary

        col_sector = next((c for c in analysis_df.columns if str(c).strip().lower() == 'sector'), 'Sector')
        col_industry = next((c for c in analysis_df.columns if 'industry' in str(c).lower()), 'Broad Industry')

        sector_summary_df = build_summary_table(analysis_df, col_sector)
        industry_summary_df = build_summary_table(analysis_df, col_industry)
        
        if not ath_df.empty:
            ath_1d_col = next((c for c in ath_df.columns if '1day return' in c.lower() or '1d' in c.lower()), None)
            if ath_1d_col:
                ath_df[ath_1d_col] = pd.to_numeric(ath_df[ath_1d_col], errors='coerce')
                
                if col_sector in ath_df.columns and not sector_summary_df.empty:
                    sec_avg = ath_df.groupby(col_sector)[ath_1d_col].mean().reset_index().rename(columns={ath_1d_col: 'Avg 1D Return %'})
                    sector_summary_df = pd.merge(sector_summary_df, sec_avg, on=col_sector, how='left')
                    sector_summary_df['Avg 1D Return %'] = sector_summary_df['Avg 1D Return %'].round(2)
                    
                if col_industry in ath_df.columns and not industry_summary_df.empty:
                    ind_avg = ath_df.groupby(col_industry)[ath_1d_col].mean().reset_index().rename(columns={ath_1d_col: 'Avg 1D Return %'})
                    industry_summary_df = pd.merge(industry_summary_df, ind_avg, on=col_industry, how='left')
                    industry_summary_df['Avg 1D Return %'] = industry_summary_df['Avg 1D Return %'].round(2)

        if not sector_summary_df.empty:
            sector_summary_df = sector_summary_df.sort_values(by='Rank', ascending=True).reset_index(drop=True)
        if not industry_summary_df.empty:
            industry_summary_df = industry_summary_df.sort_values(by='Rank', ascending=True).reset_index(drop=True)

        print("   ✅ Sector and Industry ATH rankings generated successfully.")

        # ==========================================
        # STEP 5.2: DAILY MARKET MOOD ENGINE & HOLIDAY ENGINE
        # ==========================================
        current_module = "Market Mood Engine"
        now_ist = pd.Timestamp.now(tz='Asia/Kolkata')
        
        is_time_locked = 9 <= now_ist.hour < 21

        if now_ist.hour < 9:
            trading_date = now_ist - pd.Timedelta(days=1)
        else:
            trading_date = now_ist

        today_date_str = trading_date.strftime('%Y-%m-%d')
        is_weekday = trading_date.weekday() < 5  
        
        historical_mood_df = pd.DataFrame()
        already_logged = False
        is_nse_holiday = False
        
        if is_weekday:
            if is_time_locked:
                print(f"\n   ⏸️ Market Engine Paused: Current time is between 9 AM and 9 PM IST. Skipping mood updates.")
            else:
                print(f"\n   🕒 Date check passed for trading day {today_date_str}. Running Market Engine...")
                try:
                    query_dup = text(f"""SELECT * FROM historical_market_mood WHERE "Date" = '{today_date_str}'""")
                    with engine.connect() as conn:
                        existing_mood = pd.read_sql(query_dup, conn)
                    already_logged = not existing_mood.empty
                except Exception:
                    already_logged = False
                    
                if not already_logged:
                    mood_analysis_df = merged_df[merged_df['Exchange'].astype(str).str.strip().str.upper() == 'NSE'].copy()
                    
                    col_chg = next((c for c in mood_analysis_df.columns if 'return over 1day' in c.lower() or '1d' in c.lower() or 'chg' in c.lower()), None)
                    if not col_chg: col_chg = next((c for c in mood_analysis_df.columns if 'return' in c.lower() and '1' in c.lower()), None)

                    if col_chg:
                        mood_analysis_df[col_chg] = pd.to_numeric(mood_analysis_df[col_chg], errors='coerce')
                        valid_returns = mood_analysis_df[mood_analysis_df[col_chg].notna()]
                        total_stocks = int(len(valid_returns))
                        positive_stocks = int((valid_returns[col_chg] > 0).sum())
                        
                        if total_stocks > 0:
                            ratio = positive_stocks / total_stocks
                            score = ratio * 100
                            pct_str = f"{score:.2f}%"  
                            
                            print("   🔍 HOLIDAY DETECTOR: Comparing values with last logged entry...")
                            try:
                                query_last = text('SELECT * FROM historical_market_mood ORDER BY "Date" DESC LIMIT 1')
                                with engine.connect() as conn:
                                    last_entry_df = pd.read_sql(query_last, conn)
                                
                                if not last_entry_df.empty:
                                    last_text = str(last_entry_df['Market Breadth'].iloc[0])
                                    match_pct = re.search(r'([0-9.]+)%', last_text)
                                    if match_pct:
                                        last_logged_pct = float(match_pct.group(1))
                                        today_rounded_pct = round(score, 2)
                                        
                                        if today_rounded_pct == last_logged_pct:
                                            print("   ⚠️ Breadth match detected. Initiating deep cross-verification on individual stock prices...")
                                            try:
                                                query_verify = text(f'SELECT "Name", "{cmp_col}" FROM stock_master WHERE "{cmp_col}" IS NOT NULL LIMIT 15')
                                                with engine.connect() as conn:
                                                    db_sample = pd.read_sql(query_verify, conn)
                                                
                                                if not db_sample.empty and cmp_col:
                                                    verify_df = pd.merge(db_sample, merged_df[['Name', cmp_col]], on='Name', suffixes=('_db', '_live'))
                                                    identical_prices = (verify_df[f'{cmp_col}_db'] == verify_df[f'{cmp_col}_live']).sum()
                                                    total_samples = len(verify_df)
                                                    
                                                    if total_samples > 0 and (identical_prices / total_samples) >= 0.90:
                                                        is_nse_holiday = True
                                                        print(f"   🛑 HOLIDAY CONFIRMED: Checked {total_samples} stocks; {identical_prices} have completely identical prices.")
                                                    else:
                                                        print(f"   🚀 FALSE POSITIVE OVERRIDDEN: {total_samples - identical_prices}/{total_samples} sampled stocks show price changes.")
                                                else:
                                                    is_nse_holiday = True
                                                    print("   ⚠️ Verification sample empty. Defaulting to holiday lock to protect data integrity.")
                                            except Exception as verify_err:
                                                is_nse_holiday = True
                                                print(f"   ⚠️ Secondary verification failed ({verify_err}). Defaulting to holiday lock.")
                            except Exception as e:
                                print(f"   ⚠️ Holiday check warning (Skipping safe check execution): {e}")
                            
                            if not is_nse_holiday:
                                if score <= 20: mood_label = f"Super Negative 🐻 {pct_str}"
                                elif score <= 35: mood_label = f"Negative 🔻 {pct_str}"
                                elif score <= 50: mood_label = f"Neutral ⚖️ {pct_str}"
                                elif score <= 65: mood_label = f"Positive 💚 {pct_str}"
                                else: mood_label = f"Super Positive 🚀 {pct_str}"
                                    
                                historical_mood_df = pd.DataFrame([{"Date": today_date_str, "Market Breadth": mood_label}])
                                print(f"     📊 Today's Result: Total NSE Mainboard: {total_stocks} | Positive: {positive_stocks}")
                                print(f"     🚦 Today's Mood: {mood_label}")
                                
                                save_db_with_retry(historical_mood_df, "historical_market_mood", engine, if_exists="append", index=False)
                                print("     ✅ Market Mood successfully logged to history.")
                else:
                    print(f"   ⏸️ Market mood for {today_date_str} is already logged. Skipping duplicate.")
        else:
            print(f"\n   ⏸️ Skipping Market Mood: {today_date_str} is not a valid weekday.")

        # ==========================================
        # STEP 5.3: COMPOSITE SMOOTHED TREND ENGINE
        # ==========================================
        current_module = "Trend Engine"
        if is_weekday and not is_time_locked and not already_logged and not is_nse_holiday:
            print("\n   📈 Calculating 7-Day, 14-Day, and 21-Day Composite Trend...")
            try:
                query_all = text('SELECT * FROM historical_market_mood ORDER BY "Date" DESC LIMIT 30')
                with engine.connect() as conn:
                    hist_df = pd.read_sql(query_all, conn)
                
                if not historical_mood_df.empty:
                    hist_df = pd.concat([historical_mood_df, hist_df], ignore_index=True).drop_duplicates(subset=['Date'])
                hist_df = hist_df.sort_values(by='Date', ascending=True).reset_index(drop=True)
                
                if len(hist_df) >= 7:
                    def extract_percentage(text_val):
                        match = re.search(r'([0-9.]+)%', str(text_val))
                        return float(match.group(1)) if match else np.nan

                    hist_df['pct_value'] = hist_df['Market Breadth'].apply(extract_percentage)
                    
                    val_7d = hist_df['pct_value'].iloc[-7:].mean() if len(hist_df) >= 7 else np.nan
                    val_14d = hist_df['pct_value'].iloc[-14:].mean() if len(hist_df) >= 14 else val_7d
                    val_21d = hist_df['pct_value'].iloc[-21:].mean() if len(hist_df) >= 21 else val_14d
                    
                    final_score = (val_7d * 5 + val_14d * 3 + val_21d * 2) / 10
                    pct_str = f"{final_score:.2f}%"
                    
                    if final_score <= 20: trend_label = f"Super Negative 🐻 {pct_str}"
                    elif final_score <= 35: trend_label = f"Negative 🔻 {pct_str}"
                    elif final_score <= 50: trend_label = f"Neutral ⚖️ {pct_str}"
                    elif final_score <= 65: trend_label = f"Positive 💚 {pct_str}"
                    else: trend_label = f"Super Positive 🚀 {pct_str}"
                    
                    print(f"     🎯 Rolling Averages: 7D: {val_7d:.1f}% | 14D: {val_14d:.1f}% | 21D: {val_21d:.1f}%")
                    print(f"     🏆 Final Market Regime: {trend_label}")
                    
                    trend_summary_df = pd.DataFrame([{
                        "last_updated": today_date_str,
                        "avg_7d": round(val_7d, 2),
                        "avg_14d": round(val_14d, 2),
                        "avg_21d": round(val_21d, 2),
                        "composite_score": round(final_score, 2),
                        "trend_regime": trend_label
                    }])
                    save_db_with_retry(trend_summary_df, "market_trend_summary", engine, if_exists="replace", index=False)
                    
                    # ----------------------------------------
                    # NEW: Historical Market Breadth NSE Append
                    # ----------------------------------------
                    breadth_tracker_df = pd.DataFrame([{
                        "Date": today_date_str,
                        "trend_regime": trend_label
                    }])
                    save_db_with_retry(breadth_tracker_df, "Historical Market breadth NSE", engine, if_exists="append", index=False)
                    print("     ✅ Appended today's regime to 'Historical Market breadth NSE'.")

                else:
                    print("     ⚠️ Not enough history to calculate rolling averages yet.")
            except Exception as e:
                print(f"     ❌ Trend Engine Error: {e}")

        # ==========================================
        # NEW: Execute Microcap 250 Engine
        # ==========================================
        scrape_nifty_microcap_250(engine, merged_df)

        # ==========================================
        # STEP 6: PUSH DATA BACK TO CLOUD TABLES
        # ==========================================
        current_module = "Database Uploads"
        print("\n📦 STEP 6: Delivering all final data to Supabase (Chunked Upload)...")
        
        save_db_with_retry(merged_df, "stock_master", engine, if_exists="replace", index=False, chunksize=500, method='multi')
        print(f"   ✅ 'stock_master' overwritten successfully ({len(merged_df)} rows).")
        
        if not ath_df.empty:
            save_db_with_retry(ath_df, "ATH_Analysis", engine, if_exists="replace", index=False, chunksize=500, method='multi')
            print(f"   ✅ 'ATH_Analysis' overwritten successfully with new columns.")
            
        if not sector_summary_df.empty:
            save_db_with_retry(sector_summary_df, "ATH_Sector_Analysis", engine, if_exists="replace", index=False, chunksize=500, method='multi')
            print(f"   ✅ 'ATH_Sector_Analysis' overwritten successfully.")
            
        if not industry_summary_df.empty:
            save_db_with_retry(industry_summary_df, "ATH_Industry_Analysis", engine, if_exists="replace", index=False, chunksize=500, method='multi')
            print(f"   ✅ 'ATH_Industry_Analysis' overwritten successfully.")

        # ----------------------------------------
        # NEW: ATH Historical Tracker (NSE Stocks)
        # ----------------------------------------
        if is_weekday and not is_time_locked and not is_nse_holiday:
            print("\n📈 STEP 6.1: Calculating and Saving ATH % to Tracker...")
            total_nse = len(merged_df[merged_df['Exchange'].astype(str).str.strip().str.upper().isin(['NSE', 'NSE SME'])])
            
            if not ath_df.empty:
                total_ath_nse = len(ath_df[ath_df['Exchange'].astype(str).str.strip().str.upper().isin(['NSE', 'NSE SME'])])
                ath_percent = round((total_ath_nse / total_nse) * 100, 2) if total_nse > 0 else 0
            else:
                ath_percent = 0
            
            ath_tracker_df = pd.DataFrame([{
                "Date": today_date_str,
                "ATH_Percent": ath_percent
            }])
            save_db_with_retry(ath_tracker_df, "ATH_historical_Tracker", engine, if_exists="append", index=False)
            print(f"   ✅ Appended ATH % ({ath_percent}%) to 'ATH_historical_Tracker'.")

        # ==========================================
        # STEP 7: PULL EXACT 20-MONTH CNXSMALLCAP ROC
        # ==========================================
        current_module = "CNXSMALLCAP ROC Engine"
        print("\n📈 STEP 7: Fetching Exact-Date 20-Month ROC for CNXSMALLCAP...")

        try:
            tv = TvDatafeed()
            tv_data = None
            for attempt in range(1, 4):
                try:
                    tv_data = tv.get_hist(symbol='CNXSMALLCAP', exchange='NSE', interval=Interval.in_daily, n_bars=1000)
                    if tv_data is not None and not tv_data.empty:
                        break
                except Exception as e:
                    print(f"   ⚠️ CNXSMALLCAP fetch attempt {attempt}/3 failed: {e}")
                    if attempt < 3: time.sleep(5)

            if tv_data is not None and not tv_data.empty:
                tv_data = tv_data.sort_index()
                current_date = tv_data.index[-1]
                current_close = float(tv_data['close'].iloc[-1])
                target_date = current_date - pd.DateOffset(months=20)
                historical_data = tv_data[tv_data.index <= target_date]

                if not historical_data.empty:
                    past_date = historical_data.index[-1]
                    past_close = float(historical_data['close'].iloc[-1])
                    roc_20m = round(((current_close - past_close) / past_close) * 100, 2)

                    print(f"   Current Date: {current_date.date()} | Close: {current_close}")
                    print(f"   Target Date (20M Ago): {target_date.date()} | Past Close: {past_close}")
                    print(f"   Exact 20M ROC: {roc_20m}%")

                    roc_timestamp = pd.Timestamp.now(tz='Asia/Kolkata').strftime('%Y-%m-%d %H:%M:%S')
                    roc_df = pd.DataFrame([{
                        "Date": roc_timestamp,
                        "Symbol": "CNXSMALLCAP",
                        "Current_Date": str(current_date.date()),
                        "Past_Date": str(past_date.date()),
                        "Current_Price": current_close,
                        "Price_20_Months_Ago": past_close,
                        "ROC_20M_Percent": roc_20m
                    }])

                    save_db_with_retry(roc_df, "CNXSMALLCAP_ROC", engine, if_exists="append", index=False)
                    print("   ✅ 'CNXSMALLCAP_ROC' updated successfully.")
                else:
                    print("   ⚠️ Not enough history to calculate 20M ROC.")
            else:
                raise Exception("Failed to fetch CNXSMALLCAP data after 3 attempts.")
        except Exception as e:
            print(f"   ❌ ERROR during CNXSMALLCAP ROC calculation: {e}")
            
        # ==========================================
        # STEP 8: DOWNLOAD & RANK ETFS (NEW & UPDATED)
        # ==========================================
        current_module = "ETF Screener Engine"
        download_and_rank_etfs()      # India ETF with expense ratio
        download_usa_etfs(engine)     # New USA ETF scraper mapping
        
        # ==========================================
        # SUCCESS LOGGING
        # ==========================================
        current_module = "Sync Success"
        log_sync_status(engine, status="SUCCESS", failed_module="None")
        print("\n" + "="*60)
        print("🎉 SUCCESS: Entire daily pipeline finished without errors!")
        print("="*60 + "\n")

    except Exception as fatal_err:
        print(f"\n❌ FATAL SCRIPT CRASH in module [{current_module}]: {fatal_err}")
        log_sync_status(engine, status="ERROR", failed_module=current_module)
        raise fatal_err  # Re-raise to trigger the global retry wrapper


if __name__ == "__main__":
    max_script_retries = 3
    retry_delay_seconds = 60  
    
    for global_attempt in range(1, max_script_retries + 1):
        try:
            run_daily_scraper()
            break  
        except Exception as global_error:
            print(f"\n⚠️ GLOBAL EXCEPTION CAUGHT: Pipeline crashed during attempt {global_attempt}/{max_script_retries}.")
            if global_attempt < max_script_retries:
                print(f"⏳ Waiting {retry_delay_seconds} seconds before executing full system reboot...")
                time.sleep(retry_delay_seconds)
            else:
                print("\n❌ ALL GLOBAL RETRIES EXHAUSTED. Script terminated completely.")
                sys.exit(1)
