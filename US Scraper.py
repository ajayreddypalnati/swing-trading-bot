import os
import sys
import time
import requests
import re
import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy import text

# ==========================================
# 0. DATABASE CONFIG & HELPER FUNCTIONS
# ==========================================
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("\n❌ FATAL ERROR: DATABASE_URL environment variable is missing.")
    sys.exit(1)

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

if "?pgbouncer=true" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("?pgbouncer=true", "")

try:
    print("\n🔌 SYSTEM: Connecting to Supabase Cloud Database...")
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)
    print("✅ SYSTEM: Database connection established successfully.")
except Exception as e:
    print(f"❌ FATAL ERROR: Could not connect to database: {e}")
    sys.exit(1)


def save_db_with_retry(df, table_name, engine, if_exists="replace", index=False, chunksize=None, method=None):
    """Saves DataFrame to Supabase with an automatic 3-attempt retry loop."""
    for attempt in range(1, 4):
        try:
            df.to_sql(table_name, engine, if_exists=if_exists, index=index, chunksize=chunksize, method=method)
            return True
        except Exception as e:
            print(f"   ⚠️ Database write failed for {table_name} (Attempt {attempt}/3): {e}")
            if attempt < 3: time.sleep(5)
    print(f"❌ Failed to save {table_name} to database after 3 attempts.")


# ==========================================
# 1. SCRAPING FUNCTIONS
# ==========================================
def fetch_tradingview_etfs_all():
    url = "https://scanner.tradingview.com/america/scan?label-product=screener-stock"
    payload = {
        "columns": [
            "ticker-view","close","change","market_cap_basic","sector.tr","industry.tr","exchange.tr","Perf.W","Perf.1M","Perf.3M","Perf.6M","Perf.Y","Value.Traded|1M"
        ],
        "filter":[{"left":"is_blacklisted","operation":"equal","right":False},{"left":"is_primary","operation":"equal","right":True}],
        "ignore_unknown_fields":False,
        "options":{"lang":"en"},
        "range":[0,3000],
        "sort":{"sortBy":"market_cap_basic","sortOrder":"desc"},
        "symbols":{"symbolset":["SYML:TVC;RUA"]},
        "markets":["america"],
        "filter2":{
            "operator":"and",
            "operands":[
                {"operation":{"operator":"or","operands":[
                    {"operation":{"operator":"and","operands":[
                        {"expression":{"left":"type","operation":"equal","right":"stock"}},
                        {"expression":{"left":"typespecs","operation":"has","right":["common"]}}
                    ]}},
                    {"operation":{"operator":"and","operands":[
                        {"expression":{"left":"type","operation":"equal","right":"stock"}},
                        {"expression":{"left":"typespecs","operation":"has","right":["preferred"]}}
                    ]}},
                    {"operation":{"operator":"and","operands":[
                        {"expression":{"left":"type","operation":"equal","right":"dr"}}
                    ]}},
                    {"operation":{"operator":"and","operands":[
                        {"expression":{"left":"type","operation":"equal","right":"fund"}},
                        {"expression":{"left":"typespecs","operation":"has_none_of","right":["etf","mutual"]}}
                    ]}}
                ]}},
                {"expression":{"left":"typespecs","operation":"has_none_of","right":["pre-ipo"]}}
            ]
        }
    }

    print("\nFetching US Stock/Fund data from TradingView...")
    response = requests.post(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
        json=payload,
        timeout=30
    )
    response.raise_for_status()
    data = response.json()
    
    rows = [item["d"] for item in data.get("data", [])]
    processed=[]
    for r in rows:
        sym=r[0].get("name","") if isinstance(r[0],dict) else r[0]
        processed.append([sym,*r[1:]])

    df = pd.DataFrame(processed, columns=[
        "Symbol","Price (USD)","Chg %","Market Cap","Sector","Industry","Exchange","Perf 1W","Perf 1M","Perf 3M","Perf 6M","Perf 1Y","Price x Vol (1M)"
    ])

    print("-" * 50)
    print(f"Success! Downloaded {len(df)} US Stocks/Funds.")
    print("-" * 50)
    return df


def fetch_tradingview_etfs_near_ath():
    url = "https://scanner.tradingview.com/america/scan?label-product=screener-stock"
    payload = {
        "columns":[
            "ticker-view","close","change","market_cap_basic","sector.tr","industry.tr","exchange.tr","Perf.W","Perf.1M","Perf.3M","Perf.6M","Perf.Y","Value.Traded|1M"
        ],
        "filter":[
            {"left":"close","operation":"in_range%","right":["High.All",0.9,1]},
            {"left":"is_blacklisted","operation":"equal","right":False},
            {"left":"is_primary","operation":"equal","right":True}
        ],
        "ignore_unknown_fields":False,
        "options":{"lang":"en"},
        "range":[0,3000],
        "sort":{"sortBy":"market_cap_basic","sortOrder":"asc"},
        "symbols":{"symbolset":["SYML:TVC;RUA"]},
        "markets":["america"],
        "filter2":{"operator":"and","operands":[{"operation":{"operator":"or","operands":[{"operation":{"operator":"and","operands":[{"expression":{"left":"type","operation":"equal","right":"stock"}},{"expression":{"left":"typespecs","operation":"has","right":["common"]}}]}},{"operation":{"operator":"and","operands":[{"expression":{"left":"type","operation":"equal","right":"stock"}},{"expression":{"left":"typespecs","operation":"has","right":["preferred"]}}]}},{"operation":{"operator":"and","operands":[{"expression":{"left":"type","operation":"equal","right":"dr"}}]}},{"operation":{"operator":"and","operands":[{"expression":{"left":"type","operation":"equal","right":"fund"}},{"expression":{"left":"typespecs","operation":"has_none_of","right":["etf","mutual"]}}]}}]}},{"expression":{"left":"typespecs","operation":"has_none_of","right":["pre-ipo"]}}]}
    }

    r = requests.post(url, json=payload, headers={"User-Agent":"Mozilla/5.0","Content-Type":"application/json"}, timeout=30)
    r.raise_for_status()
    rows=[x["d"] for x in r.json().get("data",[])]
    processed=[]
    for row in rows:
        sym=row[0].get("name","") if isinstance(row[0],dict) else row[0]
        processed.append([sym,*row[1:]])
    return pd.DataFrame(processed,columns=[
        "Symbol","Price (USD)","Chg %","Market Cap","Sector","Industry","Exchange","Perf 1W","Perf 1M","Perf 3M","Perf 6M","Perf 1Y","Price x Vol (1M)"
    ])


def fetch_usdinr():
    url="https://scanner.tradingview.com/global/scan"
    payload={
        "symbols":{"tickers":["FX_IDC:USDINR"]},
        "columns":["close"]
    }
    r=requests.post(url,json=payload,headers={"User-Agent":"Mozilla/5.0","Content-Type":"application/json"},timeout=20)
    r.raise_for_status()
    return float(r.json()["data"][0]["d"][0])


# ==========================================
# PORTED COMPLETE US ETF SCREENER LOGIC
# ==========================================
def fetch_and_rank_actual_us_etfs(engine):
    print("\n🇺🇸 Fetching and Ranking Actual USA ETFs...")
    url = "https://scanner.tradingview.com/america/scan"
    payload = {
        "columns": [
            "name", "close", "change", 
            "Perf.W", "Perf.1M", "Perf.3M", "Perf.6M", "Perf.Y", 
            "exchange", "average_volume_30d_calc", "EMA21", "expense_ratio"
        ],
        "filter": [
            {"left": "type", "operation": "equal", "right": "fund"},
            {"left": "Value.Traded", "operation": "greater", "right": 5000000}
        ],
        "markets": ["america"],
        "options": {"lang": "en"},
        "range": [0, 4000], 
        "sort": {"sortBy": "Perf.10Y", "sortOrder": "desc"}
    }

    try:
        response = requests.post(url, headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        rows = [item["d"] for item in data.get("data", [])]
        df = pd.DataFrame(rows, columns=[
            "Symbol", "Price (USD)", "Chg %", 
            "Perf 1W %", "Perf 1M %", "Perf 3M %", "Perf 6M %", 
            "Perf 1Y %", "Exchange", "Avg Vol 30D", "EMA 21", "Expense Ratio"
        ])
        df["Symbol"] = df["Symbol"].str.upper().str.strip()
        print(f"   📋 Retrieved {len(df)} USA ETFs from TradingView.")

        # VLOOKUP Logic from USA_ETF_Catagory
        with engine.connect() as conn:
            cat_df = pd.read_sql(text('SELECT "Symbol", "Category", "Index" FROM "USA_ETF_Catagory"'), conn)
        
        cat_df["Symbol"] = cat_df["Symbol"].astype(str).str.upper().str.strip()
        df = df.merge(cat_df, on="Symbol", how="inner")
        print(f"   🔗 Matched {len(df)} USA ETFs against Supabase category map.")

        df["EMA 21 Status"] = df.apply(
            lambda r: "Above 21 EMA" if pd.notna(r["Price (USD)"]) and pd.notna(r["EMA 21"]) and r["Price (USD)"] > r["EMA 21"]
            else ("Below 21 EMA" if pd.notna(r["Price (USD)"]) and pd.notna(r["EMA 21"]) else "N/A"), axis=1
        )
        df["Turnover (M USD)"] = (df["Price (USD)"] * df["Avg Vol 30D"] / 1_000_000).round(2)

        r1 = df["Perf 1M %"].rank(ascending=False, method="min", na_option="bottom")
        r3 = df["Perf 3M %"].rank(ascending=False, method="min", na_option="bottom")
        r6 = df["Perf 6M %"].rank(ascending=False, method="min", na_option="bottom")
        df["Relative Score"] = r1 * 2 + r3 * 4 + r6 * 4
        df["Final Rank"] = df["Relative Score"].rank(ascending=True, method="min").astype(int)
        
        cols = [
            "Final Rank", "Relative Score", "Symbol", "Category", "Index",
            "Exchange", "Price (USD)", "EMA 21", "EMA 21 Status", "Chg %", 
            "Turnover (M USD)", "Avg Vol 30D", "Expense Ratio",
            "Perf 1W %", "Perf 1M %", "Perf 3M %", "Perf 6M %", "Perf 1Y %"
        ]
        
        df = df[[c for c in cols if c in df.columns]].sort_values("Final Rank")
        return df

    except Exception as e:
        print(f"   ❌ Failed to scrape and rank USA ETFs: {e}")
        return pd.DataFrame()


# ==========================================
# 2. MAIN EXECUTION
# ==========================================
if __name__=="__main__":
    
    # ----------------------------------------
    # TIME & MARKET LOCKOUT LOGIC
    # ----------------------------------------
    now_et = pd.Timestamp.now(tz='US/Eastern')
    
    # Date alignment for proper logging
    if now_et.hour < 9:
        trading_date = now_et - pd.Timedelta(days=1)
    else:
        trading_date = now_et
        
    today_date_str = trading_date.strftime('%Y-%m-%d')
    is_weekday = trading_date.weekday() < 5
    
    # Lockout check: 9 AM to 5 PM (17:00) Eastern Time AND it must be a weekday
    is_time_locked = (9 <= now_et.hour < 17) and is_weekday
    
    # ----------------------------------------
    # RUN SCRAPERS
    # ----------------------------------------
    df_all = fetch_tradingview_etfs_all()
    usd_inr = fetch_usdinr()
    
    # PORTED US ETF PIPELINE 
    us_etfs_df = fetch_and_rank_actual_us_etfs(engine)

    # Momentum Score & Rank (US Stocks)
    r1=df_all["Perf 1M"].rank(ascending=False,method="min")
    r3=df_all["Perf 3M"].rank(ascending=False,method="min")
    r6=df_all["Perf 6M"].rank(ascending=False,method="min")
    df_all["Momentum Score"]=r1*2+r3*4+r6*4
    df_all["Momentum Rank"]=df_all["Momentum Score"].rank(ascending=True,method="min").astype(int)
    df_all["Turnover in Cr"]=(df_all["Price x Vol (1M)"]*usd_inr/1e7)
    df_all=df_all.sort_values("Momentum Rank").reset_index(drop=True)

    df_ath = fetch_tradingview_etfs_near_ath()

    summary = (
        df_all.groupby("Industry")
        .agg(
            Total_Stocks=("Symbol","count"),
            Avg_1D_Return=("Chg %","mean")
        )
        .reset_index()
    )

    ath_counts = (
        df_ath.groupby("Industry")
        .agg(ATH_Stocks=("Symbol","count"))
        .reset_index()
    )

    summary = summary.merge(ath_counts,on="Industry",how="left")
    summary["ATH_Stocks"] = summary["ATH_Stocks"].fillna(0).astype(int)
    summary["ATH %"] = (summary["ATH_Stocks"]/summary["Total_Stocks"]*100).round(2)
    summary = summary.sort_values("ATH %",ascending=False).reset_index(drop=True)
    summary["Rank"] = range(1,len(summary)+1)
    summary = summary[["Industry","Total_Stocks","ATH_Stocks","ATH %","Rank","Avg_1D_Return"]]

    sector_summary=(df_all.groupby("Sector").agg(Total_Stocks=("Symbol","count"),Avg_1D_Return=("Chg %","mean")).reset_index())
    sector_ath=(df_ath.groupby("Sector").agg(ATH_Stocks=("Symbol","count")).reset_index())
    sector_summary=sector_summary.merge(sector_ath,on="Sector",how="left")
    sector_summary["ATH_Stocks"]=sector_summary["ATH_Stocks"].fillna(0).astype(int)
    sector_summary["ATH %"]=(sector_summary["ATH_Stocks"]/sector_summary["Total_Stocks"]*100).round(2)
    sector_summary=sector_summary.sort_values("ATH %",ascending=False).reset_index(drop=True)
    sector_summary["Rank"]=range(1,len(sector_summary)+1)
    sector_summary=sector_summary[["Sector","Total_Stocks","ATH_Stocks","ATH %","Rank","Avg_1D_Return"]]

    # ----------------------------------------
    # ADVANCED HOLIDAY / MARKET BREADTH ENGINE
    # ----------------------------------------
    is_us_holiday = False
    
    if is_weekday:
        # Variance Check: Are prices completely frozen?
        if 'Chg %' in df_all.columns:
            chg_variance = float(df_all["Chg %"].var())
            
            if pd.isna(chg_variance) or chg_variance == 0.0 or (df_all["Chg %"] == 0.0).mean() > 0.95:
                is_us_holiday = True
                is_time_locked = False # Override the time lock so the database can update safely
                print("\n🛑 WEEKEND/HOLIDAY DETECTED: Market price variance is zero or completely stagnant.")
                
        # Existing Log Check
        already_logged = False
        try:
            with engine.connect() as conn:
                existing = pd.read_sql(text(f'SELECT * FROM "US historical_market_mood" WHERE "Date" = \'{today_date_str}\''), conn)
                if not existing.empty:
                    already_logged = True
        except Exception:
            pass

        if not is_us_holiday and not already_logged:
            positive=(df_all["Chg %"]>0).sum()
            breadth=round((positive/len(df_all))*100,2)
            pct=f"{breadth:.2f}%"
            if breadth<=20:
                mood=f"Super Negative 🐻 {pct}"
            elif breadth<=35:
                mood=f"Negative 🔻 {pct}"
            elif breadth<=50:
                mood=f"Neutral ⚖️ {pct}"
            elif breadth<=65:
                mood=f"Positive 💚 {pct}"
            else:
                mood=f"Super Positive 🚀 {pct}"
            
            breadth_df=pd.DataFrame({"Date":[today_date_str],"Market Breadth":[mood]})
            print(f"\n📊 Today's Breadth calculated: {mood}")
        else:
            breadth_df = pd.DataFrame()
            if already_logged:
                print(f"\n⏸️ Market mood for {today_date_str} already logged. Skipping duplicate.")
    else:
        is_us_holiday = True
        breadth_df = pd.DataFrame()
        print("\n⏸️ Today is a weekend. Skipping market mood calculations.")


    # Round all numeric columns to 2 decimals safely
    dfs_to_round = [df_all, df_ath, summary, sector_summary, us_etfs_df]
    if not breadth_df.empty:
        dfs_to_round.append(breadth_df)
        
    for _df in dfs_to_round:
        if not _df.empty:
            num=_df.select_dtypes(include="number").columns
            _df[num]=_df[num].round(2)

    sync_log=pd.DataFrame({"last_sync":[pd.Timestamp.now(tz='US/Eastern').strftime("%d %b %Y, %I:%M %p ET")],"status":["SUCCESS"],"failed_module":["None"]})

    # ==========================================
    # 3. PUSH TO SUPABASE (TIME LOCKED)
    # ==========================================
    if is_time_locked:
        print("\n⏸️ US Market is currently OPEN (9 AM - 5 PM ET).")
        print("⏸️ Database writing is strictly LOCKED to prevent mid-day fragmentation.")
        print("\n" + "="*60)
        print("⚠️ SCRAPE SUCCESSFUL, BUT NO DB WRITES EXECUTED.")
        print("="*60 + "\n")
        
    else:
        print("\n📦 Pushing data to Supabase...")

        # Main Screener Tables
        save_db_with_retry(df_all, "US Stock screener", engine, if_exists="replace", index=False, chunksize=500, method='multi')
        print("   ✅ 'US Stock screener' updated successfully.")

        save_db_with_retry(df_ath, "US ATH screeener", engine, if_exists="replace", index=False, chunksize=500, method='multi')
        print("   ✅ 'US ATH screeener' updated successfully.")

        # Actual US ETF Screener
        if not us_etfs_df.empty:
            save_db_with_retry(us_etfs_df, "USA_ETF_Screener", engine, if_exists="replace", index=False)
            print("   ✅ 'USA_ETF_Screener' updated successfully.")

        # Industry and Sector Analysis
        save_db_with_retry(summary, "US Industry Analysis", engine, if_exists="replace", index=False)
        print("   ✅ 'US Industry Analysis' updated successfully.")

        save_db_with_retry(sector_summary, "USA Sector Analysis", engine, if_exists="replace", index=False)
        print("   ✅ 'USA Sector Analysis' updated successfully.")

        # Historical Mood (Append)
        if not breadth_df.empty and not is_us_holiday:
            save_db_with_retry(breadth_df, "US historical_market_mood", engine, if_exists="append", index=False)
            print("   ✅ 'US historical_market_mood' updated successfully.")

        # Sync Log (Replace)
        save_db_with_retry(sync_log, "US Sync log", engine, if_exists="replace", index=False)
        print("   ✅ 'US Sync log' updated successfully.")

        print("\n" + "="*60)
        print("🎉 SUCCESS: USA Data synced to Supabase!")
        print("="*60 + "\n")
