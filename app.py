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
import yfinance as yf

# Silence terminal spam
warnings.simplefilter(action='ignore', category=FutureWarning)

st.set_page_config(page_title="9-EMA Swing Screener", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# --- CSS INJECTION (Dark-Themed Sleek UI & Bulletproof Mobile Scrolling) ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
        #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
        .block-container { padding-top: 1.5rem; padding-bottom: 0rem; max-width: 98%; }
        
        .blob.green { background: rgba(39, 174, 96, 1); border-radius: 50%; margin: 8px; height: 12px; width: 12px; animation: pulse-green 2s infinite; display: inline-block; }
        
        .scrollable-table-container {
            width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch; 
            margin-bottom: 1rem;
        }
        .scrollable-table-container table {
            width: 100%;
            min-width: 900px; 
            border-collapse: collapse;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        .scrollable-table-container th {
            background-color: rgba(128, 128, 128, 0.08) !important;
            text-align: center !important;
            vertical-align: middle !important;
            font-size: 0.85rem;
            padding: 15px !important;
            white-space: nowrap; 
        }
        .scrollable-table-container td {
            text-align: center !important;
            vertical-align: middle !important;
            padding: 12px !important;
            border-bottom: 1px solid rgba(128, 128, 128, 0.1) !important;
            white-space: nowrap; 
        }
        
        .sleek-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }
        .sleek-table th {
            background-color: rgba(128, 128, 128, 0.08) !important; 
            text-align: center;
            vertical-align: middle;
            padding: 10px 8px;
            border-bottom: 1px solid rgba(128, 128, 128, 0.2);
            font-weight: bold !important;
        }
        .sleek-table td {
            text-align: center;
            vertical-align: middle;
            padding: 8px;
            border-bottom: 1px solid rgba(128, 128, 128, 0.1);
        }
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
# 2. DATA FETCHING 
# ==========================================
@st.cache_data(ttl=600)
def fetch_database_reference():
    try:
        db_url = st.secrets["DATABASE_URL"]
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

        engine = create_engine(db_url)

        main_df = pd.read_sql('SELECT "Ticker" as ticker, "Sector" as sector, "Broad Industry" as broad_industry, "Relative score" as relative_score FROM stock_master', engine)
        raw_sec = pd.read_sql('SELECT * FROM "ATH_Sector_Analysis"', engine)
        raw_ind = pd.read_sql('SELECT * FROM "ATH_Industry_Analysis"', engine)

        sec_rank_df = raw_sec[['Sector', 'Rank']].rename(columns={'Sector': 'sector', 'Rank': 'sec_rank'})
        ind_rank_df = raw_ind[['Broad Industry', 'Rank']].rename(columns={'Broad Industry': 'broad_industry', 'Rank': 'ind_rank'})

        try:
            sync_df = pd.read_sql('SELECT * FROM sync_log', engine)
            last_sync = sync_df['last_sync'].iloc[0]
        except:
            last_sync = "Pending..."

        try:
            trend_df = pd.read_sql('SELECT * FROM market_trend_summary LIMIT 1', engine)
            trend_regime = trend_df['trend_regime'].iloc[0] if not trend_df.empty else "Pending..."
            
            # --- 5-DAY TREND LOGIC ---
            mood_df = pd.read_sql('SELECT "Market Breadth" FROM historical_market_mood ORDER BY "Date" DESC LIMIT 5', engine)
            if len(mood_df) >= 5:
                def extract_pct(s):
                    match = re.search(r'(\d+\.?\d*)%', str(s))
                    return float(match.group(1)) if match else None
                
                vals = mood_df['Market Breadth'].apply(extract_pct).dropna().tolist()
                if len(vals) >= 5:
                    latest_val = vals[0]
                    oldest_val = vals[4] # The 5th day previous
                    diff = latest_val - oldest_val
                    
                    if diff >= 2.0: trend_sym = "📈"
                    elif diff <= -2.0: trend_sym = "📉"
                    else: trend_sym = "➖"
                        
                    trend_regime = f"{trend_regime} {trend_sym}"
        except:
            if 'trend_regime' not in locals(): trend_regime = "N/A"

        return main_df, sec_rank_df, ind_rank_df, raw_sec, raw_ind, last_sync, trend_regime
    except Exception as e:
        st.error(f"DATABASE ERROR: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "Error", "Error"

@st.cache_data(ttl=600)
def fetch_smallcap_20m_return():
    try:
        end_date = datetime.now()
        start_date = end_date - pd.DateOffset(months=20)
        tickers = ["^CNXSMALLCAP", "^CNXSC", "NIFTYSMLCAP100.NS"]
        df = pd.DataFrame()
        for t in tickers:
            df = yf.Ticker(t).history(start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
            if not df.empty: break
        
        if not df.empty:
            ret = ((df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0]) * 100
            color = "rgba(187, 247, 208, 0.4)" if ret > 0 else "rgba(252, 165, 165, 0.4)"
            return f"{'+' if ret > 0 else ''}{ret:.2f}%", color
        return "N/A", "rgba(216, 180, 254, 0.3)"
    except:
        return "N/A", "rgba(216, 180, 254, 0.3)"

def fetch_market_breadth_from_gsheets():
    try:
        url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR1Evjm0QI8lj_k3439UzQShcg9fL8oTDq2nWPOY-2aXpKIesb3NsstOO_08pxAsTL6TL6WmLacqq9N/pub?gid=2103540271&single=true&output=csv"
        df = pd.read_csv(url, header=None)
        return str(df.iloc[5, 7]) if not pd.isna(df.iloc[5, 7]) else "N/A"
    except: return "N/A"

def get_combined_data():
    chartink = fetch_chartink_data()
    tv = fetch_tradingview_data()
    seen = set()
    combined = []
    for row in chartink + tv:
        sym = re.sub(r'\s+', '', str(row[0])).upper()
        if sym not in seen:
            combined.append(row)
            seen.add(sym)
    return combined

def fetch_chartink_data():
    with requests.Session() as s:
        try:
            r = s.get(CHARTINK_SCREENER_URL, timeout=10)
            token = BeautifulSoup(r.text, 'html.parser').find('meta', {'name': 'csrf-token'})['content']
            data = s.post(CHARTINK_PROCESS_URL, headers={'x-csrf-token': token}, data={'scan_clause': CHARTINK_SCAN_CLAUSE}, timeout=10).json()
            return [[r['nsecode'], r['close'], r['per_chg'], r['volume'], 'NSE'] for r in data['data']]
        except: return []

def fetch_tradingview_data():
    try:
        r = requests.post(TV_URL, headers=TV_HEADERS, json=TV_PAYLOAD, timeout=10).json()
        return [[item["s"].split(':')[1] if ':' in item["s"] else item["s"], item["d"][1], item["d"][4], item["d"][5], 'NSE'] for item in r.get("data", [])]
    except: return []

def get_breadth_color(b):
    try:
        v = float(re.search(r'(\d+\.?\d*)%', str(b)).group(1))
        if v <= 30: return "rgba(252, 165, 165, 0.4)"
        if v <= 40: return "rgba(254, 202, 202, 0.4)"
        if v <= 50: return "rgba(253, 230, 138, 0.4)"
        if v <= 60: return "rgba(187, 247, 208, 0.4)"
        return "rgba(134, 239, 172, 0.4)"
    except: return "rgba(216, 180, 254, 0.3)"

def create_metric_card(t, v, c):
    return f'<div style="background:{c}; border-radius:12px; padding:1.5rem; border:1px solid rgba(128,128,128,0.1); height:100%;"><span style="font-size:0.875rem; color:#4B5563;">{t}</span><br><span style="font-size:1.7rem; font-weight:600;">{v}</span></div>'

# --- DASHBOARD ---
st.markdown("<h1 style='margin-bottom:0px;'>⚡ 9-EMA Swing trading screener</h1>", unsafe_allow_html=True)
st.divider()

with st.spinner("Syncing..."):
    data = get_combined_data()
    main_df, sec_rank_df, ind_rank_df, raw_sec, raw_ind, last_sync, trend_regime = fetch_database_reference()
    live_breadth = fetch_market_breadth_from_gsheets()
    smallcap_val, smallcap_bg = fetch_smallcap_20m_return()
    
    # Dashboard Cards
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.markdown(create_metric_card("📊 Market Breadth (Live)", live_breadth, get_breadth_color(live_breadth)), unsafe_allow_html=True)
    c2.markdown(create_metric_card("⚖️ Market Breadth (NSE)", trend_regime, get_breadth_color(trend_regime)), unsafe_allow_html=True)
    c3.markdown(create_metric_card("💼 Portfolio Allocation", "80% Equity", "rgba(187, 247, 208, 0.4)"), unsafe_allow_html=True)
    c4.markdown(create_metric_card("📈 CNX Smallcap (20M)", smallcap_val, smallcap_bg), unsafe_allow_html=True)
    c5.markdown(create_metric_card("🔄 Last DB Update", last_sync, "rgba(216, 180, 254, 0.3)"), unsafe_allow_html=True)

    if data:
        df = pd.DataFrame(data, columns=["Symbol", "Close", "% Change", "Volume", "Exchange"])
        df['Symbol'] = df['Symbol'].astype(str).str.strip().str.upper()
        if not main_df.empty:
            df = df.merge(main_df, left_on="Symbol", right_on="ticker", how="left")
            df = df.merge(sec_rank_df, on="sector", how="left")
            df = df.merge(ind_rank_df, on="broad_industry", how="left")
        
        df['Turnover (Cr)'] = (pd.to_numeric(df['Close'], errors='coerce') * pd.to_numeric(df['Volume'], errors='coerce')) / 10000000
        
        # Priority Logic
        df['Priority'] = np.nan
        p1 = (df['sec_rank'] <= 5) & (df['ind_rank'] <= 10)
        p2 = (df['sec_rank'] <= 5) & (df['ind_rank'] <= 15) & ~p1
        p3 = (df['ind_rank'] <= 10) & ~p1 & ~p2
        p4 = (df['sec_rank'] <= 5) & ~p1 & ~p2 & ~p3
        df.loc[p1, 'Priority'] = 1; df.loc[p2, 'Priority'] = 2; df.loc[p3, 'Priority'] = 3; df.loc[p4, 'Priority'] = 4
        
        disp = df[["Priority", "Symbol", "Close", "% Change", "Turnover (Cr)", "Volume", "sector", "sec_rank", "broad_industry", "ind_rank", "relative_score"]]
        disp = disp.rename(columns={"sector": "Sector", "sec_rank": "Sector Rank", "broad_industry": "Industry", "ind_rank": "Ind. Rank", "relative_score": "Momentum Rank"})
        disp = disp.sort_values(by=["Priority", "relative_score"], ascending=[True, True]).fillna("")
        
        # Table output
        styled = disp.style.hide(axis="index").map(lambda x: 'background-color: rgba(39, 174, 96, 0.15)' if float(x) > 0 else '', subset=['Priority']).format({"Close": "₹{:.2f}", "% Change": "{:.2f}%", "Turnover (Cr)": "₹{:.2f} Cr", "Volume": "{:,.0f}"})
        st.markdown(f'<div class="scrollable-table-container">{styled.to_html()}</div>', unsafe_allow_html=True)
    else:
        st.info("No stocks matching.")

time.sleep(60)
st.rerun()
