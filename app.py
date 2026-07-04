import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
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
            margin-bottom: 30px;
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
        
        /* TABLE STYLING - MODIFIED TO ABSORB NEW COLUMN AND AVOID SCROLLING */
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

        /* MOBILE GRAPH RESPONSIVENESS */
        @media (max-width: 768px) {
            div.stPlotlyChart svg text {
                font-size: 10px !important;
            }
            /* Shift text labels up on mobile to prevent clipping the curve */
            div.stPlotlyChart svg g.textpoint {
                transform: translateY(-15px);
            }
        }

        /* PROFESSIONAL FULL-WIDTH SAAS TABS */
        div[data-baseweb="tab-list"] { 
            display: flex !important;
            width: 100% !important;
            gap: 15px !important;
            border-bottom: none !important;
            margin-bottom: 25px !important;
            padding-top: 10px !important; /* Space for hover pop */
        }
        
        div[data-baseweb="tab"] { 
            padding: 0 !important;
            background: transparent !important;
            flex: 1 !important; /* Forces all tabs to be equal width and span entire screen */
            min-width: 0 !important;
        }
        
        /* Tab Button Physics & Styling */
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
        
        /* IMMERSIVE POPUP - Hover Effect for Tabs */
        button[role="tab"]:hover {
            transform: translateY(-6px) !important;
            box-shadow: 0 20px 40px rgba(11, 29, 48, 0.35), 0 8px 15px rgba(11, 29, 48, 0.2) !important;
            background: linear-gradient(135deg, #0f2640 0%, #1d3a5a 100%) !important;
        }
        
        /* Selected Tab State (The White Layer with Thick Navy Line) */
        button[role="tab"][aria-selected="true"] {
            background: #FFFFFF !important;
            border: 2px solid #0B1D30 !important;
            border-top: 6px solid #0B1D30 !important; /* Thick anchoring line */
            transform: translateY(-6px) !important; /* Keep it popped up when active */
            box-shadow: 0 15px 30px rgba(11, 29, 48, 0.15) !important;
        }
        
        /* Tab Text Sizing - Restored to large 1.4rem size */
        button[role="tab"] p { 
            font-size: 1.4rem !important; 
            font-weight: 800 !important; 
            color: #FFFFFF !important; 
            margin: 0 !important;
            transition: color 0.3s ease !important;
            white-space: nowrap !important;
        }
        
        /* Selected Tab Text Color */
        button[role="tab"][aria-selected="true"] p {
            color: #0B1D30 !important;
        }
        
        /* Remove default Streamlit tab active line */
        div[data-baseweb="tab-highlight"] { 
            display: none !important; 
        }
        
        /* FORCE ALL BUTTONS TO BE WHITE WITH NAVY TEXT (Fixes dark mode mobile issue) */
        div[data-testid="stButton"] button {
            background-color: #FFFFFF !important;
            color: #0B1D30 !important;
            border: 2px solid #0B1D30 !important;
            border-radius: 8px !important;
            font-weight: 800 !important;
        }
        div[data-testid="stButton"] button:hover {
            background-color: #F4F1E1 !important;
            color: #0B1D30 !important;
        }
        
        /* FORCE TEXT INPUTS TO BE WHITE/LIGHT */
        div[data-testid="stTextInput"] input {
            background-color: #FFFFFF !important;
            color: #0B1D30 !important;
            border: 1px solid #0B1D30 !important;
        }
        
        /* Make Number Input values (like 3.00) massive and bold and white background */
        div[data-testid="stNumberInput"] input {
            background-color: #FFFFFF !important;
            font-size: 1.5rem !important;
            font-weight: 800 !important;
            color: #0B1D30 !important;
            border: 1px solid #0B1D30 !important;
        }
        
        /* FORCE RADIO BUTTONS TEXT/BACKGROUND */
        div[role="radiogroup"] label {
            color: #0B1D30 !important;
        }

        /* UPLOAD BUTTON VISIBILITY ON MOBILE - FORCE WHITE BACKGROUND */
        div[data-testid="stFileUploader"] {
            background-color: #FFFFFF !important;
            border: 2px dashed #0B1D30 !important;
            border-radius: 8px !important;
            padding: 15px !important;
        }
        div[data-testid="stFileUploader"] section {
            background-color: transparent !important;
        }
        div[data-testid="stFileUploader"] span, 
        div[data-testid="stFileUploader"] p, 
        div[data-testid="stFileUploader"] small {
            color: #0B1D30 !important;
            font-weight: 600 !important;
        }
        /* Force the Browse Files button to be white with navy text */
        div[data-testid="stFileUploader"] button {
            background-color: #FFFFFF !important;
            color: #0B1D30 !important;
            border: 2px solid #0B1D30 !important;
            border-radius: 6px !important;
            font-weight: 800 !important;
        }
        div[data-testid="stFileUploader"] button:hover {
            background-color: #F4F1E1 !important;
        }
        
        /* Pulse Animation for Loader */
        @keyframes pulse-logo {
            0% { transform: scale(1); opacity: 0.6; }
            50% { transform: scale(1.3); opacity: 1; text-shadow: 0 0 20px #FFD700; }
            100% { transform: scale(1); opacity: 0.6; }
        }

    </style>
""", unsafe_allow_html=True)

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

@st.cache_data(ttl=86400)
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

@st.cache_data(ttl=60)
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
# UPSTOX HELPER FUNCTIONS
# ==========================================
@st.cache_data(ttl=604800) # Exact match: Cache for 1 week (604,800 seconds)
def get_instrument_mapping():
    try:
        url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        
        with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as f:
            df = pd.read_json(f)
            
        df = df[df["segment"].isin(["NSE_EQ", "BSE_EQ", "BSE"])]
        df = df.drop_duplicates(subset=["trading_symbol"])
        return dict(zip(df["trading_symbol"].astype(str).str.upper(), df["instrument_key"]))
    except Exception as e:
        return {"error": str(e)}

def fetch_upstox_history(instrument_key, start_date, end_date, token):
    encoded_key = urllib.parse.quote(instrument_key)
    url = f"https://api.upstox.com/v2/historical-candle/{encoded_key}/day/{end_date}/{start_date}"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, headers=headers)
        time.sleep(0.3)
        if response.status_code != 200:
            return pd.DataFrame(), response.status_code
        candles = response.json().get("data", {}).get("candles", [])
        if not candles:
            return pd.DataFrame(), 200
        df = pd.DataFrame(candles, columns=["timestamp", "Open", "High", "Low", "Close", "Volume", "OI"])
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
        for col in ["Open", "High", "Low", "Close"]:
            df[col] = pd.to_numeric(df[col])
        return df, 200
    except Exception as e:
        return pd.DataFrame(), 500

def get_live_quote(instrument_key, token):
    url = "https://api.upstox.com/v2/market-quote/quotes"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    params = {
        "instrument_key": instrument_key
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        quote = data.get("data", {}).get(instrument_key, {})
        if not quote:
            return None
            
        ltp = quote.get("last_price")
        prev = quote.get("ohlc", {}).get("close")
        
        if prev and prev != 0 and ltp:
            pct = ((ltp - prev) / prev) * 100
        else:
            pct = 0.0
            
        return ltp, pct
    except Exception:
        return None

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
    trend_dir = "up"
    if len(roc_vals) > 1:
        lookback_index = 20 if len(roc_vals) > 20 else len(roc_vals) - 1
        if roc_val < float(roc_vals[lookback_index]): trend_dir = "down"

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
        <p style="margin: 8px 0 0 0; font-size: 1rem; color: #374151; font-style: italic;">"{note}"</p>
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

loader_placeholder = st.empty()
loader_placeholder.markdown("""
    <div style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(244, 241, 225, 0.65); backdrop-filter: blur(3px); z-index: 9999; display: flex; justify-content: center; align-items: center; flex-direction: column;">
        <div style="font-size: 5rem; animation: pulse-logo 1.5s infinite ease-in-out;">⚡</div>
        <div style="color: #0B1D30; font-weight: 800; font-size: 1.2rem; margin-top: 15px; letter-spacing: 2px;">SYNCING LIVE DATA</div>
    </div>
""", unsafe_allow_html=True)

data = get_combined_data()
current_cache_key = get_db_cache_key()
main_df, sec_rank_df, ind_rank_df, raw_sec, raw_ind, last_sync, trend_regime, roc_vals, etf_df, us_etf_df, micro_df = fetch_database_reference(current_cache_key)  
live_sheet_breadth = fetch_market_breadth_from_gsheets()

loader_placeholder.empty()

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
        df = df.merge(sec_rank_df, on="sector", how="left")
        df = df.merge(ind_rank_df, on="broad_industry", how="left")
        df['Exchange'] = np.where(df['db_exchange'].notna() & (df['db_exchange'] != ""), df['db_exchange'], df['Temp_Exchange'])
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
    "📈 9-EMA Portfolio Tracker"
])

# --- 1. DEFAULT TAB: 9-EMA SCREENER (LIVE FEED) ---
with tab_main:
    if not display_df.empty:
        # Applying the SAFE formatter everywhere
        styled_df = display_df.style.hide(axis="index").apply(highlight_main_table, axis=1).format({
            "Close": lambda x: safe_fmt(x, "₹{:.2f}"), 
            "% Change": lambda x: safe_fmt(x, "{:.2f}%"), 
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

        # Render a tiny, interactive Copy Button right above the table using a sandboxed iframe
        copy_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600&display=swap');
            body {{ margin: 0; padding: 0; display: flex; justify-content: flex-end; align-items: flex-end; background-color: transparent; overflow: hidden; }}
            button {{
                font-family: 'Inter', sans-serif; background-color: #0B1D30; color: #FFFFFF; 
                border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; 
                font-weight: 600; font-size: 0.85rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                transition: all 0.2s;
            }}
            button:hover {{ background-color: #162C46; transform: translateY(-1px); }}
        </style>
        </head>
        <body>
            <button id="copyBtn" onclick="copyToClipboard()">📋 Copy Symbols</button>
            <script>
            function copyToClipboard() {{
                const ta = document.createElement('textarea');
                ta.value = "{copy_str}";
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                
                // Visual feedback that it actually worked
                const btn = document.getElementById('copyBtn');
                btn.innerHTML = '✅ Copied!';
                setTimeout(() => btn.innerHTML = '📋 Copy Symbols', 2000);
            }}
            </script>
        </body>
        </html>
        """
        # Inject the micro-component directly above the table
        components.html(copy_html, height=40)
        
        for _, r in display_df.iterrows():
            sym = str(r['Symbol'])
            exch = str(r['Exchange']).upper()
            if 'NSE' in exch:
                url = f"https://in.tradingview.com/chart/4efUco2X/?symbol=NSE%3A{sym}"
            else:
                url = f"https://in.tradingview.com/chart/?symbol=BSE%3A{sym}"
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
            top_ind = raw_ind.nssmallest(15, 'Rank')[ind_cols]
            
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
        st.markdown("### Minimum Turnover (in Cr)")
        etf_min_turnover = st.number_input("ETF Minimum Turnover (in Cr)", min_value=0.0, value=3.0, step=1.0, key="etf_turnover", label_visibility="collapsed")
        
        if not etf_df.empty:
            e_df = etf_df.copy()
            if 'Catergory' in e_df.columns: e_df = e_df.rename(columns={'Catergory': 'Category'})
                
            e_df['Turnover (Cr)'] = pd.to_numeric(e_df['Turnover (Cr)'], errors='coerce')
            e_df['Relative Score'] = pd.to_numeric(e_df['Relative Score'], errors='coerce')
            e_df['Chg %'] = pd.to_numeric(e_df['Chg %'], errors='coerce')
            
            f_ema = e_df['EMA 21 Status'].astype(str).str.strip() == "Above 21 Ema"
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
                
                st.markdown(f"#### Average 1D Return (Top 4): <span style='color: {avg_color};'>{top_4_avg:.2f}%</span>", unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)
                
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

                # 1. GENERATE COPY BUTTON FOR INDIAN ETFs
                etf_copy_str = ",".join(etf_display['Symbol'].astype(str).tolist())
                etf_copy_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600&display=swap');
                    body {{ margin: 0; padding: 0; display: flex; justify-content: flex-end; align-items: flex-end; background-color: transparent; overflow: hidden; }}
                    button {{
                        font-family: 'Inter', sans-serif; background-color: #0B1D30; color: #FFFFFF; 
                        border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; 
                        font-weight: 600; font-size: 0.85rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                        transition: all 0.2s;
                    }}
                    button:hover {{ background-color: #162C46; transform: translateY(-1px); }}
                </style>
                </head>
                <body>
                    <button id="copyEtfBtn" onclick="copyToClipboard()">📋 Copy Symbols</button>
                    <script>
                    function copyToClipboard() {{
                        const ta = document.createElement('textarea');
                        ta.value = "{etf_copy_str}";
                        document.body.appendChild(ta);
                        ta.select();
                        document.execCommand('copy');
                        document.body.removeChild(ta);
                        
                        const btn = document.getElementById('copyEtfBtn');
                        btn.innerHTML = '✅ Copied!';
                        setTimeout(() => btn.innerHTML = '📋 Copy Symbols', 2000);
                    }}
                    </script>
                </body>
                </html>
                """
                components.html(etf_copy_html, height=40)

                # 2. CONVERT TO HTML AND INJECT TRADINGVIEW REDIRECT LINKS
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
        st.markdown("### Minimum Turnover (in Cr)")
        min_turnover = st.number_input("Minimum Turnover (in Cr)", min_value=0.0, value=3.0, step=1.0, key="mom_turnover", label_visibility="collapsed")
        
        if not main_df.empty:
            mom_df = main_df.copy()
            mom_df['turnover'] = pd.to_numeric(mom_df['turnover'], errors='coerce')
            mom_df['down_ath'] = pd.to_numeric(mom_df['down_ath'], errors='coerce')
            mom_df['relative_score'] = pd.to_numeric(mom_df['relative_score'], errors='coerce')
            mom_df['market_cap'] = pd.to_numeric(mom_df['market_cap'], errors='coerce')
            mom_df['1d_return'] = pd.to_numeric(mom_df['1d_return'], errors='coerce')
            
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
                st.markdown(f"#### Average 1D Return (Top 25): <span style='color: {avg_color};'>{top_25_avg:.2f}%</span>", unsafe_allow_html=True)
                
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
            
            f_us_ema = us_df['EMA 21 Status'].astype(str).str.strip().str.upper() == 'ABOVE 21 EMA'
            
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
                
                st.markdown(
                    f"#### Average 1D Return (Top 4): <span style='color:{avg_color};'>{top_4_avg:.2f}%</span>",
                    unsafe_allow_html=True
                )
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                def style_us_row(row):
                    is_top_4 = row.name in top_4_chg_idx
                    styles = []

                    for col in row.index:
                        style = ""

                        if is_top_4:
                            style += "font-weight:700;"

                            if col == "Chg %":
                                style += "background-color: rgba(187,247,208,0.5);"

                        styles.append(style)

                    return styles
                
                styled_us_etf = us_display.style.apply(style_us_row, axis=1).hide(axis="index").format({
                    'Price (USD)': lambda x: safe_fmt(x, "${:.2f}"),
                    'Chg %': lambda x: safe_fmt(x, "{:.2f}%"),
                    'Avg Vol 30D': lambda x: safe_fmt(x, "{:,.0f}"),
                    'Expense Ratio': lambda x: safe_fmt(x, "{:.2f}")
                })

                # 1. GENERATE COPY BUTTON FOR US ETFs
                us_etf_copy_str = ",".join(us_display['Symbol'].astype(str).tolist())
                us_etf_copy_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600&display=swap');
                    body {{ margin: 0; padding: 0; display: flex; justify-content: flex-end; align-items: flex-end; background-color: transparent; overflow: hidden; }}
                    button {{
                        font-family: 'Inter', sans-serif; background-color: #0B1D30; color: #FFFFFF; 
                        border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; 
                        font-weight: 600; font-size: 0.85rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                        transition: all 0.2s;
                    }}
                    button:hover {{ background-color: #162C46; transform: translateY(-1px); }}
                </style>
                </head>
                <body>
                    <button id="copyUsEtfBtn" onclick="copyToClipboard()">📋 Copy Symbols</button>
                    <script>
                    function copyToClipboard() {{
                        const ta = document.createElement('textarea');
                        ta.value = "{us_etf_copy_str}";
                        document.body.appendChild(ta);
                        ta.select();
                        document.execCommand('copy');
                        document.body.removeChild(ta);
                        
                        const btn = document.getElementById('copyUsEtfBtn');
                        btn.innerHTML = '✅ Copied!';
                        setTimeout(() => btn.innerHTML = '📋 Copy Symbols', 2000);
                    }}
                    </script>
                </body>
                </html>
                """
                components.html(us_etf_copy_html, height=40)

                # 2. CONVERT TO HTML AND INJECT TRADINGVIEW REDIRECT LINKS
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
        st.markdown("### Minimum Turnover (in Cr)")
        val_min_turnover = st.number_input("Minimum Turnover (in Cr)", min_value=0.0, value=3.0, step=1.0, key="val_turnover", label_visibility="collapsed")
        
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
                st.markdown(f"#### Average 1D Return (Top 25): <span style='color: {v_avg_color};'>{top_25_val_avg:.2f}%</span>", unsafe_allow_html=True)
                
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
                
                # SAFE FORMATTER APPLIED HERE 
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
                            elif 'Rebalance' in str(row['Status']): return ['background-color: rgba(254, 202
