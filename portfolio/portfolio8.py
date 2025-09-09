import streamlit as st
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import date
import io
import requests

# ========== 設定 ==========
FX_TO_JPY = {"USD": 155.0, "JPY": 1.0}   # 為替レート
FEE_RATE = 0.00495  # 手数料率 0.495%

# GitHub CSV（公開リポジトリの Raw URL を指定）
PORTFOLIO_CSV_URL = "https://raw.githubusercontent.com/hayatonn/family_portfolio/refs/heads/main/portfolio/portfolio.csv"
TRADES_CSV_URL    = "https://raw.githubusercontent.com/hayatonn/family_portfolio/refs/heads/main/portfolio/trades.csv"

# ========== 関数 ==========
def fetch_csv_from_github(url):
    try:
        r = requests.get(url)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text), encoding="utf-8")
        df.columns = df.columns.str.strip().str.replace("　", "")  # 列名クリーン
        return df
    except Exception as e:
        st.warning(f"GitHub CSV取得失敗: {e}")
        return pd.DataFrame()

def guess_currency(ticker: str) -> str:
    if ticker.endswith(".T"):
        return "JPY"
    return "USD"

def load_prices_and_sector(tickers):
    prices, sectors = {}, {}
    for t in tickers:
        try:
            ticker = yf.Ticker(t)
            hist = ticker.history(period="5d")
            prices[t] = float(hist["Close"].dropna().iloc[-1])
            sectors[t] = ticker.info.get("sector", "Unknown")
        except Exception:
            prices[t] = None
            sectors[t] = "Unknown"
    return prices, sectors

def calculate_portfolio(df):
    df.columns = df.columns.str.strip().str.replace("　", "")
    tickers_stock = df[df["asset_type"]=="stock"]["ticker"].unique()
    prices, sectors = load_prices_and_sector(tickers_stock)

    df["currency"] = df.get("currency", df["ticker"].map(guess_currency))
    df["fee"] = 0

    mask_stock = df["asset_type"]=="stock"
    df.loc[mask_stock, "fee"] = df.loc[mask_stock, "buy_price"] * df.loc[mask_stock, "shares"] * FEE_RATE

    df["prev_close"] = df["ticker"].map(prices)
    df["sector"] = df.get("sector", df["ticker"].map(lambda t: sectors.get(t, "Cash")))

    df["market_value"] = 0
    df["cost_basis"]  = 0
    df.loc[mask_stock, "market_value"] = df.loc[mask_stock, "shares"] * df.loc[mask_stock, "prev_close"]
    df.loc[mask_stock, "cost_basis"]  = df.loc[mask_stock, "shares"] * df.loc[mask_stock, "buy_price"] + df.loc[mask_stock, "fee"]

    mask_cash = df["asset_type"]=="cash"
    df.loc[mask_cash, "market_value"] = df.loc[mask_cash, "shares"]
    df.loc[mask_cash, "cost_basis"]  = df.loc[mask_cash, "shares"]

    df["pnl_abs"] = df["market_value"] - df["cost_basis"]
    df["pnl_pct"] = df["pnl_abs"] / df["cost_basis"] * 100

    df["fx_to_jpy"] = df["currency"].map(FX_TO_JPY).fillna(1.0)
    df["mv_jpy"]    = df["market_value"] * df["fx_to_jpy"]
    df["cost_jpy"]  = df["cost_basis"]   * df["fx_to_jpy"]
    df["pnl_jpy"]   = df["mv_jpy"] - df["cost_jpy"]

    total_pnl = df["pnl_jpy"].sum()
    df["pnl_contrib"] = df["pnl_jpy"] / total_pnl * 100 if total_pnl != 0 else 0

    return df

def load_history(df_portfolio, df_trades=None, period="6mo"):
    history = pd.DataFrame()
    for _, row in df_portfolio.iterrows():
        if row["asset_type"]=="stock":
            try:
                hist = yf.download(row["ticker"], period=period)["Close"]
                if row["currency"]=="USD":
                    hist_val = hist * row["shares"] * FX_TO_JPY["USD"]
                else:
                    hist_val = hist * row["shares"]
                history[row["ticker"]] = hist_val
            except Exception:
                continue
    history["Total"] = history.sum(axis=1)

    # 現金加算
    for _, row in df_portfolio[df_portfolio["asset_type"]=="cash"].iterrows():
        if row["currency"]=="USD":
            history["Total"] += row["shares"] * FX_TO_JPY["USD"]
        else:
            history["Total"] += row["shares"]

    # 売買履歴
    if df_trades is not None and not df_trades.empty:
        if "type" not in df_trades.columns:
            st.error("❌ trades.csv に 'type' 列がありません。列名を確認してください。")
            st.write("読み込んだ trades.csv の列:", df_trades.columns.tolist())
        else:
            df_trades["date"] = pd.to_datetime(df_trades["date"])
            for _, trade in df_trades.iterrows():
                trade_date = trade["date"]
                if trade_date in history.index:
                    mult = 1 if str(trade["type"]).strip().lower() == "buy" else -1
                    if trade["currency"]=="USD":
                        history.loc[trade_date, "Total"] += trade["shares"] * FX_TO_JPY["USD"] * mult
                    else:
                        history.loc[trade_date, "Total"] += trade["shares"] * mult

    return history

# ========== Streamlit UI ==========
st.set_page_config(page_title="ポートフォリオ管理", layout="wide")
st.title("📊 家族で共有できる資産管理アプリ")

# CSVアップロード or GitHub取得
uploaded_portfolio = st.file_uploader("ポートフォリオCSVをアップロード", type=["csv"])
uploaded_trades    = st.file_uploader("売買履歴CSVをアップロード", type=["csv"])

if uploaded_portfolio:
    df_portfolio = pd.read_csv(uploaded_portfolio, encoding="utf-8-sig")
    df_portfolio.columns = df_portfolio.columns.str.strip().str.replace("　","")
else:
    df_portfolio = fetch_csv_from_github(PORTFOLIO_CSV_URL)

if uploaded_trades:
    df_trades = pd.read_csv(uploaded_trades, encoding="utf-8-sig")
    df_trades.columns = df_trades.columns.str.strip().str.replace("　","")
else:
    df_trades = fetch_csv_from_github(TRADES_CSV_URL)

df_portfolio = calculate_portfolio(df_portfolio)

# 銘柄別集計
st.subheader("銘柄別集計")
st.dataframe(df_portfolio[[
    "ticker","asset_type","shares","buy_price","prev_close",
    "market_value","pnl_abs","pnl_pct",
    "mv_jpy","pnl_jpy","pnl_contrib","sector"
]])

# セクター別寄与度
st.subheader("セクター別寄与度")
sector_df = df_portfolio.groupby("sector").agg(
    mv_jpy=("mv_jpy","sum"),
    pnl_jpy=("pnl_jpy","sum")
).reset_index()
total_pnl = df_portfolio["pnl_jpy"].sum()
sector_df["pnl_contrib"] = sector_df["pnl_jpy"] / total_pnl * 100
st.dataframe(sector_df)

# 合計
st.subheader("合計")
st.metric("評価額合計 (JPY)", f"{df_portfolio['mv_jpy'].sum():,.0f}")
st.metric("含み損益 (JPY)", f"{df_portfolio['pnl_jpy'].sum():,.0f}")

# 円グラフ（株＋現金）
st.subheader("資産別寄与度（円グラフ）")
latest_assets = df_portfolio.groupby("ticker")["mv_jpy"].sum()
fig, ax = plt.subplots()
ax.pie(latest_assets.values, labels=latest_assets.index, autopct="%1.1f%%", startangle=90)
ax.set_title("資産寄与度")
st.pyplot(fig)

# セクター円グラフ
st.subheader("セクター別資産比率")
sector_assets = df_portfolio.groupby("sector")["mv_jpy"].sum()
fig2, ax2 = plt.subplots()
ax2.pie(sector_assets.values, labels=sector_assets.index, autopct="%1.1f%%", startangle=90)
ax2.set_title("セクター別資産比率")
st.pyplot(fig2)

# 総資産推移
st.subheader("総資産推移（過去6か月）")
history = load_history(df_portfolio, df_trades=df_trades, period="6mo")
st.line_chart(history["Total"])
