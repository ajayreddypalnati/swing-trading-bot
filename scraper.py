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

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
warnings.simplefilter(action='ignore', category=FutureWarning)

# ==========================================
# 0. CREDENTIALS & DATABASE CONFIG
# ==========================================
SCREENER_EMAIL = "ajayreddypalnati@gmail.com"
SCREENER_PASSWORD = "sunnyreddi999@AA"

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("\n❌ FATAL ERROR: DATABASE_URL environment variable is missing.")
    sys.exit(1)

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
if "?pgbouncer=true" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("?pgbouncer=true", "")

try:
    print("\n🔌 SYSTEM: Connecting to Supabase Cloud Database...")
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)
    print("✅ SYSTEM: Database connection established.")
except Exception as e:
    print(f"❌ FATAL ERROR: Could not connect to database: {e}")
    sys.exit(1)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ==========================================
# HELPER FUNCTIONS (Auth & Fetch)
# ==========================================
def get_fresh_screener_cookies(email, password):
    print("\n🤖 AUTO-LOGIN: Launching invisible browser to authenticate...")
    cookie_string = ""
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
            
            if session: print("   ✅ Login successful!")
            else: 
                print("   ❌ WARNING: Login failed.")
                sys.exit(1)
            
            cookie_string = f"csrftoken={csrf}; sessionid={session}"
            browser.close()
    except Exception as e:
        print(f"   ❌ Auto-login script crashed: {e}")
        sys.exit(1)
    return cookie_string

def random_sleep(min_ms=800, max_ms=2000):
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

def fetch_with_retry(session, url, retries=3):
    headers = {
        "User-Agent": USER_AGENT,
        "Cookie": session.screener_cookies
    }
    for _ in range(retries):
        try:
            resp = session.get(url, headers=headers, timeout=15)
            if resp.status_code == 200: return resp.text
            elif resp.status_code == 429: time.sleep(15)
        except Exception: pass
        random_sleep(1500, 3500)
    return None

def build_summary_table(df, group_col):
    valid_df = df[(df[group_col] != "Unknown") & (df[group_col].notna())]
    if valid_df.empty: return pd.DataFrame()
    summary = valid_df.groupby(group_col).agg(Total_Stocks=('is_ath', 'count'), ATH_Stocks=('is_ath', 'sum')).reset_index()
    summary['ATH %'] = (summary['ATH_Stocks'] / summary['Total_Stocks'] * 100).round(2)
    summary = summary.sort_values(by='ATH %', ascending=False).reset_index(drop=True)
    summary['Rank'] = summary.index + 1
    return summary

# ==========================================
# MAIN TEST LOGIC
# ==========================================
def run_test_script():
    print("\n" + "="*60)
    print("🚀 STARTING: Standalone ATH & Sector Logic Test")
    print("="*60)
    
    fresh_cookies = get_fresh_screener_cookies(SCREENER_EMAIL, SCREENER_PASSWORD)
    session = requests.Session()
    session.screener_cookies = fresh_cookies

    # ---------------------------------------------------------
    # STEP 1: SCRAPE ATH SCREENER (ALL COLUMNS)
    # ---------------------------------------------------------
    print("\n📥 STEP 1: Scraping full data from ATH Screener...")
    ath_url = "https://www.screener.in/screens/3315507/ath-sector-analysis/"
    first_page = fetch_with_retry(session, ath_url)
    
    if not first_page:
        print("   ❌ Failed to reach ATH Screener.")
        return

    page_match = re.search(r'Showing page \d+ of (\d+)', first_page)
    total_pages = int(page_match.group(1)) if page_match else 1
    print(f"   📋 Found {total_pages} pages of ATH stocks. Downloading...")
    
    ath_dataframes = []
    
    for page in range(1, total_pages + 1):
        p_url = ath_url if page == 1 else f"{ath_url}?page={page}"
        html_content = first_page if page == 1 else fetch_with_retry(session, p_url)
        
        if html_content:
            try:
                tables = pd.read_html(io.StringIO(html_content), thousands=',')
                if tables:
                    df = tables[0]
                    # Drop recurring header rows
                    df = df[df['Name'] != 'Name'].copy() 
                    df['Name'] = df['Name'].astype(str).str.strip()
                    ath_dataframes.append(df)
            except Exception as e:
                print(f"      ⚠️ ERROR parsing page {page}: {e}")
                
        if page % 2 == 0 or page == total_pages:
            print(f"      -> Processed {page}/{total_pages} pages...")
        if page < total_pages: random_sleep(1000, 2000)

    ath_df = pd.concat(ath_dataframes, ignore_index=True)
    
    # Drop the redundant 'Is not SME' column as requested
    if 'Is not SME' in ath_df.columns:
        ath_df = ath_df.drop(columns=['Is not SME'])
        
    print(f"   ✅ Collected detailed data for {len(ath_df)} ATH companies.")

    # ---------------------------------------------------------
    # STEP 2: LOAD MAIN TABLE & APPLY NEW SME LOGIC
    # ---------------------------------------------------------
    print("\n📚 STEP 2: Loading 'stock_master' & Filtering SMEs...")
    try:
        stock_master_df = pd.read_sql("SELECT * FROM stock_master", engine)
        print(f"   ✅ Loaded {len(stock_master_df)} rows from stock_master.")
    except Exception as e:
        print(f"   ❌ Failed to load stock_master: {e}")
        return

    # NEW LOGIC: Look specifically at the "Is SME" column to filter out SMEs (Value '1' = SME)
    sme_col = next((c for c in stock_master_df.columns if str(c).strip().lower() == 'is sme'), None)
    
    if sme_col:
        analysis_df = stock_master_df[stock_master_df[sme_col].astype(str).str.strip() != '1'].copy()
        print(f"   🧹 Filtered out SMEs using '{sme_col}' column. {len(analysis_df)} Mainboard stocks remain.")
    else:
        print("   ⚠️ WARNING: 'Is SME' column not found in stock_master! Proceeding without SME filtering.")
        analysis_df = stock_master_df.copy()

    # ---------------------------------------------------------
    # STEP 3: ACCURATE CROSS-REFERENCE & SECTOR/INDUSTRY CALC
    # ---------------------------------------------------------
    print("\n🧮 STEP 3: Cross-referencing stocks & calculating sector breadth...")
    
    # --- NEW VLOOKUP LOGIC ---
    # Merge (VLOOKUP) Ticker, Sector, Broad Industry, and Exchange from stock_master to ath_df
    cols_to_pull = ['Name', 'Ticker', 'Sector', 'Broad Industry', 'Exchange']
    existing_cols = [c for c in cols_to_pull if c in stock_master_df.columns]
    
    # Perform a left join so every scraped ATH stock gets its matching sector data attached
    ath_df = pd.merge(ath_df, stock_master_df[existing_cols], on='Name', how='left')
    print("   ✅ Performed VLOOKUP to add Sector, Industry, Ticker, and Exchange to ATH_Analysis.")
    # -------------------------

    # Flag the mainboard stocks if their name appears in the ATH list
    ath_names = set(ath_df['Name'].tolist())
    analysis_df['is_ath'] = analysis_df['Name'].astype(str).str.strip().isin(ath_names)

    col_sector = next((c for c in analysis_df.columns if str(c).strip().lower() == 'sector'), 'Sector')
    col_industry = next((c for c in analysis_df.columns if 'industry' in str(c).lower()), 'Broad Industry')

    sector_summary_df = build_summary_table(analysis_df, col_sector)
    industry_summary_df = build_summary_table(analysis_df, col_industry)
    
    print("   ✅ Accurate Sector and Industry rankings generated.")

    # ---------------------------------------------------------
    # STEP 4: UPLOAD EVERYTHING TO SUPABASE
    # ---------------------------------------------------------
    print("\n📦 STEP 4: Uploading test data to Supabase...")
    try:
        # 1. Upload the raw scraped ATH data with all columns + the new mapped Sector/Industry columns
        ath_df.to_sql("ATH_Analysis", engine, if_exists="replace", index=False, chunksize=500, method='multi')
        print(f"   ✅ 'ATH_Analysis' created/overwritten successfully with new columns.")

        # 2. Upload the recalculated Sector/Industry tables
        if not sector_summary_df.empty:
            sector_summary_df.to_sql("ATH_Sector_Analysis", engine, if_exists="replace", index=False)
            print("   ✅ 'ATH_Sector_Analysis' updated.")
            
        if not industry_summary_df.empty:
            industry_summary_df.to_sql("ATH_Industry_Analysis", engine, if_exists="replace", index=False)
            print("   ✅ 'ATH_Industry_Analysis' updated.")

    except Exception as e:
        print(f"   ❌ Failed to upload data to Supabase: {e}")

    print("\n🎉 TEST COMPLETE! Check your Supabase database to verify the tables.")

if __name__ == "__main__":
    run_test_script()
