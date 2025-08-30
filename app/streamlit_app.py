# app/streamlit_app.py
# --- make project root importable (because this file is in /app) ---
import os, sys
from pathlib import Path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# --- libs ---
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px

# --- local modules ---
from src.fetch import fetch_raw, sample_raw
from src.etl import tidy
from src.metrics import aggregate_monthly, add_growth, seasonal_anomaly

# --- page setup ---
st.set_page_config(page_title="Bangladesh MFS Trends", layout="wide")
st.title("Bangladesh Mobile Financial Services — Trends Dashboard")
st.caption("Source: Bangladesh Bank MFS statistics (latest monthly comparative statements).")
st.caption("Data mode: live if available, otherwise sample")

# ---------------------------------------------------------------
# Data loading with manual CSV merge AFTER tidy (canonical schema)
# ---------------------------------------------------------------
@st.cache_data(ttl=60 * 60)
def load_data() -> pd.DataFrame:
    # 1) fetch raw (html -> pdf -> sample)
    try:
        raw = fetch_raw()
    except Exception as e:
        print("fetch_raw failed, using sample:", e)
        raw = sample_raw()

    # 2) tidy to canonical columns: month (datetime), category (str), amount_bdt (float)
    clean = tidy(raw)

    # 3) merge manual history if present: data/mfs_manual.csv
    manual_path = Path(ROOT) / "data" / "mfs_manual.csv"
    if manual_path.exists():
        try:
            manual = pd.read_csv(manual_path, parse_dates=["month"])
            # accept either amount_bdt or amount_crore_bdt
            if "amount_bdt" not in manual.columns and "amount_crore_bdt" in manual.columns:
                manual["amount_bdt"] = pd.to_numeric(manual["amount_crore_bdt"], errors="coerce").fillna(0) * 1e7
            manual = manual[["month", "category", "amount_bdt"]].copy()
            manual["category"] = manual["category"].astype(str)
            manual["amount_bdt"] = pd.to_numeric(manual["amount_bdt"], errors="coerce").fillna(0)

            clean = pd.concat(
                [clean[["month", "category", "amount_bdt"]], manual],
                ignore_index=True,
            )
            # keep latest value per (month, category)
            clean = (
                clean.drop_duplicates(subset=["month", "category"], keep="last")
                     .sort_values(["month", "category"])
                     .reset_index(drop=True)
            )
        except Exception as e:
            st.warning(f"Manual CSV found but could not be merged: {e}")

    # 4) monthly metrics
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

# --- quick debug so you can confirm it worked ---
st.caption(
    f"Distinct months: {df['month'].dt.to_period('M').nunique()} "
    f"(range: {df['month'].min().date() if pd.notnull(df['month'].min()) else 'n/a'}"
    f" → {df['month'].max().date() if pd.notnull(df['month'].max()) else 'n/a'})"
)

if df.empty:
    st.error("No data parsed. Try again later or check source URLs in src/fetch.py")
    st.stop()

# --- controls ---
cats = sorted(df["category"].unique().tolist())
pick = st.multiselect("Choose categories", cats, default=cats)
view = df[df["category"].isin(pick)]

latest = view["month"].max()
st.info(f"Latest month in data: {latest.date() if pd.notnull(latest) else 'unknown'}")

# --- KPI row ---
col1, col2, col3 = st.columns(3)
with col1:
    total_latest = view[view["month"] == latest]["amount_bdt"].sum()
    st.metric("Total (latest)", f"{int(total_latest):,} BDT")
with col2:
    mom_val = view[view["month"] == latest]["mom"].mean() if "mom" in view else None
    st.metric("MoM", f"{mom_val:.1%}" if pd.notnull(mom_val) else "—")
with col3:
    yoy_val = view[view["month"] == latest]["yoy"].mean() if "yoy" in view else None
    st.metric("YoY", f"{yoy_val:.1%}" if pd.notnull(yoy_val) else "—")

# --- tabs ---
tab1, tab2, tab3, tab4 = st.tabs(["Amounts (BDT)", "Growth (MoM/YoY)", "Anomalies", "Category mix (%)"])

with tab1:
    # Show bar if only 1 month; line otherwise
    n_months = view["month"].dt.to_period("M").nunique()
    if n_months < 2:
        st.info("Only one month of data available — showing a bar chart instead of a trend line.")
        fig = px.bar(view, x="category", y="amount_bdt", color="category")
    else:
        fig = px.line(view, x="month", y="amount_bdt", color="category", markers=True)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    gsel = st.selectbox("Growth metric", ["mom", "yoy"], index=1)
    n_months = view["month"].dt.to_period("M").nunique()
    if n_months < 2:
        st.info("Need at least 2 months for growth.")
    else:
        fig = px.line(view, x="month", y=gsel, color="category", markers=True)
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    out = []
    for c, sub in view.groupby("category"):
        s = sub.set_index("month")["amount_bdt"]
        try:
            flags = seasonal_anomaly(s)
        except Exception:
            # if not enough points for STL, mark all False
            flags = pd.Series(False, index=s.index)
        out.append(pd.DataFrame({"month": s.index, "category": c, "anomaly": flags.values}))
    flags_df = pd.concat(out)
    st.dataframe(flags_df[flags_df["anomaly"]])

with tab4:
    mix = view.groupby(["month", "category"], as_index=False)["amount_bdt"].sum()
    fig = px.area(mix, x="month", y="amount_bdt", color="category", groupnorm="fraction")
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)

# --- export ---
st.download_button(
    "Download cleaned monthly CSV",
    data=view.to_csv(index=False),
    file_name="mfs_monthly_clean.csv",
)
