import requests
import time
import random
import re
import pandas as pd
import numpy as np
import io  
import os
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
    print("🚀 STARTING: Cloud-Native Screener (Exact Header Match Edition)")
    
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    
    # ==========================================
    # STEP 1: FETCH STATIC DB MAP (Extracting ONLY static columns)
    # ==========================================
    print("🧠 Reading existing 'sector_master' to build memory cache...")
    try:
        static_df = pd.read_sql("SELECT * FROM sector_master", engine)
        
        # Flexibly find exact column names from your uploaded CSV, accounting for double spaces
        col_n = next((c for c in static_df.columns if str(c).strip().lower() == 'name'), 'Name')
        col_t = next((c for c in static_df.columns if str(c).strip().lower() == 'ticker'), 'Ticker')
        col_s = next((c for c in static_df.columns if str(c).strip().lower() == 'sector'), 'Sector')
        col_i = next((c for c in static_df.columns if 'industry' in str(c).lower()), 'Broad Industry')
        col_e = next((c for c in static_df.columns if 'exchange' in str(c).lower()), 'Exchange')
        col_ath = next((c for c in static_df.columns if 'alltime' in str(c).lower() or 'ath' in str(c).lower()), 'Alltime High  Rs.')
        
        # Keep ONLY the static mapping columns so we don't accidentally merge old prices
        cols_to_keep = [c for c in [col_n, col_t, col_s, col_i, col_e, col_ath] if c in static_df.columns]
        static_subset = static_df[cols_to_keep].copy()
        
        # Rename them internally so the merge is flawless
        static_subset.columns = ['Name', 'Ticker', 'Sector', 'Broad Industry', 'Exchange', 'Static_ATH']
        static_subset['Name'] = static_subset['Name'].astype(str).str.strip()
        
        known_names = set(static_subset['Name'].tolist())
        print(f"✅ Loaded {len(known_names)} existing companies into memory.")
    except Exception as e:
        print(f"⚠️ Could not load cache: {e}")
        known_names = set()
        static_subset = pd.DataFrame(columns=['Name', 'Ticker', 'Sector', 'Broad Industry', 'Exchange', 'Static_ATH'])

    if 'Exchange' not in static_subset.columns:
        static_subset['Exchange'] = "NSE"

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
    live_names = set(live_df['Name'].tolist())
    missing_names = [n for n in live_names if n not in known_names]
    
    if missing_names:
        missing_df = live_df[live_df['Name'].isin(missing_names)].drop_duplicates(subset=['Name'])
        print(f"\n🔍 Found {len(missing_df)} NEW companies. Deep scraping...")
        new_records = []
        
        for idx, row in missing_df.iterrows():
            stock_name = row['Name']
            code = row['live_ticker_slug']
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
                
            # Appending to Sector Master with the EXACT original column headers from the DB
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
            print("☁️ Appending new companies permanently to 'sector_master'...")
            try:
                new_static_df.to_sql("sector_master", engine, if_exists="append", index=False)
                print("✅ 'sector_master' updated with new companies.")
                
                # Update memory cache dynamically
                new_static_mapped = pd.DataFrame({
                    'Name': [r.get(original_col_n) for r in new_records],
                    'Ticker': [r.get(original_col_t) for r in new_records],
                    'Sector': [r.get(original_col_s) for r in new_records],
                    'Broad Industry': [r.get(original_col_i) for r in new_records],
                    'Exchange': [r.get(original_col_e) for r in new_records],
                    'Static_ATH': [np.nan for _ in new_records]
                })
                static_subset = pd.concat([static_subset, new_static_mapped], ignore_index=True)
            except Exception as e:
                print(f"❌ Failed to append to sector_master: {e}")
    else:
        print("\n✅ No new companies found. Database is perfectly synced.")

    # ==========================================
    # STEP 4: MERGE, CLEAN, & CALCULATE MOMENTUM
    # ==========================================
    print("🥞 Merging live data with full sector cache...")
    
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
        live_df['Relative score'] = momentum_score.where(valid_mask, np.nan)
    else:
        live_df['Relative score'] = np.nan

    # Throw away the raw URL slug 
    live_df = live_df.drop(columns=['live_ticker_slug'])
    
    # Merge on the 'Name' column precisely
    merged_df = pd.merge(live_df, static_subset, on='Name', how='left')
    merged_df = merged_df.loc[:, ~merged_df.columns.duplicated()].copy()

    # ==========================================
    # STEP 5: SECTOR & INDUSTRY ATH (Excluding SMEs)
    # ==========================================
    print("📊 Calculating Sector and Industry ATH Rankings (Filtering out SMEs)...")
    
    col_cmp = next((c for c in merged_df.columns if 'cmp' in c.lower()), None)
    
    sector_summary_df = pd.DataFrame()
    industry_summary_df = pd.DataFrame()
    
    if col_cmp and 'Static_ATH' in merged_df.columns:
        merged_df['Static_ATH'] = pd.to_numeric(merged_df['Static_ATH'], errors='coerce')
        merged_df[col_cmp] = pd.to_numeric(merged_df[col_cmp], errors='coerce')
        
        merged_df['is_ath'] = merged_df[col_cmp] >= (0.9 * merged_df['Static_ATH'])
        analysis_df = merged_df[~merged_df['Exchange'].astype(str).str.contains('SME', case=False, na=False)].copy()

        def build_summary_table(df, group_col):
            valid_df = df[(df[group_col] != "Unknown") & (df[group_col].notna())]
            if valid_df.empty: return pd.DataFrame()
            summary = valid_df.groupby(group_col).agg(
                Total_Stocks=('is_ath', 'count'), ATH_Stocks=('is_ath', 'sum')
            ).reset_index()
            summary['ATH %'] = (summary['ATH_Stocks'] / summary['Total_Stocks'] * 100).round(2)
            summary = summary.sort_values(by='ATH %', ascending=False).reset_index(drop=True)
            summary['Rank'] = summary.index + 1
            return summary

        sector_summary_df = build_summary_table(analysis_df, 'Sector')
        industry_summary_df = build_summary_table(analysis_df, 'Broad Industry')
        
        # Drop temporary ATH variables so they don't clutter the main table
        merged_df = merged_df.drop(columns=['Static_ATH', 'is_ath'])

    # ==========================================
    # STEP 6: PUSH TO SUPABASE & LOG TIMESTAMP
    # ==========================================
    print("☁️ Pushing final tables to Supabase with exact Google Sheets Formatting...")
    try:
        # Pushing stock_master with exact Capital Letters and Spaces preserved!
        merged_df.to_sql("stock_master", engine, if_exists="replace", index=False)
        print("✅ 'stock_master' overwritten successfully.")
        
        if not sector_summary_df.empty:
            sector_summary_df.to_sql("sector_analysis", engine, if_exists="replace", index=False)
            
        if not industry_summary_df.empty:
            industry_summary_df.to_sql("industry_analysis", engine, if_exists="replace", index=False)
            
        # --- NEW CODE: Stamp the exact completion time in IST ---
        sync_df = pd.DataFrame([{"last_sync": pd.Timestamp.now(tz='Asia/Kolkata').strftime('%d %b %Y, %I:%M %p')}])
        sync_df.to_sql("sync_log", engine, if_exists="replace", index=False)
        print("✅ Timestamp successfully logged in sync_log.")
        # --------------------------------------------------------
            
    except Exception as e:
        print(f"❌ Database push failed: {e}")

    print("🎉 ALL DONE! Daily run complete.")

if __name__ == "__main__":
    run_daily_scraper()
