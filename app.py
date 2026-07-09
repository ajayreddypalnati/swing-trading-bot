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

# Silence terminal spam
warnings.simplefilter(action='ignore', category=FutureWarning)

st.set_page_config(page_title="9-EMA Screener", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# Initialize portfolio refresh time in session state
if 'port_refresh_time' not in st.session_state:
    st.session_state['port_refresh_time'] = "Never"

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
        /* Blur all elements that are updating */
        [data-stale="true"] {
            opacity: 0.6 !important;
            filter: blur(4px) grayscale(10%) !important;
            transition: filter 0.3s ease, opacity 0.3s ease !important;
            pointer-events: none !important;
        }
        
        /* Attach the Zooming ⚡ Icon ONLY to the main app container so it appears ONCE */
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
        
        /* RESTORED CENTERED ALIGNMENT CAP */
        .block-container { 
            padding-top: 1.5rem; 
            padding-bottom: 0rem; 
            max-width: 98%; 
        }
        
        .blob.green { background: rgba(39, 174, 96, 1); border-radius: 50%; margin: 0 0 0 5px; height: 10px; width: 10px; animation: pulse-green 2s infinite; display: inline-block; }
        
        /* GLOBAL THEME BACKGROUND (Cream) */
        .stApp { background-color: #F4F1E1 !important; }
        h1, h2, h3, h4, h5, h6, p, span { color: #0B1D30; }
        
        /* PREMIUM CUSTOM HEADER - IMMERSIVE 3D POPUP */
        .premium-header {
            background: linear-gradient(135deg, #0B1D30 0%, #162C46 100%); 
            border-radius: 16px;
            padding: 28px 36px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: relative;
            overflow: hidden;
            margin-bottom: 20px; /* Reduced gap */
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
        
        /* PLOTLY GRAPH STYLING TO POP UP */
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
        
        /* FORCE TEXT INPUTS TO BE WHITE/LIGHT */
        div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input {
            background-color: #FFFFFF !important;
            color: #0B1D30 !important;
            border: 1px solid #0B1D30 !important;
        }
        
        /* Remove default Streamlit vertical block padding to tighten spacing */
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
    st.stop() # Stops the Indian app, but keeps the CSS!
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

            main_df = main_df_raw.rename(columns={
                col_ticker: 'ticker', col_name: 'stock_name', col_sector: 'sector', col_ind: 'broad_industry',
                col_score: 'relative_score', col_exch: 'db_exchange', col_mcap: 'market_cap', col_turnover: 'turnover',
                col_band: 'band', col_down_ath: 'down_ath', col_1d_ret: '1d_return'
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
                roc_df = pd.read_sql(text('SELECT * FROM "CNXSMALLCAP_ROC" ORDER BY "Date" DESC LIMIT 25'), conn)
                roc_col = next((c for c in roc_df.columns if 'ROC_20M' in str(c).upper()), None)
                roc_vals = roc_df[roc_col].tolist() if roc_col is not None and not roc_df.empty else []
            except Exception as e:
                st.warning(f"⚠️ SQL Error fetching Market Cycle ROC: {e}")
                roc_vals = []

            try:
                etf_df = pd.read_sql(text('SELECT * FROM "ETF Screener"'), conn)
            except Exception as e:
                st.warning(f"⚠️ SQL Error fetching ETF Screener: {e}")
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
        st.error(f"DATABASE ERROR: {e}")
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
@st.cache_data(ttl=86400, show_spinner=False) # Increased to 24 hours for superfast updates
def fetch_exchange_mapping():
    """Connects to Supabase to build a VLOOKUP dictionary for Indian and US tickers."""
    exchange_map = {}
    try:
        db_url = st.secrets["DATABASE_URL"]
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        
        engine = create_engine(db_url)
        with engine.connect() as conn:
            # 1. Indian Stocks (stock_master)
            try:
                ind_df = pd.read_sql(text('SELECT "Ticker", "Exchange" FROM "stock_master"'), conn)
                for _, row in ind_df.iterrows():
                    ticker = str(row['Ticker']).strip().upper()
                    exch = str(row['Exchange']).strip().upper()
                    # Clean up SME tags to match generic TradingView exchanges
                    if 'NSE' in exch: exch = 'NSE'
                    elif 'BSE' in exch: exch = 'BSE'
                    
                    if ticker and ticker != "NAN":
                        exchange_map[ticker] = f"{exch}:{ticker}"
            except Exception as e:
                print(f"Lookup Error (India): {e}")
            
            # 2. US Stocks (US Stock screener)
            try:
                us_df = pd.read_sql(text('SELECT "Symbol", "Exchange" FROM "US Stock screener"'), conn)
                for _, row in us_df.iterrows():
                    ticker = str(row['Symbol']).strip().upper()
                    exch = str(row['Exchange']).strip().upper()
                    if ticker and ticker != "NAN":
                        exchange_map[ticker] = f"{exch}:{ticker}"
            except Exception as e:
                print(f"Lookup Error (US): {e}")
                
    except Exception as e:
        print(f"Database Connect Error (Mapping): {e}")
        
    return exchange_map

@st.cache_data(ttl=60, show_spinner=False)
def fetch_portfolio_tv_data(pure_tickers):
    """Fetches live data directly using the 'in_range' filter for massive speed improvements."""
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
            "markets": ["america","argentina","australia","austria","bahrain","bangladesh","belgium","brazil","canada","chile","china","colombia","croatia","cyprus","czech","denmark","egypt","estonia","finland","france","germany","greece","hongkong","hungary","iceland","india","indonesia","ireland","israel","italy","japan","kenya","kuwait","latvia","lithuania","luxembourg","malaysia","mexico","morocco","netherlands","newzealand","nigeria","norway","pakistan","peru","philippines","poland","portugal","qatar","romania","russia","ksa","serbia","singapore","slovakia","slovenia","rsa","korea","spain","srilanka","sweden","switzerland","taiwan","thailand","tunisia","turkey","uae","uk","venezuela","vietnam"],
            "filter2": {
                "operator": "and",
                "operands": [
                    {"operation": {"operator": "or", "operands": [
                        {"operation": {"operator": "and", "operands": [{"expression": {"left": "type", "operation": "equal", "right": "stock"}}, {"expression": {"left": "typespecs", "operation": "has", "right": ["common"]}}]}},
                        {"operation": {"operator": "and", "operands": [{"expression": {"left": "type", "operation": "equal", "right": "stock"}}, {"expression": {"left": "typespecs", "operation": "has", "right": ["preferred"]}}]}},
                        {"operation": {"operator": "and", "operands": [{"expression": {"left": "type", "operation": "equal", "right": "dr"}}]}},
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
        print("TradingView Fetch Error:", e)
        return {}


# ==========================================
# 4. UI COMPONENTS, GRAPHS & SAFE FORMATTERS
# ==========================================

# THIS SAFE FORMATTER PREVENTS VALUEERRORS FROM BLANK DATABASE CELLS
def safe_fmt(val, fmt_str):
    try:
        if pd.isna(val) or str(val).strip() == "":
            return "-"
        return fmt_str.format(float(val))
    except:
        return "-"

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
    except:
        return "#FFFFFF"

def get_portfolio_allocation(nse_breadth_str, live_breadth_str):
    try:
        match = re.search(r'(\d+\.?\d*)%', str(nse_breadth_str))
        live_match = re.search(r'(\d+\.?\d*)', str(live_breadth_str))

        if match:
            val = float(match.group(1))
            live_val = float(live_match.group(1)) if live_match else 0.0

            if "📉" in str(nse_breadth_str):
                action_suffix = " - Stop Trading"
            elif "📈" in str(nse_breadth_str):
                action_suffix = " - Trade"
            else:
                if live_val > 50.0:
                    action_suffix = " - Trade"
                else:
                    action_suffix = " - Stop Trading"

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
    except:
        return "N/A", "#FFFFFF"

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
        lookback_window = roc_vals[:20][::-1]
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
        elif roc_val >= 75: stage, note = "Anxiety", "Why am I getting margin calls? This dip is taking longer than expected."
        elif roc_val >= 65: stage, note = "Denial", "My investments are with great companies. They will come back."
        elif roc_val >= 40: stage, note = "Panic", "Shit! Everyone is selling. I need to get out!"
        elif roc_val >= 10: stage, note = "Anger", "Who shorted the market?? Why did the government allow this to happen??"
        else: stage, note = "Depression", "My retirement money is lost. How can we pay for all this new stuff? I am an idiot."

    dot_y = np.interp(dot_x, curve_x, curve_y)

    red_stages = ["Euphoria", "Complacency", "Anxiety", "Denial", "Panic", "Anger", "Depression"]
    if stage in red_stages:
        theme_color = '#EF4444' 
        bg_theme_start = 'rgba(239, 68, 68, 0.1)'
        bg_theme_end = 'rgba(239, 68, 68, 0.02)'
    else:
        theme_color = '#10B981' 
        bg_theme_start = 'rgba(39, 174, 96, 0.1)'
        bg_theme_end = 'rgba(39, 174, 96, 0.02)'

    stage_names = ["<b>Disbelief</b>", "<b>Hope</b>", "<b>Optimism</b>", "<b>Belief</b>", "<b>Thrill</b>", "<b>Euphoria</b>", "<b>Complacency</b>", "<b>Anxiety</b>", "<b>Denial</b>", "<b>Panic</b>", "<b>Anger</b>", "<b>Depression</b>", "<b>Disbelief</b>"]
    text_colors = ['#111827'] * 13 
    text_colors[5] = '#EF4444' 

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=curve_x, y=curve_y, mode='lines+text', text=stage_names, textposition="top center", textfont=dict(family="Inter, sans-serif", size=20, color=text_colors), line=dict(shape='spline', smoothing=1.3, color='#0B1D30', width=4), fill='tozeroy', fillcolor='rgba(11, 29, 48, 0.05)', hoverinfo='none', name='Market Cycle'))
    fig.add_trace(go.Scatter(x=[dot_x], y=[dot_y], mode='markers', marker=dict(color=theme_color, size=24, line=dict(color='#0B1D30', width=4)), hoverinfo='none', name='Current Stage'))
    fig.add_shape(type="line", x0=20, y0=0, x1=20, y1=100, line=dict(color="#0B1D30", width=3))
    fig.add_annotation(x=dot_x, y=dot_y + 15, text=f"<b>{stage}</b>", showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2, arrowcolor=theme_color, font=dict(family="Inter, sans-serif", size=14, color=theme_color), bgcolor="rgba(255, 255, 255, 0.95)", bordercolor=theme_color, borderwidth=2, borderpad=6, opacity=1.0)

    fig.update_layout(
        xaxis=dict(title=dict(text="<b>Time (Months)</b>", font=dict(family="Inter", size=18, color="#0B1D30")), showgrid=True, gridcolor='rgba(11,29,48,0.1)', zeroline=False, showticklabels=True, tickfont=dict(size=14, color="#0B1D30", family="Inter"), showline=True, linewidth=3, linecolor='#0B1D30', dtick=2, range=[-2, 50]),
        yaxis=dict(title=dict(text="<b>Price (ROC)</b>", font=dict(family="Inter", size=18, color="#0B1D30")), showgrid=True, gridcolor='rgba(11,29,48,0.1)', zeroline=False, showticklabels=True, tickfont=dict(size=14, color="#0B1D30", family="Inter"), showline=True, linewidth=3, linecolor='#0B1D30', range=[-5, 125]),
        plot_bgcolor='#FFFFFF', paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=60, r=40, t=30, b=60), showlegend=False, height=550 
    )
    
    st.markdown(f"""
    <div style="background: linear-gradient(145deg, {bg_theme_start} 0%, {bg_theme_end} 100%); 
                border-left: 5px solid {theme_color}; padding: 15px 20px; border-radius: 8px; 
                margin-bottom: 20px; border-top: 1px solid rgba(0,0,0,0.05); border-right: 1px solid rgba(0,0,0,0.05); border-bottom: 1px solid rgba(0,0,0,0.05);">
        <h4 style="margin: 0; color: #0B1D30; font-family: 'Inter', sans-serif; font-weight: 800; font-size: 1.2rem;">
            Current Stage: <span style="color: {theme_color};">{stage}</span> 
            <span style="color: #6B7280; font-size: 0.95rem; font-weight: normal;">(CNXSMALLCAP ROC: <b>{roc_val}%</b>)</span>
        </h4>
        <p style="margin: 8px 0 0 0; font-size: 1rem; color: #374151; font-style: italic;">{note}</p>
    </div>
    """, unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 5. DASHBOARD MAIN LAYOUT & HEADER
# ==========================================
ist = timezone(timedelta(hours=5, minutes=30))
current_time = datetime.now(ist).strftime('%I:%M:%S %p')
current_date = datetime.now(ist).strftime('%d %b %Y')

st.markdown(f"""
    <div class="premium-header">
        <div class="header-left">
            <div class="header-title"><a href="/" target="_self" style="text-decoration: none; color: inherit; cursor: pointer;">⚡ 9-EMA Screener</a></div>
            <div class="header-subtitle">Refreshed every 1 minute paired with Sector, Industry & Momentum rank.</div>
        </div>
        <div class="header-right">
            <div class="live-status">LIVE DATA <div class="blob green"></div></div>
            <div class="time">{current_time}</div>
            <div class="date">{current_date}</div>
        </div>
    </div>
""", unsafe_allow_html=True)

data = get_combined_data()
current_cache_key = get_db_cache_key()
main_df, sec_rank_df, ind_rank_df, raw_sec, raw_ind, last_sync, trend_regime, roc_vals, etf_df, us_etf_df, micro_df = fetch_database_reference(current_cache_key)  
live_sheet_breadth = fetch_market_breadth_from_gsheets()

live_bg = get_breadth_color(live_sheet_breadth)
nse_bg = get_breadth_color(trend_regime)
alloc_val, alloc_bg = get_portfolio_allocation(trend_regime, live_sheet_breadth)

if roc_vals:
    try:
        current_roc = float(roc_vals[0])
        if current_roc > 90.0:
            if " - Trade" in alloc_val: alloc_val = alloc_val.replace(" - Trade", " - Tight stop loss")
            elif " - Stop Trading" in alloc_val: alloc_val = alloc_val.replace(" - Stop Trading", " - Tight stop loss")
            else: alloc_val += " - Tight stop loss"
            alloc_bg = "rgba(254, 202, 202, 0.4)"
    except: pass

last_sync_bg = "rgba(216, 180, 254, 0.3)"
if str(last_sync) != "Pending Run...":
    try:
        if isinstance(last_sync, str):
            try: parsed_sync = datetime.strptime(last_sync.strip(), "%d %b %Y, %I:%M %p")
            except: parsed_sync = datetime.strptime(last_sync.strip(), "%Y-%m-%d %H:%M:%S")
        else:
            parsed_sync = pd.to_datetime(last_sync)
            
        ist_now = datetime.now(ist).replace(tzinfo=None)
        if hasattr(parsed_sync, 'tzinfo') and parsed_sync.tzinfo is not None:
            parsed_sync = parsed_sync.replace(tzinfo=None)
            
        if (ist_now - parsed_sync).total_seconds() > 86400:
            last_sync_bg = "rgba(254, 202, 202, 0.4)"
    except Exception: pass

metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
if live_bg == "#FFFFFF" or "linear-gradient" in live_bg: live_bg = "#FFFFFF"
if nse_bg == "#FFFFFF" or "linear-gradient" in nse_bg: nse_bg = "#FFFFFF"
if alloc_bg == "#FFFFFF" or "linear-gradient" in alloc_bg: alloc_bg = "#FFFFFF"

with metric_col1: st.markdown(create_metric_card("📊 Market Breadth (Live)", live_sheet_breadth, live_bg), unsafe_allow_html=True)
with metric_col2: st.markdown(create_metric_card("⚖️ Market Breadth (NSE)", trend_regime, nse_bg), unsafe_allow_html=True)
with metric_col3: st.markdown(create_metric_card("💼 Portfolio Allocation", alloc_val, alloc_bg), unsafe_allow_html=True)
with metric_col4: st.markdown(create_metric_card("🔄 Last DB Update", last_sync, last_sync_bg), unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# DATA PROCESSING FOR TABS
# ==========================================
display_df = pd.DataFrame()
if data:
    df = pd.DataFrame(data, columns=["Symbol", "Close", "% Change", "Volume", "Temp_Exchange"])
    df['Symbol'] = df['Symbol'].astype(str).str.strip().str.upper()

    if not main_df.empty:
        df = df.merge(main_df, left_on="Symbol", right_on="ticker", how="left")
        
        if 'sector' in df.columns: df = df.merge(sec_rank_df, on="sector", how="left")
        if 'broad_industry' in df.columns: df = df.merge(ind_rank_df, on="broad_industry", how="left")
        
        db_exch = df.get('db_exchange', pd.Series([""] * len(df), index=df.index))
        df['Exchange'] = np.where(db_exch.notna() & (db_exch != ""), db_exch, df['Temp_Exchange'])
        
        for col in ['band', 'sector', 'broad_industry', 'sec_rank', 'ind_rank', 'relative_score']:
            if col not in df.columns: df[col] = ""
    else:
        df['sector'], df['broad_industry'], df['relative_score'], df['sec_rank'], df['ind_rank'], df['band'] = "", "", np.nan, np.nan, np.nan, ""
        df['Exchange'] = df['Temp_Exchange']

    df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
    df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
    df['Turnover (Cr)'] = (df['Close'] * df['Volume']) / 10000000

    for col in ['market_cap', 'sec_rank', 'ind_rank', 'relative_score']:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')

    df['Priority'] = np.nan
    if 'sec_rank' in df.columns and 'ind_rank' in df.columns:
        p1 = (df['sec_rank'] <= 5) & (df['ind_rank'] <= 10)
        p2 = (df['sec_rank'] <= 5) & (df['ind_rank'] <= 15) & ~p1
        p3 = (df['ind_rank'] <= 10) & ~p1 & ~p2
        p4 = (df['sec_rank'] <= 5) & ~p1 & ~p2 & ~p3
        p5 = (df['ind_rank'] <= 15) & (df['sec_rank'] >= 6) & ~p1 & ~p2 & ~p3 & ~p4
        df.loc[p1, 'Priority'] = 1
        df.loc[p2, 'Priority'] = 2
        df.loc[p3, 'Priority'] = 3
        df.loc[p4, 'Priority'] = 4
        df.loc[p5, 'Priority'] = 5

    display_cols = ["Priority", "Symbol", "Exchange", "band", "Close", "% Change", "market_cap", "Turnover (Cr)", "Volume", "sector", "sec_rank", "broad_industry", "ind_rank", "relative_score"]
    display_df = df[[c for c in display_cols if c in df.columns]].copy()
    display_df = display_df.sort_values(by=["Priority", "relative_score"], ascending=[True, True], na_position="last").fillna("")
    display_df = display_df.rename(columns={"band": "Band", "market_cap": "Mar Cap (Cr)", "sector": "Sector", "sec_rank": "Sector Rank", "broad_industry": "Industry", "ind_rank": "Ind. Rank", "relative_score": "Momentum Rank"})
    if 'Band' in display_df.columns: display_df['Band'] = display_df['Band'].replace("", "-").fillna("-")

def highlight_main_table(row):
    styles = []
    for col in row.index:
        style = ""
        if col == 'Priority' and pd.notna(row['Priority']) and str(row['Priority']).strip() != "":
            try:
                if float(row['Priority']) > 0: style += 'background-color: rgba(39, 174, 96, 0.15); '
            except: pass
        if col == 'Band' and str(row['Band']).strip() == '5': style += 'background-color: rgba(254, 202, 202, 0.4); '
        styles.append(style)
    return styles

def safe_int(val, prefix="", suffix=""):
    if val == "" or pd.isna(val): return ""
    try: return f"{prefix}{int(float(val))}{suffix}"
    except: return ""

def format_stars(val):
    if val == "" or pd.isna(val): return ""
    try:
        stars = 6 - int(float(val))
        if 1 <= stars <= 5: return "⭐" * stars
        return ""
    except: return ""

# ==========================================
# SAAS NAVIGATION TABS
# ==========================================
tab_main, tab_cycle, tab_leaders, tab_screeners, tab_port = st.tabs([
    "⚡ 9-EMA Screener", 
    "🎢 Market Cycle", 
    "🏆 Market Leaders",
    "🔎 Screeners", 
    "📈 Portfolio Tracker"
])

# --- 1. DEFAULT TAB: 9-EMA SCREENER (LIVE FEED) ---
with tab_main:
    if not display_df.empty:
        styled_df = display_df.style.hide(axis="index").apply(highlight_main_table, axis=1).format({
            "Close": lambda x: safe_fmt(x, "₹{:.2f}"), 
            "Chg %": lambda x: safe_fmt(x, "{:.2f}%"), 
            "Mar Cap (Cr)": lambda x: safe_fmt(x, "{:.0f}"), 
            "Turnover (Cr)": lambda x: safe_fmt(x, "{:.0f}"), 
            "Volume": lambda x: safe_fmt(x, "{:,.0f}"),
            "Momentum Rank": lambda x: safe_int(x), 
            "Priority": lambda x: format_stars(x),
            "Sector Rank": lambda x: safe_int(x, "#"), 
            "Ind. Rank": lambda x: safe_int(x, "#"),
        })
        
        html_table = styled_df.to_html()
        copy_str = ",".join(display_df['Symbol'].tolist())

        copy_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600;800&display=swap');
            body {{ margin: 0; padding: 0; display: flex; justify-content: flex-end; align-items: center; background-color: transparent; overflow: hidden; height: 100vh; }}
            button {{
                font-family: 'Inter', sans-serif; 
                background-color: #FFFFFF; color: #0B1D30; border: 2px solid #0B1D30; padding: 6px 16px; border-radius: 8px; cursor: pointer; font-weight: 800; font-size: 0.85rem; box-shadow: 0 6px 12px rgba(11, 29, 48, 0.15); transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); transform: translateY(0);
            }}
            button:hover {{ background-color: #F4F1E1; transform: translateY(-4px); box-shadow: 0 12px 24px rgba(11, 29, 48, 0.25); }}
            button:active {{ transform: translateY(1px); box-shadow: 0 2px 5px rgba(11, 29, 48, 0.15); }}
        </style>
        </head>
        <body>
            <button id="copyBtn" onclick="copyToClipboard()">📋 Copy Symbols</button>
            <script>
            function copyToClipboard() {{
                const ta = document.createElement('textarea'); ta.value = "{copy_str}"; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
                const btn = document.getElementById('copyBtn'); btn.innerHTML = '✅ Copied!'; setTimeout(() => btn.innerHTML = '📋 Copy Symbols', 2000);
            }}
            </script>
        </body>
        </html>
        """
        # Inline the copy button for Main Tab
        col_main_space, col_main_copy = st.columns([8.5, 1.5], vertical_alignment="bottom")
        with col_main_copy:
            components.html(copy_html, height=45)
        
        for _, r in display_df.iterrows():
            sym = str(r['Symbol'])
            exch = str(r['Exchange']).upper()
            if 'NSE' in exch: url = f"https://in.tradingview.com/chart/4efUco2X/?symbol=NSE%3A{sym}"
            else: url = f"https://in.tradingview.com/chart/?symbol=BSE%3A{sym}"
            link = f'<a href="{url}" target="_blank" style="color: inherit; text-decoration: none; border-bottom: 1px dashed #0B1D30; font-weight: 600;">{sym}</a>'
            html_table = re.sub(rf'(<td[^>]*>)({re.escape(sym)})(</td>)', rf'\1{link}\3', html_table)
            
        st.markdown(f'<div class="scrollable-table-container">{html_table}</div>', unsafe_allow_html=True)
    else: 
        st.info("No stocks matching criteria right now. Waiting for momentum...")

# --- 2. MARKET CYCLE TAB ---
with tab_cycle:
    if not raw_sec.empty and not raw_ind.empty:
        render_market_cycle_graph(roc_vals)

# --- 3. MARKET LEADERS TAB ---
with tab_leaders:
    if not raw_sec.empty and not raw_ind.empty:
        lead_col1, lead_col2 = st.columns(2)
        with lead_col1:
            st.markdown("##### 🔥 Top 5 Sectors")
            sec_cols = ['Rank', 'Sector', 'Avg 1D Return %', 'ATH_Stocks', 'ATH %']
            sec_cols = [c for c in sec_cols if c in raw_sec.columns]
            top_sec = raw_sec.nsmallest(5, 'Rank')[sec_cols]
            
            top_2_sec_idx = []
            if 'Avg 1D Return %' in top_sec.columns: top_2_sec_idx = top_sec['Avg 1D Return %'].astype(float).nlargest(2).index.tolist()
            if 'ATH %' in top_sec.columns: top_sec['ATH %'] = top_sec['ATH %'].astype(float).map("{:.2f}%".format)
            if 'Avg 1D Return %' in top_sec.columns: top_sec['Avg 1D Return %'] = top_sec['Avg 1D Return %'].astype(float).map("{:.2f}%".format)
            
            top_sec = top_sec.rename(columns={'ATH_Stocks': 'ATH Count', 'Avg 1D Return %': '1D Avg %'})
            html = "<div class='sleek-table-wrapper'><table class='sleek-table'><thead><tr>"
            for col in top_sec.columns: html += f"<th>{col}</th>"
            html += "</tr></thead><tbody>"
            for idx, row in top_sec.iterrows():
                html += "<tr>"
                for c in top_sec.columns:
                    val = row[c]
                    if idx in top_2_sec_idx and c == '1D Avg %': html += f"<td style='background-color: rgba(187, 247, 208, 0.5); font-weight: 600;'>{val}</td>"
                    elif idx in top_2_sec_idx and c == 'Sector': html += f"<td><b>{val}</b></td>"
                    else: html += f"<td>{val}</td>"
                html += "</tr>"
            html += "</tbody></table></div>"
            st.markdown(html, unsafe_allow_html=True)
            
        with lead_col2:
            st.markdown("##### 🚀 Top 15 Industries")
            ind_cols = ['Rank', 'Broad Industry', 'Avg 1D Return %', 'ATH_Stocks', 'ATH %']
            ind_cols = [c for c in ind_cols if c in raw_ind.columns]
            top_ind = raw_ind.nsmallest(15, 'Rank')[ind_cols]
            
            top_4_ind_idx = []
            if 'Avg 1D Return %' in top_ind.columns: top_4_ind_idx = top_ind['Avg 1D Return %'].astype(float).nlargest(4).index.tolist()
            if 'ATH %' in top_ind.columns: top_ind['ATH %'] = top_ind['ATH %'].astype(float).map("{:.2f}%".format)
            if 'Avg 1D Return %' in top_ind.columns: top_ind['Avg 1D Return %'] = top_ind['Avg 1D Return %'].astype(float).map("{:.2f}%".format)
            
            top_ind = top_ind.rename(columns={'ATH_Stocks': 'ATH Count', 'Avg 1D Return %': '1D Avg %'})
            html = "<div class='sleek-table-wrapper'><table class='sleek-table'><thead><tr>"
            for col in top_ind.columns: html += f"<th>{col}</th>"
            html += "</tr></thead><tbody>"
            for idx, row in top_ind.iterrows():
                html += "<tr>"
                for c in top_ind.columns:
                    val = row[c]
                    if idx in top_4_ind_idx and c == '1D Avg %': html += f"<td style='background-color: rgba(187, 247, 208, 0.5); font-weight: 600;'>{val}</td>"
                    elif idx in top_4_ind_idx and c == 'Broad Industry': html += f"<td><b>{val}</b></td>"
                    else: html += f"<td>{val}</td>"
                html += "</tr>"
            html += "</tbody></table></div>"
            st.markdown(html, unsafe_allow_html=True)

# --- 4. SCREENERS HUB TAB ---
with tab_screeners:
    sub_etf, sub_mom, sub_us_etf, sub_val = st.tabs([
        "📊 ETF Screener", 
        "🚀 Momentum Screener", 
        "🌍 US ETF Screener",
        "💎 Value Screener"
    ])
    
    # --- SUB 1: ETF SCREENER ---
    with sub_etf:
        col_etf_input, col_etf_space = st.columns([2, 8])
        with col_etf_input:
            etf_min_turnover = st.number_input("Minimum Turnover (in Cr)", min_value=0.0, value=3.0, step=1.0, key="etf_turnover")
        
        if not etf_df.empty:
            e_df = etf_df.copy()
            if 'Catergory' in e_df.columns: e_df = e_df.rename(columns={'Catergory': 'Category'})
                
            e_df['Turnover (Cr)'] = pd.to_numeric(e_df.get('Turnover (Cr)', 0), errors='coerce')
            e_df['Relative Score'] = pd.to_numeric(e_df.get('Relative Score', 0), errors='coerce')
            e_df['Chg %'] = pd.to_numeric(e_df.get('Chg %', 0), errors='coerce')
            
            f_ema = e_df.get('EMA 21 Status', '').astype(str).str.strip() == "Above 21 Ema"
            f_turn = e_df['Turnover (Cr)'] >= etf_min_turnover
            valid_etfs = e_df[f_ema & f_turn].sort_values('Relative Score', ascending=True)
            
            final_etfs = []
            seen_categories = set()
            for _, row in valid_etfs.iterrows():
                cat = str(row.get('Category', 'Unknown')).strip()
                if cat not in seen_categories and cat != 'nan' and cat != 'Unknown':
                    seen_categories.add(cat)
                    final_etfs.append(row)
                elif cat == 'Unknown' or cat == 'nan':
                    if 'Unknown' not in seen_categories:
                        seen_categories.add('Unknown')
                        final_etfs.append(row)
                        
            etf_display = pd.DataFrame(final_etfs)
            if not etf_display.empty:
                etf_display = etf_display.head(10).reset_index(drop=True)
                etf_display['Rank'] = etf_display.index + 1
                
                show_cols = ['Rank', 'Symbol', 'Chg %', 'Name', 'Category', 'EMA 21 Status', 'Turnover (Cr)']
                show_cols = [c for c in show_cols if c in etf_display.columns]
                etf_display = etf_display[show_cols]
                
                top_4_chg_idx = etf_display.head(4).index.tolist()
                top_4_avg = etf_display.head(4)['Chg %'].mean() if not etf_display.empty else 0.0
                avg_color = "#10B981" if top_4_avg > 0 else "#EF4444"
                
                etf_copy_str = ",".join(etf_display['Symbol'].astype(str).tolist())
                etf_copy_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600;800&display=swap');
                    body {{ margin: 0; padding: 0; display: flex; justify-content: flex-end; align-items: center; background-color: transparent; overflow: hidden; height: 100vh; }}
                    button {{
                        font-family: 'Inter', sans-serif; background-color: #FFFFFF; color: #0B1D30; border: 2px solid #0B1D30; padding: 6px 16px; border-radius: 8px; cursor: pointer; font-weight: 800; font-size: 0.85rem; box-shadow: 0 6px 12px rgba(11, 29, 48, 0.15); transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); transform: translateY(0);
                    }}
                    button:hover {{ background-color: #F4F1E1; transform: translateY(-4px); box-shadow: 0 12px 24px rgba(11, 29, 48, 0.25); }}
                    button:active {{ transform: translateY(1px); box-shadow: 0 2px 5px rgba(11, 29, 48, 0.15); }}
                </style>
                </head>
                <body>
                    <button id="copyEtfBtn" onclick="copyToClipboard()">📋 Copy Symbols</button>
                    <script>
                    function copyToClipboard() {{
                        const ta = document.createElement('textarea'); ta.value = "{etf_copy_str}"; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
                        const btn = document.getElementById('copyEtfBtn'); btn.innerHTML = '✅ Copied!'; setTimeout(() => btn.innerHTML = '📋 Copy Symbols', 2000);
                    }}
                    </script>
                </body>
                </html>
                """
                
                # Inline Average text and Copy Button side-by-side
                col_etf_avg, col_etf_copy = st.columns([8.5, 1.5], vertical_alignment="bottom")
                with col_etf_avg:
                    st.markdown(f"<h4 style='margin-bottom: 0px;'>Average 1D Return (Top 4): <span style='color: {avg_color};'>{top_4_avg:.2f}%</span></h4>", unsafe_allow_html=True)
                with col_etf_copy:
                    components.html(etf_copy_html, height=45)
                
                def style_etf_row(row):
                    is_top_4 = row.name in top_4_chg_idx
                    styles = []
                    for col in row.index:
                        cell_style = ""
                        if is_top_4:
                            cell_style += "font-weight: 700; "
                            if col == 'Chg %': cell_style += "background-color: rgba(187, 247, 208, 0.5); "
                        styles.append(cell_style)
                    return styles
                    
                styled_etf = etf_display.style.apply(style_etf_row, axis=1).hide(axis="index").format({
                    'Turnover (Cr)': lambda x: safe_fmt(x, "{:.0f}"), 
                    'Chg %': lambda x: safe_fmt(x, "{:.2f}%")
                })

                # CONVERT TO HTML AND INJECT TRADINGVIEW REDIRECT LINKS
                html_etf_table = styled_etf.to_html()
                for _, r in etf_display.iterrows():
                    sym = str(r['Symbol'])
                    url = f"https://in.tradingview.com/chart/4efUco2X/?symbol=NSE%3A{sym}"
                    link = f'<a href="{url}" target="_blank" style="color: inherit; text-decoration: none; border-bottom: 1px dashed #0B1D30; font-weight: 600;">{sym}</a>'
                    html_etf_table = re.sub(rf'(<td[^>]*>)({re.escape(sym)})(</td>)', rf'\1{link}\3', html_etf_table)

                st.markdown(f'<div class="scrollable-table-container">{html_etf_table}</div>', unsafe_allow_html=True)
            else: st.info("No ETFs match the criteria at the moment.")
        else: st.warning("ETF data is currently empty or failed to load.")

    # --- SUB 2: MOMENTUM SCREENER ---
    with sub_mom:
        col_mom_input, col_mom_space = st.columns([2, 8])
        with col_mom_input:
            min_turnover = st.number_input("Minimum Turnover (in Cr)", min_value=0.0, value=3.0, step=1.0, key="mom_turnover")
        
        if not main_df.empty:
            mom_df = main_df.copy()
            def _col_series(df, col, default=0):
                src = df.get(col, pd.Series([default] * len(df), index=df.index))
                return pd.to_numeric(src.astype(str).str.replace(',', '', regex=False).str.rstrip('%').replace({'nan': ''}), errors='coerce')

            mom_df['turnover'] = _col_series(mom_df, 'turnover')
            mom_df['down_ath'] = _col_series(mom_df, 'down_ath')
            mom_df['relative_score'] = _col_series(mom_df, 'relative_score')
            mom_df['market_cap'] = _col_series(mom_df, 'market_cap')
            mom_df['1d_return'] = _col_series(mom_df, '1d_return')
            
            if 'band' not in mom_df.columns: mom_df['band'] = ''
            if 'db_exchange' not in mom_df.columns: mom_df['db_exchange'] = 'NSE'
            
            f_exchange = mom_df['db_exchange'].astype(str).str.strip().str.upper() == 'NSE'
            f_turnover = mom_df['turnover'] >= min_turnover
            f_band     = ~mom_df['band'].astype(str).str.strip().isin(['2', '5', '2.0', '5.0'])
            f_ath      = mom_df['down_ath'] <= 20.0
            
            full_filtered_mom = mom_df[f_exchange & f_turnover & f_band & f_ath].copy()
            full_filtered_mom = full_filtered_mom.sort_values(by='relative_score', ascending=True).reset_index(drop=True)
            full_filtered_mom['Rank'] = full_filtered_mom.index + 1
            filtered_mom = full_filtered_mom.head(30)
            
            if not filtered_mom.empty:
                top_25_avg = filtered_mom.head(25)['1d_return'].mean()
                avg_color = "#10B981" if top_25_avg > 0 else "#EF4444"
                
                # Align inline text neatly
                col_mom_avg, col_mom_space2 = st.columns([8.5, 1.5], vertical_alignment="bottom")
                with col_mom_avg:
                    st.markdown(f"<h4 style='margin-bottom: 0px;'>Average 1D Return (Top 25): <span style='color: {avg_color};'>{top_25_avg:.2f}%</span></h4>", unsafe_allow_html=True)
                
                display_mom = filtered_mom[['Rank', 'ticker', 'stock_name', 'db_exchange', 'market_cap', 'turnover', '1d_return', 'band', 'sector', 'broad_industry']]
                display_mom = display_mom.rename(columns={'ticker': 'Ticker', 'stock_name': 'Stock Name', 'db_exchange': 'Exchange', 'market_cap': 'Market Cap (Cr)', 'turnover': 'Turnover (Cr)', '1d_return': '1 Day Return %', 'band': 'Band', 'sector': 'Sector', 'broad_industry': 'Industry'})
                display_mom['Band'] = display_mom['Band'].fillna("-")
                
                styled_mom = display_mom.style.hide(axis="index").format({
                    'Market Cap (Cr)': lambda x: safe_fmt(x, "{:.0f}"), 
                    'Turnover (Cr)': lambda x: safe_fmt(x, "{:.0f}"), 
                    '1 Day Return %': lambda x: safe_fmt(x, "{:.2f}%"), 
                    'Rank': lambda x: safe_fmt(x, "{:.0f}")
                })
                st.markdown(f'<div class="scrollable-table-container">{styled_mom.to_html()}</div>', unsafe_allow_html=True)
            else: st.info("No stocks match the Momentum Screener criteria at the moment.")
                
            st.divider()
            st.markdown("### 🔄 Upload Portfolio Stocks")
            st.markdown("<span style='color: #6B7280; font-size: 0.95rem;'>Upload a simple CSV or text file containing your portfolio tickers. The system will look at twice the size of your portfolio universe to determine the safe range and suggest rebalances.</span>", unsafe_allow_html=True)
            uploaded_file = st.file_uploader("Upload Rebalance Portfolio", type=['csv', 'txt'], label_visibility="collapsed", key="rebal_uploader")
            
            if uploaded_file is not None:
                try:
                    if uploaded_file.name.endswith('.csv'): 
                        st.session_state['rebal_port_df'] = pd.read_csv(uploaded_file, header=None)
                    else: 
                        st.session_state['rebal_port_df'] = pd.read_csv(uploaded_file, header=None, sep='\t')
                except Exception as e: st.error(f"Error reading file: {e}")
                    
            if 'rebal_port_df' in st.session_state:
                try:
                    user_port_df = st.session_state['rebal_port_df']
                    raw_tickers = user_port_df.iloc[:, 0].astype(str).str.strip().str.upper().tolist()
                    user_tickers = [t for t in raw_tickers if t and t not in ['TICKER', 'SYMBOL', 'NAME']]
                    user_tickers = list(dict.fromkeys(user_tickers)) 
                    
                    n_stocks = len(user_tickers)
                    if n_stocks > 0:
                        st.info(f"Loaded **{n_stocks}** unique tickers from your portfolio.")
                        st.markdown("#### 🚫 Exclude Unavailable Stocks")
                        unavailable_tickers = st.multiselect("Select replacement tickers hitting upper circuits or with low liquidity to skip them:", options=full_filtered_mom['ticker'].tolist(), help="Excluded stocks will be instantly bypassed, pulling the next best ranked stock.", key="mom_multi")
                        
                        unavailable_clean = [str(x).strip().upper() for x in unavailable_tickers]
                        user_clean = [str(x).strip().upper() for x in user_tickers]
                        full_filtered_mom['ticker_clean'] = full_filtered_mom['ticker'].astype(str).str.strip().str.upper()
                        mom_df['ticker_clean'] = mom_df['ticker'].astype(str).str.strip().str.upper()
                        
                        target_pool_size = n_stocks * 2
                        top_pool = full_filtered_mom.head(target_pool_size)
                        top_pool_tickers = top_pool['ticker_clean'].tolist()
                        
                        valid_reps = full_filtered_mom[~full_filtered_mom['ticker_clean'].isin(user_clean) & ~full_filtered_mom['ticker_clean'].isin(unavailable_clean)]
                        replacements_available = valid_reps.to_dict('records')
                        
                        rebalance_data = []
                        for t in user_tickers:
                            t_clean = str(t).strip().upper()
                            rank_match = full_filtered_mom[full_filtered_mom['ticker_clean'] == t_clean]
                            
                            if not rank_match.empty: curr_rank = int(rank_match['Rank'].iloc[0])
                            else:
                                fallback_match = mom_df[mom_df['ticker_clean'] == t_clean]
                                if not fallback_match.empty:
                                    score = fallback_match['relative_score'].iloc[0]
                                    curr_rank = int(float(score)) if pd.notna(score) and str(score).strip() != "" else "No Data"
                                else: curr_rank = "Not in DB"
                            
                            if t_clean in top_pool_tickers:
                                rebalance_data.append({"Portfolio Ticker": t, "Current Rank": curr_rank, "Status": "In Range (Hold)", "Suggested Replacement": "-", "Replacement Rank": "-"})
                            else:
                                if replacements_available:
                                    rep = replacements_available.pop(0) 
                                    rep_ticker = rep['ticker']
                                    rep_rank = rep['Rank']
                                else:
                                    rep_ticker = "No valid replacements left"
                                    rep_rank = "-"
                                rebalance_data.append({"Portfolio Ticker": t, "Current Rank": curr_rank, "Status": "Out of Range (Rebalance)", "Suggested Replacement": rep_ticker, "Replacement Rank": rep_rank})
                        
                        rebal_df = pd.DataFrame(rebalance_data)
                        def color_status(row):
                            if 'Hold' in str(row['Status']): return ['background-color: rgba(187, 247, 208, 0.3)'] * len(row) 
                            elif 'Rebalance' in str(row['Status']): return ['background-color: rgba(254, 202, 202, 0.3)'] * len(row) 
                            return [''] * len(row)
                        
                        styled_rebal = rebal_df.style.apply(color_status, axis=1).hide(axis="index")
                        st.markdown(f'<div class="scrollable-table-container">{styled_rebal.to_html()}</div>', unsafe_allow_html=True)
                    else: st.warning("Could not find any valid tickers in the uploaded file.")
                except Exception as e: st.error(f"Error processing portfolio: {e}")

    # --- SUB 3: US ETF SCREENER ---
    with sub_us_etf:
        if not us_etf_df.empty:
            us_df = us_etf_df.copy()
            
            us_df['Relative Score'] = pd.to_numeric(us_df.get('Relative Score', 0), errors='coerce')
            us_df['Price (USD)'] = pd.to_numeric(us_df.get('Price (USD)', 0), errors='coerce')
            us_df['Chg %'] = pd.to_numeric(us_df.get('Chg %', 0), errors='coerce')
            us_df['Avg Vol 30D'] = pd.to_numeric(us_df.get('Avg Vol 30D', 0), errors='coerce')
            us_df['Expense Ratio'] = pd.to_numeric(us_df.get('Expense Ratio', 0), errors='coerce')
            
            f_us_ema = us_df.get('EMA 21 Status', '').astype(str).str.strip().str.upper() == 'ABOVE 21 EMA'
            
            valid_us = us_df[f_us_ema].sort_values('Relative Score', ascending=True)
            
            final_us_etfs = []
            seen_us_categories = set()
            for _, row in valid_us.iterrows():
                cat = str(row.get('Category', 'Unknown')).strip()
                if cat not in seen_us_categories and cat != 'nan' and cat != 'Unknown':
                    seen_us_categories.add(cat)
                    final_us_etfs.append(row)
                if len(final_us_etfs) >= 10:
                    break
                    
            us_display = pd.DataFrame(final_us_etfs)
            if not us_display.empty:
                us_display = us_display.reset_index(drop=True)
                us_display['Rank'] = us_display.index + 1
                
                us_show_cols = ['Rank', 'Symbol', 'Price (USD)', 'Chg %', 'Category', 'Index', 'EMA 21 Status', 'Avg Vol 30D', 'Expense Ratio']
                us_show_cols = [c for c in us_show_cols if c in us_display.columns]
                us_display = us_display[us_show_cols]
                top_4_chg_idx = us_display.head(4).index.tolist()
                top_4_avg = us_display.head(4)['Chg %'].mean() if not us_display.empty else 0.0
                avg_color = "#10B981" if top_4_avg > 0 else "#EF4444"
                
                us_etf_copy_str = ",".join(us_display['Symbol'].astype(str).tolist())
                us_etf_copy_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600;800&display=swap');
                    body {{ margin: 0; padding: 0; display: flex; justify-content: flex-end; align-items: center; background-color: transparent; overflow: hidden; height: 100vh; }}
                    button {{
                        font-family: 'Inter', sans-serif; background-color: #FFFFFF; color: #0B1D30; border: 2px solid #0B1D30; padding: 6px 16px; border-radius: 8px; cursor: pointer; font-weight: 800; font-size: 0.85rem; box-shadow: 0 6px 12px rgba(11, 29, 48, 0.15); transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); transform: translateY(0);
                    }}
                    button:hover {{ background-color: #F4F1E1; transform: translateY(-4px); box-shadow: 0 12px 24px rgba(11, 29, 48, 0.25); }}
                    button:active {{ transform: translateY(1px); box-shadow: 0 2px 5px rgba(11, 29, 48, 0.15); }}
                </style>
                </head>
                <body>
                    <button id="copyUsEtfBtn" onclick="copyToClipboard()">📋 Copy Symbols</button>
                    <script>
                    function copyToClipboard() {{
                        const ta = document.createElement('textarea'); ta.value = "{us_etf_copy_str}"; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
                        const btn = document.getElementById('copyUsEtfBtn'); btn.innerHTML = '✅ Copied!'; setTimeout(() => btn.innerHTML = '📋 Copy Symbols', 2000);
                    }}
                    </script>
                </body>
                </html>
                """

                # Inline Average text and Copy Button side-by-side
                col_us_avg, col_us_copy = st.columns([8.5, 1.5], vertical_alignment="bottom")
                with col_us_avg:
                    st.markdown(f"<h4 style='margin-bottom: 0px;'>Average 1D Return (Top 4): <span style='color:{avg_color};'>{top_4_avg:.2f}%</span></h4>", unsafe_allow_html=True)
                with col_us_copy:
                    components.html(us_etf_copy_html, height=45)
                
                def style_us_row(row):
                    is_top_4 = row.name in top_4_chg_idx
                    styles = []
                    for col in row.index:
                        style = ""
                        if is_top_4:
                            style += "font-weight:700;"
                            if col == "Chg %": style += "background-color: rgba(187,247,208,0.5);"
                        styles.append(style)
                    return styles
                
                styled_us_etf = us_display.style.apply(style_us_row, axis=1).hide(axis="index").format({
                    'Price (USD)': lambda x: safe_fmt(x, "${:.2f}"),
                    'Chg %': lambda x: safe_fmt(x, "{:.2f}%"),
                    'Avg Vol 30D': lambda x: safe_fmt(x, "{:,.0f}"),
                    'Expense Ratio': lambda x: safe_fmt(x, "{:.2f}")
                })

                # CONVERT TO HTML AND INJECT TRADINGVIEW REDIRECT LINKS
                html_us_table = styled_us_etf.to_html()
                for _, r in us_display.iterrows():
                    sym = str(r['Symbol'])
                    url = f"https://www.tradingview.com/chart/4efUco2X/?symbol={sym}"
                    link = f'<a href="{url}" target="_blank" style="color: inherit; text-decoration: none; border-bottom: 1px dashed #0B1D30; font-weight: 600;">{sym}</a>'
                    html_us_table = re.sub(rf'(<td[^>]*>)({re.escape(sym)})(</td>)', rf'\1{link}\3', html_us_table)

                st.markdown(f'<div class="scrollable-table-container">{html_us_table}</div>', unsafe_allow_html=True)
            else: st.info("No US ETFs match the criteria at the moment.")
        else: st.warning("US ETF data is currently empty or failed to load.")

    # --- SUB 4: VALUE SCREENER ---
    with sub_val:
        col_val_input, col_val_space = st.columns([2, 8])
        with col_val_input:
            val_min_turnover = st.number_input("Minimum Turnover (in Cr)", min_value=0.0, value=3.0, step=1.0, key="val_turnover")
        
        if not micro_df.empty:
            v_df = micro_df.copy()
            
            col_cmp = next((c for c in v_df.columns if 'cmp' in str(c).lower() and '%' not in str(c).lower()), 'Price')
            col_chg = next(
                (c for c in v_df.columns if '1day return' in str(c).lower()),
                '1day return %'
            )
            col_vscore = next((c for c in v_df.columns if 'value score' in str(c).lower()), 'Value score')
            col_band = next((c for c in v_df.columns if 'band' in str(c).lower()), 'Band')
            col_sector = next((c for c in v_df.columns if 'sector' in str(c).lower()), 'Sector')
            col_ind = next((c for c in v_df.columns if 'industry' in str(c).lower()), 'Broad Industry')
            col_dath = next((c for c in v_df.columns if 'down %_ath' in str(c).lower() or 'down' in str(c).lower()), 'Down %_ATH')
            
            v_df[col_cmp] = pd.to_numeric(v_df.get(col_cmp, 0), errors='coerce')
            v_df[col_chg] = pd.to_numeric(v_df.get(col_chg, 0), errors='coerce')
            v_df[col_vscore] = pd.to_numeric(v_df.get(col_vscore, 0), errors='coerce')
            v_df[col_band] = pd.to_numeric(v_df.get(col_band, 100), errors='coerce')
            v_df['Turnover'] = pd.to_numeric(v_df.get('Turnover', 0), errors='coerce')
            v_df[col_dath] = pd.to_numeric(v_df.get(col_dath, 0), errors='coerce')
            
            f_vband = v_df[col_band] > 5
            f_vturn = v_df['Turnover'] >= val_min_turnover
            
            v_filtered = v_df[f_vband & f_vturn].sort_values(by=col_vscore, ascending=True).reset_index(drop=True)
            v_filtered['Rank'] = v_filtered.index + 1
            
            top_50_value = v_filtered.head(50)
            
            if not top_50_value.empty:
                top_25_val_avg = top_50_value.head(25)[col_chg].mean()
                v_avg_color = "#10B981" if top_25_val_avg > 0 else "#EF4444"
                
                # Align inline text neatly
                col_val_avg, col_val_space2 = st.columns([8.5, 1.5], vertical_alignment="bottom")
                with col_val_avg:
                    st.markdown(f"<h4 style='margin-bottom: 0px;'>Average 1D Return (Top 25): <span style='color: {v_avg_color};'>{top_25_val_avg:.2f}%</span></h4>", unsafe_allow_html=True)
                
                val_cols = ['Rank', 'Ticker', 'Name', col_chg, col_cmp, col_sector, col_ind, col_band, col_dath, 'Turnover']
                val_cols = [c for c in val_cols if c in top_50_value.columns]
                val_display = top_50_value[val_cols].copy()
                
                val_display = val_display.rename(columns={
                    'Ticker': 'Symbol',
                    col_chg: 'Chg %',
                    col_cmp: 'Price',
                    col_sector: 'Sector',
                    col_ind: 'Industry',
                    col_band: 'Band',
                    col_dath: 'Down%_ATH'
                })
                
                styled_val = val_display.style.hide(axis="index").format({
                    'Price': lambda x: safe_fmt(x, "₹{:.2f}"), 
                    'Chg %': lambda x: safe_fmt(x, "{:.2f}%"), 
                    'Turnover': lambda x: safe_fmt(x, "{:,.0f}"),
                    'Down%_ATH': lambda x: safe_fmt(x, "{:.2f}%"),
                    'Band': lambda x: safe_fmt(x, "{:.0f}")
                })
                st.markdown(f'<div class="scrollable-table-container">{styled_val.to_html()}</div>', unsafe_allow_html=True)
            else: st.info("No stocks match the Value Screener criteria at the moment.")
            
            st.divider()
            st.markdown("### 🔄 Upload Portfolio Stocks to Rebalance")
            val_uploaded_file = st.file_uploader("Upload Value Portfolio", type=['csv', 'txt'], label_visibility="collapsed", key="val_rebal_uploader")
            
            if val_uploaded_file is not None:
                try:
                    if val_uploaded_file.name.endswith('.csv'): 
                        st.session_state['val_rebal_port_df'] = pd.read_csv(val_uploaded_file, header=None)
                    else: 
                        st.session_state['val_rebal_port_df'] = pd.read_csv(val_uploaded_file, header=None, sep='\t')
                except Exception as e: st.error(f"Error reading file: {e}")
                    
            if 'val_rebal_port_df' in st.session_state:
                try:
                    v_user_df = st.session_state['val_rebal_port_df']
                    v_raw_tickers = v_user_df.iloc[:, 0].astype(str).str.strip().str.upper().tolist()
                    v_user_tickers = [t for t in v_raw_tickers if t and t not in ['TICKER', 'SYMBOL', 'NAME']]
                    v_user_tickers = list(dict.fromkeys(v_user_tickers)) 
                    
                    v_n_stocks = len(v_user_tickers)
                    if v_n_stocks > 0:
                        st.info(f"Loaded **{v_n_stocks}** unique tickers from your portfolio.")
                        v_unavailable = st.multiselect("Select replacement tickers to skip:", options=v_filtered['Ticker'].tolist(), key="val_multi")
                        
                        v_unavail_clean = [str(x).strip().upper() for x in v_unavailable]
                        v_user_clean = [str(x).strip().upper() for x in v_user_tickers]
                        v_filtered['ticker_clean'] = v_filtered['Ticker'].astype(str).str.strip().str.upper()
                        
                        v_target_size = v_n_stocks * 2
                        v_top_pool = v_filtered.head(v_target_size)
                        v_top_pool_tickers = v_top_pool['ticker_clean'].tolist()
                        
                        v_valid_reps = v_filtered[~v_filtered['ticker_clean'].isin(v_user_clean) & ~v_filtered['ticker_clean'].isin(v_unavail_clean)]
                        v_reps_avail = v_valid_reps.to_dict('records')
                        
                        v_rebal_data = []
                        for t in v_user_tickers:
                            t_clean = str(t).strip().upper()
                            rank_match = v_filtered[v_filtered['ticker_clean'] == t_clean]
                            
                            if not rank_match.empty: v_curr_rank = int(rank_match['Rank'].iloc[0])
                            else: v_curr_rank = "Not in DB"
                            
                            if t_clean in v_top_pool_tickers:
                                v_rebal_data.append({"Portfolio Ticker": t, "Current Rank": v_curr_rank, "Status": "In Range (Hold)", "Suggested Replacement": "-", "Replacement Rank": "-"})
                            else:
                                if v_reps_avail:
                                    rep = v_reps_avail.pop(0) 
                                    v_rep_ticker = rep['Ticker']
                                    v_rep_rank = rep['Rank']
                                else:
                                    v_rep_ticker = "No valid replacements left"
                                    v_rep_rank = "-"
                                v_rebal_data.append({"Portfolio Ticker": t, "Current Rank": v_curr_rank, "Status": "Out of Range (Rebalance)", "Suggested Replacement": v_rep_ticker, "Replacement Rank": v_rep_rank})
                        
                        v_rebal_df = pd.DataFrame(v_rebal_data)
                        def val_color_status(row):
                            if 'Hold' in str(row['Status']): return ['background-color: rgba(187, 247, 208, 0.3)'] * len(row) 
                            elif 'Rebalance' in str(row['Status']): return ['background-color: rgba(254, 202, 202, 0.3)'] * len(row) 
                            return [''] * len(row)
                        
                        styled_v_rebal = v_rebal_df.style.apply(val_color_status, axis=1).hide(axis="index")
                        st.markdown(f'<div class="scrollable-table-container">{styled_v_rebal.to_html()}</div>', unsafe_allow_html=True)
                    else: st.warning("Could not find any valid tickers in the uploaded file.")
                except Exception as e: st.error(f"Error processing portfolio: {e}")
        else: st.warning("Value Screener data is currently empty or failed to load.")

# --- 5. PORTFOLIO TRACKER TAB ---
with tab_port:
    col_text, col_clear = st.columns([9, 2], vertical_alignment="center")
    with col_text:
        st.markdown("<p style='color:#4B5563; font-size: 0.9rem; margin: 0;'>Track your portfolio via Google Sheets or CSV upload. The app pulls the first 5 columns: Ticker, Entry Date, Entry Price, Stop Loss, Risk.</p>", unsafe_allow_html=True)
    with col_clear:
        if st.button("🧹 Clear Cache & Reset Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    st.markdown("""
<style>
div[data-testid="stRadio"]{
    margin-top:-4px !important;
    margin-bottom:0px !important;
    padding-top:0px !important;
    padding-bottom:0px !important;
}

div[role="radiogroup"]{
    margin:0 !important;
    padding:0 !important;
}
</style>
""", unsafe_allow_html=True)

    data_source = st.radio(
        "",
        ["Upload CSV", "Google Sheets"],
        index=1,
        horizontal=True,
        label_visibility="collapsed"
    )

    # Input and Load Button layout
    input_col, btn_col = st.columns([9, 2])
    with input_col:
        if data_source == "Upload CSV":
            uploaded_file = st.file_uploader("Upload your Portfolio CSV file", type=['csv'], label_visibility="collapsed")
        else:
            gs_url = st.text_input("Google Sheets URL:", value="https://docs.google.com/spreadsheets/d/1GqgxZk8Z2xJAVAaKONWVGy8pTQ38qcQWlSw3qC9tL98/edit?gid=0#gid=0", label_visibility="collapsed")
    
    with btn_col:
        load_data = st.button("🔄 Load / Refresh Sheet", use_container_width=True)

    if load_data:
        with st.spinner("🔄 Fetching and syncing portfolio data..."):
            try:
                port_df = pd.DataFrame()
                
                # 1. Parse File/URL
                if data_source == "Google Sheets" and "docs.google.com" in gs_url:
                    match = re.search(r'[#&?]gid=([0-9]+)', gs_url)
                    gid = match.group(1) if match else "0"
                    csv_url = re.sub(r'/edit.*', f'/export?format=csv&gid={gid}', gs_url)
                    port_df = pd.read_csv(csv_url)
                elif data_source == "Upload CSV" and uploaded_file is not None:
                    port_df = pd.read_csv(uploaded_file)
                else:
                    st.warning("Please provide a valid data source.")
                    st.stop()
                
                # 2. Fuzzy Matching & Regex Cleanup
                port_df.columns = port_df.columns.str.strip()
                for col in port_df.columns:
                    col_name = str(col).lower()
                    if 'ticker' in col_name or 'symbol' in col_name: port_df = port_df.rename(columns={col: "Stock Ticker"})
                    elif 'risk' in col_name: port_df = port_df.rename(columns={col: "Risk"})
                    elif 'entry price' in col_name: port_df = port_df.rename(columns={col: "Entry Price"})
                    elif 'stop loss' in col_name: port_df = port_df.rename(columns={col: "Stop Loss"})
                    elif 'date' in col_name: port_df = port_df.rename(columns={col: "Entry date"})

                if "Risk" in port_df.columns:
                    port_df["Risk"] = port_df["Risk"].astype(str).str.replace(r'[^\d.-]', '', regex=True)
                    port_df["Risk"] = pd.to_numeric(port_df["Risk"], errors='coerce') / 100
                if "Entry Price" in port_df.columns:
                    port_df["Entry Price"] = pd.to_numeric(port_df["Entry Price"].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce')
                if "Stop Loss" in port_df.columns:
                    port_df["Stop Loss"] = pd.to_numeric(port_df["Stop Loss"].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce')
                
                # 3. Supabase Prefix Mapping (VLOOKUP)
                exchange_map = fetch_exchange_mapping()
                search_symbols = []
                
                for idx, row in port_df.iterrows():
                    sym = str(row.get('Stock Ticker', '')).strip().upper()
                    if not sym or sym == "NAN": continue
                    
                    if ":" not in sym:
                        mapped_sym = exchange_map.get(sym, sym) # Fetch from dictionary, fallback to raw
                        search_symbols.append(mapped_sym)
                        port_df.at[idx, 'Mapped_Symbol'] = mapped_sym
                    else:
                        search_symbols.append(sym)
                        port_df.at[idx, 'Mapped_Symbol'] = sym

                # Extract pure tickers for the API filter
                pure_tickers = list(set([s.split(":")[-1] if ":" in s else s for s in search_symbols]))
                
                # 4. Fetch Live Data
                live_tv_data = fetch_portfolio_tv_data(pure_tickers)

                # 5. Build Final Dataset with Multi-Market Holidays
                tracker_data = []
                today = pd.to_datetime('today').normalize()
                years_to_check = [today.year, today.year - 1]
                us_holidays = np.array(list(holidays.country_holidays('US', years=years_to_check).keys()), dtype='datetime64[D]')
                in_holidays = np.array(list(holidays.country_holidays('IN', years=years_to_check).keys()), dtype='datetime64[D]')

                for _, row in port_df.iterrows():
                    mapped_sym = str(row.get('Mapped_Symbol', '')).strip().upper()
                    pure_sym = mapped_sym.split(":")[-1] if ":" in mapped_sym else mapped_sym
                    if not mapped_sym or mapped_sym == "NAN": continue
                    
                    tv = live_tv_data.get(mapped_sym)
                    if not tv: # Fallback matcher just in case
                        for k, v in live_tv_data.items():
                            if k.endswith(f":{pure_sym}"):
                                tv = v
                                break
                    if not tv: tv = {"price": 0.0, "change": 0.0, "ema21": 0.0}
                    
                    entry_price = float(row['Entry Price']) if pd.notna(row['Entry Price']) else 0.0
                    stop_loss = float(row['Stop Loss']) if pd.notna(row['Stop Loss']) else 0.0
                    
                    current_price = tv["price"]
                    profit_loss = current_price - entry_price if entry_price > 0 else 0.0
                    return_pct = (profit_loss / entry_price * 100) if entry_price > 0 else 0.0
                    
                    try:
                        entry_dt = pd.to_datetime(row['Entry date'], format='%d-%m-%Y', errors='coerce')
                        start_date = np.datetime64(entry_dt, 'D')
                        end_date = np.datetime64(today, 'D')
                        
                        if pd.isna(entry_dt) or start_date > end_date:
                            trading_days = 0
                        else:
                            if 'NSE:' in mapped_sym or 'BSE:' in mapped_sym:
                                trading_days = np.busday_count(start_date, end_date, holidays=in_holidays)
                            else:
                                trading_days = np.busday_count(start_date, end_date, holidays=us_holidays)
                    except:
                        trading_days = 0
                    
                    ema21_val = tv["ema21"]
                    ema_status = "ABOVE EMA21" if current_price > ema21_val else "BELOW EMA21"
                    
                    # Cumulative 10-Day Math
                    if trading_days < 10:
                        rule_status = f"PENDING ({int(trading_days)}/10)"
                    else:
                        required_return = (trading_days // 10) * 5.0
                        if return_pct < required_return:
                            rule_status = f"EXIT ({return_pct:.2f}%)"
                        else:
                            rule_status = f"PASS ({return_pct:.2f}%)"
                            
                    # Currency Prefix for Formatting
                    curr_pfx = "₹" if ('NSE:' in mapped_sym or 'BSE:' in mapped_sym) else "$"

                    tracker_data.append({
                        "Symbol": pure_sym,
                        "Entry Date": row['Entry date'],
                        "Today chg%": tv["change"],
                        "Entry Price": f"{curr_pfx}{entry_price:.2f}",
                        "Stop Loss": f"{curr_pfx}{stop_loss:.2f}",
                        "Risk %": row.get('Risk', 0.0),
                        "Current Price": f"{curr_pfx}{current_price:.2f}",
                        "Profit/Loss": f"{curr_pfx}{profit_loss:.2f}",
                        "Return %": return_pct,
                        "Trading Days": trading_days,
                        "EMA21": f"{curr_pfx}{ema21_val:.2f}",
                        "EMA 21 Status": ema_status,
                        "10 Day Rule": rule_status
                    })
                
                final_port_df = pd.DataFrame(tracker_data)
                avg_chg = final_port_df['Today chg%'].mean()
                
                port_col1, port_col2 = st.columns([8.5, 1.5], vertical_alignment="bottom")
                with port_col1:
                    avg_color = "#10B981" if avg_chg > 0 else "#EF4444"
                    st.markdown(f"<h4 style='margin-bottom: 0px;'>Avg chg%: <span style='color: {avg_color};'>{avg_chg:.2f}%</span></h4>", unsafe_allow_html=True)
                
                with port_col2:
                    port_copy_str = ",".join(final_port_df['Symbol'].tolist())
                    port_copy_html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                    <style>
                        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600;800&display=swap');
                        body {{ margin: 0; padding: 0; display: flex; justify-content: flex-end; align-items: center; background-color: transparent; overflow: hidden; height: 100vh; }}
                        button {{
                            font-family: 'Inter', sans-serif; background-color: #FFFFFF; color: #0B1D30; border: 2px solid #0B1D30; padding: 6px 16px; border-radius: 8px; cursor: pointer; font-weight: 800; font-size: 0.85rem; box-shadow: 0 6px 12px rgba(11, 29, 48, 0.15); transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); transform: translateY(0);
                        }}
                        button:hover {{ background-color: #F4F1E1; transform: translateY(-4px); box-shadow: 0 12px 24px rgba(11, 29, 48, 0.25); }}
                        button:active {{ transform: translateY(1px); box-shadow: 0 2px 5px rgba(11, 29, 48, 0.15); }}
                    </style>
                    </head>
                    <body>
                        <button id="copyPortBtn" onclick="copyToClipboard()">📋 Copy Symbols</button>
                        <script>
                        function copyToClipboard() {{
                            const ta = document.createElement('textarea');
                            ta.value = "{port_copy_str}";
                            document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
                            const btn = document.getElementById('copyPortBtn');
                            btn.innerHTML = '✅ Copied!'; setTimeout(() => btn.innerHTML = '📋 Copy Symbols', 2000);
                        }}
                        </script>
                    </body>
                    </html>
                    """
                    components.html(port_copy_html, height=45)
                
                def style_portfolio(row):
                    bg_color = [''] * len(row)
                    ret_idx = final_port_df.columns.get_loc('Return %')
                    ema_stat_idx = final_port_df.columns.get_loc('EMA 21 Status')
                    rule_idx = final_port_df.columns.get_loc('10 Day Rule')
                    sl_idx = final_port_df.columns.get_loc('Stop Loss')
                    sym_idx = final_port_df.columns.get_loc('Symbol')
                    
                    if row['Return %'] > 0: bg_color[ret_idx] = 'background-color: rgba(187, 247, 208, 0.4); color: green; font-weight: bold;'
                    elif row['Return %'] < 0: bg_color[ret_idx] = 'background-color: rgba(254, 202, 202, 0.4); color: red; font-weight: bold;'
                    
                    has_alert = False
                    
                    if "ABOVE" in str(row['EMA 21 Status']): bg_color[ema_stat_idx] = 'color: green; font-weight: bold;'
                    elif "BELOW" in str(row['EMA 21 Status']): 
                        bg_color[ema_stat_idx] = 'background-color: rgba(254, 202, 202, 0.7); color: red; font-weight: bold;'
                        has_alert = True
                    
                    if "PASS" in str(row['10 Day Rule']): bg_color[rule_idx] = 'background-color: rgba(187, 247, 208, 0.4); color: green; font-weight: bold;'
                    elif "EXIT" in str(row['10 Day Rule']): 
                        bg_color[rule_idx] = 'background-color: rgba(254, 202, 202, 0.7); color: red; font-weight: bold;'
                        has_alert = True
                        
                    try:
                        curr_p = float(str(row['Current Price']).replace('$','').replace('₹','').strip())
                        sl_p = float(str(row['Stop Loss']).replace('$','').replace('₹','').strip())
                        if curr_p <= sl_p and curr_p > 0:
                            bg_color[sl_idx] = 'background-color: rgba(254, 202, 202, 0.7); color: red; font-weight: bold;'
                            has_alert = True
                    except: pass
                    
                    if has_alert:
                        bg_color[sym_idx] = 'background-color: rgba(254, 202, 202, 0.7); color: red; font-weight: bold;'
                    
                    return bg_color

                styled_port = final_port_df.style.apply(style_portfolio, axis=1).hide(axis="index").format({
                    "Today chg%": "{:.2f}%",
                    "Return %": "{:.2f}%",
                    "Risk %": "{:.2%}"
                })
                
                # Inject TradingView links back in based on the pure symbol!
                html_port_table = styled_port.to_html()
                for _, r in final_port_df.iterrows():
                    sym = str(r["Symbol"])
                    url = f"https://in.tradingview.com/chart/4efUco2X/?symbol={sym}"
                    link = f'<a href="{url}" target="_blank" style="color: inherit; text-decoration: none; border-bottom: 1px dashed #0B1D30; font-weight: 600;">{sym}</a>'
                    html_port_table = re.sub(rf'(<td[^>]*>)({re.escape(sym)})(</td>)', rf'\1{link}\3', html_port_table)
                
                st.markdown(f'<div class="scrollable-table-container">{html_port_table}</div>', unsafe_allow_html=True)
                
            except Exception as e:
                st.error(f"Error loading data: {str(e)}. Ensure columns match: 'Stock Ticker', 'Entry date', 'Entry Price', 'Stop Loss', 'Risk'")

time.sleep(60)
st.rerun()
