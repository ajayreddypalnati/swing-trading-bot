import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import time
from datetime import datetime
import streamlit as st
import re
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

st.set_page_config(page_title="9-EMA Swing Screener", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# --- CSS INJECTION (Same as before) ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
        #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
        .block-container { padding-top: 1.5rem; padding-bottom: 0rem; max-width: 98%; }
        [data-testid="stMetric"] { background: linear-gradient(145deg, rgba(128, 128, 128, 0.05) 0%, rgba(128, 128, 128, 0.02) 100%); border-radius: 12px; padding: 20px; text-align: center; border: 1px solid rgba(128, 128, 128, 0.15); box-shadow: 0 4px 6px rgba(0,0,0,0.02); transition: all 0.3s ease; }
        [data-testid="stTable"] table { width: 100%; border-collapse: collapse; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        [data-testid="stTable"] th { background-color: rgba(128, 128, 128, 0.08) !important; text-align: center !important; font-size: 0.85rem; padding: 15px !important; }
        [data-testid="stTable"] td { text-align: center !important; padding: 12px !important; border-bottom: 1px solid rgba(128, 128, 128, 0.1) !important; }
        .blob.green { background: rgba(39, 174, 96, 1); border-radius: 50%; margin: 8px; height: 12px; width: 12px; animation: pulse-green 2s infinite; display: inline-block; }
        .blob.red { background: rgba(231, 76, 60, 1); border-radius: 50%; margin: 8px; height: 12px; width: 12px; animation: pulse-red 2s infinite; display: inline-block; }
        @keyframes pulse-green { 0% { transform: scale(0.95); } 70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(39, 174, 96, 0); } 100% { transform: scale(0.95); } }
        @keyframes pulse-red { 0% { transform: scale(0.95); } 70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(231, 76, 60, 0); } 100% { transform: scale(0.95); } }
    </style>
""", unsafe_allow_html=True)

# --- APIs ---
CHARTINK_SCREENER_URL = 'https://chartink.com/screener/copy-9-ema-retest-114'
CHARTINK_PROCESS_URL = 'https://chartink.com/screener/process'
CHARTINK_SCAN_CLAUSE = "( {cash} (  daily high >  daily ema(  daily close , 9 ) and  daily low <  daily ema(  daily close , 9 ) and  daily close >  daily ema(  daily close , 9 ) and  daily close >  1 month ago close * 1.1 and  daily close >  1 day ago max( 300 ,  daily high ) * 0.9 and  market cap >=  500 and  daily rsi( 14 ) >=  65 and  daily \"close - 1 candle ago close / 1 candle ago close * 100\" >  0 and  daily \"close - 1 candle ago close / 1 candle ago close * 100\" <  5 and  daily volume * daily close >=  10000000 ) )"

TV_URL = 'https://scanner.tradingview.com/india/scan'
TV_HEADERS = { 'User-Agent': 'Mozilla/5.0', 'Origin': 'https://www.tradingview.com', 'Content-Type': 'application/json' }
TV_PAYLOAD = {
    "columns": ["ticker-view", "close", "type", "typespecs", "change", "volume", "sector.tr", "market", "sector"],
    "filter": [{"left": "Value.Traded", "operation": "greater", "right": 30000000}, {"left": "close", "operation": "in_range%", "right": ["High.All", 0.9, 1]}, {"left": "RSI", "operation": "greater", "right": 65}, {"left": "Perf.1M", "operation": "greater", "right": 10}, {"left": "high", "operation": "greater", "right": "EMA9"}, {"left": "close", "operation": "egreater", "right": "EMA9"}, {"left": "change", "operation": "in_range", "right": [0, 5]}, {"left": "low", "operation": "less", "right": "EMA9"}, {"left": "is_primary", "operation": "equal", "right": True}],
    "options": {"lang": "en"}, "range": [0, 100], "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"}, "markets": ["india"]
}

# ==========================================
# 2. DATA FETCHING (Cloud Only)
# ==========================================
@st.cache_data(ttl=3600) 
def fetch_database_reference():
    """Pulls the Static Master List from Supabase Database"""
    try:
        conn = st.connection("postgresql", type="sql")
        main_df = conn.query("SELECT ticker as \"Ticker\", sector as \"Sector\", broad_industry as \"Broad Industry\", relative_score as \"Relative score\" FROM stock_master")
        return main_df
    except Exception as e:
        st.sidebar.error(f"DB Error: Ensure Secrets are configured. ({e})")
        return pd.DataFrame()

def fetch_chartink_data():
    with requests.Session() as session:
        try:
            resp = session.get(CHARTINK_SCREENER_URL, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            meta_tag = soup.find('meta', {'name': 'csrf-token'})
            if not meta_tag: return []
            headers = {'x-csrf-token': meta_tag['content'], 'x-requested-with': 'XMLHttpRequest'}
            api_response = session.post(CHARTINK_PROCESS_URL, headers=headers, data={'scan_clause': CHARTINK_SCAN_CLAUSE}, timeout=10)
            data = api_response.json()
            if 'data' in data and len(data['data']) > 0:
                df = pd.DataFrame(data['data'])
                return [[row['nsecode'], row['close'], row['per_chg'], row['volume'], 'NSE'] for _, row in df.iterrows()]
            return []
        except Exception:
            return []

def fetch_tradingview_data():
    try:
        response = requests.post(TV_URL, headers=TV_HEADERS, json=TV_PAYLOAD, timeout=10)
        raw_data = response.json().get("data", [])
        formatted_data = []
        for item in raw_data:
            full_ticker = item.get("s", "")
            exchange, clean_name = full_ticker.split(':') if ':' in full_ticker else ("NSE", full_ticker)
            formatted_data.append([clean_name, item["d"][1], item["d"][4], item["d"][5], exchange])
        return formatted_data
    except Exception:
        return []

@st.cache_data(ttl=60)
def get_combined_data():
    chartink_list = fetch_chartink_data()
    tv_list = fetch_tradingview_data()
    tv_list.sort(key=lambda x: 0 if x[4] == 'NSE' else 1)
    
    combined_data, seen_symbols = [], set()
    for row in chartink_list:
        symbol = re.sub(r'\s+', '', str(row[0])).upper()
        combined_data.append(row)
        seen_symbols.add(symbol)
        
    for row in tv_list:
        symbol = re.sub(r'\s+', '', str(row[0])).upper()
        if symbol not in seen_symbols:
            combined_data.append(row)
            seen_symbols.add(symbol)
    return combined_data

# ==========================================
# 3. DASHBOARD UI
# ==========================================
header_col1, header_col2 = st.columns([2, 1])
with header_col1:
    st.markdown("<h1 style='margin-bottom: 0px;'>⚡ 9-EMA Swing Screener</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: gray; font-size: 1.1rem;'>Real-time institutional tracking from <b>Chartink</b> & <b>TradingView</b>.</p>", unsafe_allow_html=True)

with header_col2:
    current_time = datetime.now().strftime('%I:%M:%S %p')
    current_date = datetime.now().strftime('%d %b %Y')
    auto_refresh = st.toggle("⏱️ Auto-Refresh (60s)", value=True)
    dot_color = "green" if auto_refresh else "red"
    status_text = "LIVE DATA" if auto_refresh else "PAUSED"
    st.markdown(f"""
        <div style="text-align: right; margin-top: 5px; color: gray;">
            <span style="font-size: 0.85rem; font-weight: 700; text-transform: uppercase;">
                {status_text} <div class="blob {dot_color}"></div><br>
                <span style="color: #1E88E5; font-size: 1.4rem; font-weight: 800;">{current_time}</span><br>
                <span style="font-size: 0.85rem;">{current_date}</span>
            </span>
        </div>
        """, unsafe_allow_html=True)

st.divider()

with st.spinner("Scanning live markets & syncing with Supabase..."):
    data = get_combined_data()
    main_df = fetch_database_reference()
    
    if data:
        df = pd.DataFrame(data, columns=["Symbol", "Close", "% Change", "Volume", "Exchange"])
        
        # Merge Live Data with Database Master List
        if not main_df.empty:
            df = df.merge(main_df, left_on="Symbol", right_on="Ticker", how="left")
            if 'Sector' in df.columns:
                df['Sec Rank'] = df.groupby('Sector')['Symbol'].transform('count') 
            if 'Broad Industry' in df.columns:
                df['Ind Rank'] = df.groupby('Broad Industry')['Symbol'].transform('count')
        else:
            df['Sector'], df['Broad Industry'], df['Relative score'], df['Sec Rank'], df['Ind Rank'] = "", "", "", "", ""

        for col in ['Sec Rank', 'Ind Rank', 'Relative score']:
            if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')

        if 'Sec Rank' in df.columns and 'Ind Rank' in df.columns:
            valid_mask = (df['Sec Rank'] <= 5) & (df['Ind Rank'] <= 15)
            valid_df = df[valid_mask].copy().sort_values(by=['Sec Rank', 'Ind Rank'], ascending=[True, True])
            valid_df['Screen Rank'] = range(1, len(valid_df) + 1)
            df['Screen Rank'] = np.nan
            df.loc[valid_df.index, 'Screen Rank'] = valid_df['Screen Rank']
        else:
            df['Screen Rank'] = np.nan

        display_cols = ["Screen Rank", "Symbol", "Close", "% Change", "Volume", "Sector", "Sec Rank", "Broad Industry", "Ind Rank", "Relative score"]
        display_df = df[[c for c in display_cols if c in df.columns]].copy().sort_values(by="Screen Rank", na_position="last").fillna("")

        metric_col1, metric_col2, metric_col3 = st.columns(3)
        metric_col1.metric("🔥 Total Matches", len(display_df))
        metric_col2.metric("⭐ Top Tier Setups", len(display_df[display_df['Screen Rank'] != ""])) 
        metric_col3.metric("📈 Database Syncs", len(display_df[display_df['Sector'] != ""]))
        st.markdown("<br>", unsafe_allow_html=True)
        
        def highlight_change(val):
            try: return 'background-color: rgba(39, 174, 96, 0.15)' if float(val) > 0 else 'background-color: rgba(231, 76, 60, 0.15)'
            except: return ''
                
        styled_df = display_df.style.hide(axis="index").map(highlight_change, subset=['% Change']).format({
            "Close": "₹{:.2f}", "% Change": "{:.2f}%", "Volume": "{:,.0f}",
            "Screen Rank": lambda x: f"👑 {int(x)}" if x != "" else "",
            "Sec Rank": lambda x: f"{int(x)}" if x != "" else "",
            "Ind Rank": lambda x: f"{int(x)}" if x != "" else "",
        })
        st.table(styled_df)
    else:
        st.info("No stocks matching criteria right now. Waiting for momentum...")

if auto_refresh:
    time.sleep(60)
    st.rerun()