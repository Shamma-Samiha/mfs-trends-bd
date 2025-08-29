from __future__ import annotations
import pandas as pd
from statsmodels.tsa.seasonal import STL

CATEGORIES = [
    "Cash In","Cash Out","P2P","Utility Bill Payment (P2B)",
    "Merchant Payment","Government Payment","Salary Disbursement (B2P)","Others"
]

def aggregate_monthly(tidy_df: pd.DataFrame) -> pd.DataFrame:
    g = (
        tidy_df.assign(month=lambda d: d["date"].dt.to_period("M").dt.to_timestamp())
               .groupby(["month","category"], as_index=False)["amount_bdt"].sum()
    )
    return g

def add_growth(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["category","month"]).copy()
    df["mom"] = df.groupby("category")["amount_bdt"].pct_change()
    df["yoy"] = df.groupby("category")["amount_bdt"].pct_change(12)
    return df

def seasonal_anomaly(series: pd.Series) -> pd.Series:
    # STL residual z-score; flags |z|>2
    idx = series.index
    s = series.astype(float).fillna(method="ffill")
    if len(s) < 24:  # need at least 2 years for stable seasonality
        return pd.Series([False]*len(s), index=idx)
    stl = STL(s, period=12, robust=True).fit()
    resid = (stl.resid - stl.resid.mean())/stl.resid.std(ddof=0)
    return resid.abs() > 2.0