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

# Silence terminal spam
warnings.simplefilter(action='ignore', category=FutureWarning)

st.set_page_config(page_title="9-EMA Swing Screener", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# ==========================================
# 1. CSS INJECTION (Premium Navy & Cream Theme + 3D Hover Header)
# ==========================================
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght=400;600;700;800&display=swap');
        html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
        #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
        .block-container { padding-top: 1.5rem; padding-bottom: 0rem; max-width: 98%; }
        
        .blob.green { background: rgba(39, 174, 96, 1); border-radius: 50%; margin: 0 0 0 5px; height: 10px; width: 10px; animation: pulse-green 2s infinite; display: inline-block; }
        
        /* GLOBAL THEME BACKGROUND (Cream) */
        .stApp { background-color: #F4F1E1 !important; }
        h1, h2, h3, h4, h5, h6, p, span { color: #0B1D30; }
        
        /* PREMIUM CUSTOM HEADER - IMMERSIVE 3D POPUP */
        .premium-header {
            background: linear-gradient(135deg, #0B1D30 0%, #162C46 100%); /* Subtle 3D lighting gradient */
            border-radius: 16px;
            padding: 28px 36px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: relative;
            overflow: hidden;
            margin-bottom: 30px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            /* Layered heavy shadows for massive depth */
            box-shadow: 0 12px 30px rgba(11, 29, 48, 0.25), 0 4px 10px rgba(11, 29, 48, 0.15);
            transform: translateY(0);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); /* Smooth hover animation */
        }
        
        /* Float upward when mouse hovers over it */
        .premium-header:hover {
            transform: translateY(-5px);
            box-shadow: 0 20px 40px rgba(11, 29, 48, 0.35), 0 8px 15px rgba(11, 29, 48, 0.2);
        }

        /* Geometric Light Overlay with deeper drop shadow */
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
            /* Projects a dark shadow directly onto the navy blue */
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
        .scrollable-table-container { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 0.5rem; }
        .scrollable-table-container table { width: 100%; min-width: 900px; border-collapse: collapse; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); background: #FFFFFF; border: 2px solid #0B1D30;}
        .scrollable-table-container th { background-color: #0B1D30 !important; color: #F4F1E1 !important; text-align: center !important; vertical-align: middle !important; font-size: 0.9rem; padding: 15px !important; white-space: nowrap; font-weight: 700 !important;}
        .scrollable-table-container td { color: #111827 !important; text-align: center !important; vertical-align: middle !important; padding: 12px !important; border-bottom: 1px solid rgba(11, 29, 48, 0.1) !important; white-space: nowrap; }
        
        .sleek-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; background: #FFFFFF; border: 2px solid #0B1D30; border-radius: 8px; overflow: hidden;}
        .sleek-table th { background-color: #0B1D30 !important; color: #F4F1E1 !important; text-align: center; vertical-align: middle; padding: 10px 8px; font-weight: 700 !important; }
        .sleek-table td { color: #111827 !important; text-align: center; vertical-align: middle; padding: 8px; border-bottom: 1px solid rgba(11, 29, 48, 0.1); }

        /* EXPANDER & TAB STYLING */
        [data-testid="stExpander"] { background: #FFFFFF !important; border: 2px solid #0B1D30 !important; border-radius: 8px !important; margin-bottom: 15px !important; box-shadow: 0 4px 10px rgba(0,0,0,0.04) !important; }
        [data-testid="stExpander"] summary { background: #FFFFFF !important; border-radius: 8px !important; }
        [data-testid="stExpander"] summary p { font-size: 1.3rem !important; font-weight: 800 !important; color: #0B1D30 !important;}
        
        /* Make Tab Titles Big and Bold */
        button[data-baseweb="tab"] p, button[role="tab"] p { font-size: 1.4rem !important; font-weight: 800 !important; color: #0B1D30 !important; }
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
    if 9 <= now.hour < 21: return f"locked_{now.strftime('%Y-%m-%d_%H')}"
    else: return f"active_{now.strftime('%Y-%m-%d_%H')}_{now.minute // 10}"

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

        return main_df, sec_rank_df, ind_rank_df, raw_sec, raw_ind, last_sync, trend_regime, roc_vals, etf_df
    except Exception as e:
        st.error(f"DATABASE ERROR: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "Error", "Error", [], pd.DataFrame()

@st.cache_data(ttl=60)
def fetch_market_breadth_from_gsheets():
    try:
        url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR1Evjm0QI8lj_k3439UzQShcg9fL8oTDq2nWPOY-2aXpKIesb3NsstOO_08pxAsTL6TL6WmLacqq9N/pub?gid=2103540271&single=true&output=csv"
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
@st.cache_data(ttl=86400)
def get_instrument_mapping():
    try:
        try:
            df = pd.read_json("complete.json")
        except:
            url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
            df = pd.read_json(url)
        df = df[df["segment"] == "NSE_EQ"]
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

# ==========================================
# 4. UI COMPONENTS & GRAPHS 
# ==========================================
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

            if live_val > 50.0: action_suffix = " - Trade"
            elif val <= 50.0:
                if "📈" in str(nse_breadth_str): action_suffix = " - Trade"
                elif "📉" in str(nse_breadth_str) or "➖" in str(nse_breadth_str): action_suffix = " - Stop Trading"
                else: action_suffix = "" 
            else: action_suffix = " - Trade"

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
    return f"""
    <div style="background: {bg_color}; border-radius: 12px; padding: 1.5rem; text-align: left; border: 2px solid #0B1D30; box-shadow: 0 4px 6px rgba(0,0,0,0.05); height: 100%;">
        <span style="font-size: 0.85rem; color: #0B1D30; font-weight: 700; font-family: 'Inter', sans-serif; text-transform: uppercase; letter-spacing: 0.5px;">{title}</span><br>
        <span style="color: #0B1D30; font-size: 1.7rem; font-weight: 800; display: block; margin-top: 0.4rem; font-family: 'Inter', sans-serif;">{value}</span>
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

    # SMOOTH CONTINUOUS DOT LOGIC
    if trend_dir == "up":
        dot_x = np.interp(roc_val, [0, 20, 40, 60, 100, 150], [0, 4, 8, 12, 16, 20])
        if roc_val <= 0: stage, note = "Disbelief", "This rally will fail like the others."
        elif roc_val <= 20: stage, note = "Hope", "A recovery is possible."
        elif roc_val <= 40: stage, note = "Optimism", "This rally is real."
        elif roc_val <= 60: stage, note = "Belief", "Time to get fully invested."
        elif roc_val <= 100: stage, note = "Thrill", "I will buy more on margin. Gotta tell everyone to buy!"
        else: stage, note = "Euphoria", "I am a genius! We're all going to be rich!"
    else:
        xp = [-20, 0, 20, 60, 70, 80, 90, 100]
        fp = [48, 44, 40, 36, 32, 28, 24, 20]
        dot_x = np.interp(roc_val, xp, fp)
        if roc_val >= 90: stage, note = "Complacency", "We just need to cool off for the next rally."
        elif roc_val >= 80: stage, note = "Anxiety", "Why am I getting margin calls? This dip is taking longer than expected."
        elif roc_val >= 70: stage, note = "Denial", "My investments are with great companies. They will come back."
        elif roc_val >= 60: stage, note = "Panic", "Shit! Everyone is selling. I need to get out!"
        elif roc_val > 20: stage, note = "Anger", "Who shorted the market?? Why did the government allow this to happen??"
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
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=60, r=40, t=30, b=60), showlegend=False, height=550 
    )
    
    st.markdown(f"""
    <div style="background: linear-gradient(145deg, {bg_theme_start} 0%, {bg_theme_end} 100%); 
                border-left: 5px solid {theme_color}; padding: 15px 20px; border-radius: 8px; 
                margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-top: 1px solid rgba(0,0,0,0.05); border-right: 1px solid rgba(0,0,0,0.05); border-bottom: 1px solid rgba(0,0,0,0.05);">
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

# Custom Premium Header Block (Light Theme)
st.markdown(f"""
    <div class="premium-header">
        <div class="header-left">
            <div class="header-title">⚡ 9-EMA Swing Screener</div>
            <div class="header-subtitle">Refreshed every 1 minute paired with Sector, Industry & Momentum rank.</div>
        </div>
        <div class="header-right">
            <div class="live-status">LIVE DATA <div class="blob green"></div></div>
            <div class="time">{current_time}</div>
            <div class="date">{current_date}</div>
        </div>
    </div>
""", unsafe_allow_html=True)

with st.spinner("Scanning live markets & syncing with Supabase..."):
    data = get_combined_data()
    current_cache_key = get_db_cache_key()
    main_df, sec_rank_df, ind_rank_df, raw_sec, raw_ind, last_sync, trend_regime, roc_vals, etf_df = fetch_database_reference(current_cache_key)  
    live_sheet_breadth = fetch_market_breadth_from_gsheets()

    live_bg = get_breadth_color(live_sheet_breadth)
    nse_bg = get_breadth_color(trend_regime)
    alloc_val, alloc_bg = get_portfolio_allocation(trend_regime, live_sheet_breadth)
    
    # -----------------------------------------------
    # LOGIC: ROC > 90 Tight Stop Loss Check
    # -----------------------------------------------
    if roc_vals:
        try:
            current_roc = float(roc_vals[0])
            if current_roc > 90.0:
                if " - Trade" in alloc_val:
                    alloc_val = alloc_val.replace(" - Trade", " - Tight stop loss")
                elif " - Stop Trading" in alloc_val:
                    alloc_val = alloc_val.replace(" - Stop Trading", " - Tight stop loss")
                else:
                    alloc_val += " - Tight stop loss"
                alloc_bg = "rgba(254, 202, 202, 0.4)" # Light red
        except:
            pass

    # -----------------------------------------------
    # LOGIC: Last DB Update > 24 Hours Check
    # -----------------------------------------------
    last_sync_bg = "rgba(216, 180, 254, 0.3)" # Default light purple
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
                last_sync_bg = "rgba(254, 202, 202, 0.4)" # Light red warning
        except Exception:
            pass

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
    # LIVE STOCKS TABLE (MAIN VIEW)
    # ==========================================
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

        for col in ['sec_rank', 'ind_rank', 'relative_score']:
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

        display_cols = ["Priority", "Symbol", "Exchange", "band", "Close", "% Change", "Turnover (Cr)", "Volume", "sector", "sec_rank", "broad_industry", "ind_rank", "relative_score"]
        display_df = df[[c for c in display_cols if c in df.columns]].copy()
        display_df = display_df.sort_values(by=["Priority", "relative_score"], ascending=[True, True], na_position="last").fillna("")
        display_df = display_df.rename(columns={"band": "Band", "sector": "Sector", "sec_rank": "Sector Rank", "broad_industry": "Industry", "ind_rank": "Ind. Rank", "relative_score": "Momentum Rank"})
        
        if 'Band' in display_df.columns: display_df['Band'] = display_df['Band'].replace("", "-").fillna("-")
        
        if not raw_sec.empty and not raw_ind.empty:
            
            # --- 1. COMBINED MARKET CYCLE & LEADERS ---
            with st.expander("🎢 Market Cycle & Current Market Leaders (Top Sectors & Industry)", expanded=False):
                render_market_cycle_graph(roc_vals)
                st.divider()
                
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
                    html = "<table class='sleek-table'><thead><tr>"
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
                    html += "</tbody></table>"
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
                    html = "<table class='sleek-table'><thead><tr>"
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
                    html += "</tbody></table>"
                    st.markdown(html, unsafe_allow_html=True)
                
            # --- 2. UPSTOX PORTFOLIO TRACKER ---
            with st.expander("📈 Upstox Portfolio Tracker", expanded=False):
                st.markdown("<span style='color: #6B7280; font-size: 0.95rem;'>Track your portfolio via Google Sheets or CSV upload. Required columns: <b>Stock Ticker</b>, <b>Entry date</b>, <b>Entry Price</b>.</span>", unsafe_allow_html=True)
                
                col_t1, col_t2 = st.columns([1, 2])
                with col_t1:
                    upstox_token = st.text_input("Upstox Access Token", type="password", value="eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0RkJLQjYiLCJqdGkiOiI2YTM3NmVmN2ZlOGNjNTM2ODA1MWYzNDciLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlzRXh0ZW5kZWQiOnRydWUsImlhdCI6MTc4MjAxNzc4MywiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxODEzNjE1MjAwfQ.hDOC4JVkYd-rzbuQdWNzLU6p1RtROfvVtj9UeFiGQX4")
                with col_t2:
                    input_method = st.radio("Select Input Method:", ["Upload CSV", "Google Sheets"], index=1, horizontal=True, label_visibility="collapsed", key="tracker_method")

                port_df = pd.DataFrame()

                if input_method == "Upload CSV":
                    upstox_file = st.file_uploader("Upload Portfolio (CSV)", type=['csv'])
                    if upstox_file is not None:
                        try: port_df = pd.read_csv(upstox_file)
                        except Exception as e: st.error(f"Error reading file: {e}")

                elif input_method == "Google Sheets":
                    col_gs1, col_gs2 = st.columns([3, 1])
                    with col_gs1:
                        gsheet_url = st.text_input("Google Sheets URL:", value="https://docs.google.com/spreadsheets/d/1GqgxZk8Z2xJAVAaKONWVGy8pTQ38qcQWlSw3qC9tL98/edit?gid=0#gid=0", label_visibility="collapsed", key="tracker_url")
                    with col_gs2:
                        load_clicked = st.button("🔄 Load / Refresh Sheet")
                        
                    if load_clicked and gsheet_url:
                        try:
                            if "docs.google.com/spreadsheets" in gsheet_url:
                                sheet_id_match = re.search(r"/d/([a-zA-Z0-9-_]+)", gsheet_url)
                                if sheet_id_match:
                                    sheet_id = sheet_id_match.group(1)
                                    gid_match = re.search(r"[#&]gid=([0-9]+)", gsheet_url)
                                    gid = gid_match.group(1) if gid_match else "0"
                                    
                                    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
                                    port_df = pd.read_csv(export_url, usecols=[0, 1, 2])
                                    port_df.columns = ['Stock Ticker', 'Entry date', 'Entry Price']
                                    port_df = port_df.dropna(how='all')
                                else: st.error("Could not extract Sheet ID.")
                            else: st.error("Invalid Google Sheets URL format.")
                        except Exception as e: st.error(f"Error loading Google Sheet: {e}. Check if the link is public.")

                if not port_df.empty and upstox_token:
                    try:
                        col_stock = next((c for c in port_df.columns if 'stock' in c.lower() or 'symbol' in c.lower() or 'ticker' in c.lower()), None)
                        col_date = next((c for c in port_df.columns if 'entry' in c.lower() and 'date' in c.lower()), None)
                        col_price = next((c for c in port_df.columns if 'price' in c.lower()), None)
                        
                        if not col_stock or not col_date or not col_price:
                            st.error("Data must contain columns for Stock Ticker, Entry Date, and Entry Price.")
                        else:
                            with st.spinner("Fetching data from Upstox API..."):
                                inst_dict = get_instrument_mapping()
                                if "error" in inst_dict: st.error(f"Failed to load Upstox instrument mapping: {inst_dict['error']}")
                                else:
                                    results = []
                                    today_str = datetime.now().strftime("%Y-%m-%d")
                                    api_failed = False
                                    
                                    for _, row in port_df.iterrows():
                                        symbol = str(row[col_stock]).strip().upper()
                                        if symbol in ['NAN', 'NONE', '']: continue
                                        try:
                                            entry_date = pd.to_datetime(row[col_date], dayfirst=True).tz_localize(None)
                                            entry_price = float(row[col_price])
                                        except: continue
                                            
                                        if symbol not in inst_dict: continue
                                            
                                        inst_key = inst_dict[symbol]
                                        start_fetch_date = (entry_date - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
                                        df_hist, status_code = fetch_upstox_history(inst_key, start_fetch_date, today_str, upstox_token)
                                        
                                        if status_code != 200:
                                            api_failed = True
                                            st.error(f"Upstox API Error {status_code} for {symbol}. Token might be expired or invalid.")
                                            break
                                            
                                        if df_hist.empty: continue
                                            
                                        df_hist["EMA21"] = df_hist["Close"].ewm(span=21, adjust=False).mean()
                                        future_data = df_hist[df_hist.index >= entry_date]
                                        if future_data.empty: continue
                                        
                                        current_price = float(df_hist.iloc[-1]["Close"])
                                        ema21 = float(df_hist.iloc[-1]["EMA21"])
                                        trading_days = len(future_data)
                                        
                                        return_pct = ((current_price - entry_price) / entry_price) * 100
                                        ema_status = "ABOVE EMA21" if current_price > ema21 else "BELOW EMA21"
                                        
                                        if trading_days >= 10:
                                            required_return = (trading_days // 10) * 5.0
                                            ten_day_rule = "EXIT" if return_pct < required_return else "PASS"
                                        else: ten_day_rule = f"PENDING ({trading_days}/10)"
                                            
                                        results.append({
                                            "Symbol": symbol, "Entry Date": entry_date.strftime("%d-%m-%Y"),
                                            "Entry Price": entry_price, "Current Price": current_price,
                                            "Return %": return_pct, "Trading Days": trading_days,
                                            "EMA21": ema21, "EMA Status": ema_status, "10 Day Rule": ten_day_rule
                                        })
                                        
                                    if not api_failed and results:
                                        res_df = pd.DataFrame(results).sort_values("Return %", ascending=False)
                                        def highlight_upstox(row):
                                            if row['EMA Status'] == 'BELOW EMA21' or row['10 Day Rule'] == 'EXIT': return ['background-color: rgba(254, 202, 202, 0.4)'] * len(row)
                                            return [''] * len(row)
                                        styled_res = res_df.style.apply(highlight_upstox, axis=1).hide(axis="index").format({"Entry Price": "₹{:.2f}", "Current Price": "₹{:.2f}", "Return %": "{:.2f}%", "EMA21": "₹{:.2f}"})
                                        st.markdown(f'<div class="scrollable-table-container">{styled_res.to_html()}</div>', unsafe_allow_html=True)
                                    elif not api_failed: st.info("No valid data processed. Check if tickers match NSE format.")
                    except Exception as e: st.error(f"Error parsing portfolio file: {e}")

            # --- 3. MOMENTUM SCREENER (PARENT WITH TABS) ---
            with st.expander("🚀 Momentum Screener", expanded=False):
                tab1, tab2 = st.tabs(["📊 ETF Screener", "🚀 Stock momentum screener"])
                
                # --- TAB 1: ETF SCREENER ---
                with tab1:
                    st.markdown("### ETF Minimum Turnover (in Cr)")
                    etf_min_turnover = st.number_input("ETF Minimum Turnover (in Cr)", min_value=0.0, value=3.0, step=1.0, key="etf_turnover", label_visibility="collapsed")
                    
                    if not etf_df.empty:
                        e_df = etf_df.copy()
                        if 'Catergory' in e_
