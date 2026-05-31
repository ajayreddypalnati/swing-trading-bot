import requests
import time
import random
import re
import pandas as pd
import numpy as np
import io  
import os
import urllib.parse
import warnings
from bs4 import BeautifulSoup
from sqlalchemy import create_engine

# Silence terminal spam
warnings.simplefilter(action='ignore', category=FutureWarning)

# --- Cloud Database Setup ---
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("❌ ERROR: No DATABASE_URL found. Check your GitHub Secrets.")
    exit()

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
engine = create_engine(DATABASE_URL)

SCREENER_URL = "https://www.screener.in/screens/3299871/all-screener-stocks/"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Cookie": "csrftoken=cBucGDxR9HDRLquxvu5coW5K84dVl71t; sessionid=agwll5zqzkdpo0lg7xdck2t8tw2a85p2"
}

def random_sleep(min_ms=800, max_ms=2000):
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

def fetch_with_retry(session, url, retries=3):
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200: return resp.text
        except Exception:
            pass
        random_sleep(1000, 3000)
    return None

def run_daily_scraper():
    print("🚀 STARTING: Cloud-Native Deep Screener (Name-Match Edition)")
    
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    
    # ==========================================
    # STEP 1: FETCH STATIC DB MAP (MEMORY CACHE)
    # ==========================================
    print("🧠 Reading existing 'sector_master' to build memory cache...")
    try:
        static_df = pd.read_sql("SELECT * FROM sector_master", engine)
        
        # Dynamically map columns exactly as they appear from Google Sheets
        col_n = next((c for c in static_df.columns if str(c).strip().lower() == 'name'), 'Name')
        col_t = next((c for c in static_df.columns if str(c).strip().lower() == 'ticker'), 'Ticker')
        col_s = next((c for c in static_df.columns if str(c).strip().lower() == 'sector'), 'Sector')
        col_i = next((c for c in static_df.columns if 'industry' in str(c).lower()), 'Broad Industry')
        col_e = next((c for c in static_df.columns if 'exchange' in str(c).lower()), 'Exchange')
        
        # Clean names for perfect matching
        static_df[col_n] = static_df[col_n].astype(str).str.strip()
        known_names = set(static_df[col_n].tolist())
        print(f"✅ Loaded {len(known_names)} existing companies into memory.")
    except Exception as e:
        print(f"⚠️ Could not load cache: {e}")
        known_names = set()
        static_df = pd.DataFrame(columns=['Name', 'Ticker', 'Sector', 'Broad Industry', 'Exchange'])
        col_n, col_t, col_s, col_i, col_e = 'Name', 'Ticker', 'Sector', 'Broad Industry', 'Exchange'

    if col_e not in static_df.columns:
        static_df[col_e] = "NSE"

    # ==========================================
    # STEP 2: FAST LIVE SCRAPE (MAIN TABLES)
    # ==========================================
    first_page = fetch_with_retry(session, SCREENER_URL)
    if not first_page: return
    page_match = re.search(r'Showing page \d+ of (\d+)', first_page)
    total_pages = int(page_match.group(1)) if page_match else 1
    
    all_dataframes = []
    print(f"📄 Scraping {total_pages} live market pages...")
    
    for page in range(1, total_pages + 1):
        page_url = SCREENER_URL if page == 1 else f"{SCREENER_URL}?page={page}"
        html_content = first_page if page == 1 else fetch_with_retry(session, page_url)
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
                
                df['live_ticker_slug'] = codes 
                all_dataframes.append(df)
        except Exception:
            pass
        if page < total_pages: random_sleep(800, 1500)

    if not all_dataframes: return
    live_df = pd.concat(all_dataframes, ignore_index=True)
    
    # ==========================================
    # STEP 3: DEEP SCRAPE MISSING NAMES ONLY
    # ==========================================
    # Compare by NAME, exactly like the Google Sheets script
    live_names = set(live_df['Name'].tolist())
    missing_names = [n for n in live_names if n not in known_names]
    
    if missing_names:
        missing_df = live_df[live_df['Name'].isin(missing_names)].drop_duplicates(subset=['Name'])
        print(f"\n🔍 Found {len(missing_df)} NEW companies. Deep scraping sectors and exchanges...")
        new_records = []
        
        for idx, row in missing_df.iterrows():
            stock_name = row['Name']
            code = row['live_ticker_slug']
            
            print(f"[{len(new_records) + 1}/{len(missing_df)}] Scraping NEW: {stock_name} ({code})")
            url = f"https://www.screener.in/company/{code}/"
            page_html = fetch_with_retry(session, url)
            
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
                
            new_records.append({
                col_n: stock_name,
                col_t: code, 
                col_s: sector, 
                col_i: industry, 
                col_e: exchange_class
            })
            random_sleep(800, 1500)
            
        new_static_df = pd.DataFrame(new_records)
        print("☁️ Appending new companies permanently to 'sector_master'...")
        try:
            new_static_df.to_sql("sector_master", engine, if_exists="append", index=False)
            print("✅ 'sector_master' updated with new companies.")
            static_df = pd.concat([static_df, new_static_df], ignore_index=True)
        except Exception as e:
            print(f"❌ Failed to append to sector_master: {e}")
    else:
        print("\n✅ No new companies found. Database is perfectly synced.")

    # ==========================================
    # STEP 4: MERGE, CLEAN, & CALCULATE MOMENTUM
    # ==========================================
    print("🥞 Merging live data with full sector cache...")
    
    col_g = next((c for c in live_df.columns if '1m' in c.lower() and 'return' in c.lower()), None)
    col_h = next((c for c in live_df.columns if '3m' in c.lower() and 'return' in c.lower()), None)
    col_i = next((c for c in live_df.columns if '6m' in c.lower() and 'return' in c.lower()), None)

    if col_g and col_h and col_i:
        live_df[col_g] = pd.to_numeric(live_df[col_g], errors='coerce')
        live_df[col_h] = pd.to_numeric(live_df[col_h], errors='coerce')
        live_df[col_i] = pd.to_numeric(live_df[col_i], errors='coerce')

        rank_g = live_df[col_g].rank(ascending=False, method='min')
        rank_h = live_df[col_h].rank(ascending=False, method='min')
        rank_i = live_df[col_i].rank(ascending=False, method='min')
        
        momentum_score = (rank_g * 2) + (rank_h * 4) + (rank_i * 4)
        valid_mask = live_df[[col_g, col_h, col_i]].notna().all(axis=1)
        live_df['relative_score'] = momentum_score.where(valid_mask, np.nan)
    else:
        live_df['relative_score'] = np.nan

    # Throw away the raw URL slug and map the data cleanly by Name
    live_df = live_df.drop(columns=['live_ticker_slug'])
    live_df = live_df.rename(columns={'Name': 'name'})
    
    static_subset = static_df[[col_n, col_t, col_s, col_i, col_e]].copy()
    static_subset.columns = ['name', 'ticker', 'sector', 'broad_industry', 'exchange']
    
    merged_df = pd.merge(live_df, static_subset, on='name', how='left')
    merged_df = merged_df.loc[:, ~merged_df.columns.duplicated()].copy()

    # Aggressively clean column names for PostgreSQL
    cleaned_columns = []
    for col in merged_df.columns:
        clean = str(col).lower().strip().replace(" ", "_").replace(".", "").replace("/", "").replace("%", "pct").replace("(", "").replace(")", "").replace("-", "_")
        clean = re.sub(r'_+', '_', clean).strip('_')
        cleaned_columns.append(clean)
    merged_df.columns = cleaned_columns

    # ==========================================
    # STEP 5: SECTOR & INDUSTRY ATH (Excluding SMEs)
    # ==========================================
    print("📊 Calculating Sector and Industry ATH Rankings (Filtering out SMEs)...")
    
    col_cmp = next((c for c in merged_df.columns if 'cmp' in c), None)
    col_ath = next((c for c in static_df.columns if 'alltime' in str(c).lower() or 'ath' in str(c).lower()), None)
    
    sector_summary_df = pd.DataFrame()
    industry_summary_df = pd.DataFrame()
    
    if col_cmp and col_ath:
        # Pull static ATH by Name
        merged_df['temp_ath'] = pd.to_numeric(merged_df['name'].map(static_df.set_index(col_n)[col_ath]), errors='coerce')
        merged_df[col_cmp] = pd.to_numeric(merged_df[col_cmp], errors='coerce')
        
        merged_df['is_ath'] = merged_df[col_cmp] >= (0.9 * merged_df['temp_ath'])
        analysis_df = merged_df[~merged_df['exchange'].astype(str).str.contains('SME', case=False, na=False)].copy()

        def build_summary_table(df, group_col):
            valid_df = df[(df[group_col] != "Unknown") & (df[group_col].notna())]
            if valid_df.empty: return pd.DataFrame()
            summary = valid_df.groupby(group_col).agg(
                total_stocks=('is_ath', 'count'), ath_stocks=('is_ath', 'sum')
            ).reset_index()
            summary['ath_pct'] = (summary['ath_stocks'] / summary['total_stocks'] * 100).round(2)
            summary = summary.sort_values(by='ath_pct', ascending=False).reset_index(drop=True)
            summary['rank'] = summary.index + 1
            return summary

        sector_summary_df = build_summary_table(analysis_df, 'sector')
        industry_summary_df = build_summary_table(analysis_df, 'broad_industry')
        
        merged_df = merged_df.drop(columns=['temp_ath', 'is_ath'])

    # ==========================================
    # STEP 6: PUSH TO SUPABASE
    # ==========================================
    print("☁️ Pushing final overridden tables to Supabase...")
    try:
        merged_df.to_sql("stock_master", engine, if_exists="replace", index=False)
        print("✅ 'stock_master' overwritten successfully.")
        
        if not sector_summary_df.empty:
            sector_summary_df.to_sql("sector_analysis", engine, if_exists="replace", index=False)
            
        if not industry_summary_df.empty:
            industry_summary_df.to_sql("industry_analysis", engine, if_exists="replace", index=False)
            
    except Exception as e:
        print(f"❌ Database push failed: {e}")

    print("🎉 ALL DONE! Daily run complete.")

if __name__ == "__main__":
    run_daily_scraper()
