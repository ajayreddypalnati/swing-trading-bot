import requests
import pandas as pd
import numpy as np
import time
import re
from datetime import datetime, timezone, timedelta
import pytz
import streamlit as st
from sqlalchemy import create_engine, text
import streamlit.components.v1 as components
import holidays

def run_usa_screener():
    # Auto-refresh the page every 60 seconds
    components.html('<meta http-equiv="refresh" content="60">', height=0)

    # ==========================================
    # APIs & ENDPOINTS
    # ==========================================
    TV_URL = 'https://scanner.tradingview.com/america/scan'
    TV_HEADERS = { 'User-Agent': 'Mozilla/5.0', 'Origin': 'https://www.tradingview.com', 'Content-Type': 'application/json' }
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
                {
                    "operation": {
                        "operator": "or",
                        "operands": [
                            {"operation": {"operator": "and", "operands": [{"expression": {"left": "type", "operation": "equal", "right": "stock"}}, {"expression": {"left": "typespecs", "operation": "has", "right": ["common"]}}]}},
                            {"operation": {"operator": "and", "operands": [{"expression": {"left": "type", "operation": "equal", "right": "stock"}}, {"expression": {"left": "typespecs", "operation": "has", "right": ["preferred"]}}]}},
                            {"operation": {"operator": "and", "operands": [{"expression": {"left": "type", "operation": "equal", "right": "dr"}}]}},
                            {"operation": {"operator": "and", "operands": [{"expression": {"left": "type", "operation": "equal", "right": "fund"}}, {"expression": {"left": "typespecs", "operation": "has_none_of", "right": ["etf", "mutual"]}}]}}
                        ]
                    }
                },
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
                    us_stock_df['Symbol'] = us_stock_df['Symbol'].astype(str).str.strip().str.upper()
                except Exception:
                    us_stock_df = pd.DataFrame(columns=['Symbol', 'Turnover in Cr', 'Momentum Rank'])

                try:
                    raw_sec = pd.read_sql(text('SELECT * FROM "USA Sector Analysis"'), conn)
                    raw_ind = pd.read_sql(text('SELECT * FROM "US Industry Analysis"'), conn)
                except:
                    raw_sec, raw_ind = pd.DataFrame(), pd.DataFrame()

                try:
                    trend_df = pd.read_sql(
                        text('SELECT trend_regime FROM "US Market trend summary" LIMIT 1'),
                        conn
                    )
                    trend_regime = (
                        trend_df["trend_regime"].iloc[0]
                        if not trend_df.empty
                        else "Pending..."
                    )
                except Exception as e:
                    print(e)
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

    @st.cache_data(ttl=86400) # Increased to 24 hours for superfast updates
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

    @st.cache_data(ttl=60)
    def fetch_us_live_breadth():
        try:
            ts = int(time.time())
            url = f"https://docs.google.com/spreadsheets/d/e/2PACX-1vR1Evjm0QI8lj_k3439UzQShcg9fL8oTDq2nWPOY-2aXpKIesb3NsstOO_08pxAsTL6TL6WmLacqq9N/pub?gid=2103540271&single=true&output=csv&t={ts}"
            df = pd.read_csv(url, header=None)
            raw_val = df.iloc[5, 28]
            market_breadth_value = str(raw_val).strip()
            if pd.isna(raw_val) or "DIV/0" in market_breadth_value or "REF!" in market_breadth_value or "N/A" in market_breadth_value:
                return "N/A"
            return market_breadth_value
        except Exception:
            return "N/A"

    def fetch_usa_tradingview():
        try:
            response = requests.post(TV_URL, headers=TV_HEADERS, json=TV_PAYLOAD, timeout=10)
            raw_data = response.json().get("data", [])
            formatted_data = []
            for item in raw_data:
                d = item["d"]
                raw_ticker = str(d[0])
                symbol = raw_ticker
                if "{" in raw_ticker:
                    try:
                        import ast
                        parsed_ticker = ast.literal_eval(raw_ticker)
                        symbol = parsed_ticker.get("name", raw_ticker)
                    except: pass
                price = d[1]
                change = d[9]
                vol = d[10]
                mcap = d[11]
                sector = d[15]
                industry = d[17]
                exchange = d[18]
                formatted_data.append([symbol, price, change, vol, mcap, sector, industry, exchange])
            return formatted_data
        except Exception:
            return []
            
    @st.cache_data(ttl=60)
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
    # SAFE FORMATTERS & UI HELPERS
    # ==========================================
    def safe_fmt(val, fmt_str):
        try:
            if pd.isna(val) or str(val).strip() == "": return "-"
            return fmt_str.format(float(val))
        except: return "-"

    def safe_int(val, prefix="", suffix=""):
        if val == "" or pd.isna(val): return "-"
        try: return f"{prefix}{int(float(val))}{suffix}"
        except: return "-"

    def format_stars(val):
        if val == "" or pd.isna(val) or val == 6: return ""
        try:
            stars = 6 - int(float(val))
            if 1 <= stars <= 5: return "⭐" * stars
            return ""
        except: return ""

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
                action_suffix = " - Trade" if "📈" in str(nse_breadth_str) else " - Stop Trading"
                if "📉" not in str(nse_breadth_str) and "📈" not in str(nse_breadth_str):
                    action_suffix = " - Trade" if live_val > 50.0 else " - Stop Trading"

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

    # ==========================================
    # DASHBOARD MAIN LAYOUT & HEADER (ET Time)
    # ==========================================
    et_tz = pytz.timezone('US/Eastern')
    now_et = datetime.now(et_tz)
    current_time = now_et.strftime('%I:%M:%S %p ET')
    current_date = now_et.strftime('%d %b %Y')

    st.markdown(f"""
        <div class="premium-header">
            <div class="header-left">
                <div class="header-title">⚡ USA 9-EMA Screener</div>
                <div class="header-subtitle">Refreshed every 1 minute paired with Sector, Industry & Momentum rank.</div>
            </div>
            <div class="header-right">
                <div class="live-status">LIVE DATA <div class="blob green"></div></div>
                <div class="time">{current_time}</div>
                <div class="date">{current_date}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    tv_data = fetch_usa_tradingview()
    us_stock_df, raw_sec, raw_ind, trend_regime, last_sync, us_etf_df = fetch_usa_database_reference()
    live_sheet_breadth = fetch_us_live_breadth()

    live_bg = get_breadth_color(live_sheet_breadth)
    nse_bg = get_breadth_color(trend_regime)
    alloc_val, alloc_bg = get_portfolio_allocation(trend_regime, live_sheet_breadth)
    last_sync_bg = "rgba(216, 180, 254, 0.3)"

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    with metric_col1: st.markdown(create_metric_card("📊 Market Breadth (Live)", live_sheet_breadth, live_bg), unsafe_allow_html=True)
    with metric_col2: st.markdown(create_metric_card("⚖️ Market Breadth (USA)", trend_regime, nse_bg), unsafe_allow_html=True)
    with metric_col3: st.markdown(create_metric_card("💼 Portfolio Allocation", alloc_val, alloc_bg), unsafe_allow_html=True)
    with metric_col4: st.markdown(create_metric_card("🔄 Last DB Update", last_sync, last_sync_bg), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ==========================================
    # DATA PROCESSING FOR MAIN TABS
    # ==========================================
    display_df = pd.DataFrame()
    if tv_data:
        df = pd.DataFrame(tv_data, columns=["Ticker", "Price", "Chg %", "Vol", "Mcap", "Sector", "Industry", "Exchange"])
        df['Symbol'] = df['Ticker'].astype(str).str.strip().str.upper()

        if not raw_sec.empty:
            sec_rank_dict = {str(k).strip().lower(): v for k, v in zip(raw_sec['Sector'], raw_sec['Rank'])}
            df['Sector Rank'] = df['Sector'].astype(str).str.strip().str.lower().map(sec_rank_dict)
        else: df['Sector Rank'] = np.nan
            
        if not raw_ind.empty:
            ind_rank_dict = {str(k).strip().lower(): v for k, v in zip(raw_ind['Industry'], raw_ind['Rank'])}
            df['Ind. Rank'] = df['Industry'].astype(str).str.strip().str.lower().map(ind_rank_dict)
        else: df['Ind. Rank'] = np.nan

        if not us_stock_df.empty:
            df = df.merge(us_stock_df, on="Symbol", how="left")
        else:
            df['Turnover in Cr'] = np.nan
            df['Momentum Rank'] = np.nan

        df['Sector Rank'] = pd.to_numeric(df['Sector Rank'], errors='coerce')
        df['Ind. Rank'] = pd.to_numeric(df['Ind. Rank'], errors='coerce')

        df['Priority'] = 6 
        
        t_sec = df['Sector Rank'].fillna(999)
        t_ind = df['Ind. Rank'].fillna(999)

        p1 = (t_sec <= 5) & (t_ind <= 20)
        p2 = (t_sec <= 5) & (t_ind >= 21) & (t_ind <= 30)
        p3 = (t_sec > 5) & (t_ind <= 20)
        p4 = (t_sec <= 5) & (t_ind > 30)
        p5 = (t_sec >= 6) & (t_ind >= 21) & (t_ind <= 30)
        
        df.loc[p1, 'Priority'] = 1
        df.loc[p2, 'Priority'] = 2
        df.loc[p3, 'Priority'] = 3
        df.loc[p4, 'Priority'] = 4
        df.loc[p5, 'Priority'] = 5

        display_cols = ["Priority", "Symbol", "Exchange", "Price", "Chg %", "Mcap", "Turnover in Cr", "Vol", "Sector", "Sector Rank", "Industry", "Ind. Rank", "Momentum Rank"]
        display_df = df[[c for c in display_cols if c in df.columns]].copy()
        display_df = display_df.sort_values(by=["Priority", "Momentum Rank"], ascending=[True, True], na_position="last").fillna("")

    def highlight_main_table(row):
        styles = []
        for col in row.index:
            style = ""
            if col == 'Priority' and pd.notna(row['Priority']) and str(row['Priority']).strip() != "" and str(row['Priority']) != '6':
                try:
                    if float(row['Priority']) < 6: style += 'background-color: rgba(39, 174, 96, 0.15); '
                except: pass
            styles.append(style)
        return styles

    # ==========================================
    # NAVIGATION TABS 
    # ==========================================
    tab_main, tab_leaders, tab_us_etf, tab_port = st.tabs([
        "⚡ 9-EMA Screener", 
        "🏆 Market Leaders",
        "🌍 US ETF Screener",
        "📈 Portfolio Tracker"
    ])

    # --- 1. 9-EMA SCREENER TAB ---
    with tab_main:
        if not display_df.empty:
            styled_df = display_df.style.hide(axis="index").apply(highlight_main_table, axis=1).format({
                "Price": lambda x: safe_fmt(x, "${:.2f}"), 
                "Chg %": lambda x: safe_fmt(x, "{:.2f}%"), 
                "Mcap": lambda x: safe_fmt(x, "{:,.0f}"),
                "Turnover in Cr": lambda x: safe_fmt(x, "{:.0f}"),
                "Vol": lambda x: safe_fmt(x, "{:,.0f}"),
                "Momentum Rank": lambda x: safe_int(x),
                "Priority": lambda x: format_stars(x),
                "Sector Rank": lambda x: safe_int(x, "#"),
                "Ind. Rank": lambda x: safe_int(x, "#")
            })
            html_table = styled_df.to_html()
            
            copy_str = ",".join(display_df['Symbol'].tolist())
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
                    const btn = document.getElementById('copyBtn');
                    btn.innerHTML = '✅ Copied!';
                    setTimeout(() => btn.innerHTML = '📋 Copy Symbols', 2000);
                }}
                </script>
            </body>
            </html>
            """
            components.html(copy_html, height=40)

            for _, r in display_df.iterrows():
                sym = str(r['Symbol'])
                url = f"https://www.tradingview.com/chart/?symbol={sym}"
                link = f'<a href="{url}" target="_blank" style="color: inherit; text-decoration: none; border-bottom: 1px dashed #0B1D30; font-weight: 600;">{sym}</a>'
                html_table = re.sub(rf'(<td[^>]*>)({re.escape(sym)})(</td>)', rf'\1{link}\3', html_table)
                
            st.markdown(f'<div class="scrollable-table-container">{html_table}</div>', unsafe_allow_html=True)
        else: 
            st.info("No US stocks matching criteria right now.")

    # --- 2. MARKET LEADERS TAB ---
    with tab_leaders:
        if not raw_sec.empty and not raw_ind.empty:
            lead_col1, lead_col2 = st.columns(2)
            
            with lead_col1:
                st.markdown("##### 🔥 Top 5 Sectors (USA)")
                top_sec = raw_sec.copy()
                top_sec = top_sec.rename(columns={'Avg_1D_Return': '1d Avg %', 'ATH_Stocks': 'ATH count'})
                sec_cols = ['Rank', 'Sector', '1d Avg %', 'ATH count', 'ATH %']
                top_sec = top_sec[[c for c in sec_cols if c in top_sec.columns]].sort_values('Rank').head(5)
                
                top_2_sec_idx = []
                if '1d Avg %' in top_sec.columns: top_2_sec_idx = top_sec['1d Avg %'].astype(float).nlargest(2).index.tolist()
                if 'ATH %' in top_sec.columns: top_sec['ATH %'] = top_sec['ATH %'].astype(float).map("{:.2f}%".format)
                if '1d Avg %' in top_sec.columns: top_sec['1d Avg %'] = top_sec['1d Avg %'].astype(float).map("{:.2f}%".format)
                
                html = "<div class='sleek-table-wrapper'><table class='sleek-table'><thead><tr>"
                for col in top_sec.columns: html += f"<th>{col}</th>"
                html += "</tr></thead><tbody>"
                for idx, row in top_sec.iterrows():
                    html += "<tr>"
                    for c in top_sec.columns:
                        val = row[c]
                        if idx in top_2_sec_idx and c == '1d Avg %': html += f"<td style='background-color: rgba(187, 247, 208, 0.5); font-weight: 600;'>{val}</td>"
                        elif idx in top_2_sec_idx and c == 'Sector': html += f"<td><b>{val}</b></td>"
                        else: html += f"<td>{val}</td>"
                    html += "</tr>"
                html += "</tbody></table></div>"
                st.markdown(html, unsafe_allow_html=True)
                
            with lead_col2:
                st.markdown("##### 🚀 Top 30 Industries (USA)")
                top_ind = raw_ind.copy()
                top_ind = top_ind.rename(columns={'Avg_1D_Return': '1d Avg %', 'ATH_Stocks': 'ATH count'})
                ind_cols = ['Rank', 'Industry', '1d Avg %', 'ATH count', 'ATH %']
                top_ind = top_ind[[c for c in ind_cols if c in top_ind.columns]].sort_values('Rank').head(30)
                
                top_4_ind_idx = []
                if '1d Avg %' in top_ind.columns: top_4_ind_idx = top_ind['1d Avg %'].astype(float).nlargest(4).index.tolist()
                if 'ATH %' in top_ind.columns: top_ind['ATH %'] = top_ind['ATH %'].astype(float).map("{:.2f}%".format)
                if '1d Avg %' in top_ind.columns: top_ind['1d Avg %'] = top_ind['1d Avg %'].astype(float).map("{:.2f}%".format)
                
                html = "<div class='sleek-table-wrapper'><table class='sleek-table'><thead><tr>"
                for col in top_ind.columns: html += f"<th>{col}</th>"
                html += "</tr></thead><tbody>"
                for idx, row in top_ind.iterrows():
                    html += "<tr>"
                    for c in top_ind.columns:
                        val = row[c]
                        if idx in top_4_ind_idx and c == '1d Avg %': html += f"<td style='background-color: rgba(187, 247, 208, 0.5); font-weight: 600;'>{val}</td>"
                        elif idx in top_4_ind_idx and c == 'Industry': html += f"<td><b>{val}</b></td>"
                        else: html += f"<td>{val}</td>"
                    html += "</tr>"
                html += "</tbody></table></div>"
                st.markdown(html, unsafe_allow_html=True)

    # --- 3. US ETF SCREENER TAB ---
    with tab_us_etf:
        if not us_etf_df.empty:
            us_df = us_etf_df.copy()
            
            us_df['Price (USD)'] = pd.to_numeric(us_df['Price (USD)'], errors='coerce')
            us_df['Avg Vol 30D'] = pd.to_numeric(us_df['Avg Vol 30D'], errors='coerce')
            us_df['Expense Ratio'] = pd.to_numeric(us_df['Expense Ratio'], errors='coerce')
            us_df['Chg %'] = pd.to_numeric(us_df['Chg %'], errors='coerce')

            us_df['Turnover (Cr)'] = (us_df['Avg Vol 30D'] * us_df['Price (USD)'] * 95) / 10000000
            
            f_us_ema = us_df['EMA 21 Status'].astype(str).str.strip().str.upper() == 'ABOVE 21 EMA'
            valid_us = us_df[f_us_ema].sort_values('Relative Score', ascending=True).head(10)
            
            if not valid_us.empty:
                valid_us = valid_us.reset_index(drop=True)
                valid_us['Rank'] = valid_us.index + 1
                show_cols = ['Rank', 'Symbol', 'Price (USD)', 'Chg %', 'Category', 'Index', 'EMA 21 Status', 'Avg Vol 30D', 'Turnover (Cr)', 'Expense Ratio']
                valid_us = valid_us[[c for c in show_cols if c in valid_us.columns]]

                top_4_chg_idx = valid_us.head(4).index.tolist()
                top_4_avg = valid_us.head(4)['Chg %'].mean() if not valid_us.empty else 0.0
                avg_color = "#10B981" if top_4_avg > 0 else "#EF4444"
                
                etf_col1, etf_col2 = st.columns([8.5, 1.5])
                with etf_col1:
                    st.markdown(f"<h4 style='margin-top: 5px; margin-bottom: 0px;'>Average 1D Return (Top 4): <span style='color: {avg_color};'>{top_4_avg:.2f}%</span></h4>", unsafe_allow_html=True)
                
                with etf_col2:
                    us_etf_copy_str = ",".join(valid_us['Symbol'].astype(str).tolist())
                    us_etf_copy_html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                    <style>
                        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600&display=swap');
                        body {{ margin: 0; padding: 0; display: flex; justify-content: flex-end; align-items: center; height: 100%; background-color: transparent; overflow: hidden; }}
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
                    components.html(us_etf_copy_html, height=35)

                st.markdown("<div style='margin-top: -15px;'></div>", unsafe_allow_html=True)

                def style_us_etf_row(row):
                    is_top_4 = row.name in top_4_chg_idx
                    styles = []
                    for col in row.index:
                        cell_style = ""
                        if is_top_4:
                            cell_style += "font-weight: 700; "
                            if col == 'Chg %': cell_style += "background-color: rgba(187, 247, 208, 0.5); "
                        styles.append(cell_style)
                    return styles
                
                styled_us_etf = valid_us.style.apply(style_us_etf_row, axis=1).hide(axis="index").format({
                    'Price (USD)': lambda x: safe_fmt(x, "${:.2f}"),
                    'Chg %': lambda x: safe_fmt(x, "{:.2f}%"),
                    'Avg Vol 30D': lambda x: safe_fmt(x, "{:,.0f}"),
                    'Turnover (Cr)': lambda x: safe_fmt(x, "₹{:.2f}"),
                    'Expense Ratio': lambda x: safe_fmt(x, "{:.2f}")
                })

                html_us_table = styled_us_etf.to_html()
                
                for _, r in valid_us.iterrows():
                    sym = str(r['Symbol'])
                    url = f"https://www.tradingview.com/chart/4efUco2X/?symbol={sym}"
                    link = f'<a href="{url}" target="_blank" style="color: inherit; text-decoration: none; border-bottom: 1px dashed #0B1D30; font-weight: 600;">{sym}</a>'
                    html_us_table = re.sub(rf'(<td[^>]*>)({re.escape(sym)})(</td>)', rf'\1{link}\3', html_us_table)
                
                st.markdown(f'<div class="scrollable-table-container">{html_us_table}</div>', unsafe_allow_html=True)
            else: st.info("No US ETFs match the criteria at the moment.")

    # --- 4. PORTFOLIO TRACKER TAB ---
    with tab_port:
        col_text, col_clear = st.columns([9, 2], vertical_alignment="center")
        with col_text:
            st.markdown("<p style='color:#4B5563; font-size:0.9rem; margin:0;'>Track your portfolio via Google Sheets or CSV upload. The app pulls the first 5 columns: Ticker, Entry Date, Entry Price, Stop Loss, Risk.</p>", unsafe_allow_html=True)
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
                
                port_col1, port_col2 = st.columns([8.5, 1.5])
                with port_col1:
                    avg_color = "#10B981" if avg_chg > 0 else "#EF4444"
                    st.markdown(f"<h4 style='margin-top: 5px; margin-bottom: 0px;'>Avg chg%: <span style='color: {avg_color};'>{avg_chg:.2f}%</span></h4>", unsafe_allow_html=True)
                
                with port_col2:
                    port_copy_str = ",".join(final_port_df['Symbol'].tolist())
                    port_copy_html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                    <style>
                        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600&display=swap');
                        body {{ margin: 0; padding: 0; display: flex; justify-content: flex-end; align-items: center; height: 100%; background-color: transparent; overflow: hidden; }}
                        button {{ font-family: 'Inter', sans-serif; background-color: #0B1D30; color: #FFFFFF; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1); transition: all 0.2s; }}
                        button:hover {{ background-color: #162C46; transform: translateY(-1px); }}
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
                    components.html(port_copy_html, height=35)
                
                st.markdown("<div style='margin-top: -15px;'></div>", unsafe_allow_html=True)
                
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
                
                st.markdown(f'<div class="scrollable-table-container">{styled_port.to_html()}</div>', unsafe_allow_html=True)
                
            except Exception as e:
                st.error(f"Error loading data: {str(e)}. Ensure columns match: 'Stock Ticker', 'Entry date', 'Entry Price', 'Stop Loss', 'Risk'")
