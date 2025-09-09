import streamlit as st
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import io, requests

# ========== 設定 ==========
FX_TO_JPY = {"USD": 155.0, "JPY": 1.0}   # 為替レート
FEE_RATE = 0.00495  # 手数料率 0.495%

PORTFOLIO_CSV_URL = "https://raw.githubusercontent.com/<username>/<repo>/main/portfolio/portfolio.csv"
TRADES_CSV_URL    = "https://raw.githubusercontent.com/<username>/<repo>/main/portfolio/trades.csv"

# ========== 関数 ==========
def fetch_csv_from_github(url):
    try:
        r = requests.get(url)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text), encoding="utf-8")
        df.columns = df.columns.str.strip().str.replace("　","")  # 列名クリーニング
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
    required_cols = {"ticker","asset_type","shares","buy_price","currency"}
    if not required_cols.issubset(df.columns):
        st.error(f"CSVに必要な列が不足しています: {required_cols - set(df.columns)}")
        return pd.DataFrame()

    tickers_stock = df[df["asset_type"]=="stock"]["ticker"].unique()
    prices, sectors = load_prices_and_sector(tickers_stock)

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

# ========== Streamlit UI ==========
st.set_page_config(page_title="ポートフォリオ管理", layout="wide")
st.title("📊 家族で共有できる資産管理アプリ")

uploaded_portfolio = st.file_uploader("ポートフォリオCSVをアップロード", type=["csv"])
uploaded_trades    = st.file_uploader("売買履歴CSVをアップロード", type=["csv"])

# --- CSV読み込み ---
if uploaded_portfolio:
    df_portfolio = pd.read_csv(uploaded_portfolio, encoding="utf-8")
    df_portfolio.columns = df_portfolio.columns.str.strip().str.replace("　","")
else:
    df_portfolio = fetch_csv_from_github(PORTFOLIO_CSV_URL)

if uploaded_trades:
    df_trades = pd.read_csv(uploaded_trades, encoding="utf-8")
    df_trades.columns = df_trades.columns.str.strip().str.replace("　","")
else:
    df_trades = fetch_csv_from_github(TRADES_CSV_URL)

if not df_portfolio.empty:
    df_portfolio = calculate_portfolio(df_portfolio)

    # --- 銘柄別集計 ---
    st.subheader("銘柄別集計")
    st.dataframe(df_portfolio)

    # --- セクター別集計 ---
    st.subheader("セクター別集計")
    sector_df = df_portfolio.groupby("sector").agg(
        mv_jpy=("mv_jpy","sum"),
        pnl_jpy=("pnl_jpy","sum")
    ).reset_index()
    total_pnl = df_portfolio["pnl_jpy"].sum()
    sector_df["pnl_contrib"] = sector_df["pnl_jpy"] / total_pnl * 100
    st.dataframe(sector_df)

    # --- 円グラフ（銘柄別） ---
    st.subheader("資産別寄与度（円グラフ）")
    latest_assets = df_portfolio.groupby("ticker")["mv_jpy"].sum()
    fig, ax = plt.subplots()
    ax.pie(latest_assets.values, labels=latest_assets.index, autopct="%1.1f%%", startangle=90)
    st.pyplot(fig)

    # --- 円グラフ（セクター別） ---
    st.subheader("セクター別資産比率")
    sector_assets = df_portfolio.groupby("sector")["mv_jpy"].sum()
    fig2, ax2 = plt.subplots()
    ax2.pie(sector_assets.values, labels=sector_assets.index, autopct="%1.1f%%", startangle=90)
    st.pyplot(fig2)

    # --- 合計表示 ---
    st.subheader("合計")
    st.metric("評価額合計 (JPY)", f"{df_portfolio['mv_jpy'].sum():,.0f}")
    st.metric("含み損益 (JPY)", f"{df_portfolio['pnl_jpy'].sum():,.0f}")





