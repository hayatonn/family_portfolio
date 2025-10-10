import streamlit as st
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import date
import io
import requests

# ========== 為替自動取得関数 ==========
def get_usd_to_jpy():
    """Yahoo Financeから最新USD/JPYレートを取得。失敗時は155円にフォールバック。"""
    try:
        rate = yf.Ticker("USDJPY=X").history(period="1d")["Close"].iloc[-1]
        return float(rate)
    except Exception as e:
        st.warning(f"為替取得失敗。155円を使用します。詳細: {e}")
        return 155.0

# 為替レート辞書
FX_TO_JPY = {"USD": get_usd_to_jpy(), "JPY": 1.0}

# ========== 設定 ==========
FEE_RATE = 0.00495  # 手数料率 0.495%

PORTFOLIO_CSV_URL = "https://raw.githubusercontent.com/hayatonn/family_portfolio/refs/heads/main/portfolio/portfolio.csv"
TRADES_CSV_URL    = "https://raw.githubusercontent.com/hayatonn/family_portfolio/refs/heads/main/portfolio/trades.csv"

# ========== 関数 ==========
def fetch_csv_from_github(url):
    try:
        r = requests.get(url)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text), encoding="utf-8")
        df.columns = df.columns.str.strip().str.replace("　", "")
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

            if t.endswith("-USD"):
                sectors[t] = "Crypto"
            else:
                info = getattr(ticker, "info", {})
                if isinstance(info, dict):
                    sectors[t] = info.get("sector", "Unknown")
                else:
                    sectors[t] = "Unknown"
        except Exception:
            prices[t] = None
            sectors[t] = "Unknown"
    return prices, sectors

def calculate_portfolio(df):
    df.columns = df.columns.str.strip().str.replace("　", "")

    tickers_target = df[df["asset_type"].isin(["stock","crypto"])]["ticker"].unique()
    prices, sectors = load_prices_and_sector(tickers_target)

    df["currency"] = df.get("currency", df["ticker"].map(guess_currency))
    df["fee"] = 0

    mask_equity = df["asset_type"].isin(["stock","crypto"])
    df.loc[mask_equity, "fee"] = df.loc[mask_equity, "buy_price"] * df.loc[mask_equity, "shares"] * FEE_RATE

    df["prev_close"] = df["ticker"].map(prices)
    df["sector"] = df.get("sector", df["ticker"].map(lambda t: sectors.get(t, "Cash")))

    df["market_value"] = 0
    df["cost_basis"]  = 0
    df.loc[mask_equity, "market_value"] = df.loc[mask_equity, "shares"] * df.loc[mask_equity, "prev_close"]
    df.loc[mask_equity, "cost_basis"]  = df.loc[mask_equity, "shares"] * df.loc[mask_equity, "buy_price"] + df.loc[mask_equity, "fee"]

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
    df["pnl_over_mv_pct"] = df["pnl_jpy"] / df["mv_jpy"] * 100

    # もし確定損益列があれば取得
    if "realized_pnl_jpy" not in df.columns:
        df["realized_pnl_jpy"] = 0.0

    return df

# ========== Streamlit UI ==========
st.set_page_config(page_title="ポートフォリオ管理", layout="wide")
st.title("📊 家族で共有できる資産管理アプリ")

# ファイル入力
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

# 計算
df_portfolio = calculate_portfolio(df_portfolio)

# 為替レート表示
st.info(f"💱 現在のUSD/JPYレート: {FX_TO_JPY['USD']:.2f}")

# 銘柄別集計
st.subheader("銘柄別集計")
total_pnl = df_portfolio["pnl_jpy"].sum()
df_portfolio["pnl_ratio_pct"] = df_portfolio["pnl_jpy"] / total_pnl * 100 if total_pnl != 0 else 0

st.dataframe(df_portfolio[[
    "ticker","asset_type","shares","buy_price","prev_close",
    "market_value","pnl_abs","pnl_pct",
    "mv_jpy","pnl_jpy","pnl_ratio_pct","pnl_over_mv_pct","sector"
]])

# セクター別寄与度
st.subheader("セクター別寄与度")
sector_df = df_portfolio.groupby("sector").agg(
    mv_jpy=("mv_jpy","sum"),
    pnl_jpy=("pnl_jpy","sum")
).reset_index()

sector_df["mv_contrib_pct"] = sector_df["mv_jpy"] / sector_df["mv_jpy"].sum() * 100
sector_df["pnl_ratio_pct"] = sector_df["pnl_jpy"] / total_pnl * 100 if total_pnl != 0 else 0
sector_df["pnl_over_mv_pct"] = sector_df["pnl_jpy"] / sector_df["mv_jpy"] * 100

st.dataframe(sector_df)

# 合計表示（確定損益対応）
st.subheader("合計")
total_mv = df_portfolio["mv_jpy"].sum()
total_unrealized = df_portfolio["pnl_jpy"].sum()
total_realized = df_portfolio["realized_pnl_jpy"].sum()

st.metric("評価額合計 (JPY)", f"{total_mv:,.0f}")
st.metric("含み損益 (JPY)", f"{total_unrealized:,.0f}")
st.metric("確定損益 (JPY)", f"{total_realized:,.0f}")
st.metric("総損益 (JPY)", f"{total_unrealized + total_realized:,.0f}")

# 資産構成グラフ
st.subheader("資産別寄与度（円グラフ）")
latest_assets = df_portfolio.groupby("ticker")["mv_jpy"].sum()
fig, ax = plt.subplots()
ax.pie(latest_assets.values, labels=latest_assets.index, autopct="%1.1f%%", startangle=90)
ax.set_title("stock_ratio")
st.pyplot(fig)

st.subheader("セクター別資産比率")
sector_assets = df_portfolio.groupby("sector")["mv_jpy"].sum()
fig2, ax2 = plt.subplots()
ax2.pie(sector_assets.values, labels=sector_assets.index, autopct="%1.1f%%", startangle=90)
ax2.set_title("sector_ratio")
st.pyplot(fig2)
