import os
import sys
import time
import requests
import pandas as pd
from sqlalchemy import create_engine

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
    raise Exception(f"Failed to save {table_name} to database after 3 attempts.")


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

    print("\nFetching ETF data from TradingView...")
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
    rows=processed

    df = pd.DataFrame(rows, columns=[
        "Symbol","Price (USD)","Chg %","Market Cap","Sector","Industry","Exchange","Perf 1W","Perf 1M","Perf 3M","Perf 6M","Perf 1Y","Price x Vol (1M)"
    ])

    print("-" * 50)
    print(f"Success! Downloaded {len(df)} ETFs.")
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
# 2. MAIN EXECUTION
# ==========================================
if __name__=="__main__":
    
    df_all = fetch_tradingview_etfs_all()
    usd_inr = fetch_usdinr()

    # Momentum Score & Rank
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
    breadth_df=pd.DataFrame({"Date":[pd.Timestamp.now().strftime("%Y-%m-%d")],"Market Breadth":[mood]})

    # Round all numeric columns to 2 decimals
    for _df in [df_all, df_ath, summary, sector_summary, breadth_df]:
        num=_df.select_dtypes(include="number").columns
        _df[num]=_df[num].round(2)

    sync_log=pd.DataFrame({"last_sync":[pd.Timestamp.now().strftime("%d %b %Y, %I:%M %p")],"status":["SUCCESS"],"failed_module":["None"]})

    # ==========================================
    # 3. PUSH TO SUPABASE
    # ==========================================
    print("\n📦 Pushing data to Supabase...")

    # Main Screener Tables (Replace)
    save_db_with_retry(df_all, "US Stock screener", engine, if_exists="replace", index=False, chunksize=500, method='multi')
    print("   ✅ 'US Stock screener' updated successfully.")

    save_db_with_retry(df_ath, "US ATH screeener", engine, if_exists="replace", index=False, chunksize=500, method='multi')
    print("   ✅ 'US ATH screeener' updated successfully.")

    # Industry and Sector Analysis (Replace)
    save_db_with_retry(summary, "US Industry Analysis", engine, if_exists="replace", index=False)
    print("   ✅ 'US Industry Analysis' updated successfully.")

    save_db_with_retry(sector_summary, "USA Sector Analysis", engine, if_exists="replace", index=False)
    print("   ✅ 'USA Sector Analysis' updated successfully.")

    # Historical Mood (Append)
    save_db_with_retry(breadth_df, "US historical_market_mood", engine, if_exists="append", index=False)
    print("   ✅ 'US historical_market_mood' updated successfully.")

    # Sync Log (Replace)
    save_db_with_retry(sync_log, "US Sync log", engine, if_exists="replace", index=False)
    print("   ✅ 'US Sync log' updated successfully.")

    print("\n" + "="*60)
    print("🎉 SUCCESS: USA ETF Data synced to Supabase!")
    print("="*60 + "\n")
