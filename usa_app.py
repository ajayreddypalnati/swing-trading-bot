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

    @st.cache_data(ttl=86400) 
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
                except Exception as e:
                    print(f"Lookup Error (India): {e}")
                
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
                formatted_data.append([symbol, d[1], d[9], d[10], d[11], d[15], d[17], d[18]])
            return formatted_data
        except Exception:
            return []
            
    @st.cache_data(ttl=60)
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
                composite_sym = f"{str(exchange_raw).upper()}:{str(ticker_name).upper()}" if exchange_raw and ticker_name else str(item["s"]).upper()
                    
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
        try: return "-" if pd.isna(val) or str(val).strip() == "" else fmt_str.format(float(val))
        except: return "-"

    def safe_int(val, prefix="", suffix=""):
        try: return "-" if pd.isna(val) or val == "" else f"{prefix}{int(float(val))}{suffix}"
        except: return "-"

    def format_stars(val):
        try:
            if val in ["", 6] or pd.isna(val): return ""
            stars = 6 - int(float(val))
            return "⭐" * stars if 1 <= stars <= 5 else ""
        except: return ""

    def get_breadth_color(breadth_str):
        try:
            match = re.search(r'(\d+\.?\d*)%', str(breadth_str))
            if match:
                val = float(match.group(1))
                if val <= 30.0: return "rgba(252, 165, 165, 0.4)"  
                elif val <= 40.0: return "rgba(254, 202, 202, 0.4)"  
                elif val <= 60.0: return "rgba(253, 230, 138, 0.4)"  
                else: return "rgba(134, 239, 172, 0.4)"  
            return "#FFFFFF"
        except: return "#FFFFFF"

    def create_metric_card(title, value, bg_color):
        return f"""
        <div style="background: {bg_color}; border-radius: 8px; padding: 0.8rem 1rem; border: 1px solid #0B1D30; box-shadow: 0 2px 4px rgba(0,0,0,0.05); height: 85px; display: flex; flex-direction: column; justify-content: center; margin-bottom: 5px;">
            <span style="font-size: 0.75rem; color: #0B1D30; font-weight: 700; text-transform: uppercase;">{title}</span>
            <span style="color: #0B1D30; font-size: 1.2rem; font-weight: 800; display: block; margin-top: 0.1rem;">{value}</span>
        </div>
        """

    def gen_copy_btn(copy_str, id):
        return f"""
        <!DOCTYPE html><html><head><style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600&display=swap');
        body {{ margin: 0; display: flex; justify-content: flex-end; align-items: center; background: transparent; overflow: hidden; }}
        button {{ font-family: 'Inter', sans-serif; background: #0B1D30; color: #fff; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 0.8rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        button:hover {{ background: #162C46; }}
        </style></head><body>
        <button id="btn{id}" onclick="c()">📋 Copy Symbols</button>
        <script>function c() {{ let t = document.createElement('textarea'); t.value = "{copy_str}"; document.body.appendChild(t); t.select(); document.execCommand('copy'); document.body.removeChild(t); let b = document.getElementById('btn{id}'); b.innerHTML = '✅ Copied!'; setTimeout(()=>b.innerHTML='📋 Copy Symbols', 2000); }}</script>
        </body></html>"""

    # ==========================================
    # DASHBOARD MAIN LAYOUT & HEADER (ET Time)
    # ==========================================
    et_tz = pytz.timezone('US/Eastern')
    now_et = datetime.now(et_tz)

    st.markdown(f"""
        <div class="premium-header">
            <div class="header-left">
                <div class="header-title">⚡ USA 9-EMA Screener</div>
                <div class="header-subtitle">Refreshed every 1 minute paired with Sector, Industry & Momentum rank.</div>
            </div>
            <div class="header-right">
                <div class="live-status">LIVE DATA <div class="blob green"></div></div>
                <div class="time">{now_et.strftime('%I:%M:%S %p ET')}</div>
                <div class="date">{now_et.strftime('%d %b %Y')}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    tv_data = fetch_usa_tradingview()
    us_stock_df, raw_sec, raw_ind, trend_regime, last_sync, us_etf_df = fetch_usa_database_reference()
    live_sheet_breadth = fetch_us_live_breadth()

    live_bg = get_breadth_color(live_sheet_breadth)
    nse_bg = get_breadth_color(trend_regime)

    m1, m2, m3, m4 = st.columns(4)
    with m1: st.markdown(create_metric_card("📊 Breadth (Live)", live_sheet_breadth, live_bg), unsafe_allow_html=True)
    with m2: st.markdown(create_metric_card("⚖️ Breadth (USA)", trend_regime, nse_bg), unsafe_allow_html=True)
    with m3: st.markdown(create_metric_card("💼 Portfolio Alloc", "N/A", "#FFFFFF"), unsafe_allow_html=True)
    with m4: st.markdown(create_metric_card("🔄 Last Update", last_sync, "rgba(216, 180, 254, 0.3)"), unsafe_allow_html=True)

    # ==========================================
    # DATA PROCESSING 
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

        df = df.merge(us_stock_df, on="Symbol", how="left") if not us_stock_df.empty else df.assign(**{'Turnover in Cr': np.nan, 'Momentum Rank': np.nan})

        df['Sector Rank'] = pd.to_numeric(df['Sector Rank'], errors='coerce')
        df['Ind. Rank'] = pd.to_numeric(df['Ind. Rank'], errors='coerce')

        df['Priority'] = 6 
        t_sec, t_ind = df['Sector Rank'].fillna(999), df['Ind. Rank'].fillna(999)
        
        df.loc[(t_sec <= 5) & (t_ind <= 20), 'Priority'] = 1
        df.loc[(t_sec <= 5) & (t_ind >= 21) & (t_ind <= 30), 'Priority'] = 2
        df.loc[(t_sec > 5) & (t_ind <= 20), 'Priority'] = 3
        df.loc[(t_sec <= 5) & (t_ind > 30), 'Priority'] = 4
        df.loc[(t_sec >= 6) & (t_ind >= 21) & (t_ind <= 30), 'Priority'] = 5

        display_cols = ["Priority", "Symbol", "Exchange", "Price", "Chg %", "Mcap", "Turnover in Cr", "Vol", "Sector", "Sector Rank", "Industry", "Ind. Rank", "Momentum Rank"]
        display_df = df[[c for c in display_cols if c in df.columns]].copy().sort_values(by=["Priority", "Momentum Rank"], ascending=[True, True], na_position="last").fillna("")

    # ==========================================
    # NAVIGATION TABS 
    # ==========================================
    tab_main, tab_leaders, tab_us_etf, tab_port = st.tabs([
        "⚡ 9-EMA Screener", "🏆 Market Leaders", "🌍 US ETF Screener", "📈 Portfolio Tracker"
    ])

    with tab_main:
        if not display_df.empty:
            html_table = display_df.style.hide(axis="index").apply(lambda r: ['background-color: rgba(39, 174, 96, 0.15);' if c == 'Priority' and str(r.get('Priority','')) not in ['6',''] else '' for c in r.index], axis=1).format({
                "Price": lambda x: safe_fmt(x, "${:.2f}"), "Chg %": lambda x: safe_fmt(x, "{:.2f}%"), 
                "Mcap": lambda x: safe_fmt(x, "{:,.0f}"), "Turnover in Cr": lambda x: safe_fmt(x, "{:.0f}"), 
                "Vol": lambda x: safe_fmt(x, "{:,.0f}"), "Momentum Rank": safe_int, "Priority": format_stars, 
                "Sector Rank": lambda x: safe_int(x, "#"), "Ind. Rank": lambda x: safe_int(x, "#")
            }).to_html()
            
            components.html(gen_copy_btn(",".join(display_df['Symbol'].tolist()), "usamain"), height=30)
            for _, r in display_df.iterrows(): 
                html_table = re.sub(rf'(<td[^>]*>)({re.escape(str(r["Symbol"]))})(</td>)', rf'\1<a href="https://www.tradingview.com/chart/?symbol={str(r["Symbol"])}" target="_blank" style="color:inherit;text-decoration:none;border-bottom:1px dashed #0B1D30;font-weight:600;">{str(r["Symbol"])}</a>\3', html_table)
            st.markdown(f'<div class="scrollable-table-container">{html_table}</div>', unsafe_allow_html=True)
        else: 
            st.info("No US stocks matching criteria right now.")

    with tab_leaders:
        if not raw_sec.empty and not raw_ind.empty:
            lc1, lc2 = st.columns(2)
            with lc1:
                st.markdown("##### 🔥 Top 5 Sectors (USA)")
                ts = raw_sec.copy().rename(columns={'Avg_1D_Return': '1d Avg %', 'ATH_Stocks': 'ATH count'}).sort_values('Rank').head(5)
                html = "<div class='sleek-table-wrapper'><table class='sleek-table'><thead><tr>" + "".join([f"<th>{c}</th>" for c in ts.columns]) + "</tr></thead><tbody>"
                for i, r in ts.iterrows(): html += "<tr>" + "".join([f"<td>{r[c]}</td>" for c in ts.columns]) + "</tr>"
                st.markdown(html + "</tbody></table></div>", unsafe_allow_html=True)
            with lc2:
                st.markdown("##### 🚀 Top 30 Industries (USA)")
                ti = raw_ind.copy().rename(columns={'Avg_1D_Return': '1d Avg %', 'ATH_Stocks': 'ATH count'}).sort_values('Rank').head(30)
                html = "<div class='sleek-table-wrapper'><table class='sleek-table'><thead><tr>" + "".join([f"<th>{c}</th>" for c in ti.columns]) + "</tr></thead><tbody>"
                for i, r in ti.iterrows(): html += "<tr>" + "".join([f"<td>{r[c]}</td>" for c in ti.columns]) + "</tr>"
                st.markdown(html + "</tbody></table></div>", unsafe_allow_html=True)

    with tab_us_etf:
        if not us_etf_df.empty:
            u_df = us_etf_df.copy()
            for c in ['Price (USD)', 'Avg Vol 30D', 'Expense Ratio', 'Chg %']: u_df[c] = pd.to_numeric(u_df.get(c, 0), errors='coerce')
            u_df['Turnover (Cr)'] = (u_df['Avg Vol 30D'] * u_df['Price (USD)'] * 95) / 10000000
            
            v_us = u_df[u_df['EMA 21 Status'].astype(str).str.strip().str.upper() == 'ABOVE 21 EMA'].sort_values('Relative Score', ascending=True).head(10).reset_index(drop=True)
            if not v_us.empty:
                v_us['Rank'] = v_us.index + 1
                v_us = v_us[['Rank', 'Symbol', 'Price (USD)', 'Chg %', 'Category', 'Index', 'EMA 21 Status', 'Avg Vol 30D', 'Turnover (Cr)', 'Expense Ratio']]
                
                t_idx, t_avg = v_us.head(4).index.tolist(), v_us.head(4)['Chg %'].mean()
                
                ec1, ec2, ec3 = st.columns([3, 4, 3])
                with ec2: st.markdown(f"<div style='text-align:center; padding-top:10px; font-weight:700;'>Avg Return: <span style='color:{'#10B981' if t_avg > 0 else '#EF4444'};'>{t_avg:.2f}%</span></div>", unsafe_allow_html=True)
                with ec3: components.html(gen_copy_btn(",".join(v_us['Symbol'].tolist()), "usae"), height=30)

                h_us = v_us.style.apply(lambda r: ["font-weight:700; background-color:rgba(187,247,208,0.5);" if r.name in t_idx and c == "Chg %" else "font-weight:700;" if r.name in t_idx else "" for c in r.index], axis=1).hide(axis="index").format({'Price (USD)': lambda x: safe_fmt(x, "${:.2f}"), 'Chg %': lambda x: safe_fmt(x, "{:.2f}%"), 'Turnover (Cr)': lambda x: safe_fmt(x, "{:.2f}"), 'Avg Vol 30D': lambda x: safe_fmt(x, "{:,.0f}"), 'Expense Ratio': lambda x: safe_fmt(x, "{:.2f}")}).to_html()
                
                for _, r in v_us.iterrows(): h_us = re.sub(rf'(<td[^>]*>)({re.escape(str(r["Symbol"]))})(</td>)', rf'\1<a href="https://www.tradingview.com/chart/4efUco2X/?symbol={str(r["Symbol"])}" target="_blank" style="color:inherit;text-decoration:none;border-bottom:1px dashed #0B1D30;font-weight:600;">{str(r["Symbol"])}</a>\3', h_us)
                st.markdown(f'<div class="scrollable-table-container">{h_us}</div>', unsafe_allow_html=True)

    with tab_port:
        col_rad, col_clr = st.columns([8, 2])
        with col_rad: data_source = st.radio("Source", ["Google Sheets", "Upload CSV"], horizontal=True, label_visibility="collapsed")
        with col_clr:
            if st.button("🧹 Clear Cache", use_container_width=True): st.cache_data.clear(); st.rerun()

        if 'us_port_refresh' not in st.session_state: st.session_state['us_port_refresh'] = "Never"

        if data_source == "Google Sheets":
            if 'saved_us_gsheet' not in st.session_state: st.session_state['saved_us_gsheet'] = "https://docs.google.com/..."
            cu, cb = st.columns([8, 2])
            with cu: gs_url = st.text_input("URL", value=st.session_state['saved_us_gsheet'], label_visibility="collapsed")
            with cb: load_data = st.button("🔄 Refresh", use_container_width=True)
            st.markdown(f"<div style='font-size:0.8rem; color:#6B7280;'>🟢 Last Refresh: {st.session_state['us_port_refresh']}</div>", unsafe_allow_html=True)
            if load_data: st.session_state['saved_us_gsheet'] = gs_url
        else:
            cu, cb = st.columns([8, 2])
            with cu: uploaded_file = st.file_uploader("Upload CSV", type=['csv'], label_visibility="collapsed")
            with cb: load_data = st.button("🔄 Load", use_container_width=True)

        if load_data:
            st.session_state['us_port_refresh'] = datetime.now(pytz.timezone('US/Eastern')).strftime('%d %b %Y, %I:%M %p ET')
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
                        mapped_sym = exchange_map.get(sym, sym)
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
                    if not tv:
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
                
                port_col1, port_col2, port_col3 = st.columns([3, 4, 3])
                with port_col2:
                    avg_color = "#10B981" if avg_chg > 0 else "#EF4444"
                    st.markdown(f"<div style='text-align:center; padding-top:10px; font-weight:700;'>Avg chg%: <span style='color: {avg_color};'>{avg_chg:.2f}%</span></div>", unsafe_allow_html=True)
                
                with port_col3:
                    components.html(gen_copy_btn(",".join(final_port_df['Symbol'].tolist()), "usaport"), height=30)
                
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
                    
                    if has_alert: bg_color[sym_idx] = 'background-color: rgba(254, 202, 202, 0.7); color: red; font-weight: bold;'
                    return bg_color

                styled_port = final_port_df.style.apply(style_portfolio, axis=1).hide(axis="index").format({
                    "Today chg%": "{:.2f}%", "Return %": "{:.2f}%", "Risk %": "{:.2%}"
                })
                
                st.markdown(f'<div class="scrollable-table-container">{styled_port.to_html()}</div>', unsafe_allow_html=True)
                
            except Exception as e:
                st.error(f"Error loading data: {str(e)}. Ensure columns match: 'Stock Ticker', 'Entry date', 'Entry Price', 'Stop Loss', 'Risk'")
