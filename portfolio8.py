#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import streamlit as st
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# ================= 設定 =================
FX_TO_JPY = {"USD": 155.0, "JPY": 1.0}  # 為替レート（手動更新）
FEE_RATE = 0.0045  # 株式売買手数料率

# ================= 関数 =================
def guess_currency(ticker: str) -> str:
    if ticker.endswith(".T"):
        return "JPY"
    return "USD"

def load_prices_and_sector(tickers):
    prices, sectors = {}, {}
    for t in tickers:
        try:
            hist = yf.Ticker(t).history(period="1d")["Close"]
            prices[t] = hist.iloc[-1]
            sectors[t] = yf.Ticker(t).info.get("sector", "Unknown")
        except:
            prices[t] = None
            sectors[t] = "Unknown"
    return prices, sectors

def apply_trades(df_portfolio, df_trades):
    """売買履歴を反映した日次資産推移を作成"""
    df_trades["date"] = pd.to_datetime(df_trades["date"])
    df_trades = df_trades.sort_values("date")

    start = df_trades["date"].min() - timedelta(days=1)
    end = datetime.today()
    dates = pd.date_range(start=start, end=end, freq="D")

    holdings = {}
    for _, row in df_portfolio.iterrows():
        holdings[row["ticker"]] = row["shares"]

    history = []
    for d in dates:
        trades_today = df_trades[df_trades["date"] == d]
        for _, trade in trades_today.iterrows():
            ticker = trade["ticker"]
            qty = trade["shares"]
            if trade["action"] == "buy":
                holdings[ticker] = holdings.get(ticker, 0) + qty
            elif trade["action"] == "sell":
                holdings[ticker] = holdings.get(ticker, 0) - qty

        total_value = 0
        for ticker, qty in holdings.items():
            if qty == 0:
                continue
            row = df_portfolio[df_portfolio["ticker"]==ticker].iloc[0]
            if row["asset_type"] == "stock":
                try:
                    price = yf.Ticker(ticker).history(period="1d")["Close"].iloc[-1]
                    currency = row["currency"]
                    total_value += price * FX_TO_JPY.get(currency,1) * qty
                except:
                    pass
            else:
                currency = row["currency"]
                total_value += qty * FX_TO_JPY.get(currency,1)
        history.append(total_value)

    return pd.Series(history, index=dates)

# ================= Streamlit UI =================
st.title("📊 資産管理アプリ（売買履歴＆セクター表示）")

uploaded_portfolio = st.file_uploader("ポートフォリオCSVをアップロード", type=["csv"])
uploaded_trades = st.file_uploader("売買履歴CSVをアップロード", type=["csv"])

if uploaded_portfolio:
    df_portfolio = pd.read_csv(uploaded_portfolio)
    df_portfolio.columns = df_portfolio.columns.str.strip()
    
    # 株式の最新価格・セクター
    tickers_stock = df_portfolio[df_portfolio["asset_type"]=="stock"]["ticker"].tolist()
    prices, sectors = load_prices_and_sector(tickers_stock)
    df_portfolio["prev_close"] = df_portfolio["ticker"].map(prices)
    df_portfolio["sector"] = df_portfolio["ticker"].map(lambda t: sectors.get(t, "Cash"))

    # 円グラフ（資産内訳）
    df_portfolio["mv_jpy"] = df_portfolio.apply(
        lambda r: r["shares"]*r["prev_close"]*FX_TO_JPY.get(r["currency"],1) if r["asset_type"]=="stock" else r["shares"]*FX_TO_JPY.get(r["currency"],1),
        axis=1
    )

    st.subheader("銘柄別ポートフォリオ")
    st.dataframe(df_portfolio[["ticker","asset_type","shares","prev_close","mv_jpy","sector"]])

    st.subheader("資産内訳（円換算）")
    fig, ax = plt.subplots()
    ax.pie(df_portfolio["mv_jpy"], labels=df_portfolio["ticker"], autopct="%1.1f%%", startangle=90)
    st.pyplot(fig)

    # セクター別集計
    st.subheader("セクター別集計")
    sector_df = df_portfolio.groupby("sector").agg(
        mv_jpy=("mv_jpy","sum")
    ).reset_index()
    st.dataframe(sector_df)

    st.subheader("セクター別円グラフ")
    fig2, ax2 = plt.subplots()
    ax2.pie(sector_df["mv_jpy"], labels=sector_df["sector"], autopct="%1.1f%%", startangle=90)
    st.pyplot(fig2)

    # 売買履歴反映
    if uploaded_trades:
        df_trades = pd.read_csv(uploaded_trades)
        df_trades.columns = df_trades.columns.str.strip()
        asset_history = apply_trades(df_portfolio, df_trades)
        st.subheader("日次総資産推移")
        st.line_chart(asset_history)

