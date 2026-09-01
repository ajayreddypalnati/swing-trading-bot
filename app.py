import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
import pytz
import holidays
import streamlit as st
import re
import warnings
from sqlalchemy import create_engine, text
import plotly.graph_objects as go
import io
import gzip
from st_copy_to_clipboard import st_copy_to_clipboard
import streamlit.components.v1 as components
from tvDatafeed import TvDatafeed, Interval

# Silence terminal spam
warnings.simplefilter(action='ignore', category=FutureWarning)

st.set_page_config(page_title="9-EMA Screener", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# Initialize portfolio refresh time and data in session state
if 'port_refresh_time' not in st.session_state:
    st.session_state['port_refresh_time'] = "Never"
if 'final_port_df' not in st.session_state:
    st.session_state['final_port_df'] = pd.DataFrame()

# ==========================================
# 1. CSS INJECTION (Premium Navy & Cream Theme + Immersive Tabs)
# ==========================================
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
        
        /* FORCE 80% ZOOM AESTHETIC AND CENTER ALIGNMENT BY DEFAULT */
        html { zoom: 1; } 
        
        html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
        #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
        
        /* HIDE NATIVE STREAMLIT RUNNING INDICATOR */
        div[data-testid="stStatusWidget"] { visibility: hidden; }

        /* --- PROFESSIONAL BLUR & PULSING ICON ON REFRESH --- */
        [data-stale="true"] {
            opacity: 0.6 !important;
            filter: blur(4px) grayscale(10%) !important;
            transition: filter 0.3s ease, opacity 0.3s ease !important;
            pointer-events: none !important;
        }
        
        [data-testid="stMainBlockContainer"][data-stale="true"]::after {
            content: "⚡";
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 5.5rem;
            z-index: 99999;
            animation: pulse-zoom 0.8s infinite alternate ease-in-out;
            text-shadow: 0 0 20px rgba(255, 255, 255, 0.9);
        }

        @keyframes pulse-zoom {
            0% { transform: translate(-50%, -50%) scale(0.8); opacity: 0.7; }
            100% { transform: translate(-50%, -50%) scale(1.2); opacity: 1; text-shadow: 0 0 40px rgba(255, 255, 255, 1); }
        }
        
        .block-container { 
            padding-top: 1.5rem; 
            padding-bottom: 0rem; 
            max-width: 98%; 
        }
        
        .blob.green { background: rgba(39, 174, 96, 1); border-radius: 50%; margin: 0 0 0 5px; height: 10px; width: 10px; animation: pulse-green 2s infinite; display: inline-block; }
        
        .stApp { background-color: #F4F1E1 !important; }
        h1, h2, h3, h4, h5, h6, p, span { color: #0B1D30; }
        
        .premium-header {
            background: linear-gradient(135deg, #0B1D30 0%, #162C46 100%); 
            border-radius: 16px;
            padding: 28px 36px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: relative;
            overflow: hidden;
            margin-bottom: 20px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 12px 30px rgba(11, 29, 48, 0.25), 0 4px 10px rgba(11, 29, 48, 0.15);
            transform: translateY(0);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); 
        }
        
        .premium-header:hover {
            transform: translateY(-5px);
            box-shadow: 0 20px 40px rgba(11, 29, 48, 0.35), 0 8px 15px rgba(11, 29, 48, 0.2);
        }

        .premium-header::after {
            content: '';
            position: absolute;
            top: -50px;
            right: -50px;
            width: 350px;
            height: 200%;
            background: #F4F1E1; 
            transform: rotate(20deg);
            z-index: 1;
            box-shadow: -15px 0 35px rgba(0,0,0,0.4); 
            border-left: 2px solid rgba(255, 255, 255, 0.4);
        }
        
        .header-left { position: relative; z-index: 2; }
        .header-title { color: #FFFFFF !important; margin: 0; font-size: 2.2rem; font-weight: 800; letter-spacing: -0.5px;}
        .header-subtitle { color: #FFFFFF !important; margin: 5px 0 0 0; font-size: 1rem; opacity: 0.9; }
        
        .header-right { position: relative; z-index: 2; text-align: right; padding-right: 15px;}
        .header-right .live-status { font-size: 0.85rem; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; color: #0B1D30;}
        .header-right .time { font-size: 1.6rem; font-weight: 800; margin: 0; color: #0B1D30; line-height: 1.2;}
        .header-right .date { font-size: 0.9rem; font-weight: 600; color: #3A4A5A;}

        @media (max-width: 768px) {
            .premium-header { flex-direction: column; align-items: flex-start; padding: 20px; }
            .premium-header::after { width: 100%; height: 120px; top: auto; bottom: 0; right: 0; transform: none; box-shadow: none; border-top: 5px solid #E5E1CD;}
            .header-right { text-align: left; padding-top: 25px; padding-right: 0;}
        }
        
        /* TABLE STYLING */
        .scrollable-table-container { width: 100%; margin-bottom: 0.5rem; overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: 8px;}
        .scrollable-table-container table { width: 100%; border-collapse: collapse; background: #FFFFFF; border: 2px solid #0B1D30; overflow: hidden;}
        .scrollable-table-container th { background-color: #0B1D30 !important; color: #F4F1E1 !important; text-align: center !important; vertical-align: middle !important; font-size: 0.95rem !important; padding: 10px 5px !important; font-weight: 700 !important;}
        .scrollable-table-container td { color: #111827 !important; text-align: center !important; vertical-align: middle !important; padding: 8px 5px !important; border-bottom: 1px solid rgba(11, 29, 48, 0.1) !important; font-size: 0.95rem !important; }
        
        .sleek-table-wrapper { width: 100%; border: 2px solid #0B1D30; border-radius: 8px; overflow-x: auto; -webkit-overflow-scrolling: touch; background: #FFFFFF; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .sleek-table { width: 100%; border-collapse: collapse; font-size: 1.0rem !important; background: transparent; }
        .sleek-table th { background-color: #0B1D30 !important; color: #F4F1E1 !important; text-align: center; vertical-align: middle; padding: 10px 8px; font-weight: 700 !important; font-size: 1.05rem !important; }
        .sleek-table td { color: #111827 !important; text-align: center; vertical-align: middle; padding: 8px; border-bottom: 1px solid rgba(11, 29, 48, 0.1); font-size: 1.0rem !important; }
        
        div.stPlotlyChart { 
            background-color: #FFFFFF !important; 
            border: 2px solid #0B1D30 !important; 
            border-radius: 12px !important; 
            box-shadow: 0 8px 20px rgba(11, 29, 48, 0.08) !important; 
            padding: 15px !important; 
        }

        /* PROFESSIONAL FULL-WIDTH SAAS TABS */
        div[data-baseweb="tab-list"] { 
            display: flex !important;
            width: 100% !important;
            gap: 15px !important;
            border-bottom: none !important;
            margin-bottom: 15px !important;
            padding-top: 10px !important; 
        }
        
        div[data-baseweb="tab"] { 
            padding: 0 !important;
            background: transparent !important;
            flex: 1 !important; 
            min-width: 0 !important;
        }
        
        button[role="tab"] {
            width: 100% !important;
            background: linear-gradient(135deg, #0B1D30 0%, #162C46 100%) !important;
            border-radius: 12px !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            box-shadow: 0 8px 20px rgba(11, 29, 48, 0.15) !important;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1) !important;
            padding: 20px 10px !important;
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            transform: translateY(0) !important;
        }
        
        button[role="tab"]:hover {
            transform: translateY(-6px) !important;
            box-shadow: 0 20px 40px rgba(11, 29, 48, 0.35), 0 8px 15px rgba(11, 29, 48, 0.2) !important;
            background: linear-gradient(135deg, #0f2640 0%, #1d3a5a 100%) !important;
        }
        
        button[role="tab"][aria-selected="true"] {
            background: #FFFFFF !important;
            border: 2px solid #0B1D30 !important;
            border-top: 6px solid #0B1D30 !important; 
            transform: translateY(-6px) !important; 
            box-shadow: 0 15px 30px rgba(11, 29, 48, 0.15) !important;
        }
        
        button[role="tab"] p { 
            font-size: 1.4rem !important; 
            font-weight: 800 !important; 
            color: #FFFFFF !important; 
            margin: 0 !important;
            transition: color 0.3s ease !important;
            white-space: nowrap !important;
        }
        
        button[role="tab"][aria-selected="true"] p {
            color: #0B1D30 !important;
        }
        
        div[data-baseweb="tab-highlight"] { display: none !important; }
        
        /* FORCE TEXT & NUMBER INPUT FULL WRAPPER BORDER TO BLACK (Req 1/2) */
        /* Target the outermost input container to prevent inner elements from covering the top/bottom borders */
        div[data-testid="stNumberInput"] [data-baseweb="input"],
        div[data-testid="stTextInput"] [data-baseweb="input"] {
            border: 2px solid #000000 !important;
            border-radius: 8px !important;
            background-color: #FFFFFF !important;
            overflow: hidden !important;
        }
        
        /* Stop the red/blue outline on focus */
        div[data-testid="stNumberInput"] [data-baseweb="input"]:focus-within,
        div[data-testid="stTextInput"] [data-baseweb="input"]:focus-within {
            border-color: #000000 !important;
            box-shadow: none !important;
        }
        
        /* Strip background and borders from nested Streamlit inputs so they don't clip the parent border */
        div[data-testid="stNumberInput"] [data-baseweb="base-input"],
        div[data-testid="stTextInput"] [data-baseweb="base-input"],
        div[data-testid="stNumberInput"] input,
        div[data-testid="stTextInput"] input {
            background-color: transparent !important;
            color: #0B1D30 !important;
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }
        
        div[data-testid="stNumberInput"] button {
            background-color: #F4F1E1 !important;
            color: #0B1D30 !important;
        }
        
        /* Global Buttons (like Load/Refresh) */
        div[data-testid="stButton"] button {
            border: 2px solid #000000 !important;
            font-weight: 700 !important;
            color: #0B1D30 !important;
            transition: all 0.3s ease !important;
        }
        
        div[data-testid="stButton"] button:hover {
            background-color: #E5E1CD !important;
            transform: translateY(-2px);
        }

        div[data-testid="stVerticalBlock"] {
            gap: 0.5rem !important;
        }

    </style>
""", unsafe_allow_html=True)


# ==========================================
# MARKET TOGGLE (Placed AFTER CSS so styles load!)
# ==========================================
col_blank, col_toggle = st.columns([8.5, 1.5])
with col_toggle:
    is_usa = st.toggle("🇺🇸 USA / 🇮🇳 IND", value=False)

if is_usa:
    import usa_app
    usa_app.run_usa_screener()
    st.stop()
# ==========================================

# ==========================================
# 2. APIs & ENDPOINTS
# ==========================================
CHARTINK_SCREENER_URL = 'https://chartink.com/screener/copy-9-ema-retest-114'
CHARTINK_PROCESS_URL = 'https://chartink.com/screener/process'
CHARTINK_SCAN_CLAUSE = "( {cash} (  daily high >  daily ema(  daily close , 9 ) and  daily low <  daily ema(  daily close , 9 ) and  daily close >  daily ema(  daily close , 9 ) and  daily close >  1 month ago close * 1.1 and  daily close >  1 day ago max( 300 ,  daily high ) * 0.9 and  market cap >=  500 and  daily rsi( 14 ) >=  65 and  daily \"close - 1 candle ago close / 1 candle ago close * 100\" >  0 and  daily \"close - 1 candle ago close / 1 candle ago close * 100\" <  10 and  daily volume * daily close >=  10000000 ) )"

TV_URL = 'https://scanner.tradingview.com/india/scan'
TV_HEADERS = { 'User-Agent': 'Mozilla/5.0', 'Origin': 'https://www.tradingview.com', 'Content-Type': 'application/json' }
TV_PAYLOAD = {
    "columns": ["ticker-view", "close", "type", "typespecs", "change", "volume", "sector.tr", "market", "sector"],
    "filter": [{"left": "Value.Traded", "operation": "greater", "right": 10000000}, {"left": "close", "operation": "in_range%", "right": ["High.All", 0.9, 1]}, {"left": "RSI", "operation": "greater", "right": 65}, {"left": "Perf.1M", "operation": "greater", "right": 10}, {"left": "high", "operation": "greater", "right": "EMA9"}, {"left": "close", "operation": "egreater", "right": "EMA9"}, {"left": "change", "operation": "in_range", "right": [0, 10]}, {"left": "low", "operation": "less", "right": "EMA9"}, {"left": "is_primary", "operation": "equal", "right": True}],
    "options": {"lang": "en"}, "range": [0, 100], "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"}, "markets": ["india"]
}

# ==========================================
# 3. DATA FETCHING 
# ==========================================
def get_db_cache_key():
    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(ist)
    if 9 <= now.hour < 21:
        return f"locked_{now.strftime('%Y-%m-%d')}"
    else:
        return f"active_{now.strftime('%Y-%m-%d_%H')}"

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_database_reference(cache_key):
    try:
        db_url = st.secrets["DATABASE_URL"]
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

        engine = create_engine(db_url)
        with engine.connect() as conn:
            main_df_raw = pd.read_sql(text('SELECT * FROM stock_master'), conn)
            
            col_ticker = next((c for c in main_df_raw.columns if 'ticker' in str(c).lower()), 'Ticker')
            col_name = next((c for c in main_df_raw.columns if 'name' in str(c).lower()), 'Name')
            col_sector = next((c for c in main_df_raw.columns if 'sector' in str(c).lower()), 'Sector')
            col_ind = next((c for c in main_df_raw.columns if 'industry' in str(c).lower()), 'Broad Industry')
            col_score = next((c for c in main_df_raw.columns if 'relative score' in str(c).lower()), 'Relative score')
            col_exch = next((c for c in main_df_raw.columns if 'exchange' in str(c).lower()), 'Exchange')
            col_mcap = next((c for c in main_df_raw.columns if 'mar cap' in str(c).lower() or 'market cap' in str(c).lower()), 'Mar Cap Rs.Cr.')
            col_turnover = next((c for c in main_df_raw.columns if 'turnover' in str(c).lower()), 'Turnover')
            col_band = next((c for c in main_df_raw.columns if 'band' in str(c).lower()), 'Band')
            col_down_ath = next((c for c in main_df_raw.columns if 'down' in str(c).lower() and 'ath' in str(c).lower()), 'Down %_ATH')
            col_1d_ret = next((c for c in main_df_raw.columns if '1day' in str(c).lower() and 'return' in str(c).lower()), '1day return %')
            col_cmp = next((c for c in main_df_raw.columns if 'cmp' in str(c).lower()), 'CMP Rs.')

            main_df = main_df_raw.rename(columns={
                col_ticker: 'ticker', col_name: 'stock_name', col_sector: 'sector', col_ind: 'broad_industry',
                col_score: 'relative_score', col_exch: 'db_exchange', col_mcap: 'market_cap', col_turnover: 'turnover',
                col_band: 'band', col_down_ath: 'down_ath', col_1d_ret: '1d_return', col_cmp: 'price'
            })

            raw_sec = pd.read_sql(text('SELECT * FROM "ATH_Sector_Analysis"'), conn)
            raw_ind = pd.read_sql(text('SELECT * FROM "ATH_Industry_Analysis"'), conn)
            sec_rank_df = raw_sec[['Sector', 'Rank']].rename(columns={'Sector': 'sector', 'Rank': 'sec_rank'})
            ind_rank_df = raw_ind[['Broad Industry', 'Rank']].rename(columns={'Broad Industry': 'broad_industry', 'Rank': 'ind_rank'})
            
            try:
                sync_df = pd.read_sql(text('SELECT * FROM sync_log'), conn)
                last_sync = sync_df['last_sync'].iloc[0]
            except Exception:
                last_sync = "Pending Run..."

            try:
                trend_df = pd.read_sql(text('SELECT * FROM market_trend_summary LIMIT 1'), conn)
                trend_regime = trend_df['trend_regime'].iloc[0] if not trend_df.empty else "Pending..."
                market_trend_summary_val = trend_df['composite_score'].iloc[0] if not trend_df.empty else None
                
                mood_df = pd.read_sql(text('SELECT "Date", "Market Breadth" FROM historical_market_mood ORDER BY "Date" DESC LIMIT 5'), conn)
                if not mood_df.empty and market_trend_summary_val is not None:
                    def extract_pct(s):
                        match = re.search(r'(\d+\.?\d*)', str(s))
                        return float(match.group(1)) if match else None
                    vals = mood_df['Market Breadth'].apply(extract_pct).dropna().tolist()
                    current_val = extract_pct(market_trend_summary_val)
                    if len(vals) > 0 and current_val is not None:
                        avg_5d = sum(vals) / len(vals)
                        diff = avg_5d - current_val
                        if diff >= 2.0: trend_sym = "📈"
                        elif diff <= -2.0: trend_sym = "📉"
                        else: trend_sym = "➖"
                        trend_regime = f"{trend_regime} {trend_sym}"
            except Exception:
                if 'trend_regime' not in locals(): trend_regime = "N/A"

            try:
                roc_df = pd.read_sql(text('SELECT * FROM "CNXSMALLCAP_ROC" ORDER BY "Date" DESC LIMIT 400'), conn)
                if not roc_df.empty:
                    roc_df['Date_Only'] = pd.to_datetime(roc_df['Date']).dt.date
                    roc_df = roc_df.drop_duplicates(subset=['Date_Only'], keep='first')
                    
                roc_col = next((c for c in roc_df.columns if 'ROC_20M' in str(c).upper()), None)
                roc_vals = roc_df[roc_col].tolist() if roc_col is not None and not roc_df.empty else []
            except Exception as e:
                st.warning(f"⚠️ SQL Error fetching Market Cycle ROC: {e}")
                roc_vals = []

            try:
                etf_df = pd.read_sql(text('SELECT * FROM "ETF Screener"'), conn)
            except Exception as e:
                etf_df = pd.DataFrame()
                
            try:
                us_etf_df = pd.read_sql(text('SELECT * FROM "USA_ETF_Screener"'), conn)
            except Exception as e:
                us_etf_df = pd.DataFrame()
                
            try:
                micro_df = pd.read_sql(text('SELECT * FROM "Nifty_Microcap_250_Index"'), conn)
            except Exception as e:
                micro_df = pd.DataFrame()

        return main_df, sec_rank_df, ind_rank_df, raw_sec, raw_ind, last_sync, trend_regime, roc_vals, etf_df, us_etf_df, micro_df
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "Error", "Error", [], pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def fetch_market_breadth_from_gsheets():
    try:
        ts = int(time.time())
        url = f"https://docs.google.com/spreadsheets/d/e/2PACX-1vR1Evjm0QI8lj_k3439UzQShcg9fL8oTDq2nWPOY-2aXpKIesb3NsstOO_08pxAsTL6TL6WmLacqq9N/pub?gid=2103540271&single=true&output=csv&t={ts}"
        df = pd.read_csv(url, header=None)
        market_breadth_value = df.iloc[5, 7] 
        return "N/A" if pd.isna(market_breadth_value) else str(market_breadth_value)
    except Exception:
        return "N/A"

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

@st.cache_data(ttl=60, show_spinner=False)
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
# PORTFOLIO TRACKER HELPER FUNCTIONS
# ==========================================
@st.cache_data(ttl=86400, show_spinner=False) 
def fetch_exchange_mapping():
    exchange_map = {}
    try:
        db_url = st.secrets["DATABASE_URL"]
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        
        engine = create_engine(db_url)
        with engine.connect() as conn:
            try:
                ind_df = pd.read_sql(text('SELECT "Ticker", "Exchange" FROM "stock_master"'), conn)
                for _, row in ind_df.iterrows():
                    ticker = str(row['Ticker']).strip().upper()
                    exch = str(row['Exchange']).strip().upper()
                    if 'NSE' in exch: exch = 'NSE'
                    elif 'BSE' in exch: exch = 'BSE'
                    if ticker and ticker != "NAN":
                        exchange_map[ticker] = f"{exch}:{ticker}"
            except Exception: pass
            
            try:
                us_df = pd.read_sql(text('SELECT "Symbol", "Exchange" FROM "US Stock screener"'), conn)
                for _, row in us_df.iterrows():
                    ticker = str(row['Symbol']).strip().upper()
                    exch = str(row['Exchange']).strip().upper()
                    if ticker and ticker != "NAN":
                        exchange_map[ticker] = f"{exch}:{ticker}"
            except Exception: pass
    except Exception: pass
    return exchange_map

@st.cache_data(ttl=60, show_spinner=False)
def fetch_portfolio_tv_data(pure_tickers):
    if not pure_tickers: return {}
    try:
        payload = {
            "columns": ["ticker-view", "close", "type", "typespecs", "pricescale", "minmov", "fractional", "minmove2", "currency", "change", "market_cap_basic", "fundamental_currency_code", "sector.tr", "market", "sector", "industry.tr", "industry", "EMA21", "exchange.tr", "source-logoid"],
            "filter": [
                {"left": "is_primary", "operation": "equal", "right": True},
                {"left": "name", "operation": "in_range", "right": pure_tickers}
            ],
            "ignore_unknown_fields": False,
            "options": {"lang": "en"},
            "price_conversion": {"to_currency": "usd"},
            "range": [0, 5000],
            "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
            "markets": ["america","india"],
            "filter2": {
                "operator": "and",
                "operands": [
                    {"operation": {"operator": "or", "operands": [
                        {"operation": {"operator": "and", "operands": [{"expression": {"left": "type", "operation": "equal", "right": "stock"}}, {"expression": {"left": "typespecs", "operation": "has", "right": ["common"]}}]}},
                        {"operation": {"operator": "and", "operands": [{"expression": {"left": "type", "operation": "equal", "right": "fund"}}, {"expression": {"left": "typespecs", "operation": "has_none_of", "right": ["etf", "mutual"]}}]}}
                    ]}},
                    {"expression": {"left": "typespecs", "operation": "has_none_of", "right": ["pre-ipo"]}}
                ]
            }
        }
        url = 'https://scanner.tradingview.com/global/scan'
        response = requests.post(url, headers={'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'}, json=payload, timeout=10)
        
        results = {}
        for item in response.json().get("data", []):
            d = item["d"]
            ticker_name = d[0]["name"] if isinstance(d[0], dict) else d[0]
            exchange_raw = d[18]
            
            if exchange_raw and ticker_name:
                composite_sym = f"{str(exchange_raw).upper()}:{str(ticker_name).upper()}"
            else:
                composite_sym = str(item["s"]).upper()
                
            results[composite_sym] = {
                "price": float(d[1]) if d[1] is not None else 0.0,
                "change": float(d[9]) if d[9] is not None else 0.0,
                "ema21": float(d[17]) if d[17] is not None else 0.0
            }
        return results
    except Exception as e:
        return {}


# ==========================================
# 4. UI COMPONENTS, GRAPHS & SAFE FORMATTERS
# ==========================================
def safe_fmt(val, fmt_str):
    try:
        if pd.isna(val) or str(val).strip() == "": return "-"
        return fmt_str.format(float(val))
    except: return "-"

def get_breadth_color(breadth_str):
    try:
        match = re.search(r'(\d+\.?\d*)%', str(breadth_str))
        if match:
            val = float(match.group(1))
            if val <= 30.0: return "rgba(252, 165, 165, 0.4)"  
            elif val <= 40.0: return "rgba(254, 202, 202, 0.4)"  
            elif val <= 50.0: return "rgba(253, 230, 138, 0.4)"  
            elif val <= 60.0: return "rgba(187, 247, 208, 0.4)"  
            else: return "rgba(134, 239, 172, 0.4)"  
        return "#FFFFFF"
    except: return "#FFFFFF"

def get_portfolio_allocation(nse_breadth_str, live_breadth_str):
    try:
        match = re.search(r'(\d+\.?\d*)%', str(nse_breadth_str))
        live_match = re.search(r'(\d+\.?\d*)', str(live_breadth_str))

        if match:
            val = float(match.group(1))
            live_val = float(live_match.group(1)) if live_match else 0.0

            if "📉" in str(nse_breadth_str): action_suffix = " - Stop Trading"
            elif "📈" in str(nse_breadth_str): action_suffix = " - Trade"
            else:
                if live_val > 50.0: action_suffix = " - Trade"
                else: action_suffix = " - Stop Trading"

            if val <= 20.0: alloc_str, color = f"0% Equity{action_suffix}", "rgba(252, 165, 165, 0.4)"     
            elif val <= 25.0: alloc_str, color = f"10% Equity{action_suffix}", "rgba(254, 202, 202, 0.4)"     
            elif val <= 30.0: alloc_str, color = f"20% Equity{action_suffix}", "rgba(254, 202, 202, 0.4)"     
            elif val <= 35.0: alloc_str, color = f"35% Equity{action_suffix}", "rgba(253, 230, 138, 0.4)"     
            elif val <= 40.0: alloc_str, color = f"50% Equity{action_suffix}", "rgba(253, 230, 138, 0.4)"     
            elif val <= 45.0: alloc_str, color = f"65% Equity{action_suffix}", "rgba(187, 247, 208, 0.4)"     
            elif val <= 50.0: alloc_str, color = f"80% Equity{action_suffix}", "rgba(187, 247, 208, 0.4)"     
            else: alloc_str, color = f"100% Equity{action_suffix}", "rgba(134, 239, 172, 0.4)"   

            if action_suffix != " - Trade": color = "rgba(252, 165, 165, 0.4)" 
            return alloc_str, color
        return "N/A", "#FFFFFF"
    except: return "N/A", "#FFFFFF"

def create_metric_card(title, value, bg_color):
    val_size = "1.35rem" if len(str(value)) > 20 else "1.65rem"
    return f"""
    <div style="background: {bg_color}; border-radius: 12px; padding: 1.2rem 1.5rem; text-align: left; border: 2px solid #0B1D30; box-shadow: 0 4px 6px rgba(0,0,0,0.05); height: 115px; display: flex; flex-direction: column; justify-content: center;">
        <span style="font-size: 0.85rem; color: #0B1D30; font-weight: 700; font-family: 'Inter', sans-serif; text-transform: uppercase; letter-spacing: 0.5px;">{title}</span>
        <span style="color: #0B1D30; font-size: {val_size}; font-weight: 800; display: block; margin-top: 0.2rem; font-family: 'Inter', sans-serif; line-height: 1.2;">{value}</span>
    </div>
    """

def render_market_cycle_graph(roc_vals):
    if not roc_vals:
        st.info("No ROC data available to plot Market Cycle.")
        return

    roc_val = float(roc_vals[0])
    
    if len(roc_vals) > 1:
        lookback_window = roc_vals[:60][::-1]
        y = np.array(lookback_window, dtype=float)
        x = np.arange(len(y))
        slope, _ = np.polyfit(x, y, 1)
        if slope >= 0: trend_dir = "up"
        else: trend_dir = "down"
    else:
        trend_dir = "up"

    curve_x = [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48]
    curve_y = [2, 5, 15, 33, 66, 100, 90, 66, 33, 15, 5, 2, 1]

    if trend_dir == "up":
        dot_x = np.interp(roc_val, [0, 20, 40, 60, 100, 150], [0, 4, 8, 12, 16, 20])
        if roc_val <= 10: stage, note = "Disbelief", "This rally will fail like the others."
        elif roc_val <= 30: stage, note = "Hope", "A recovery is possible."
        elif roc_val <= 50: stage, note = "Optimism", "This rally is real."
        elif roc_val <= 80: stage, note = "Belief", "Time to get fully invested."
        elif roc_val <= 125: stage, note = "Thrill", "I will buy more on margin. Gotta tell everyone to buy!"
        else: stage, note = "Euphoria", "I am a genius! We're all going to be rich!"
    else:
        xp = [-20, 0, 20, 60, 70, 80, 90, 100]
        fp = [48, 44, 40, 36, 32, 28, 24, 20]
        dot_x = np.interp(roc_val, xp, fp)
        if roc_val >= 85: stage, note = "Complacency", "We just need to cool off for the next rally."
        elif roc_val >= 75: st
