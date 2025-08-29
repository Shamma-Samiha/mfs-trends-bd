# app/streamlit_app.py  — full drop-in

# --- make project root importable (because this file is in /app) ---
import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# --- libs ---
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# consistent category colors (tweak as you like)
COLOR_MAP = {
    "Cash In": "#4e79a7",
    "Cash Out": "#f28e2c",
    "P2P": "#e15759",
    "Utility Bill Payment (P2B)": "#76b7b2",
    "Merchant Payment": "#59a14f",
    "Government Payment": "#edc949",
    "Salary Disbursement (B2P)": "#af7aa1",
    "Others": "#ff9da7",
}

# --- local modules ---
from src.fetch import fetch_raw, sample_raw
from src.etl import tidy
from src.metrics import aggregate_monthly, add_growth, seasonal_anomaly

# --- page setup ---
st.set_page_config(page_title="Bangladesh MFS Trends", layout="wide")
st.title("Bangladesh Mobile Financial Services — Trends Dashboard")
st.caption("Source: Bangladesh Bank MFS statistics (latest monthly comparative statements).")

# --- data loading (live -> sample fallback) ---
@st.cache_data(ttl=60 * 60)
def load_data():
    try:
        raw = fetch_raw()  # try live (HTML/PDF)
    except Exception as e:
        print("fetch_raw failed, using sample:", e)
        raw = sample_raw()

    clean = tidy(raw)
    monthly = aggregate_monthly(clean)
    with_growth = add_growth(monthly)

    # if parsing produced nothing, force sample so UI still works
    if with_growth.empty:
        raw = sample_raw()
        clean = tidy(raw)
        monthly = aggregate_monthly(clean)
        with_growth = add_growth(monthly)

    return with_growth

df = load_data()
st.caption("Data mode: **live if available, otherwise sample**")

if df.empty:
    st.error("No data parsed. Try again later or check source URLs in src/fetch.py")
    st.stop()

# --- controls ---
cats = sorted(df["category"].unique().tolist())
pick = st.multiselect("Choose categories", cats, default=cats)
view = df[df["category"].isin(pick)]

latest = view["month"].max()
st.info(f"Latest month in data: {latest.date() if pd.notnull(latest) else 'unknown'}")

# --- KPI cards (Total / MoM / YoY) ---
def pct_change(curr, prev):
    if prev in (None, 0) or pd.isna(prev):
        return None
    return curr / prev - 1

if pd.notnull(latest):
    prev_m = latest - pd.offsets.MonthBegin(1)
    prev_y = latest - pd.DateOffset(years=1)

    tot_latest = view.loc[view["month"] == latest, "amount_bdt"].sum()
    tot_prev_m = view.loc[view["month"] == prev_m, "amount_bdt"].sum()
    tot_prev_y = view.loc[view["month"] == prev_y, "amount_bdt"].sum()

    mom = pct_change(tot_latest, tot_prev_m)
    yoy = pct_change(tot_latest, tot_prev_y)

    c1, c2, c3 = st.columns(3)
    c1.metric("Total (latest)", f"{tot_latest:,.0f} BDT")
    c2.metric("MoM", f"{mom*100:.1f}%" if mom is not None else "—")
    c3.metric("YoY", f"{yoy*100:.1f}%" if yoy is not None else "—")

# --- tabs ---
tab1, tab2, tab3, tab4 = st.tabs(
    ["Amounts (BDT)", "Growth (MoM/YoY)", "Anomalies", "Category mix (%)"]
)

n_months = view["month"].dt.to_period("M").nunique()

# -------- Tab 1: Amounts (line if >=2 months, else bar) --------
with tab1:
    if n_months < 2:
        st.info("Only one month of data available — showing a bar chart instead of a trend line.")
        bar_df = view.groupby("category", as_index=False)["amount_bdt"].sum()
        fig = px.bar(
            bar_df, x="category", y="amount_bdt",
            color="category", color_discrete_map=COLOR_MAP,
            hover_data={"amount_bdt":":,.0f"}
        )
        fig.update_yaxes(title="BDT", tickformat="~s")
        st.plotly_chart(fig, use_container_width=True)
    else:
        show_ma = st.checkbox("Show 3-month moving average", value=True)
        if show_ma:
            ma = (
                view.sort_values(["category", "month"])
                    .groupby("category")
                    .apply(lambda d: d.assign(amount_bdt=d["amount_bdt"].rolling(3, min_periods=1).mean()))
                    .reset_index(drop=True)
            )
            ma["category"] = ma["category"] + " (MA3)"
            plot_df = pd.concat([view, ma], ignore_index=True)
        else:
            plot_df = view

        fig = px.line(
            plot_df, x="month", y="amount_bdt", color="category",
            markers=True, color_discrete_map=COLOR_MAP,
            hover_data={"amount_bdt":":,.0f","category":True,"month":True},
        )
        fig.update_traces(mode="lines+markers")
        fig.update_yaxes(title="BDT", tickformat="~s")
        st.plotly_chart(fig, use_container_width=True)

# -------- Tab 2: Growth (guard for insufficient history) --------
with tab2:
    if n_months < 2:
        st.warning("Need at least 2 months for MoM and ~13 months for YoY to plot growth.")
    else:
        gsel = st.selectbox("Growth metric", ["mom", "yoy"], index=1)
        fig = px.line(
            view, x="month", y=gsel, color="category",
            markers=True, color_discrete_map=COLOR_MAP,
            hover_data={gsel:":.1%","category":True,"month":True},
        )
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

        if n_months >= 13:
            st.markdown("**YoY heatmap** (warm = higher growth)")
            heat = df[df["category"].isin(pick)].pivot_table(
                index="category", columns="month", values="yoy"
            ) * 100.0
            heat = heat.sort_index()
            heat.columns = [c.strftime("%Y-%m") for c in heat.columns]
            fig_hm = px.imshow(
                heat, color_continuous_scale="RdYlGn", aspect="auto", origin="lower",
                labels=dict(color="YoY %"),
            )
            fig_hm.update_xaxes(tickangle=-45)
            st.plotly_chart(fig_hm, use_container_width=True)
        else:
            st.caption("YoY heatmap appears when ≥ 13 months of data are available.")

# -------- Tab 3: Anomaly table + markers --------
with tab3:
    out = []
    for c, sub in view.groupby("category"):
        s = sub.set_index("month")["amount_bdt"]
        flags = seasonal_anomaly(s)
        if flags.any():
            tmp = sub.loc[flags.values, ["month", "category", "amount_bdt"]].copy()
            out.append(tmp)

    if out:
        flags_df = pd.concat(out).sort_values(["category", "month"])
        st.dataframe(flags_df)

        fig_a = px.line(
            view, x="month", y="amount_bdt", color="category",
            color_discrete_map=COLOR_MAP
        )
        A = pd.concat(out)
        fig_a.add_trace(
            go.Scatter(
                x=A["month"], y=A["amount_bdt"], mode="markers",
                marker=dict(size=9, color="#ff4d4f", symbol="circle-open"),
                name="Anomaly"
            )
        )
        st.plotly_chart(fig_a, use_container_width=True)
    else:
        st.success("No anomalies flagged for the selected categories.")

# -------- Tab 4: Share / Mix (donut + stacked area %) --------
with tab4:
    latest_month = view["month"].max()
    if pd.notnull(latest_month):
        last = (view[view["month"] == latest_month]
            .groupby("category", as_index=False)["amount_bdt"].sum())
        st.markdown(f"**Latest month mix:** {latest_month.date()}")
        pie = px.pie(
            last, names="category", values="amount_bdt", hole=0.55,
            color="category", color_discrete_map=COLOR_MAP
        )
        pie.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(pie, use_container_width=True)

    st.markdown("**Stacked area (share over time)**")
    mix = view.groupby(["month", "category"], as_index=False)["amount_bdt"].sum()
    area = px.area(
        mix, x="month", y="amount_bdt", color="category",
        groupnorm="fraction", color_discrete_map=COLOR_MAP
    )
    area.update_yaxes(tickformat=".0%")
    st.plotly_chart(area, use_container_width=True)

# --- export ---
st.download_button(
    "Download cleaned monthly CSV",
    data=view.to_csv(index=False),
    file_name="mfs_monthly_clean.csv",
)
