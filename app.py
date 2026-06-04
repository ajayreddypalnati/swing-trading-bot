import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import time
from datetime import datetime, timezone, timedelta
import streamlit as st
import re
import warnings
from sqlalchemy import create_engine

# Silence terminal spam
warnings.simplefilter(action='ignore', category=FutureWarning)

st.set_page_config(page_title="9-EMA Swing Screener", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# --- CSS INJECTION (Dark-Themed Sleek UI) ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght=400;600;700&display=swap');
        html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
        #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
        .block-container { padding-top: 1.5rem; padding-bottom: 0rem; max-width: 98%; }
        [data-testid="stMetric"] { background: linear-gradient(145deg, rgba(128, 128, 128, 0.05) 0%, rgba(128, 128, 128, 0.02) 100%); border-radius: 12px; padding: 20px; text-align: center; border: 1px solid rgba(128, 128, 128, 0.15); box-shadow: 0 4px 6px rgba(0,0,0,0.02); transition: all 0.3s ease; }
        [data-testid="stTable"] table { width: 100%; border-collapse: collapse; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        [data-testid="stTable"] th { background-color: rgba(128, 128, 128, 0.08) !important; text-align: center !important; font-size: 0.85rem; padding: 15px !important; }
        [data-testid="stTable"] td { text-align: center !important; padding: 12px !important; border-bottom: 1px solid rgba(128, 128, 128, 0.1) !important; }
        .blob.green { background: rgba(39, 174, 96, 1); border-radius: 50%; margin: 8px; height: 12px; width: 12px; animation: pulse-green 2s infinite; display: inline-block; }
    </style>
""", unsafe_allow_html=True)

# --- APIs & ENDPOINTS ---
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
# 2. DATA FETCHING (Cloud Native Database & Sheets)
# ==========================================
@st.cache_data(ttl=600)
def fetch_database_reference():
    try:
        db_url = st.secrets["DATABASE_URL"]

        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

        engine = create_engine(db_url)

        main_df = pd.read_sql('SELECT "Ticker" as ticker, "Sector" as sector, "Broad Industry" as broad_industry, "Relative score" as relative_score FROM stock_master', engine)
        raw_sec = pd.read_sql('SELECT * FROM sector_analysis', engine)
        raw_ind = pd.read_sql('SELECT * FROM industry_analysis', engine)

        sec_rank_df = raw_sec[['Sector', 'Rank']].rename(columns={'Sector': 'sector', 'Rank': 'sec_rank'})
        ind_rank_df = raw_ind[['Broad Industry', 'Rank']].rename(columns={'Broad Industry': 'broad_industry', 'Rank': 'ind_rank'})

        try:
            sync_df = pd.read_sql('SELECT * FROM sync_log', engine)
            last_sync = sync_df['last_sync'].iloc[0]
        except Exception:
            last_sync = "Pending Run..."

        try:
            trend_df = pd.read_sql('SELECT * FROM market_trend_summary LIMIT 1', engine)
            trend_regime = trend_df['trend_regime'].iloc[0] if not trend_df.empty else "Pending..."
        except Exception:
            trend_regime = "N/A"

        return main_df, sec_rank_df, ind_rank_df, raw_sec, raw_ind, last_sync, trend_regime

    except Exception as e:
        st.error(f"DATABASE ERROR: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "Error", "Error"

@st.cache_data(ttl=60)
def fetch_market_breadth_from_gsheets():
    try:
        # Using the direct export URL with the exact GID to prevent 404 errors
        sheet_id = "1ngF7Ci5SrN8lP0-QSB0Be1Ave84Asig04pCaY8qDXKU"
        gid = "2103540271" 
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        
        df = pd.read_csv(url, header=None)
        
        # Targets Cell H6 (Row index 5, Column index 7)
        market_breadth_value = df.iloc[5, 7] 
        
        if pd.isna(market_breadth_value):
            return "Empty Cell"
            
        return str(market_breadth_value)
    except Exception as e:
        return f"Err: {str(e)[:20]}"

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
# 3. DASHBOARD UI LAYOUT
# ==========================================
header_col1, header_col2 = st.columns([2, 1])
with header_col1:
    st.markdown("<h1 style='margin-bottom: 0px;'>⚡ 9-EMA Swing trading screener</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: gray; font-size: 1.1rem;'>Real-time momentum paired with Supabase ATH Sector Rankings.</p>", unsafe_allow_html=True)

with header_col2:
    ist = timezone(timedelta(hours=5, minutes=30))
    current_time = datetime.now(ist).strftime('%I:%M:%S %p')
    current_date = datetime.now(ist).strftime('%d %b %Y')
    
    st.markdown(f"""
        <div style="text-align: right; margin-top: 5px; color: gray;">
            <span style="font-size: 0.85rem; font-weight: 700; text-transform: uppercase;">
                LIVE DATA <div class="blob green"></div><br>
                <span style="color: #1E88E5; font-size: 1.4rem; font-weight: 800;">{current_time}</span><br>
                <span style="font-size: 0.85rem;">{current_date}</span>
            </span>
        </div>
        """, unsafe_allow_html=True)

st.divider()

with st.spinner("Scanning live markets & syncing with Supabase..."):
    data = get_combined_data()
    main_df, sec_rank_df, ind_rank_df, raw_sec, raw_ind, last_sync, trend_regime = fetch_database_reference()  
    live_sheet_breadth = fetch_market_breadth_from_gsheets()

    if data:
        df = pd.DataFrame(data, columns=["Symbol", "Close", "% Change", "Volume", "Exchange"])
        df['Symbol'] = df['Symbol'].astype(str).str.strip().str.upper()

        if not main_df.empty:
            df = df.merge(main_df, left_on="Symbol", right_on="ticker", how="left")
            df = df.merge(sec_rank_df, on="sector", how="left")
            df = df.merge(ind_rank_df, on="broad_industry", how="left")
        else:
            df['sector'], df['broad_industry'], df['relative_score'], df['sec_rank'], df['ind_rank'] = "", "", np.nan, np.nan, np.nan

        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
        df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
        df['Turnover (Cr)'] = (df['Close'] * df['Volume']) / 10000000

        for col in ['sec_rank', 'ind_rank', 'relative_score']:
            if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')

        df['Priority'] = np.nan

        if 'sec_rank' in df.columns and 'ind_rank' in df.columns:
            p1 = (df['sec_rank'] <= 5) & (df['ind_rank'] <= 10)
            p2 = (df['sec_rank'] <= 5) & (df['ind_rank'] <= 15) & ~p1
            p3 = (df['ind_rank'] <= 10) & ~p1 & ~p2
            p4 = (df['sec_rank'] <= 5) & ~p1 & ~p2 & ~p3

            df.loc[p1, 'Priority'] = 1
            df.loc[p2, 'Priority'] = 2
            df.loc[p3, 'Priority'] = 3
            df.loc[p4, 'Priority'] = 4

        display_cols = ["Priority", "Symbol", "Close", "% Change", "Turnover (Cr)", "Volume", "sector", "sec_rank", "broad_industry", "ind_rank", "relative_score"]
        display_df = df[[c for c in display_cols if c in df.columns]].copy()
        display_df = display_df.sort_values(by=["Priority", "relative_score"], ascending=[True, True], na_position="last").fillna("")

        display_df = display_df.rename(columns={
            "sector": "Sector", 
            "sec_rank": "Sector Rank", 
            "broad_industry": "Industry", 
            "ind_rank": "Ind. Rank", 
            "relative_score": "Momentum Score"
        })

        total_matches = len(display_df)
        top_tier_count = len(display_df[display_df['Priority'] != ""]) if 'Priority' in display_df.columns else 0
        db_sync_count = len(display_df[display_df['Sector'] != ""]) if 'Sector' in display_df.columns else 0

        # --- HORIZONTAL INLINE METRICS GRID (6 Columns) ---
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        
        m1.metric("📊 Breadth (Live)", live_sheet_breadth)
        m2.metric("⚖️ Breadth (NSE)", trend_regime) 
        m3.metric("🔥 Matches", total_matches)
        m4.metric("⭐ Top Tier", top_tier_count)
        m5.metric("📈 DB Syncs", db_sync_count)
        
        with m6:
            st.markdown(f"""
                <div style="background: linear-gradient(145deg, rgba(128, 128, 128, 0.05) 0%, rgba(128, 128, 128, 0.02) 100%); 
                            border-radius: 12px; padding: 15px 10px; text-align: center; height: 100%;
                            border: 1px solid rgba(128, 128, 128, 0.15); box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                    <span style="font-size: 0.75rem; color: gray; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">📅 Last DB Update</span><br>
                    <span style="color: #FFFFFF; font-size: 1.15rem; font-weight: 900; display: block; margin-top: 5px; white-space: nowrap;">{last_sync}</span>
                </div>
                """, unsafe_allow_html=True)
                
        st.markdown("<br>", unsafe_allow_html=True)
        # ----------------------------------------
        
        if not raw_sec.empty and not raw_ind.empty:
            with st.expander("🏆 Current Market Leaders (Top Sectors & Industries)", expanded=False):
                lead_col1, lead_col2 = st.columns(2)
                
                with lead_col1:
                    st.markdown("##### 🔥 Top 5 Sectors")
                    top_sec = raw_sec.nsmallest(5, 'Rank')[['Rank', 'Sector', 'ATH %']]
                    top_sec['ATH %'] = top_sec['ATH %'].astype(float).map("{:.2f}%".format)
                    st.dataframe(top_sec.set_index('Rank'), use_container_width=True)
                    
                with lead_col2:
                    st.markdown("##### 🚀 Top 15 Industries")
                    top_ind = raw_ind.nsmallest(15, 'Rank')[['Rank', 'Broad Industry', 'ATH %']]
                    top_ind['ATH %'] = top_ind['ATH %'].astype(float).map("{:.2f}%".format)
                    st.dataframe(top_ind.set_index('Rank'), use_container_width=True)
            st.markdown("<br>", unsafe_allow_html=True)

        def highlight_change(val):
            try: return 'background-color: rgba(39, 174, 96, 0.15)' if float(val) > 0 else 'background-color: rgba(231, 76, 60, 0.15)'
            except: return ''
        
        def safe_int(val, prefix="", suffix=""):
            if val == "" or pd.isna(val): return ""
            try: return f"{prefix}{int(float(val))}{suffix}"
            except: return ""

        styled_df = display_df.style.hide(axis="index").map(highlight_change, subset=['% Change']).format({
            "Close": "₹{:.2f}", 
            "% Change": "{:.2f}%", 
            "Turnover (Cr)": "₹{:.2f} Cr",
            "Volume": "{:,.0f}",
            "Momentum Score": lambda x: safe_int(x),
            "Priority": lambda x: safe_int(x, "Tier "),
            "Sector Rank": lambda x: safe_int(x, "#"),
            "Ind. Rank": lambda x: safe_int(x, "#"),
        })
        st.table(styled_df)
    else:
        st.info("No stocks matching criteria right now. Waiting for momentum...")

# Hardware 60-second auto-refresh loop 
time.sleep(60)
st.rerun()

st.markdown("<br><br>", unsafe_allow_html=True)
with st.expander("🗄️ View Full Raw Supabase Tables"):
    tab1, tab2 = st.tabs(["Sector Analysis", "Industry Analysis"])
    if not raw_sec.empty:
        with tab1:
            st.dataframe(raw_sec, use_container_width=True)
    if not raw_ind.empty:
        with tab2:
            st.dataframe(raw_ind, use_container_width=True)
