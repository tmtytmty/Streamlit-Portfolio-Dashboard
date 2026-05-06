from datetime import datetime, timedelta
import re

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf


# ============================================================
# Config
# ============================================================

PRICE_CACHE_SECONDS = 300
SHEET_CACHE_SECONDS = 300

INITIAL_INVESTMENT = 100
FIXED_WARMUP_DAYS = 14

CASH_TICKERS = {"CASH", "USD", "USDT-USD"}

st.set_page_config(
    page_title="Portfolio Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Portfolio Dashboard")


# ============================================================
# Google Sheet input
# ============================================================

def parse_google_sheet_input(sheet_input):
    """
    Accepts either a full Google Sheets URL or a raw Google Sheet ID.

    Examples:
    - https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit#gid=0
    - <SHEET_ID>
    """
    sheet_input = str(sheet_input).strip()

    if not sheet_input:
        return None, None

    gid = "0"

    gid_match = re.search(r"[#&?]gid=([0-9]+)", sheet_input)
    if gid_match:
        gid = gid_match.group(1)

    sheet_id_match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", sheet_input)
    if sheet_id_match:
        return sheet_id_match.group(1), gid

    # If it is not a URL, treat it as a raw Sheet ID.
    if re.fullmatch(r"[a-zA-Z0-9-_]+", sheet_input):
        return sheet_input, gid

    return None, None


st.caption(
    "Paste a Google Sheets link or Sheet ID. "
    "The sheet must be shared as **Anyone with the link can view** so the app can read the CSV export."
)

sheet_input = st.text_input(
    "Google Sheet link or ID",
    placeholder="https://docs.google.com/spreadsheets/d/...",
)

sheet_id, gid = parse_google_sheet_input(sheet_input)

if not sheet_input:
    st.info("Paste a Google Sheet link to load a portfolio dashboard.")
    st.stop()

if sheet_id is None:
    st.error("That does not look like a valid Google Sheets link or Sheet ID.")
    st.stop()


# ============================================================
# General helpers
# ============================================================

def clean_column_name(col):
    return str(col).replace("\xa0", " ").strip()


def clean_text(series):
    return (
        series
        .astype(str)
        .str.replace("\xa0", " ", regex=False)
        .str.strip()
    )


def clean_position(series):
    return pd.to_numeric(
        series
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.strip(),
        errors="coerce",
    ).fillna(0)


def clean_percentage_column(series):
    cleaned = (
        series
        .astype(str)
        .str.replace("%", "", regex=False)
        .str.replace("Free", "", regex=False)
        .str.replace("free", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )

    result = pd.to_numeric(cleaned, errors="coerce")
    result = result.apply(lambda x: x / 100 if pd.notna(x) and x > 1 else x)

    return result


def format_usd(value):
    if pd.isna(value):
        return "-"
    return f"${value:,.0f}"


def format_number(value):
    if pd.isna(value):
        return "-"
    return f"{value:,.2f}"


def format_pct(value):
    if pd.isna(value):
        return "-"
    return f"{value:.1%}"


def format_pct_2(value):
    if pd.isna(value):
        return "-"
    return f"{value:.2%}"


def format_display_percent_columns(df, percent_cols):
    display_df = df.copy()

    for col in percent_cols:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(format_pct_2)

    return display_df


def combine_cash_rows(df):
    """
    Combines cash holdings into one display row.
    Use this for portfolio-level views, but not broker-level aggregation.
    """
    if df.empty:
        return df.copy()

    data = df.copy()
    cash_mask = (
        data["Category"].astype(str).str.lower().eq("cash")
        | data["Ticker"].astype(str).str.upper().isin(CASH_TICKERS)
    )

    cash_rows = data[cash_mask].copy()
    non_cash_rows = data[~cash_mask].copy()

    if cash_rows.empty:
        return data.copy()

    cash_value_usd = cash_rows["Market Value USD"].sum(skipna=True)
    cash_position = cash_rows["Position"].sum(skipna=True)

    cash_row = {
        "Ticker": "Cash",
        "Currency": "USD",
        "Category": "Cash",
        "Broker": "Multiple" if cash_rows["Broker"].nunique() > 1 else cash_rows["Broker"].iloc[0],
        "Position": cash_position,
        "Live Price": 1.0,
        "Yahoo Currency": "USD",
        "Adjusted Price": 1.0,
        "Pricing Currency": "USD",
        "FX to USD": 1.0,
        "Market Value Local": cash_value_usd,
        "Market Value USD": cash_value_usd,
        "Thesis / catalysts": "",
        "Notes": "Combined cash holdings",
        "Max allocation": np.nan,
        "Don't add above": np.nan,
        "Max allocation headroom": np.nan,
        "Don't-add headroom": np.nan,
        "Above max allocation": False,
        "Above don't-add threshold": False,
        "Price Error": None,
        "FX Error": None,
    }

    combined = pd.concat(
        [non_cash_rows, pd.DataFrame([cash_row])],
        ignore_index=True,
    )

    total_value = combined["Market Value USD"].sum(skipna=True)

    if total_value > 0:
        combined["Exposure"] = combined["Market Value USD"] / total_value
    else:
        combined["Exposure"] = np.nan

    if "Filtered Exposure" in data.columns:
        filtered_value = combined["Market Value USD"].sum(skipna=True)
        if filtered_value > 0:
            combined["Filtered Exposure"] = combined["Market Value USD"] / filtered_value
        else:
            combined["Filtered Exposure"] = np.nan

    combined = combined.sort_values(
        "Market Value USD",
        ascending=False,
        na_position="last",
    ).reset_index(drop=True)

    return combined


# ============================================================
# Load Google Sheet
# ============================================================

@st.cache_data(ttl=SHEET_CACHE_SECONDS)
def load_google_sheet(sheet_id, gid="0"):
    csv_url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export"
        f"?format=csv&gid={gid}"
    )

    df = pd.read_csv(csv_url)
    df.columns = [clean_column_name(c) for c in df.columns]

    return df


# ============================================================
# Market data helpers
# ============================================================

@st.cache_data(ttl=PRICE_CACHE_SECONDS)
def get_latest_price_and_currency(ticker):
    ticker = str(ticker).strip()

    if ticker.upper() in CASH_TICKERS:
        return 1.0, "USD", None

    try:
        asset = yf.Ticker(ticker)
        info = asset.fast_info

        price = info.get("last_price", None)
        currency = info.get("currency", None)

        if price is None or pd.isna(price):
            hist = asset.history(period="5d")

            if hist.empty or hist["Close"].dropna().empty:
                return np.nan, None, "No recent price history found"

            price = hist["Close"].dropna().iloc[-1]

        if currency is None:
            currency = "USD"

        return float(price), currency, None

    except Exception as e:
        return np.nan, None, str(e)


@st.cache_data(ttl=PRICE_CACHE_SECONDS)
def get_fx_to_usd(currency):
    currency = str(currency).upper().strip()

    if currency in ["USD", "", "NAN", "NONE"]:
        return 1.0, None

    try:
        pair = f"{currency}USD=X"
        hist = yf.Ticker(pair).history(period="5d")

        if hist.empty or hist["Close"].dropna().empty:
            return np.nan, "No recent FX history found"

        fx = hist["Close"].dropna().iloc[-1]

        return float(fx), None

    except Exception as e:
        return np.nan, str(e)


# ============================================================
# Portfolio calculation
# ============================================================

def build_portfolio(raw_df):
    portfolio = raw_df.copy()
    portfolio.columns = [clean_column_name(c) for c in portfolio.columns]

    required_columns = [
        "Ticker",
        "Currency",
        "Category",
        "Broker",
        "Position",
        "Max allocation",
        "Don't add above",
    ]

    missing = [col for col in required_columns if col not in portfolio.columns]

    if missing:
        raise ValueError(f"Missing required columns in Google Sheet: {missing}")

    portfolio = portfolio[
        portfolio["Ticker"].astype(str).str.strip() != ""
    ].copy()

    portfolio["Ticker"] = clean_text(portfolio["Ticker"])
    portfolio["Currency"] = clean_text(portfolio["Currency"]).str.upper()
    portfolio["Category"] = clean_text(portfolio["Category"])
    portfolio["Broker"] = clean_text(portfolio["Broker"])
    portfolio["Position"] = clean_position(portfolio["Position"])

    portfolio["Max allocation"] = clean_percentage_column(
        portfolio["Max allocation"]
    )

    portfolio["Don't add above"] = clean_percentage_column(
        portfolio["Don't add above"]
    )

    price_rows = []

    for ticker in portfolio["Ticker"].unique():
        price, yahoo_currency, error = get_latest_price_and_currency(ticker)

        price_rows.append(
            {
                "Ticker": ticker,
                "Live Price": price,
                "Yahoo Currency": yahoo_currency,
                "Price Error": error,
            }
        )

    prices = pd.DataFrame(price_rows)
    portfolio = portfolio.merge(prices, on="Ticker", how="left")

    portfolio["Adjusted Price"] = portfolio["Live Price"]
    portfolio["Pricing Currency"] = portfolio["Yahoo Currency"]

    london_mask = portfolio["Ticker"].astype(str).str.endswith(".L")
    possible_pence_mask = london_mask & (portfolio["Live Price"] > 20)

    portfolio.loc[possible_pence_mask, "Adjusted Price"] = (
        portfolio.loc[possible_pence_mask, "Live Price"] / 100
    )

    portfolio.loc[london_mask, "Pricing Currency"] = "GBP"

    cash_mask = (
        portfolio["Category"].str.lower().eq("cash")
        | portfolio["Ticker"].str.upper().isin(CASH_TICKERS)
    )

    portfolio.loc[cash_mask, "Adjusted Price"] = 1.0
    portfolio.loc[cash_mask, "Pricing Currency"] = portfolio.loc[cash_mask, "Currency"]
    portfolio.loc[cash_mask, "Price Error"] = None

    fx_rows = []

    for currency in portfolio["Pricing Currency"].dropna().unique():
        fx_rate, fx_error = get_fx_to_usd(currency)

        fx_rows.append(
            {
                "Pricing Currency": currency,
                "FX to USD": fx_rate,
                "FX Error": fx_error,
            }
        )

    fx = pd.DataFrame(fx_rows)
    portfolio = portfolio.merge(fx, on="Pricing Currency", how="left")

    portfolio["Market Value Local"] = (
        portfolio["Position"] * portfolio["Adjusted Price"]
    )

    portfolio["Market Value USD"] = (
        portfolio["Market Value Local"] * portfolio["FX to USD"]
    )

    total_value = portfolio["Market Value USD"].sum(skipna=True)

    if total_value > 0:
        portfolio["Exposure"] = portfolio["Market Value USD"] / total_value
    else:
        portfolio["Exposure"] = np.nan

    portfolio["Max allocation headroom"] = (
        portfolio["Max allocation"] - portfolio["Exposure"]
    )

    portfolio["Don't-add headroom"] = (
        portfolio["Don't add above"] - portfolio["Exposure"]
    )

    portfolio["Above max allocation"] = (
        portfolio["Max allocation"].notna()
        & portfolio["Exposure"].notna()
        & (portfolio["Exposure"] > portfolio["Max allocation"])
    )

    portfolio["Above don't-add threshold"] = (
        portfolio["Don't add above"].notna()
        & portfolio["Exposure"].notna()
        & (portfolio["Exposure"] > portfolio["Don't add above"])
    )

    portfolio = portfolio.sort_values(
        "Market Value USD",
        ascending=False,
        na_position="last",
    ).reset_index(drop=True)

    return portfolio, total_value


# ============================================================
# Historical simulation
# ============================================================

def infer_fx_ticker(pricing_currency):
    pricing_currency = str(pricing_currency).upper().strip()

    if pricing_currency == "USD":
        return None

    return f"{pricing_currency}USD=X"


@st.cache_data(ttl=PRICE_CACHE_SECONDS)
def download_simulation_data(tickers, fx_tickers, benchmark, warmup_start, end_date):
    symbols = sorted(set(tickers + fx_tickers + [benchmark]))

    data = yf.download(
        symbols,
        start=warmup_start,
        end=end_date,
        auto_adjust=True,
        progress=False,
    )

    if data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        close = data["Close"].copy()
    else:
        close = data[["Close"]].copy()

        if len(symbols) == 1:
            close.columns = symbols

    close = close.ffill()

    return close


def calculate_metrics(series, benchmark_series, name="Portfolio", benchmark_name="SPY"):
    series = series.dropna()
    benchmark_series = benchmark_series.dropna()

    daily_returns = series.pct_change().dropna()

    try:
        monthly_returns = series.resample("ME").ffill().pct_change().dropna()
    except ValueError:
        monthly_returns = series.resample("M").ffill().pct_change().dropna()

    bench_daily = benchmark_series.pct_change().dropna()

    aligned = pd.concat([daily_returns, bench_daily], axis=1).dropna()
    aligned.columns = ["port", "bench"]

    risk_free_rate = 0.04
    daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1

    if daily_returns.std() == 0 or pd.isna(daily_returns.std()):
        sharpe = np.nan
    else:
        sharpe = (
            (daily_returns.mean() - daily_rf)
            / daily_returns.std()
            * np.sqrt(252)
        )

    var_95 = np.percentile(daily_returns, 5) if len(daily_returns) else np.nan
    var_99 = np.percentile(daily_returns, 1) if len(daily_returns) else np.nan

    if len(aligned) > 1 and aligned["bench"].var() != 0:
        covariance = aligned.cov().iloc[0, 1]
        bench_variance = aligned["bench"].var()
        beta = covariance / bench_variance
        correlation = aligned["port"].corr(aligned["bench"])
    else:
        beta = np.nan
        correlation = np.nan

    port_annual_ret = (
        (1 + daily_returns.mean()) ** 252 - 1
        if len(daily_returns)
        else np.nan
    )

    bench_annual_ret = (
        (1 + bench_daily.mean()) ** 252 - 1
        if len(bench_daily)
        else np.nan
    )

    if pd.isna(beta) or pd.isna(port_annual_ret) or pd.isna(bench_annual_ret):
        alpha = np.nan
    else:
        alpha = (
            (port_annual_ret - risk_free_rate)
            - beta * (bench_annual_ret - risk_free_rate)
        )

    cumulative_max = series.cummax()
    drawdown = (series - cumulative_max) / cumulative_max
    max_dd = drawdown.min()

    is_in_dd = drawdown < 0
    dd_groups = (is_in_dd != is_in_dd.shift()).cumsum()
    dd_durations = is_in_dd.groupby(dd_groups).sum()
    longest_dd_days = dd_durations.max() if len(dd_durations) else 0

    wins = daily_returns > 0
    win_groups = (wins != wins.shift()).cumsum()
    max_wins = wins.groupby(win_groups).sum().max() if len(wins) else 0

    losses = daily_returns < 0
    loss_groups = (losses != losses.shift()).cumsum()
    max_losses = losses.groupby(loss_groups).sum().max() if len(losses) else 0

    def round_or_nan(value, digits=2):
        if pd.isna(value):
            return np.nan
        return round(value, digits)

    def pct_or_dash(value):
        if pd.isna(value):
            return "-"
        return f"{value:.2%}"

    return {
        "Metric": name,
        "Sharpe Ratio": round_or_nan(sharpe, 2),
        "Alpha (Annualized)": pct_or_dash(alpha),
        f"Beta (vs {benchmark_name})": round_or_nan(beta, 2),
        f"Correlation (vs {benchmark_name})": pct_or_dash(correlation),
        "95% Daily VaR": pct_or_dash(var_95),
        "99% Daily VaR": pct_or_dash(var_99),
        "Max Drawdown": pct_or_dash(max_dd),
        "Longest DD (Days)": int(longest_dd_days) if pd.notna(longest_dd_days) else 0,
        "Exp. Daily %": pct_or_dash(daily_returns.mean()),
        "Exp. Monthly %": pct_or_dash(monthly_returns.mean()),
        "Exp. Yearly %": pct_or_dash(port_annual_ret),
        "Max Consec. Wins": int(max_wins) if pd.notna(max_wins) else 0,
        "Max Consec. Losses": int(max_losses) if pd.notna(max_losses) else 0,
        "Best Day": pct_or_dash(daily_returns.max()),
        "Worst Day": pct_or_dash(daily_returns.min()),
        "Best Month": pct_or_dash(monthly_returns.max()),
        "Worst Month": pct_or_dash(monthly_returns.min()),
    }


def run_historical_simulation(
    portfolio_df,
    start_date,
    end_date,
    benchmark="SPY",
):
    sim_df = portfolio_df.copy()

    non_cash = sim_df[
        ~sim_df["Category"].astype(str).str.lower().eq("cash")
    ].copy()

    cash = sim_df[
        sim_df["Category"].astype(str).str.lower().eq("cash")
    ].copy()

    tickers = (
        non_cash["Ticker"]
        .dropna()
        .astype(str)
        .str.strip()
        .tolist()
    )

    if not tickers:
        return None, [], "No non-cash tickers found."

    pos_map = dict(zip(non_cash["Ticker"], non_cash["Position"]))

    fx_map = {}

    for _, row in non_cash.iterrows():
        ticker = row["Ticker"]
        pricing_currency = row["Pricing Currency"]

        fx_ticker = infer_fx_ticker(pricing_currency)

        if fx_ticker is not None:
            fx_map[ticker] = fx_ticker

    fx_tickers = sorted(set(fx_map.values()))

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    warmup_start = (start_dt - timedelta(days=FIXED_WARMUP_DAYS)).strftime("%Y-%m-%d")
    download_end = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    all_data = download_simulation_data(
        tickers=tickers,
        fx_tickers=fx_tickers,
        benchmark=benchmark,
        warmup_start=warmup_start,
        end_date=download_end,
    )

    if all_data.empty:
        return None, tickers, "Yahoo Finance returned no data."

    usd_price_data = pd.DataFrame(index=all_data.index)
    skipped = []

    for ticker in tickers:
        if ticker not in all_data.columns:
            skipped.append(ticker)
            continue

        price = all_data[ticker].copy()

        if ticker.endswith(".L"):
            price = price / 100.0

        fx_ticker = fx_map.get(ticker)

        if fx_ticker is not None:
            if fx_ticker not in all_data.columns:
                skipped.append(f"{ticker} missing FX {fx_ticker}")
                continue

            price = price * all_data[fx_ticker]

        usd_price_data[ticker] = price

    if usd_price_data.empty:
        return None, skipped, "No usable historical price data."

    raw_nav_usd = usd_price_data.multiply(pd.Series(pos_map)).sum(axis=1)

    cash_value = cash["Market Value USD"].sum(skipna=True)

    if cash_value > 0:
        raw_nav_usd = raw_nav_usd + cash_value

    raw_nav_usd = raw_nav_usd.ffill()
    raw_nav_usd = raw_nav_usd.loc[start_dt:end_dt].dropna()

    if raw_nav_usd.empty:
        return None, skipped, "No portfolio data in the selected date range."

    if benchmark not in all_data.columns:
        return None, skipped + [benchmark], f"Benchmark {benchmark} not found."

    benchmark_raw = all_data[benchmark].ffill().loc[start_dt:end_dt].dropna()

    if benchmark_raw.empty:
        return None, skipped + [benchmark], f"No benchmark data in the selected date range."

    common_index = raw_nav_usd.index.intersection(benchmark_raw.index)

    raw_nav_usd = raw_nav_usd.loc[common_index]
    benchmark_raw = benchmark_raw.loc[common_index]
    usd_price_data = usd_price_data.loc[common_index]

    if raw_nav_usd.empty or benchmark_raw.empty:
        return None, skipped, "No overlapping portfolio and benchmark dates."

    portfolio_value = raw_nav_usd / raw_nav_usd.iloc[0] * INITIAL_INVESTMENT
    benchmark_value = benchmark_raw / benchmark_raw.iloc[0] * INITIAL_INVESTMENT

    value_history = pd.DataFrame(
        {
            "Portfolio Value": portfolio_value,
            f"{benchmark} Value": benchmark_value,
            "Portfolio Growth": portfolio_value,
            f"{benchmark} Growth": benchmark_value,
        }
    )

    value_history["Portfolio Return"] = (
        value_history["Portfolio Value"] / INITIAL_INVESTMENT - 1
    )

    value_history[f"{benchmark} Return"] = (
        value_history[f"{benchmark} Value"] / INITIAL_INVESTMENT - 1
    )

    portfolio_metrics = calculate_metrics(
        value_history["Portfolio Value"],
        value_history[f"{benchmark} Value"],
        name="My Portfolio",
        benchmark_name=benchmark,
    )

    benchmark_metrics = calculate_metrics(
        value_history[f"{benchmark} Value"],
        value_history[f"{benchmark} Value"],
        name=f"{benchmark} Benchmark",
        benchmark_name=benchmark,
    )

    metrics_table = (
        pd.DataFrame([portfolio_metrics, benchmark_metrics])
        .set_index("Metric")
        .T
    )

    simple_metrics = {
        "start_value": value_history["Portfolio Value"].iloc[0],
        "end_value": value_history["Portfolio Value"].iloc[-1],
        "benchmark_end_value": value_history[f"{benchmark} Value"].iloc[-1],
        "total_return": value_history["Portfolio Value"].iloc[-1] / INITIAL_INVESTMENT - 1,
        "benchmark_return": value_history[f"{benchmark} Value"].iloc[-1] / INITIAL_INVESTMENT - 1,
        "max_drawdown": (
            value_history["Portfolio Value"]
            / value_history["Portfolio Value"].cummax()
            - 1
        ).min(),
    }

    return {
        "value_history": value_history,
        "usd_price_data": usd_price_data,
        "metrics_table": metrics_table,
        "simple_metrics": simple_metrics,
    }, skipped, None


# ============================================================
# App
# ============================================================

try:
    with st.spinner("Loading portfolio..."):
        raw_df = load_google_sheet(sheet_id, gid)
        portfolio, total_value = build_portfolio(raw_df)

    # ========================================================
    # Sidebar
    # ========================================================

    st.sidebar.header("Controls")

    if st.sidebar.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

    categories = sorted(portfolio["Category"].dropna().unique())
    brokers = sorted(portfolio["Broker"].dropna().unique())
    currencies = sorted(portfolio["Pricing Currency"].dropna().unique())

    selected_categories = st.sidebar.multiselect(
        "Category",
        options=categories,
        default=categories,
    )

    selected_brokers = st.sidebar.multiselect(
        "Broker",
        options=brokers,
        default=brokers,
    )

    selected_currencies = st.sidebar.multiselect(
        "Pricing currency",
        options=currencies,
        default=currencies,
    )

    filtered_raw = portfolio[
        portfolio["Category"].isin(selected_categories)
        & portfolio["Broker"].isin(selected_brokers)
        & portfolio["Pricing Currency"].isin(selected_currencies)
    ].copy()

    filtered_value = filtered_raw["Market Value USD"].sum(skipna=True)

    if filtered_value > 0:
        filtered_raw["Filtered Exposure"] = filtered_raw["Market Value USD"] / filtered_value
    else:
        filtered_raw["Filtered Exposure"] = np.nan

    filtered = combine_cash_rows(filtered_raw)

    st.sidebar.caption("Google Sheet and market prices refresh every 5 minutes.")

    # ========================================================
    # Data quality warnings
    # ========================================================

    price_issues = portfolio[
        portfolio["Price Error"].notna()
        | portfolio["Live Price"].isna()
    ][["Ticker", "Price Error"]].drop_duplicates()

    fx_issues = portfolio[
        portfolio["FX Error"].notna()
        | portfolio["FX to USD"].isna()
    ][["Pricing Currency", "FX Error"]].drop_duplicates()

    if len(price_issues) > 0:
        with st.expander("⚠️ Price issues detected", expanded=False):
            st.dataframe(price_issues, use_container_width=True, hide_index=True)

    if len(fx_issues) > 0:
        with st.expander("⚠️ FX issues detected", expanded=False):
            st.dataframe(fx_issues, use_container_width=True, hide_index=True)

    # ========================================================
    # Top metrics
    # ========================================================

    cash_exposure = portfolio.loc[
        portfolio["Category"].str.lower().eq("cash"),
        "Exposure",
    ].sum(skipna=True)

    flagged_count = int(portfolio["Above max allocation"].sum())

    display_portfolio = combine_cash_rows(portfolio)
    largest_holding = display_portfolio.iloc[0]["Ticker"] if len(display_portfolio) > 0 else "-"
    largest_exposure = display_portfolio.iloc[0]["Exposure"] if len(display_portfolio) > 0 else np.nan

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Total value", format_usd(total_value))
    col2.metric("Filtered value", format_usd(filtered_value))
    col3.metric("Holdings", len(display_portfolio))
    col4.metric("Cash", format_pct(cash_exposure))
    col5.metric("Risk flags", flagged_count)

    st.caption(
        f"Largest holding: **{largest_holding}** "
        f"({format_pct(largest_exposure)} of portfolio)"
    )

    st.divider()

    # ========================================================
    # Tabs
    # ========================================================

    tab_overview, tab_exposure, tab_simulation = st.tabs(
        [
            "Portfolio Overview",
            "Exposure",
            "Historical Simulation",
        ]
    )

    # ========================================================
    # Portfolio Overview
    # ========================================================

    with tab_overview:
        st.subheader("Portfolio Overview")

        if filtered.empty:
            st.info("No holdings match the selected filters.")

        else:
            left, right = st.columns([1.4, 1])

            with left:
                top_holdings = filtered.head(10).copy()

                fig = px.bar(
                    top_holdings,
                    x="Market Value USD",
                    y="Ticker",
                    orientation="h",
                    text=top_holdings["Market Value USD"].map(
                        lambda x: f"${x:,.0f}"
                    ),
                    hover_data=[
                        "Category",
                        "Broker",
                        "Position",
                        "Adjusted Price",
                        "Pricing Currency",
                        "Exposure",
                    ],
                    title="Top Holdings by Market Value",
                )

                fig.update_layout(
                    yaxis=dict(autorange="reversed"),
                    xaxis_title="Market Value USD",
                    yaxis_title="Ticker",
                )

                st.plotly_chart(fig, use_container_width=True)

            with right:
                category_alloc = (
                    filtered
                    .groupby("Category", as_index=False)["Market Value USD"]
                    .sum()
                    .sort_values("Market Value USD", ascending=False)
                )

                fig = px.pie(
                    category_alloc,
                    names="Category",
                    values="Market Value USD",
                    title="Allocation by Category",
                    hole=0.35,
                )

                st.plotly_chart(fig, use_container_width=True)

            st.markdown("### Risk Flags")

            overview_flagged = filtered[
                filtered["Above max allocation"]
            ].copy()

            if len(overview_flagged) > 0:
                st.warning("Some holdings are above their max allocation.")

                overview_flag_cols = [
                    "Ticker",
                    "Category",
                    "Broker",
                    "Exposure",
                    "Max allocation",
                    "Max allocation headroom",
                    "Above max allocation",
                ]

                overview_flagged_display = overview_flagged[
                    [c for c in overview_flag_cols if c in overview_flagged.columns]
                ].copy()

                overview_flagged_display = format_display_percent_columns(
                    overview_flagged_display,
                    [
                        "Exposure",
                        "Max allocation",
                        "Max allocation headroom",
                    ],
                )

                st.dataframe(
                    overview_flagged_display,
                    use_container_width=True,
                    hide_index=True,
                )

            else:
                st.success("No holdings are above their max allocation.")

            st.markdown("### Holdings")

            display_cols = [
                "Ticker",
                "Category",
                "Broker",
                "Currency",
                "Position",
                "Adjusted Price",
                "Pricing Currency",
                "FX to USD",
                "Market Value USD",
                "Exposure",
                "Max allocation",
                "Don't add above",
                "Thesis / catalysts",
                "Notes",
            ]

            display_cols = [c for c in display_cols if c in filtered.columns]
            holdings_display = filtered[display_cols].copy()

            holdings_display = format_display_percent_columns(
                holdings_display,
                [
                    "Exposure",
                    "Max allocation",
                    "Don't add above",
                ],
            )

            st.dataframe(
                holdings_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Position": st.column_config.NumberColumn(
                        "Position",
                        format="%.2f",
                    ),
                    "Adjusted Price": st.column_config.NumberColumn(
                        "Adjusted Price",
                        format="%.2f",
                    ),
                    "FX to USD": st.column_config.NumberColumn(
                        "FX to USD",
                        format="%.4f",
                    ),
                    "Market Value USD": st.column_config.NumberColumn(
                        "Market Value USD",
                        format="$%.2f",
                    ),
                },
            )

            csv = holdings_display.to_csv(index=False).encode("utf-8")

            st.download_button(
                "Download holdings CSV",
                data=csv,
                file_name="portfolio_holdings.csv",
                mime="text/csv",
            )

    # ========================================================
    # Exposure
    # ========================================================

    with tab_exposure:
        st.subheader("Exposure")

        if filtered.empty:
            st.info("No holdings match the selected filters.")

        else:
            st.markdown("### Exposure by Holding")

            fig = px.bar(
                filtered,
                x="Ticker",
                y="Exposure",
                text=filtered["Exposure"].map(lambda x: f"{x:.1%}"),
                hover_data=[
                    "Category",
                    "Broker",
                    "Market Value USD",
                    "Position",
                    "Max allocation",
                    "Don't add above",
                ],
                title="Current Portfolio Exposure",
            )

            fig.update_layout(
                yaxis_tickformat=".0%",
                xaxis_title="Ticker",
                yaxis_title="Portfolio Exposure",
            )

            st.plotly_chart(fig, use_container_width=True)

            col_a, col_b = st.columns(2)

            with col_a:
                category_alloc = (
                    filtered
                    .groupby("Category", as_index=False)["Market Value USD"]
                    .sum()
                    .sort_values("Market Value USD", ascending=False)
                )

                category_alloc["Exposure"] = (
                    category_alloc["Market Value USD"] / filtered_value
                    if filtered_value > 0
                    else np.nan
                )

                fig = px.bar(
                    category_alloc,
                    x="Category",
                    y="Exposure",
                    text=category_alloc["Exposure"].map(lambda x: f"{x:.1%}"),
                    title="Category Exposure",
                )

                fig.update_layout(
                    yaxis_tickformat=".0%",
                    xaxis_title="Category",
                    yaxis_title="Filtered Portfolio Exposure",
                )

                st.plotly_chart(fig, use_container_width=True)

            with col_b:
                broker_alloc = (
                    filtered_raw
                    .groupby("Broker", as_index=False)["Market Value USD"]
                    .sum()
                    .sort_values("Market Value USD", ascending=False)
                )

                broker_alloc["Exposure"] = (
                    broker_alloc["Market Value USD"] / filtered_value
                    if filtered_value > 0
                    else np.nan
                )

                fig = px.bar(
                    broker_alloc,
                    x="Broker",
                    y="Exposure",
                    text=broker_alloc["Exposure"].map(lambda x: f"{x:.1%}"),
                    title="Broker Exposure",
                )

                fig.update_layout(
                    yaxis_tickformat=".0%",
                    xaxis_title="Broker",
                    yaxis_title="Filtered Portfolio Exposure",
                )

                st.plotly_chart(fig, use_container_width=True)

            col_c, col_d = st.columns(2)

            with col_c:
                currency_alloc = (
                    filtered
                    .groupby("Pricing Currency", as_index=False)["Market Value USD"]
                    .sum()
                    .sort_values("Market Value USD", ascending=False)
                )

                fig = px.pie(
                    currency_alloc,
                    names="Pricing Currency",
                    values="Market Value USD",
                    title="Currency Exposure",
                    hole=0.35,
                )

                st.plotly_chart(fig, use_container_width=True)

            with col_d:
                broker_category = (
                    filtered_raw
                    .groupby(["Broker", "Category"], as_index=False)[
                        "Market Value USD"
                    ]
                    .sum()
                    .sort_values("Market Value USD", ascending=False)
                )

                fig = px.bar(
                    broker_category,
                    x="Broker",
                    y="Market Value USD",
                    color="Category",
                    title="Broker x Category Allocation",
                )

                fig.update_layout(
                    xaxis_title="Broker",
                    yaxis_title="Market Value USD",
                )

                st.plotly_chart(fig, use_container_width=True)

            st.markdown("### Allocation Limits")

            risk = filtered[
                filtered["Max allocation"].notna()
                | filtered["Don't add above"].notna()
            ].copy()

            if len(risk) > 0:
                fig = go.Figure()

                fig.add_trace(
                    go.Bar(
                        x=risk["Ticker"],
                        y=risk["Exposure"],
                        name="Current exposure",
                        text=risk["Exposure"].map(lambda x: f"{x:.1%}"),
                    )
                )

                fig.add_trace(
                    go.Scatter(
                        x=risk["Ticker"],
                        y=risk["Max allocation"],
                        name="Max allocation",
                        mode="lines+markers",
                    )
                )

                fig.add_trace(
                    go.Scatter(
                        x=risk["Ticker"],
                        y=risk["Don't add above"],
                        name="Don't add above",
                        mode="lines+markers",
                    )
                )

                fig.update_layout(
                    yaxis_tickformat=".0%",
                    xaxis_title="Ticker",
                    yaxis_title="Portfolio Exposure",
                    title="Current Exposure vs Limits",
                )

                st.plotly_chart(fig, use_container_width=True)

            st.markdown("### Above Max Allocation")

            flagged = filtered[
                filtered["Above max allocation"]
            ].copy()

            if len(flagged) > 0:
                st.warning("Some holdings are above their max allocation.")

                flag_cols = [
                    "Ticker",
                    "Category",
                    "Broker",
                    "Exposure",
                    "Max allocation",
                    "Max allocation headroom",
                    "Above max allocation",
                ]

                flagged_display = flagged[
                    [c for c in flag_cols if c in flagged.columns]
                ].copy()

                flagged_display = format_display_percent_columns(
                    flagged_display,
                    [
                        "Exposure",
                        "Max allocation",
                        "Max allocation headroom",
                    ],
                )

                st.dataframe(
                    flagged_display,
                    use_container_width=True,
                    hide_index=True,
                )

            else:
                st.success("No holdings are above their max allocation.")

            st.markdown("### Above Don't-Add Threshold")

            add_warning = filtered[
                filtered["Above don't-add threshold"]
            ].copy()

            if len(add_warning) > 0:
                st.info("These holdings are above the level where you prefer not to add more.")

                add_warning_cols = [
                    "Ticker",
                    "Category",
                    "Broker",
                    "Exposure",
                    "Don't add above",
                    "Don't-add headroom",
                    "Above don't-add threshold",
                ]

                add_warning_display = add_warning[
                    [c for c in add_warning_cols if c in add_warning.columns]
                ].copy()

                add_warning_display = format_display_percent_columns(
                    add_warning_display,
                    [
                        "Exposure",
                        "Don't add above",
                        "Don't-add headroom",
                    ],
                )

                st.dataframe(
                    add_warning_display,
                    use_container_width=True,
                    hide_index=True,
                )

            else:
                st.success("No holdings are above their don't-add threshold.")

    # ========================================================
    # Historical Simulation
    # ========================================================

    with tab_simulation:
        st.subheader("Historical Simulation")

        st.caption(
            "This is a current-position historical simulation. "
            "It assumes the portfolio starts at **100** on the simulation start date, "
            "uses current holding weights, converts non-USD assets into USD, keeps cash exposure constant, "
            "and compares the result against a benchmark."
        )

        col_a, col_b, col_c = st.columns(3)

        with col_a:
            start_date = st.date_input(
                "Simulation start",
                value=pd.to_datetime("2019-01-01"),
            )

        with col_b:
            end_date = st.date_input(
                "Simulation end",
                value=pd.to_datetime(datetime.now().date()),
            )

        with col_c:
            benchmark = st.text_input(
                "Benchmark",
                value="SPY",
            ).strip().upper()

        st.info(
            f"A fixed {FIXED_WARMUP_DAYS}-day warm-up window is used only to forward-fill prices/FX "
            "when the selected start date falls on a market holiday or missing-data day."
        )

        run_sim = st.button("Run historical simulation")

        if run_sim:
            today = datetime.now().date()

            if filtered_raw.empty:
                st.warning("No holdings match the selected filters.")

            elif start_date >= end_date:
                st.warning("Simulation start must be before simulation end.")

            elif end_date > today:
                st.warning("Simulation end cannot be in the future.")

            elif benchmark == "":
                st.warning("Please enter a benchmark ticker.")

            else:
                with st.spinner("Downloading historical prices and FX data..."):
                    sim_result, skipped, error = run_historical_simulation(
                        portfolio_df=filtered_raw,
                        start_date=start_date.strftime("%Y-%m-%d"),
                        end_date=end_date.strftime("%Y-%m-%d"),
                        benchmark=benchmark,
                    )

                if skipped:
                    st.warning(
                        "Some tickers or FX series were skipped: "
                        + ", ".join(sorted(set(skipped)))
                    )

                if error:
                    st.error(error)

                elif sim_result is None:
                    st.warning("No simulation result was produced.")

                else:
                    value_history = sim_result["value_history"]
                    usd_price_data = sim_result["usd_price_data"]
                    metrics_table = sim_result["metrics_table"]
                    simple_metrics = sim_result["simple_metrics"]

                    metric_1, metric_2, metric_3, metric_4 = st.columns(4)

                    metric_1.metric(
                        "Start value",
                        format_number(simple_metrics["start_value"]),
                    )

                    metric_2.metric(
                        "Portfolio end value",
                        format_number(simple_metrics["end_value"]),
                    )

                    metric_3.metric(
                        f"{benchmark} end value",
                        format_number(simple_metrics["benchmark_end_value"]),
                    )

                    metric_4.metric(
                        "Portfolio return",
                        format_pct(simple_metrics["total_return"]),
                    )

                    st.markdown("### Performance & Risk Metrics")

                    st.dataframe(
                        metrics_table,
                        use_container_width=True,
                    )

                    growth_cols = [
                        "Portfolio Growth",
                        f"{benchmark} Growth",
                    ]

                    fig = px.line(
                        value_history,
                        x=value_history.index,
                        y=growth_cols,
                        title=f"Portfolio vs {benchmark} — Start = 100",
                    )

                    fig.update_layout(
                        xaxis_title="Date",
                        yaxis_title="Indexed Value",
                        legend_title_text="Series",
                    )

                    macro_events = [
                        {
                            "name": "COVID Crash",
                            "start": "2020-02-20",
                            "end": "2020-04-15",
                        },
                        {
                            "name": "Liberation Day",
                            "start": "2025-04-01",
                            "end": "2025-04-10",
                        },
                    ]

                    for event in macro_events:
                        fig.add_vrect(
                            x0=event["start"],
                            x1=event["end"],
                            opacity=0.15,
                            line_width=0,
                            annotation_text=event["name"],
                            annotation_position="top left",
                        )

                    st.plotly_chart(fig, use_container_width=True)

                    return_cols = [
                        "Portfolio Return",
                        f"{benchmark} Return",
                    ]

                    fig = px.line(
                        value_history,
                        x=value_history.index,
                        y=return_cols,
                        title=f"Portfolio vs {benchmark} — Cumulative Return",
                    )

                    fig.update_layout(
                        xaxis_title="Date",
                        yaxis_title="Cumulative Return",
                        yaxis_tickformat=".0%",
                        legend_title_text="Series",
                    )

                    st.plotly_chart(fig, use_container_width=True)

                    with st.expander("View simulated USD price data"):
                        st.dataframe(
                            usd_price_data,
                            use_container_width=True,
                        )

                    with st.expander("View simulation output data"):
                        st.dataframe(
                            value_history,
                            use_container_width=True,
                        )

except Exception as e:
    st.error("Dashboard failed to load. Check that the Google Sheet is shared as: Anyone with the link can view.")
    st.exception(e)