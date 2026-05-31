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
    print("🚀 STARTING: Cloud-Native Deep Screener")
    
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    first_page = fetch_with_retry(session, SCREENER_URL)
    if not first_page: return

    page_match = re.search(r'Showing page \d+ of (\d+)', first_page)
    total_pages = int(page_match.group(1)) if page_match else 1
    
    all_dataframes = []
    print(f"📄 Found {total_pages} pages to scrape...")
    
    # ==========================================
    # STEP 1: FAST LIVE SCRAPE
    # ==========================================
    for page in range(1, total_pages + 1):
        page_url = SCREENER_URL if page == 1 else f"{SCREENER_URL}?page={page}"
        html_content = first_page if page == 1 else fetch_with_retry(session, page_url)
        if not html_content: continue
        
        try:
            tables = pd.read_html(io.StringIO(html_content), thousands=',')
            if tables:
                df = tables[0]
                df = df[df['Name'] != 'Name'].copy()
                
                # Extract Tickers from the HTML links
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
                
                df['Ticker'] = codes
                all_dataframes.append(df)
        except Exception as e:
            print(f"❌ Parse error page {page}: {e}")
            
        if page < total_pages: random_sleep()

    final_df = pd.concat(all_dataframes, ignore_index=True)
    
    # ==========================================
    # STEP 2: CALCULATE MOMENTUM SCORE
    # ==========================================
    print("🧮 Calculating Relative Momentum Scores...")
    col_g = next((c for c in final_df.columns if '1m' in c.lower() and 'return' in c.lower()), None)
    col_h = next((c for c in final_df.columns if '3m' in c.lower() and 'return' in c.lower()), None)
    col_i = next((c for c in final_df.columns if '6m' in c.lower() and 'return' in c.lower()), None)

    if col_g and col_h and col_i:
        final_df[col_g] = pd.to_numeric(final_df[col_g], errors='coerce')
        final_df[col_h] = pd.to_numeric(final_df[col_h], errors='coerce')
        final_df[col_i] = pd.to_numeric(final_df[col_i], errors='coerce')

        rank_g = final_df[col_g].rank(ascending=False, method='min')
        rank_h = final_df[col_h].rank(ascending=False, method='min')
        rank_i = final_df[col_i].rank(ascending=False, method='min')
        
        momentum_score = (rank_g * 2) + (rank_h * 4) + (rank_i * 4)
        valid_mask = final_df[[col_g, col_h, col_i]].notna().all(axis=1)
        final_df['Relative score'] = momentum_score.where(valid_mask, np.nan)
    else:
        final_df['Relative score'] = np.nan

    # ==========================================
    # STEP 3: MERGE STATIC SECTORS FROM SUPABASE
    # ==========================================
    print("🔍 Fetching static sector and industry mappings from Supabase...")
    try:
        sector_master_df = pd.read_sql("SELECT ticker, sector, broad_industry FROM sector_master", engine)
        sector_master_df['ticker'] = sector_master_df['ticker'].astype(str).str.strip().str.upper()
    except Exception as e:
        print(f"⚠️ Could not read 'sector_master' table. Error: {e}")
        sector_master_df = pd.DataFrame(columns=['ticker', 'sector', 'broad_industry'])

    print("🥞 Merging live metrics with sector mappings...")
    final_df['Ticker'] = final_df['Ticker'].astype(str).str.strip().str.upper()
    
    # Join the live data with the static Supabase table
    merged_df = pd.merge(final_df, sector_master_df, left_on='Ticker', right_on='ticker', how='left')
    
    # Fill missing sectors just in case
    merged_df['sector'] = merged_df['sector'].fillna('Unknown')
    merged_df['broad_industry'] = merged_df['broad_industry'].fillna('Unknown')

    # Clean all column names for PostgreSQL
    cleaned_columns = []
    for col in merged_df.columns:
        clean = col.lower().strip().replace(" ", "_").replace(".", "").replace("/", "").replace("%", "pct").replace("(", "").replace(")", "").replace("-", "_")
        cleaned_columns.append(clean)
    merged_df.columns = cleaned_columns

    if 'ticker_x' in merged_df.columns:
        merged_df = merged_df.rename(columns={'ticker_x': 'ticker'}).drop(columns=['ticker_y'])

    # ==========================================
    # STEP 4: SECTOR & INDUSTRY ATH ANALYSIS
    # ==========================================
    print("📊 Calculating Sector and Industry ATH Rankings...")
    try:
        col_cmp = next(c for c in merged_df.columns if 'cmp' in c.lower())
        col_ath = next(c for c in merged_df.columns if 'alltime' in c.lower() or 'ath' in c.lower())
        
        # Convert to numeric to be safe
        merged_df[col_cmp] = pd.to_numeric(merged_df[col_cmp], errors='coerce')
        merged_df[col_ath] = pd.to_numeric(merged_df[col_ath], errors='coerce')

        # Create ATH boolean mask (CMP >= 90% of ATH)
        merged_df['is_ath'] = merged_df[col_cmp] >= (0.9 * merged_df[col_ath])

        def build_summary_table(df, group_col):
            # Ignore stocks missing a sector
            valid_df = df[df[group_col] != "Unknown"]
            summary = valid_df.groupby(group_col).agg(
                total_stocks=('is_ath', 'count'),
                ath_stocks=('is_ath', 'sum')
            ).reset_index()
            
            summary['ath_pct'] = (summary['ath_stocks'] / summary['total_stocks'] * 100).round(2)
            summary = summary.sort_values(by='ath_pct', ascending=False).reset_index(drop=True)
            summary['rank'] = summary.index + 1
            return summary

        sector_summary_df = build_summary_table(merged_df, 'sector')
        industry_summary_df = build_summary_table(merged_df, 'broad_industry')
        
    except Exception as e:
        print(f"❌ Error calculating Sector Analysis: {e}")
        sector_summary_df = pd.DataFrame()
        industry_summary_df = pd.DataFrame()

    # ==========================================
    # STEP 5: PUSH TO SUPABASE
    # ==========================================
    print("☁️ Pushing final tables to Supabase...")
    try:
        # Push Main Table
        merged_df.to_sql("stock_master", engine, if_exists="replace", index=False)
        print("✅ 'stock_master' updated.")
        
        # Push Sector Summary (Your old Column X)
        if not sector_summary_df.empty:
            sector_summary_df.to_sql("sector_analysis", engine, if_exists="replace", index=False)
            print("✅ 'sector_analysis' updated.")
            
        # Push Industry Summary
        if not industry_summary_df.empty:
            industry_summary_df.to_sql("industry_analysis", engine, if_exists="replace", index=False)
            print("✅ 'industry_analysis' updated.")
            
    except Exception as e:
        print(f"❌ Database push failed: {e}")

    print("🎉 ALL DONE! Daily run complete.")

if __name__ == "__main__":
    run_daily_scraper()
