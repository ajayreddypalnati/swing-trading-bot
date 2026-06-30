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
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght=400;600;700;800&display=swap');
        
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
        
        /* TABLE STYLING - TIGHTER FOR SCREEN FIT */
        .scrollable-table-container { width: 100%; margin-bottom: 0.5rem; overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: 8px;}
        .scrollable-table-container table { width: 100%; border-collapse: collapse; background: #FFFFFF; border: 2px solid #0B1D30; overflow: hidden;}
        .scrollable-table-container th { background-color: #0B1D30 !important; color: #F4F1E1 !important; text-align: center !important; vertical-align: middle !important; font-size: 0.85rem !important; padding: 8px 3px !important; font-weight: 700 !important;}
        .scrollable-table-container td { color: #111827 !important; text-align: center !important; vertical-align: middle !important; padding: 6px 3px !important; border-bottom: 1px solid rgba(11, 29, 48, 0.1) !important; font-size: 0.9rem !important; }
        
        .sleek-table-wrapper { width: 100%; border: 2px solid #0B1D30; border-radius: 8px; overflow-x: auto; -webkit-overflow-scrolling: touch; background: #FFFFFF; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .sleek-table { width: 100%; border-collapse: collapse; font-size: 0.9rem !important; background: transparent; }
        .sleek-table th { background-color: #0B1D30 !important; color: #F4F1E1 !important; text-align: center; vertical-align: middle; padding: 8px 6px; font-weight: 700 !important; font-size: 0.9rem !important; }
        .sleek-table td { color: #111827 !important; text-align: center; vertical-align: middle; padding: 6px; border-bottom: 1px solid rgba(11, 29, 48, 0.1); font-size: 0.9rem !important; }
        
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
        
        div[data-testid="stTextInput"] input {
            background-color: #FFFFFF !important;
            color: #0B1D30 !important;
            border: 1px solid #0B1D30 !important;
        }
        
        div[data-testid="stNumberInput"] input {
            background-color: #FFFFFF !important;
            font-size: 1.5rem !important;
            font-weight: 800 !important;
            color: #0B1D30 !important;
            border: 1px solid #0B1D30 !important;
        }
        
        div[role="radiogroup"] label { color: #0B1D30 !important; }

        div[data-testid="stFileUploader"] {
            background-color: #FFFFFF !important;
            border: 2px dashed #0B1D30 !important;
            border-radius: 8px !important;
            padding: 15px !important;
        }
        div[data-testid="stFileUploader"] section { background-color: transparent !important; }
        div[data-testid="stFileUploader"] span, div[data-testid="stFileUploader"] p, div[data-testid="stFileUploader"] small {
            color: #0B1D30 !important;
            font-weight: 600 !important;
        }
        div[data-testid="stFileUploader"] button {
            background-color: #FFFFFF !important;
            color: #0B1D30 !important;
            border: 2px solid #0B1D30 !important;
            border-radius: 6px !important;
            font-weight: 800 !important;
        }
        div[data-testid="stFileUploader"] button:hover { background-color: #F4F1E1 !important; }
        
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
    if 9 <= now.hour < 21: return f"locked_{now.strftime('%Y-%m-%d')}"
    else: return f"active_{now.strftime('%Y-%m-%d_%H')}"

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
            except Exception: last_sync = "Pending Run..."

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

        return main_df, sec_rank_df, ind_rank_df, raw_sec, raw_ind, last_sync, trend_regime, roc_vals, etf_df
    except Exception as e:
        st.error(f"DATABASE ERROR: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "Error", "Error", [], pd.DataFrame()

@st.cache_data(ttl=60)
def fetch_market_breadth_from_gsheets():
    try:
        ts = int(time.time())
        url = f"https://docs.google.com/spreadsheets/d/e/2PACX-1vR1Evjm0QI8lj_k3439UzQShcg9fL8oTDq2nWPOY-2aXpKIesb3NsstOO_08pxAsTL6TL6WmLacqq9N/pub?gid=2103540271&single=true&output=csv&t={ts}"
        df = pd.read_csv(url, header=None)
        market_breadth_value = df.iloc[5, 7] 
        return "N/A" if pd.isna(market_breadth_value) else str(market_breadth_value)
    except Exception: return "N/A"

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
        except Exception: return []

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
    except Exception: return []

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
# 4. UPSTOX HELPER FUNCTIONS
# ==========================================
@st.cache_data(ttl=604800)
def get_instrument_mapping():
    try:
        url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as f:
            df = pd.read_json(f)
        df = df[df["segment"] == "NSE_EQ"]
        return dict(zip(df["trading_symbol"].astype(str).str.upper(), df["instrument_key"]))
    except Exception as e: return {"error": str(e)}

def fetch_upstox_history(instrument_key, start_date, end_date, token):
    encoded_key = urllib.parse.quote(instrument_key)
    url = f"https://api.upstox.com/v2/historical-candle/{encoded_key}/day/{end_date}/{start_date}"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200: return pd.DataFrame(), response.status_code
        candles = response.json().get("data", {}).get("candles", [])
        if not candles: return pd.DataFrame(), 200
        df = pd.DataFrame(candles, columns=["timestamp", "Open", "High", "Low", "Close", "Volume", "OI"])
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
        for col in ["Open", "High", "Low", "Close"]: df[col] = pd.to_numeric(df[col])
        return df, 200
    except: return pd.DataFrame(), 500

def get_live_price(instrument_key, token):
    url = "https://api.upstox.com/v2/market-quote/ltp"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    params = {"instrument_key": instrument_key}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200: return None
        return float(response.json()["data"][instrument_key]["last_price"])
    except: return None

# ==========================================
# 5. UI COMPONENTS
# ==========================================
def create_metric_card(title, value, bg_color):
    val_size = "1.35rem" if len(str(value)) > 20 else "1.65rem"
    return f"""
    <div style="background: {bg_color}; border-radius: 12px; padding: 1.2rem 1.5rem; text-align: left; border: 2px solid #0B1D30; box-shadow: 0 4px 6px rgba(0,0,0,0.05); height: 115px; display: flex; flex-direction: column; justify-content: center;">
        <span style="font-size: 0.85rem; color: #0B1D30; font-weight: 700; font-family: 'Inter', sans-serif; text-transform: uppercase; letter-spacing: 0.5px;">{title}</span>
        <span style="color: #0B1D30; font-size: {val_size}; font-weight: 800; display: block; margin-top: 0.2rem; font-family: 'Inter', sans-serif; line-height: 1.2;">{value}</span>
    </div>
    """

# ==========================================
# 6. MAIN APP LOGIC
# ==========================================
loader_placeholder = st.empty()
loader_placeholder.markdown("""<div style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(244, 241, 225, 0.65); backdrop-filter: blur(3px); z-index: 9999; display: flex; justify-content: center; align-items: center; flex-direction: column;"><div style="font-size: 5rem; animation: pulse-logo 1.5s infinite ease-in-out;">⚡</div><div style="color: #0B1D30; font-weight: 800; font-size: 1.2rem; margin-top: 15px; letter-spacing: 2px;">SYNCING LIVE DATA</div></div>""", unsafe_allow_html=True)

data = get_combined_data()
main_df, sec_rank_df, ind_rank_df, raw_sec, raw_ind, last_sync, trend_regime, roc_vals, etf_df = fetch_database_reference(get_db_cache_key())
live_sheet_breadth = fetch_market_breadth_from_gsheets()
loader_placeholder.empty()

# -- PROCESS TABLE --
df = pd.DataFrame(data, columns=["Symbol", "Close", "% Change", "Volume", "Temp_Exchange"])
df['Symbol'] = df['Symbol'].astype(str).str.strip().str.upper()
df = df.merge(main_df, left_on="Symbol", right_on="ticker", how="left")
df = df.merge(sec_rank_df, on="sector", how="left")
df = df.merge(ind_rank_df, on="broad_industry", how="left")
df['Exchange'] = np.where(df['db_exchange'].notna() & (df['db_exchange'] != ""), df['db_exchange'], df['Temp_Exchange'])
df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
df['Turnover (Cr)'] = (df['Close'] * df['Volume']) / 100000000000 # Corrected to whole number
df['market_cap'] = pd.to_numeric(df['market_cap'], errors='coerce')

df['Priority'] = np.nan
p1 = (df['sec_rank'] <= 5) & (df['ind_rank'] <= 10)
p2 = (df['sec_rank'] <= 5) & (df['ind_rank'] <= 15) & ~p1
df.loc[p1, 'Priority'] = 1
df.loc[p2, 'Priority'] = 2

display_df = df[["Priority", "Symbol", "Exchange", "band", "Close", "% Change", "market_cap", "Turnover (Cr)", "Volume", "sector", "sec_rank", "broad_industry", "ind_rank", "relative_score"]].copy()
display_df = display_df.sort_values(by=["Priority", "relative_score"], ascending=[True, True]).fillna("")
display_df = display_df.rename(columns={"band": "Band", "market_cap": "Mar Cap (Cr)", "sector": "Sector", "sec_rank": "Sector Rank", "broad_industry": "Industry", "ind_rank": "Ind. Rank", "relative_score": "Momentum Rank"})

# -- RENDER TABLE --
# 1. Prepare JS for Copy
all_symbols_csv = ",".join(display_df['Symbol'].tolist())
copy_script = f"""
<script>
function copyAll() {{
    navigator.clipboard.writeText("{all_symbols_csv}");
    alert("Copied: {all_symbols_csv}");
}}
</script>
"""
st.markdown(copy_script, unsafe_allow_html=True)

# 2. Build HTML
html_table = f'<div class="scrollable-table-container"><table><thead><tr>'
html_table += '<th>Priority</th>'
html_table += f'<th>Symbol <span style="cursor:pointer" onclick="copyAll()">📋</span></th>'
for col in display_df.columns:
    if col not in ['Priority', 'Symbol']: html_table += f'<th>{col}</th>'
html_table += '</tr></thead><tbody>'

for _, r in display_df.iterrows():
    html_table += '<tr>'
    html_table += f'<td>{r["Priority"]}</td>'
    # TV Link
    sym = r['Symbol']
    link = f"https://in.tradingview.com/chart/?symbol={'NSE' if 'NSE' in str(r['Exchange']) else 'BSE'}:{sym}"
    html_table += f'<td><a href="{link}" target="_blank">{sym}</a></td>'
    for col in display_df.columns:
        if col not in ['Priority', 'Symbol']:
            val = r[col]
            if col in ['Mar Cap (Cr)', 'Turnover (Cr)']: val = int(val) if pd.notna(val) and val != "" else 0
            html_table += f'<td>{val}</td>'
    html_table += '</tr>'
html_table += '</tbody></table></div>'

st.markdown(html_table, unsafe_allow_html=True)
