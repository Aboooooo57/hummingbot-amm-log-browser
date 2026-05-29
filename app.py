import os
import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ── Constants ─────────────────────────────────────────────────────────────────
PRICE_SCALE  = 1_000_000   # stored as integer ×10⁶
AMOUNT_SCALE = 100_000_000 # stored as integer ×10⁸  (satoshi-like)

# Default directory for SQLite files
DEFAULT_DB_DIR = os.getenv("SQLITE_DB_DIR", ".")

ORDER_STATUS_COLORS = {
    "OrderFilled":       "#2ecc71",
    "BuyOrderCompleted": "#27ae60",
    "SellOrderCompleted":"#16a085",
    "BuyOrderCreated":   "#3498db",
    "SellOrderCreated":  "#2980b9",
    "OrderCancelled":    "#e67e22",
    "OrderFailure":      "#e74c3c",
}

# ── Helpers ────────────────────────────────────────────────────────────────────
def _load_raw_table(db_path: str, table: str) -> pd.DataFrame:
    try:
        con = sqlite3.connect(db_path)
        df  = pd.read_sql_query(f'SELECT * FROM "{table}"', con)
        con.close()
        return df
    except Exception as e:
        st.error(f"Error loading table '{table}': {e}")
        return pd.DataFrame()


def _scale_prices_and_amounts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    if "price" in df.columns:
        df["price"] = df["price"] / PRICE_SCALE
    if "amount" in df.columns:
        df["amount"] = df["amount"] / AMOUNT_SCALE
    return df


def _add_datetime(df: pd.DataFrame, col: str, new_col: str = "datetime") -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df
    df[new_col] = pd.to_datetime(df[col] / 1000, unit="s", utc=True).dt.tz_convert("Asia/Tehran")
    return df


@st.cache_data(show_spinner="Loading fills…")
def load_fills(db_path: str) -> pd.DataFrame:
    df = _load_raw_table(db_path, "TradeFill")
    if df.empty:
        return df
    df = _scale_prices_and_amounts(df)
    df = _add_datetime(df, "timestamp", "datetime")
    df["notional"] = df["price"] * df["amount"]
    return df


@st.cache_data(show_spinner="Loading orders…")
def load_orders(db_path: str) -> pd.DataFrame:
    df = _load_raw_table(db_path, "Order")
    if df.empty:
        return df
    df = _scale_prices_and_amounts(df)
    df = _add_datetime(df, "creation_timestamp", "datetime")
    df = _add_datetime(df, "last_update_timestamp", "last_update_dt")
    df["notional"] = df["price"] * df["amount"]
    return df



def apply_date_filter(df, dt_col, start_date, end_date):
    mask = (df[dt_col].dt.date >= start_date) & (df[dt_col].dt.date <= end_date)
    return df[mask]


# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Hummingbot AMM Log Browser",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Hummingbot – Avellaneda Market Making Log Browser")

# ── Sidebar: DB file selector ──────────────────────────────────────────────────
st.sidebar.header("⚙️ Settings")

# Directory selector
db_dir = st.sidebar.text_input("SQLite Directory", value=DEFAULT_DB_DIR, help="Path to the directory containing Hummingbot .sqlite files.")

# Discover all .sqlite files in the chosen directory
if os.path.isdir(db_dir):
    sqlite_files = sorted([f for f in os.listdir(db_dir) if f.endswith((".sqlite", ".db"))])
else:
    st.sidebar.error(f"Directory not found: `{db_dir}`")
    sqlite_files = []

selected_file = st.sidebar.selectbox(
    "Select log file",
    options=sqlite_files,
    index=0 if sqlite_files else None,
    help="Select a Hummingbot SQLite log file from the chosen directory.",
)

uploaded = st.sidebar.file_uploader(
    "…or upload a different .sqlite file",
    type=["sqlite", "db"],
)

if uploaded is not None:
    db_path = f"/tmp/{uploaded.name}"
    with open(db_path, "wb") as f:
        f.write(uploaded.getbuffer())
elif selected_file:
    db_path = os.path.join(db_dir, selected_file)
else:
    db_path = None

if not db_path:
    st.warning("No SQLite file selected or found. Please provide a valid directory or upload a file in the sidebar.")
    st.stop()

if not os.path.exists(db_path) and uploaded is None:
    st.error(f"File not found: `{db_path}`")
    st.stop()

st.sidebar.success(f"Using: `{os.path.basename(db_path)}`")

# ── Load and pre-process tables (cached) ───────────────────────────────────────
fills  = load_fills(db_path)
orders = load_orders(db_path)

if fills.empty and orders.empty:
    st.error("The selected database seems empty or is not a valid Hummingbot log file.")
    st.stop()

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_fills, tab_orders, tab_avell = st.tabs(
    ["🔄 Trade Fills", "📋 Orders", "🧮 Avellaneda Parameters"]
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 – TRADE FILLS
# ══════════════════════════════════════════════════════════════════════════════
with tab_fills:
    st.subheader("Trade Fills")

    col1, col2, col3 = st.columns(3)
    min_date_f = fills["datetime"].dt.date.min()
    max_date_f = fills["datetime"].dt.date.max()

    with col1:
        start_f = st.date_input("From", value=min_date_f, min_value=min_date_f, max_value=max_date_f, key="f_start")
    with col2:
        end_f   = st.date_input("To",   value=max_date_f, min_value=min_date_f, max_value=max_date_f, key="f_end")
    with col3:
        trade_types = ["All"] + sorted(fills["trade_type"].unique().tolist())
        sel_type    = st.selectbox("Trade Type", trade_types, key="f_type")

    df_f = apply_date_filter(fills, "datetime", start_f, end_f)
    if sel_type != "All":
        df_f = df_f[df_f["trade_type"] == sel_type]

    # ── KPI row
    buys  = df_f[df_f["trade_type"] == "BUY"]
    sells = df_f[df_f["trade_type"] == "SELL"]

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Fills",      f"{len(df_f):,}")
    k2.metric("Buy Fills",        f"{len(buys):,}")
    k3.metric("Sell Fills",       f"{len(sells):,}")
    k4.metric("Total BTC Volume", f"{df_f['amount'].sum():.6f} BTC")
    k5.metric("Total Notional",   f"{df_f['notional'].sum():,.0f} TMN")

    st.divider()

    # ── Charts
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Fill Price Over Time (BUY vs SELL)**")
        fig_price = go.Figure()
        for ttype, color in [("BUY", "#2ecc71"), ("SELL", "#e74c3c")]:
            subset = df_f[df_f["trade_type"] == ttype]
            fig_price.add_trace(go.Scatter(
                x=subset["datetime"], y=subset["price"],
                mode="markers", name=ttype,
                marker=dict(color=color, size=4, opacity=0.7),
                hovertemplate="%{x}<br>Price: %{y:,.0f} TMN<extra></extra>",
            ))
        fig_price.update_layout(
            height=350, xaxis_title="Time", yaxis_title="Price (TMN)",
            legend=dict(orientation="h"), margin=dict(t=20),
        )
        st.plotly_chart(fig_price, use_container_width=True)

    with c2:
        st.markdown("**Cumulative BTC Volume Over Time**")
        df_vol = df_f.sort_values("datetime").copy()
        df_vol["cum_buy"]  = (df_vol["trade_type"] == "BUY").astype(float) * df_vol["amount"]
        df_vol["cum_sell"] = (df_vol["trade_type"] == "SELL").astype(float) * df_vol["amount"]
        df_vol["cum_buy"]  = df_vol["cum_buy"].cumsum()
        df_vol["cum_sell"] = df_vol["cum_sell"].cumsum()
        fig_vol = go.Figure()
        fig_vol.add_trace(go.Scatter(x=df_vol["datetime"], y=df_vol["cum_buy"],  name="Cum BUY",  line=dict(color="#2ecc71")))
        fig_vol.add_trace(go.Scatter(x=df_vol["datetime"], y=df_vol["cum_sell"], name="Cum SELL", line=dict(color="#e74c3c")))
        fig_vol.update_layout(
            height=350, xaxis_title="Time", yaxis_title="BTC",
            legend=dict(orientation="h"), margin=dict(t=20),
        )
        st.plotly_chart(fig_vol, use_container_width=True)

    st.divider()

    # ── Level distribution
    st.markdown("**Fill Count by Level**")
    level_f = df_f[df_f["level"].notna()].copy()
    if level_f.empty:
        st.info("No level data in the current fill selection.")
    else:
        level_f["level"] = level_f["level"].astype(int)
        lc1, lc2 = st.columns(2)
        with lc1:
            # Grouped by level
            lvl_counts_f = (
                level_f.groupby(["level", "trade_type"])
                .size()
                .reset_index(name="count")
            )
            fig_lvl_f = px.bar(
                lvl_counts_f, x="level", y="count", color="trade_type",
                barmode="group",
                color_discrete_map={"BUY": "#2ecc71", "SELL": "#e74c3c"},
                labels={"level": "Level", "count": "Fills", "trade_type": "Side"},
                title="Fills per Level (BUY vs SELL)",
            )
            fig_lvl_f.update_layout(height=320, margin=dict(t=40))
            st.plotly_chart(fig_lvl_f, use_container_width=True)
        with lc2:
            # BTC volume by level
            lvl_vol_f = (
                level_f.groupby(["level", "trade_type"])["amount"]
                .sum()
                .reset_index(name="volume")
            )
            fig_lvlv_f = px.bar(
                lvl_vol_f, x="level", y="volume", color="trade_type",
                barmode="group",
                color_discrete_map={"BUY": "#2ecc71", "SELL": "#e74c3c"},
                labels={"level": "Level", "volume": "BTC Volume", "trade_type": "Side"},
                title="BTC Volume per Level (BUY vs SELL)",
            )
            fig_lvlv_f.update_layout(height=320, margin=dict(t=40))
            st.plotly_chart(fig_lvlv_f, use_container_width=True)

    st.divider()
    st.markdown("**Fills Table**")
    display_cols_f = [
        "datetime", "trade_type", "order_type", "price", "amount", "notional",
        "exchange_trade_id", "order_id",
    ]
    display_df_f = df_f[display_cols_f].sort_values("datetime", ascending=False).reset_index(drop=True)
    st.dataframe(
        display_df_f,
        column_config={
            "price":    st.column_config.NumberColumn("price",    format="%,.0f"),
            "notional": st.column_config.NumberColumn("notional", format="%,.0f"),
            "amount":   st.column_config.NumberColumn("amount",   format="%,.8f"),
        },
        use_container_width=True,
        height=400,
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 – ORDERS
# ══════════════════════════════════════════════════════════════════════════════
with tab_orders:
    st.subheader("Orders")

    col1, col2, col3 = st.columns(3)
    min_date_o = orders["datetime"].dt.date.min()
    max_date_o = orders["datetime"].dt.date.max()

    with col1:
        start_o = st.date_input("From", value=min_date_o, min_value=min_date_o, max_value=max_date_o, key="o_start")
    with col2:
        end_o   = st.date_input("To",   value=max_date_o, min_value=min_date_o, max_value=max_date_o, key="o_end")
    with col3:
        statuses     = ["All"] + sorted(orders["last_status"].unique().tolist())
        sel_status   = st.selectbox("Status", statuses, key="o_status")

    col4, col5 = st.columns(2)
    with col4:
        side_map = {"All": None, "BUY (BB*)": "BB", "SELL (SB*)": "SB"}
        sel_side = st.selectbox("Side", list(side_map.keys()), key="o_side")
    with col5:
        levels = ["All"] + sorted([str(int(l)) for l in orders["level"].dropna().unique()])
        sel_level = st.selectbox("Level", levels, key="o_level")

    df_o = apply_date_filter(orders, "datetime", start_o, end_o)
    if sel_status != "All":
        df_o = df_o[df_o["last_status"] == sel_status]
    if side_map[sel_side]:
        df_o = df_o[df_o["id"].str.startswith("HB-" + side_map[sel_side])]
    if sel_level != "All":
        df_o = df_o[df_o["level"] == int(sel_level)]

    # ── KPI row
    filled  = df_o[df_o["last_status"].isin(["OrderFilled", "BuyOrderCompleted", "SellOrderCompleted"])]
    cancelled = df_o[df_o["last_status"] == "OrderCancelled"]

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Orders",     f"{len(df_o):,}")
    k2.metric("Filled",           f"{len(filled):,}")
    k3.metric("Cancelled",        f"{len(cancelled):,}")
    k4.metric("BTC Volume",       f"{df_o['amount'].sum():.6f} BTC")
    k5.metric("Notional",         f"{df_o['notional'].sum():,.0f} TMN")

    st.divider()

    # ── Charts
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Order Price Over Time (colored by Status)**")
        fig_op = go.Figure()
        for status, color in ORDER_STATUS_COLORS.items():
            sub = df_o[df_o["last_status"] == status]
            if sub.empty:
                continue
            fig_op.add_trace(go.Scatter(
                x=sub["datetime"], y=sub["price"],
                mode="markers", name=status,
                marker=dict(color=color, size=4, opacity=0.6),
                hovertemplate="%{x}<br>%{y:,.0f} TMN<extra></extra>",
            ))
        fig_op.update_layout(
            height=350, xaxis_title="Time", yaxis_title="Price (TMN)",
            legend=dict(orientation="h", y=-0.2), margin=dict(t=20),
        )
        st.plotly_chart(fig_op, use_container_width=True)

    with c2:
        st.markdown("**Orders by Status (Count)**")
        status_counts = df_o["last_status"].value_counts().reset_index()
        status_counts.columns = ["status", "count"]
        status_counts["color"] = status_counts["status"].map(
            lambda s: ORDER_STATUS_COLORS.get(s, "#95a5a6")
        )
        fig_bar = go.Figure(go.Bar(
            x=status_counts["status"], y=status_counts["count"],
            marker_color=status_counts["color"],
            hovertemplate="%{x}: %{y:,}<extra></extra>",
        ))
        fig_bar.update_layout(
            height=350, xaxis_title="", yaxis_title="Count",
            margin=dict(t=20),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    st.divider()

    # ── Level distribution
    st.markdown("**Order Distribution by Level**")
    level_o = df_o[df_o["level"].notna()].copy()
    if level_o.empty:
        st.info("No level data in the current order selection.")
    else:
        level_o["level"] = level_o["level"].astype(int)
        # Derive side from order ID prefix (vectorized)
        level_o["side"] = "OTHER"
        level_o.loc[level_o["id"].str.startswith("HB-BB"), "side"] = "BUY"
        level_o.loc[level_o["id"].str.startswith("HB-SB"), "side"] = "SELL"
        lc1, lc2, lc3 = st.columns(3)
        with lc1:
            lvl_counts_o = (
                level_o.groupby(["level", "side"])
                .size()
                .reset_index(name="count")
            )
            fig_lvl_o = px.bar(
                lvl_counts_o, x="level", y="count", color="side",
                barmode="group",
                color_discrete_map={"BUY": "#2ecc71", "SELL": "#e74c3c", "OTHER": "#95a5a6"},
                labels={"level": "Level", "count": "Orders", "side": "Side"},
                title="Orders per Level (BUY vs SELL)",
            )
            fig_lvl_o.update_layout(height=320, margin=dict(t=40))
            st.plotly_chart(fig_lvl_o, use_container_width=True)
        with lc2:
            lvl_status_o = (
                level_o.groupby(["level", "last_status"])
                .size()
                .reset_index(name="count")
            )
            color_map_status = {s: c for s, c in ORDER_STATUS_COLORS.items()}
            fig_lvl_st = px.bar(
                lvl_status_o, x="level", y="count", color="last_status",
                barmode="stack",
                color_discrete_map=color_map_status,
                labels={"level": "Level", "count": "Orders", "last_status": "Status"},
                title="Orders per Level (stacked by Status)",
            )
            fig_lvl_st.update_layout(height=320, margin=dict(t=40))
            st.plotly_chart(fig_lvl_st, use_container_width=True)
        with lc3:
            lvl_vol_o = (
                level_o.groupby(["level", "side"])["amount"]
                .sum()
                .reset_index(name="volume")
            )
            fig_lvlv_o = px.bar(
                lvl_vol_o, x="level", y="volume", color="side",
                barmode="group",
                color_discrete_map={"BUY": "#2ecc71", "SELL": "#e74c3c", "OTHER": "#95a5a6"},
                labels={"level": "Level", "volume": "BTC Volume", "side": "Side"},
                title="BTC Volume per Level (BUY vs SELL)",
            )
            fig_lvlv_o.update_layout(height=320, margin=dict(t=40))
            st.plotly_chart(fig_lvlv_o, use_container_width=True)

    st.divider()
    st.markdown("**Orders Table**")
    display_cols_o = [
        "datetime", "last_status", "order_type", "price", "amount", "notional",
        "level", "last_update_dt", "id", "exchange_order_id",
    ]
    display_df_o = df_o[display_cols_o].sort_values("datetime", ascending=False).reset_index(drop=True)
    st.dataframe(
        display_df_o,
        column_config={
            "price":    st.column_config.NumberColumn("price",    format="%,.0f"),
            "notional": st.column_config.NumberColumn("notional", format="%,.0f"),
            "amount":   st.column_config.NumberColumn("amount",   format="%,.8f"),
        },
        use_container_width=True,
        height=450,
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 – AVELLANEDA PARAMETERS
# ══════════════════════════════════════════════════════════════════════════════
with tab_avell:
    st.subheader("Avellaneda Strategy Parameters Over Time")

    # Use TradeFill rows that have Avellaneda params (more focused snapshot)
    # Fall back to Order if TradeFill has none
    avell_df = fills[fills["q"].notna()].copy()
    if avell_df.empty:
        avell_df = orders[orders["q"].notna()].copy()
        avell_df = avell_df.rename(columns={"datetime": "datetime"})
        st.info("Using Order table for Avellaneda parameters (TradeFill had no data).")
    
    if avell_df.empty:
        st.warning("No Avellaneda parameter data found in this log file.")
        st.stop()

    # Date filter
    col1, col2 = st.columns(2)
    min_date_a = avell_df["datetime"].dt.date.min()
    max_date_a = avell_df["datetime"].dt.date.max()
    with col1:
        start_a = st.date_input("From", value=min_date_a, min_value=min_date_a, max_value=max_date_a, key="a_start")
    with col2:
        end_a   = st.date_input("To",   value=max_date_a, min_value=min_date_a, max_value=max_date_a, key="a_end")

    avell_df = apply_date_filter(avell_df, "datetime", start_a, end_a).sort_values("datetime")

    if avell_df.empty:
        st.warning("No data for selected date range.")
        st.stop()

    # Latest snapshot metrics
    latest = avell_df.iloc[-1]
    st.markdown("#### Latest Snapshot")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("q (Inventory Skew)",   f"{latest['q']:.4f}")
    m2.metric("γ (Risk Aversion)",    f"{latest['gamma']:.1f}")
    m3.metric("Volatility",           f"{latest['volatility']:,.0f}")
    m4.metric("Reservation Price",    f"{latest['reservation_price']:,.0f}")
    m5.metric("Optimal Spread",       f"{latest['optimal_spread']:,.0f}")
    m6.metric("Implied Spread",       f"{latest['implied_spread']:,.0f}")

    st.divider()

    # ── Chart 1: Prices (bid / ask / reservation)
    st.markdown("#### Market Prices vs Reservation Price")
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(
        x=avell_df["datetime"], y=avell_df["best_bid"],
        name="Best Bid", line=dict(color="#2ecc71", width=1),
        hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>",
    ))
    fig1.add_trace(go.Scatter(
        x=avell_df["datetime"], y=avell_df["best_ask"],
        name="Best Ask", line=dict(color="#e74c3c", width=1),
        hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>",
    ))
    fig1.add_trace(go.Scatter(
        x=avell_df["datetime"], y=avell_df["reservation_price"],
        name="Reservation Price", line=dict(color="#f39c12", width=2, dash="dash"),
        hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>",
    ))
    fig1.add_trace(go.Scatter(
        x=avell_df["datetime"], y=avell_df["price"],
        name="Fill Price", mode="markers",
        marker=dict(color="#9b59b6", size=4, opacity=0.5),
        hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>",
    ))
    fig1.update_layout(
        height=380, xaxis_title="Time", yaxis_title="Price (TMN)",
        legend=dict(orientation="h"), margin=dict(t=10),
    )
    st.plotly_chart(fig1, use_container_width=True)

    # ── Chart 2: Spreads
    st.markdown("#### Spread Dynamics")
    fig2 = make_subplots(rows=1, cols=1)
    fig2.add_trace(go.Scatter(
        x=avell_df["datetime"], y=avell_df["optimal_spread"],
        name="Optimal Spread", line=dict(color="#3498db", width=2),
        hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>",
    ))
    fig2.add_trace(go.Scatter(
        x=avell_df["datetime"], y=avell_df["implied_spread"],
        name="Implied Spread", line=dict(color="#1abc9c", width=1, dash="dot"),
        hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>",
    ))
    fig2.update_layout(
        height=320, xaxis_title="Time", yaxis_title="Spread (TMN)",
        legend=dict(orientation="h"), margin=dict(t=10),
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ── Chart 3: q, gamma, volatility in 3 sub-rows
    st.markdown("#### Inventory Skew (q), Risk Aversion (γ), and Volatility")
    fig3 = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        subplot_titles=("q – Inventory Skew", "γ – Risk Aversion", "Volatility"),
        vertical_spacing=0.08,
    )
    fig3.add_trace(go.Scatter(
        x=avell_df["datetime"], y=avell_df["q"],
        name="q", line=dict(color="#e67e22"),
        hovertemplate="%{x}<br>q=%{y:.5f}<extra></extra>",
    ), row=1, col=1)
    fig3.add_hline(y=0, line_dash="dash", line_color="grey", opacity=0.5, row=1, col=1)

    fig3.add_trace(go.Scatter(
        x=avell_df["datetime"], y=avell_df["gamma"],
        name="γ", line=dict(color="#8e44ad"),
        hovertemplate="%{x}<br>γ=%{y:.2f}<extra></extra>",
    ), row=2, col=1)

    fig3.add_trace(go.Scatter(
        x=avell_df["datetime"], y=avell_df["volatility"],
        name="Volatility", line=dict(color="#16a085"),
        hovertemplate="%{x}<br>σ=%{y:,.0f}<extra></extra>",
    ), row=3, col=1)

    fig3.update_layout(
        height=550, showlegend=False,
        margin=dict(t=30),
    )
    fig3.update_yaxes(title_text="q",          row=1, col=1)
    fig3.update_yaxes(title_text="γ",          row=2, col=1)
    fig3.update_yaxes(title_text="Volatility", row=3, col=1)
    st.plotly_chart(fig3, use_container_width=True)

    st.divider()
    st.markdown("**Raw Avellaneda Parameters Table**")
    avell_cols = [
        "datetime", "trade_type", "price", "amount",
        "q", "gamma", "volatility",
        "reservation_price", "optimal_spread", "implied_spread",
        "best_bid", "best_ask", "level",
    ]
    avell_display = avell_df[[c for c in avell_cols if c in avell_df.columns]].sort_values("datetime", ascending=False).reset_index(drop=True)
    num_cols_0f = [c for c in ["price", "reservation_price", "optimal_spread", "implied_spread", "best_bid", "best_ask", "volatility"] if c in avell_display.columns]
    col_cfg = {c: st.column_config.NumberColumn(c, format="%,.0f") for c in num_cols_0f}
    if "amount" in avell_display.columns:
        col_cfg["amount"] = st.column_config.NumberColumn("amount", format="%,.8f")
    if "q" in avell_display.columns:
        col_cfg["q"] = st.column_config.NumberColumn("q", format="%.6f")
    st.dataframe(avell_display, column_config=col_cfg, use_container_width=True, height=400)
