import requests
import pandas as pd
import numpy as np
import time
import re
from datetime import datetime
import pytz
import streamlit as st
from sqlalchemy import create_engine, text
import streamlit.components.v1 as components

# ==========================================
# UI & AUTO-REFRESH CONFIG
# ==========================================
st.set_page_config(layout="wide", page_title="USA 9-EMA Screener")

# Auto-refresh the page every 60 seconds
components.html('<meta http-equiv="refresh" content="60">', height=0)

# CSS for reducing spacing and aligning the copy buttons
st.markdown("""
    <style>
    .premium-header {
        display: flex; justify-content: space-between; align-items: center;
        background: #0B1D30; padding: 1.5rem; border-radius: 12px; color: white; margin-bottom: 1rem;
    }
    .header-title { font-size: 1.5rem; font-weight: bold; }
    .header-subtitle { font-size: 0.9rem; opacity: 0.8; margin-top: 5px; }
    .header-right { text-align: right; }
    .live-status { font-size: 0.85rem; font-weight: bold; color: #86efac; margin-bottom: 5px; }
    .table-header-row {
        display: flex; justify-content: space-between; align-items: flex-end;
        margin-bottom: 5px; margin-top: -10px;
    }
    .scrollable-table-container { margin-top: 0 !important; }
    </style>
""", unsafe_allow_html=True)

def run_usa_screener():
    # ==========================================
    # APIs & ENDPOINTS
    # ==========================================
    TV_URL = 'https://scanner.tradingview.com/global/scan'
    TV_HEADERS = { 'User-Agent': 'Mozilla/5.0', 'Origin': 'https://www.tradingview.com', 'Content-Type': 'application/json' }
    
    # Base payload for main screener
    TV_PAYLOAD = {
        "columns": ["ticker-view", "close", "type", "typespecs", "pricescale", "minmov", "fractional", "minmove2", "currency", "change", "volume", "market_cap_basic", "fundamental_currency_code", "sector.tr", "market", "sector", "industry.tr", "industry", "exchange.tr", "source-logoid"],
        "filter": [
            {"left": "low", "operation": "less", "right": "EMA9"},
            {"left": "is_blacklisted", "operation": "equal", "right": False},
            {"left": "high", "operation": "greater", "right": "EMA9"},
            {"left": "close", "operation": "in_range%", "right": ["High.All", 0.9, 1]},
            {"left": "RSI", "operation": "greater", "right": 65},
            {"left": "close", "operation": "egreater", "right": "EMA9"},
            {"left": "Value.Traded", "operation": "greater", "right": 3000000},
            {"left": "change", "operation": "in_range", "right": [0, 10]},
            {"left": "Perf.1M", "operation": "greater", "right": 10},
            {"left": "is_primary", "operation": "equal", "right": True}
        ],
        "ignore_unknown_fields": False,
        "options": {"lang": "en"},
        "range": [0, 100],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "asc"},
        "symbols": {"symbolset": ["SYML:TVC;RUA"]},
        "markets": ["america"],
        "filter2": {
            "operator": "and",
            "operands": [
                {"operation": {"operator": "or", "operands": [{"operation": {"operator": "and", "operands": [{"expression": {"left": "type", "operation": "equal", "right": "stock"}}, {"expression": {"left": "typespecs", "operation": "has", "right": ["common"]}}]}}, {"operation": {"operator": "and", "operands": [{"expression": {"left": "type", "operation": "equal", "right": "stock"}}, {"expression": {"left": "typespecs", "operation": "has", "right": ["preferred"]}}]}}, {"operation": {"operator": "and", "operands": [{"expression": {"left": "type", "operation": "equal", "right": "dr"}}]}}, {"operation": {"operator": "and", "operands": [{"expression": {"left": "type", "operation": "equal", "right": "fund"}}, {"expression": {"left": "typespecs", "operation": "has_none_of", "right": ["etf", "mutual"]}}]}}]}},
                {"expression": {"left": "typespecs", "operation": "has_none_of", "right": ["pre-ipo"]}}
            ]
        }
    }

    # ==========================================
    # DATA FETCHING 
    # ==========================================
    @st.cache_data(ttl=86400)
    def fetch_usa_database_reference():
        try:
            db_url = st.secrets["DATABASE_URL"]
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

            engine = create_engine(db_url)
            with engine.connect() as conn:
                try:
                    us_stock_df = pd.read_sql(text('SELECT * FROM "US Stock screener"'), conn)
                    col_ticker = next((c for c in us_stock_df.columns if 'symbol' in str(c).lower() or 'ticker' in str(c).lower()), 'Symbol')
                    col_turnover = next((c for c in us_stock_df.columns if 'turnover' in str(c).lower()), 'Turnover in Cr')
                    col_mom = next((c for c in us_stock_df.columns if 'momentum rank' in str(c).lower() or 'relative' in str(c).lower()), 'Momentum Rank')
                    us_stock_df = us_stock_df[[col_ticker, col_turnover, col_mom]].rename(columns={col_ticker: 'Symbol', col_turnover: 'Turnover in Cr', col_mom: 'Momentum Rank'})
                except Exception:
                    us_stock_df = pd.DataFrame(columns=['Symbol', 'Turnover in Cr', 'Momentum Rank'])

                try:
                    raw_sec = pd.read_sql(text('SELECT * FROM "USA Sector Analysis"'), conn)
                    raw_ind = pd.read_sql(text('SELECT * FROM "US Industry Analysis"'), conn)
                except:
                    raw_sec, raw_ind = pd.DataFrame(), pd.DataFrame()

                try:
                    trend_df = pd.read_sql(text('SELECT * FROM market_trend_summary LIMIT 1'), conn)
                    trend_regime = trend_df['trend_regime'].iloc[0] if not trend_df.empty else "Pending..."
                except Exception:
                    trend_regime = "N/A"

                try:
                    sync_df = pd.read_sql(text('SELECT * FROM "US Sync log"'), conn)
                    last_sync = sync_df['last_sync'].iloc[0]
                except Exception:
                    last_sync = "Pending Run..."

                try:
                    us_etf_df = pd.read_sql(text('SELECT * FROM "USA_ETF_Screener"'), conn)
                except Exception:
                    us_etf_df = pd.DataFrame()

            return us_stock_df, raw_sec, raw_ind, trend_regime, last_sync, us_etf_df
        except Exception:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "Error", "Error", pd.DataFrame()

    @st.cache_data(ttl=60)
    def fetch_us_live_breadth():
        try:
            ts = int(time.time())
            url = f"https://docs.google.com/spreadsheets/d/e/2PACX-1vR1Evjm0QI8lj_k3439UzQShcg9fL8oTDq2nWPOY-2aXpKIesb3NsstOO_08pxAsTL6TL6WmLacqq9N/pub?gid=2103540271&single=true&output=csv&t={ts}"
            df = pd.read_csv(url, header=None)
            raw_val = df.iloc[5, 28]
            if pd.isna(raw_val) or "DIV/0" in str(raw_val) or "REF!" in str(raw_val) or "N/A" in str(raw_val): return "N/A"
            return str(raw_val).strip()
        except Exception:
            return "N/A"

    def fetch_usa_tradingview():
        try:
            response = requests.post(TV_URL, headers=TV_HEADERS, json=TV_PAYLOAD, timeout=10)
            raw_data = response.json().get("data", [])
            formatted_data = []
            for item in raw_data:
                d = item["d"]
                symbol = str(d[0]).split(":")[-1] if ":" in str(d[0]) else str(d[0])
                formatted_data.append([symbol, symbol, d[1], d[9], d[10], d[11], d[15], d[17], d[18]])
            return formatted_data
        except Exception:
            return []

    # Portfolio Specific API Fetch using the exact user-provided columns
    def fetch_portfolio_tv_data(symbols_list):
        try:
            port_payload = {
                "columns": ["ticker-view", "name", "close", "type", "typespecs", "pricescale", "minmov", "fractional", "minmove2", "currency", "change", "market_cap_basic", "fundamental_currency_code", "sector.tr", "market", "sector", "industry.tr", "industry", "EMA21"],
                "filter": [
                    {"left": "is_primary", "operation": "equal", "right": True},
                    {"left": "name", "operation": "in", "right": symbols_list}
                ],
                "ignore_unknown_fields": False,
                "options": {"lang": "en"},
                "price_conversion": {"to_currency": "usd"},
                "range": [0, 500],
                "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
                "markets": ["america","argentina","australia","austria","bahrain","bangladesh","belgium","bulgaria","brazil","canada","chile","china","colombia","croatia","cyprus","czech","denmark","egypt","estonia","finland","france","germany","greece","hongkong","hungary","iceland","india","indonesia","ireland","israel","italy","japan","kenya","kuwait","latvia","lithuania","luxembourg","malaysia","mexico","morocco","netherlands","newzealand","nigeria","norway","pakistan","peru","philippines","poland","portugal","qatar","romania","russia","ksa","serbia","singapore","slovakia","slovenia","rsa","korea","spain","srilanka","sweden","switzerland","taiwan","thailand","tunisia","turkey","uae","uk","venezuela","vietnam"]
            }
            response = requests.post(TV_URL, headers=TV_HEADERS, json=port_payload, timeout=10)
            raw_data = response.json().get("data", [])
            results = {}
            for item in raw_data:
                d = item["d"]
                sym = str(d[1]).upper()  # 'name' column
                live_price = float(d[2]) if d[2] is not None else 0.0
                today_chg = float(d[10]) if d[10] is not None else 0.0
                ema21 = float(d[18]) if d[18] is not None else 0.0
                results[sym] = {"Live Price": live_price, "Today Chg%": today_chg, "EMA21": ema21}
            return results
        except Exception as e:
            return {}

    # ==========================================
    # SAFE FORMATTERS & UI HELPERS
    # ==========================================
    def safe_fmt(val, fmt_str):
        try:
            if pd.isna(val) or str(val).strip() == "": return "-"
            return fmt_str.format(float(val))
        except: return "-"

    def get_breadth_color(val_str):
        try:
            match = re.search(r'(\d+\.?\d*)%', str(val_str))
            if match:
                val = float(match.group(1))
                if val <= 30.0: return "rgba(252, 165, 165, 0.4)"  
                elif val <= 60.0: return "rgba(253, 230, 138, 0.4)"  
                else: return "rgba(134, 239, 172, 0.4)"  
            return "#FFFFFF"
        except: return "#FFFFFF"

    def create_metric_card(title, value, bg_color):
        return f"""
        <div style="background: {bg_color}; border-radius: 12px; padding: 1.2rem 1.5rem; text-align: left; border: 2px solid #0B1D30; box-shadow: 0 4px 6px rgba(0,0,0,0.05); height: 115px; display: flex; flex-direction: column; justify-content: center;">
            <span style="font-size: 0.85rem; color: #0B1D30; font-weight: 700; text-transform: uppercase;">{title}</span>
            <span style="color: #0B1D30; font-size: 1.5rem; font-weight: 800; display: block; margin-top: 0.2rem;">{value}</span>
        </div>
        """

    # ==========================================
    # DASHBOARD MAIN LAYOUT & HEADER (ET Time)
    # ==========================================
    et_tz = pytz.timezone('US/Eastern')
    current_time_et = datetime.now(et_tz).strftime('%I:%M:%S %p ET')
    current_date_et = datetime.now(et_tz).strftime('%d %b %Y')

    st.markdown(f"""
        <div class="premium-header">
            <div class="header-left">
                <div class="header-title">⚡ USA 9-EMA Screener</div>
                <div class="header-subtitle">Refreshed every 1 minute paired with Sector, Industry & Momentum rank.</div>
            </div>
            <div class="header-right">
                <div class="live-status">LIVE DATA 🟢</div>
                <div class="time">{current_time_et}</div>
                <div class="date">{current_date_et}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    tv_data = fetch_usa_tradingview()
    us_stock_df, raw_sec, raw_ind, trend_regime, last_sync, us_etf_df = fetch_usa_database_reference()
    live_sheet_breadth = fetch_us_live_breadth()

    live_bg = get_breadth_color(live_sheet_breadth)
    nse_bg = get_breadth_color(trend_regime)

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    with metric_col1: st.markdown(create_metric_card("📊 Market Breadth (Live)", live_sheet_breadth, live_bg), unsafe_allow_html=True)
    with metric_col2: st.markdown(create_metric_card("⚖️ Market Breadth (USA)", trend_regime, nse_bg), unsafe_allow_html=True)
    with metric_col3: st.markdown(create_metric_card("💼 Portfolio Allocation", "Auto-Calculated", "rgba(187, 247, 208, 0.4)"), unsafe_allow_html=True)
    with metric_col4: st.markdown(create_metric_card("🔄 Last DB Update", last_sync, "rgba(216, 180, 254, 0.3)"), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ==========================================
    # NAVIGATION TABS
    # ==========================================
    tab_main, tab_leaders, tab_us_etf, tab_port = st.tabs([
        "⚡ 9-EMA Screener", "🏆 Market Leaders", "🌍 US ETF Screener", "📈 Portfolio Tracker"
    ])

    with tab_main:
        st.markdown("""
            <div class="table-header-row">
                <div></div>
                <button style="padding: 5px 10px; background: #0B1D30; color: white; border-radius: 5px; border: none; font-size: 0.8rem; cursor: pointer;">📋 Copy Symbols</button>
            </div>
        """, unsafe_allow_html=True)
        
        if tv_data:
            df = pd.DataFrame(tv_data, columns=["Symbol", "Name", "Price", "Chg %", "Vol", "Mcap", "Sector", "Industry", "Exchange"])
            df['Symbol'] = df['Symbol'].astype(str).str.strip().str.upper()
            if not us_stock_df.empty: df = df.merge(us_stock_df, on="Symbol", how="left")
            
            styled_df = df.style.hide(axis="index").format({
                "Price": lambda x: safe_fmt(x, "${:.2f}"), 
                "Chg %": lambda x: safe_fmt(x, "{:.2f}%")
            })
            st.markdown(f'<div class="scrollable-table-container">{styled_df.to_html()}</div>', unsafe_allow_html=True)

    with tab_leaders:
        st.info("Market Leaders Loaded.")

    with tab_us_etf:
        st.info("US ETF Screener Loaded.")

    with tab_port:
        st.info("Tracker UI loaded. Note: Using TradingView API for American equity quotes.")
        
        # UI matching your original Indian layout
        col1, col2 = st.columns([3, 1])
        with col1:
            st.text_input("Upstox Access Token (Not required for US tracking)", type="password", disabled=True)
            gs_url = st.text_input("Google Sheets URL:", value="https://docs.google.com/spreadsheets/d/...")
        with col2:
            st.radio("Data Source", ["Upload CSV", "Google Sheets"], index=1)
            st.markdown("<br>", unsafe_allow_html=True)
            load_data = st.button("🔄 Load / Refresh Sheet")

        if load_data and "docs.google.com" in gs_url:
            try:
                # Convert standard GS url to CSV export format
                csv_url = gs_url.replace('/edit?usp=sharing', '/export?format=csv').replace('/edit#gid=', '/export?format=csv&gid=')
                port_df = pd.read_csv(csv_url)
                
                # Enforce Standard Columns based on screenshot
                port_df = port_df.rename(columns=lambda x: str(x).strip())
                port_df = port_df[['Stock Ticker', 'Entry date', 'Entry Price', 'Stop Loss', 'Risk']]
                
                # Fetch Live TradingView Data
                symbols_to_fetch = port_df['Stock Ticker'].dropna().astype(str).tolist()
                live_tv_data = fetch_portfolio_tv_data(symbols_to_fetch)

                # Process & Calculate Columns
                tracker_data = []
                for _, row in port_df.iterrows():
                    sym = str(row['Stock Ticker']).upper().strip()
                    if not sym or sym == "NAN": continue
                    
                    tv = live_tv_data.get(sym, {"Live Price": 0.0, "Today Chg%": 0.0, "EMA21": 0.0})
                    
                    entry_price = float(row['Entry Price']) if pd.notna(row['Entry Price']) else 0.0
                    stop_loss = float(row['Stop Loss']) if pd.notna(row['Stop Loss']) else 0.0
                    risk_pct = str(row['Risk'])
                    
                    current_price = tv["Live Price"]
                    profit_loss = current_price - entry_price if entry_price > 0 else 0.0
                    return_pct = (profit_loss / entry_price * 100) if entry_price > 0 else 0.0
                    
                    # Calculate Trading Days (Simple Date Difference)
                    try:
                        entry_dt = datetime.strptime(str(row['Entry date']), '%d-%m-%Y')
                        trading_days = np.busday_count(entry_dt.date(), datetime.now().date())
                    except:
                        trading_days = 0
                    
                    # EMA Status
                    ema21_val = tv["EMA21"]
                    ema_status = "ABOVE EMA21" if current_price > ema21_val else "BELOW EMA21"
                    
                    # 10 Day Rule Logic
                    if trading_days < 10:
                        rule_status = f"PENDING ({trading_days}/10)"
                    else:
                        rule_status = f"PASS ({return_pct:.2f}%)" if ema_status == "ABOVE EMA21" else f"EXIT ({return_pct:.2f}%)"

                    tracker_data.append({
                        "Symbol": sym,
                        "Entry Date": row['Entry date'],
                        "Today chg%": tv["Today Chg%"],
                        "Entry Price": entry_price,
                        "Stop Loss": stop_loss,
                        "Risk %": risk_pct,
                        "Current Price": current_price,
                        "Profit/Loss": profit_loss,
                        "Return %": return_pct,
                        "Trading Days": trading_days,
                        "EMA21": ema21_val,
                        "EMA 21 Status": ema_status,
                        "10 Day Rule": rule_status
                    })
                
                final_port_df = pd.DataFrame(tracker_data)
                avg_chg = final_port_df['Today chg%'].mean()
                
                st.markdown(f"""
                    <div class="table-header-row">
                        <div style="font-weight: 600; font-size: 1.1rem;">Average chg%: <span style="color: {'red' if avg_chg < 0 else 'green'};">{avg_chg:.2f}%</span></div>
                        <button style="padding: 5px 10px; background: #0B1D30; color: white; border-radius: 5px; border: none; font-size: 0.8rem; cursor: pointer;">📋 Copy Symbols</button>
                    </div>
                """, unsafe_allow_html=True)
                
                # Styling exactly like the image
                def style_portfolio(row):
                    bg_color = [''] * len(row)
                    ret_idx = final_port_df.columns.get_loc('Return %')
                    if row['Return %'] > 0: bg_color[ret_idx] = 'background-color: rgba(187, 247, 208, 0.4); color: green; font-weight: bold;'
                    elif row['Return %'] < 0: bg_color[ret_idx] = 'background-color: rgba(254, 202, 202, 0.4); color: red; font-weight: bold;'
                    return bg_color

                styled_port = final_port_df.style.apply(style_portfolio, axis=1).hide(axis="index").format({
                    "Today chg%": "{:.2f}%",
                    "Entry Price": "${:.2f}",
                    "Stop Loss": "${:.2f}",
                    "Current Price": "${:.2f}",
                    "Profit/Loss": "${:.2f}",
                    "Return %": "{:.2f}%",
                    "EMA21": "${:.2f}"
                })
                
                st.markdown(f'<div class="scrollable-table-container">{styled_port.to_html()}</div>', unsafe_allow_html=True)
                
            except Exception as e:
                st.error(f"Error loading sheet: {str(e)}. Ensure the columns match: 'Stock Ticker', 'Entry date', 'Entry Price', 'Stop Loss', 'Risk'")

if __name__ == "__main__":
    run_usa_screener()
