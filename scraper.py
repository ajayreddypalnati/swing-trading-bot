import requests
import time
import random
import re
import pandas as pd
import io  
import os
import warnings
from bs4 import BeautifulSoup
from sqlalchemy import create_engine

warnings.simplefilter(action='ignore', category=FutureWarning)

# --- Cloud Database Setup ---
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "postgresql://postgres.yourproject:yourpassword@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
engine = create_engine(DATABASE_URL)

SCREENER_URL = "https://www.screener.in/screens/3299871/all-screener-stocks/"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Cookie": "csrftoken=cBucGDxR9HDRLquxvu5coW5K84dVl71t; sessionid=agwll5zqzkdpo0lg7xdck2t8tw2a85p2"
}

def random_sleep():
    time.sleep(random.uniform(0.8, 2.0))

def fetch_with_retry(session, url, retries=3):
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200: return resp.text
        except Exception:
            pass
        random_sleep()
    return None

def run_daily_scraper():
    print("🚀 STARTING: Daily Deep Screener (Supabase Edition)")
    
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    first_page = fetch_with_retry(session, SCREENER_URL)
    if not first_page: return

    page_match = re.search(r'Showing page \d+ of (\d+)', first_page)
    total_pages = int(page_match.group(1)) if page_match else 1
    
    all_dataframes = []
    print(f"📄 Found {total_pages} pages to scrape...")
    
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
        random_sleep()

    final_df = pd.concat(all_dataframes, ignore_index=True)
    
    # NOTE: Since you do a deep scrape to get Sector/Industry, ensure that logic is applied to final_df here.
    # For now, we ensure the required columns exist for the database.
    if 'Sector' not in final_df.columns: final_df['Sector'] = "Unknown"
    if 'Broad Industry' not in final_df.columns: final_df['Broad Industry'] = "Unknown"
    if 'Exchange' not in final_df.columns: final_df['Exchange'] = "NSE"

    # --- PUSH DIRECTLY TO SUPABASE (No Google Sheets) ---
    print("\n☁️ Pushing master data to Cloud Database...")
    try:
        master_df = final_df[['Ticker', 'Sector', 'Broad Industry']].copy()
        
        # Add a mock relative score column if needed for your strategy
        master_df['Relative score'] = 99 
        
        # Clean column names for PostgreSQL standard (lowercase, no spaces)
        master_df.columns = ['ticker', 'sector', 'broad_industry', 'relative_score']
        
        # This one line creates/replaces the table in Supabase instantly
        master_df.to_sql("stock_master", engine, if_exists="replace", index=False)
        print("✅ Cloud Database 'stock_master' updated successfully.")
    except Exception as e:
        print(f"❌ Failed to push to Cloud DB: {e}")

if __name__ == "__main__":
    run_daily_scraper()