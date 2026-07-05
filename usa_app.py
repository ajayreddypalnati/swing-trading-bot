import requests
import pandas as pd
import numpy as np
import time
import re
from datetime import datetime, timezone, timedelta
import streamlit as st
from sqlalchemy import create_engine, text
import streamlit.components.v1 as components

def run_usa_screener():
    # ==========================================
    # APIs & ENDPOINTS
    # ==========================================
    TV_URL = 'https://scanner.tradingview.com/america/scan'
    TV_HEADERS = { 'User-Agent': 'Mozilla/5.0', 'Origin': 'https://www.tradingview.com', 'Content-Type': 'application/json' }
    TV_PAYLOAD = {
        "columns":["ticker-view","close","type","typespecs","pricescale","minmov","fractional","minmove2","currency","change","volume","market_cap_basic","fundamental_currency_code","sector.tr","market","sector","industry.tr","industry","exchange.tr","source-logoid"],
        "filter":[{"left":"low","operation":"less","right":"EMA9"},{"left":"is_blacklisted","operation":"equal","right":False},{"left":"high","operation":"greater","right":"EMA9"},{"left":"close","operation":"in_range%","right":["High.All",0.9,1]},{"left":"RSI","operation":"greater","right":65},{"left":"close","operation":"egreater","right":"EMA9"},{"left":"Value.Traded","operation":"greater","right":3000000},{"left":"change","operation":"in_range","right":[0,10]},{"left":"Perf.1M","operation":"greater","right":10},{"left":"is_primary","operation":"equal","right":True}],
        "ignore_unknown_fields":False,"options":{"lang":"en"},"range":[0,100],"sort":{"sortBy":"market_cap_basic","sortOrder":"asc"},"symbols":{"symbolset":["SYML:TVC;RUA"]},"markets":["america"],
        "filter2":{"operator":"and","operands":[{"operation":{"operator":"or","operands":[{"operation":{"operator":"and","operands":[{"expression":{"left":"type","operation":"equal","right":"stock"}},{"expression":{"left":"typespecs","operation":"has","right":["common"]}}]}},{"operation":{"operator":"and","operands":[{"expression":{"left":"type","operation":"equal","right":"stock"}},{"expression":{"left":"typespecs","operation":"has","right":["preferred"]}}]}},{"operation":{"operator":"and","operands":[{"expression":{"left":"type","operation":"equal","right":"dr"}}]}},{"operation":{"operator":"and","operands":[{"expression":{"left":"type","operation":"equal","right":"fund"}},{"expression":{"left":"typespecs","operation":"has_none_of","right":["etf","mutual"]}}]}}]}},{"expression":{"left":"typespecs","operation":"has_none_of","right":["pre-ipo"]}}]}}
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
                # 1. Main USA Stock Screener (for VLOOKUP)
                try:
                    us_stock_df = pd.read_sql(text('SELECT * FROM "US Stock screener"'), conn)
                    # Extract Turnover and Momentum Rank
                    col_ticker = next((c for c in us_stock_df.columns if 'symbol' in str(c).lower() or 'ticker' in str(c).lower()), 'Symbol')
                    col_turnover = next((c for c in us_stock_df.columns if 'turnover' in str(c).lower()), 'Turnover in Cr')
                    col_mom = next((c for c in us_stock_df.columns if 'momentum rank' in str(c).lower() or 'relative' in str(c).lower()), 'Momentum Rank')
                    us_stock_df = us_stock_df[[col_ticker, col_turnover, col_mom]].rename(columns={col_ticker: 'Symbol', col_turnover: 'Turnover in Cr', col_mom: 'Momentum Rank'})
                except Exception:
                    us_stock_df = pd.DataFrame(columns=['Symbol', 'Turnover in Cr', 'Momentum Rank'])

                # 2. USA Market Leaders
                try:
                    raw_sec = pd.read_sql(text('SELECT * FROM "USA Sector Analysis"'), conn)
                    raw_ind = pd.read_sql(text('SELECT * FROM "US Industry Analysis"'), conn)
                except:
                    raw_sec, raw_ind = pd.DataFrame(), pd.DataFrame()

                # 3. US Market Trend Summary (For allocation & header)
                try:
                    trend_df = pd.read_sql(text('SELECT * FROM market_trend_summary LIMIT 1'), conn) # Adjust if table name is different
                    trend_regime = trend_df['trend_regime'].iloc[0] if not trend_df.empty else "Pending..."
                except Exception:
                    trend_regime = "N/A"

                # 4. US Sync Log
                try:
                    sync_df = pd.read_sql(text('SELECT * FROM "US Sync log"'), conn)
                    last_sync = sync_df['last_sync'].iloc[0]
                except Exception:
                    last_sync = "Pending Run..."

                # 5. US ETF Screener
                try:
                    us_etf_df = pd.read_sql(text('SELECT * FROM "USA_ETF_Screener"'), conn)
                except Exception:
                    us_etf_df = pd.DataFrame()

            return us_stock_df, raw_sec, raw_ind, trend_regime, last_sync, us_etf_df
        except Exception as e:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "Error", "Error", pd.DataFrame()

    @st.cache_data(ttl=60)
    def fetch_us_live_breadth():
        try:
            ts = int(time.time())
            url = f"https://docs.google.com/spreadsheets/d/e/2PACX-1vR1Evjm0QI8lj_k3439UzQShcg9fL8oTDq2nWPOY-2aXpKIesb3NsstOO_08pxAsTL6TL6WmLacqq9N/pub?gid=2103540271&single=true&output=csv&t={ts}"
            df = pd.read_csv(url, header=None)
            market_breadth_value = df.iloc[5, 28] # Row 6, Column AC (0-indexed)
            return "N/A" if pd.isna(market_breadth_value) else str(market_breadth_value)
        except Exception:
            return "N/A"

    def fetch_usa_tradingview():
        try:
            response = requests.post(TV_URL, headers=TV_HEADERS, json=TV_PAYLOAD, timeout=10)
            raw_data = response.json().get("data", [])
            formatted_data = []
            for item in raw_data:
                d = item["d"]
                # Mapping based on provided JSON columns
                ticker = d[0]
                price = d[1]
                change = d[9]
                vol = d[10]
                mcap = d[11]
                sector = d[15]
                industry = d[17]
                exchange = d[18]
                formatted_data.append([ticker, ticker, price, change, vol, mcap, sector, industry, exchange])
            return formatted_data
        except Exception:
            return []

    # ==========================================
    # SAFE FORMATTERS & UI HELPERS
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
    # DASHBOARD MAIN LAYOUT & HEADER
    # ==========================================
    ist = timezone(timedelta(hours=5, minutes=30))
    current_time = datetime.now(ist).strftime('%I:%M:%S %p')
    current_date = datetime.now(ist).strftime('%d %b %Y')

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
    # DATA PROCESSING FOR TABS
    # ==========================================
    display_df = pd.DataFrame()
    if tv_data:
        df = pd.DataFrame(tv_data, columns=["Ticker", "Name", "Price", "Chg %", "Vol", "Mcap", "Sector", "Industry", "Exchange"])
        df['Symbol'] = df['Ticker'].astype(str).str.strip().str.upper()

        # VLOOKUP Logic
        if not us_stock_df.empty:
            df = df.merge(us_stock_df, on="Symbol", how="left")
        else:
            df['Turnover in Cr'] = np.nan
            df['Momentum Rank'] = np.nan

        display_cols = ["Symbol", "Name", "Price", "Chg %", "Vol", "Mcap", "Turnover in Cr", "Momentum Rank", "Sector", "Industry", "Exchange"]
        display_df = df[[c for c in display_cols if c in df.columns]].copy()
        display_df = display_df.sort_values(by="Momentum Rank", ascending=True, na_position="last").fillna("")

    # ==========================================
    # NAVIGATION TABS (Only 4 for USA)
    # ==========================================
    tab_main, tab_leaders, tab_us_etf, tab_port = st.tabs([
        "⚡ 9-EMA Screener", 
        "🏆 Market Leaders",
        "🌍 US ETF Screener",
        "📈 Portfolio Tracker"
    ])

    with tab_main:
        if not display_df.empty:
            styled_df = display_df.style.hide(axis="index").format({
                "Price": lambda x: safe_fmt(x, "${:.2f}"), 
                "Chg %": lambda x: safe_fmt(x, "{:.2f}%"), 
                "Vol": lambda x: safe_fmt(x, "{:,.0f}"),
                "Mcap": lambda x: safe_fmt(x, "{:,.0f}"),
                "Turnover in Cr": lambda x: safe_fmt(x, "{:.0f}"),
                "Momentum Rank": lambda x: safe_fmt(x, "{:.0f}")
            })
            html_table = styled_df.to_html()
            
            # TradingView Links for US Stocks
            for _, r in display_df.iterrows():
                sym = str(r['Symbol'])
                url = f"https://www.tradingview.com/chart/?symbol={sym}"
                link = f'<a href="{url}" target="_blank" style="color: inherit; text-decoration: none; border-bottom: 1px dashed #0B1D30; font-weight: 600;">{sym}</a>'
                html_table = re.sub(rf'(<td[^>]*>)({re.escape(sym)})(</td>)', rf'\1{link}\3', html_table)
                
            st.markdown(f'<div class="scrollable-table-container">{html_table}</div>', unsafe_allow_html=True)
        else: 
            st.info("No US stocks matching criteria right now.")

    with tab_leaders:
        if not raw_sec.empty and not raw_ind.empty:
            lead_col1, lead_col2 = st.columns(2)
            with lead_col1:
                st.markdown("##### 🔥 Top 5 Sectors (USA)")
                sec_cols = ['Rank', 'Sector', 'Avg 1D Return %', 'ATH_Stocks', 'ATH %']
                sec_cols = [c for c in sec_cols if c in raw_sec.columns]
                top_sec = raw_sec.nsmallest(5, 'Rank')[sec_cols]
                top_sec = top_sec.rename(columns={'ATH_Stocks': 'ATH Count', 'Avg 1D Return %': '1D Avg %'})
                st.markdown(f'<div class="scrollable-table-container">{top_sec.style.hide(axis="index").to_html()}</div>', unsafe_allow_html=True)
                
            with lead_col2:
                st.markdown("##### 🚀 Top 15 Industries (USA)")
                ind_cols = ['Rank', 'Broad Industry', 'Avg 1D Return %', 'ATH_Stocks', 'ATH %']
                ind_cols = [c for c in ind_cols if c in raw_ind.columns]
                top_ind = raw_ind.nsmallest(15, 'Rank')[ind_cols]
                top_ind = top_ind.rename(columns={'ATH_Stocks': 'ATH Count', 'Avg 1D Return %': '1D Avg %'})
                st.markdown(f'<div class="scrollable-table-container">{top_ind.style.hide(axis="index").to_html()}</div>', unsafe_allow_html=True)

    with tab_us_etf:
        if not us_etf_df.empty:
            us_df = us_etf_df.copy()
            f_us_ema = us_df['EMA 21 Status'].astype(str).str.strip().str.upper() == 'ABOVE 21 EMA'
            valid_us = us_df[f_us_ema].sort_values('Relative Score', ascending=True).head(10)
            
            if not valid_us.empty:
                valid_us = valid_us.reset_index(drop=True)
                valid_us['Rank'] = valid_us.index + 1
                show_cols = ['Rank', 'Symbol', 'Price (USD)', 'Chg %', 'Category', 'Index', 'EMA 21 Status', 'Avg Vol 30D', 'Expense Ratio']
                valid_us = valid_us[[c for c in show_cols if c in valid_us.columns]]
                
                styled_us_etf = valid_us.style.hide(axis="index").format({
                    'Price (USD)': lambda x: safe_fmt(x, "${:.2f}"),
                    'Chg %': lambda x: safe_fmt(x, "{:.2f}%"),
                    'Avg Vol 30D': lambda x: safe_fmt(x, "{:,.0f}")
                })
                st.markdown(f'<div class="scrollable-table-container">{styled_us_etf.to_html()}</div>', unsafe_allow_html=True)
            else: st.info("No US ETFs match the criteria at the moment.")

    with tab_port:
        st.info("Tracker UI loaded. Note: Upstox API does not natively support live American equity quotes. Tickers like AAPL will bypass the internal instrument lookup.")
        # Place your existing Upstox tracking logic here as requested.
        pass
