from __future__ import annotations
import re
import pandas as pd
import numpy as np
from .fetch import fetch_raw

# Map loose column names to canonical ones
CANON = {
    "month": "month",
    "month ": "month",
    "particulars": "category",
    "items": "category",
    "amount (in crore bdt)": "amount_crore_bdt",
    "amount(in crore bdt)": "amount_crore_bdt",
    "value(in crore bdt)": "amount_crore_bdt",
    "p2p": "P2P",
    "merchant payment": "Merchant Payment",
    "cash in": "Cash In",
    "cash out": "Cash Out",
    "salary disbursement (b2p)": "Salary Disbursement (B2P)",
    "utility bill payment (p2b)": "Utility Bill Payment (P2B)",
    "government payment": "Government Payment",
    "others": "Others",
}

def re_date(s: str) -> bool:
    return bool(re.search(r"\b(20\d{2}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", str(s), re.I))

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # 1) Coerce headers to strings even if they are None
    normed = []
    for c in df.columns:
        c = "" if c is None else str(c)
        normed.append(c.strip().lower())
    df.columns = normed

    # 2) Drop empty/unnamed columns that come from merged cells in PDFs
    drop_cols = [c for c in df.columns if c == "" or c.startswith("unnamed")]
    if drop_cols:
        df = df.drop(columns=drop_cols)

    # 3) Also drop columns that are entirely empty (all NaN)
    df = df.dropna(axis=1, how="all")

    # 4) Apply canonical rename map
    df = df.rename(columns={c: CANON.get(c, c) for c in df.columns})
    return df


def tidy(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)  # <- already drops empty cols

    # Wide->long: if we don't have explicit amount column, try melting month columns
    if "amount_crore_bdt" not in df.columns:
        mcols = [c for c in df.columns if re_date(c)]
        id_vars = [c for c in df.columns if c not in mcols]
        if mcols:
            df = df.melt(id_vars=id_vars, value_vars=mcols, var_name="month", value_name="amount_crore_bdt")

    # Create category column where needed
    if "category" not in df.columns:
        first_col = df.columns[0]
        df["category"] = df[first_col]

    # Clean numeric (handle blanks, commas, weird characters)
    val = (
    df["amount_crore_bdt"]
      .astype(str)
      .str.replace(",", "", regex=False)
      .str.replace("\u00a0", " ", regex=False)  # non-breaking space
      .str.replace(r"[^\d.\-]", "", regex=True)  # keep digits/dot/minus only
      .str.strip()
   )
    df["amount_crore_bdt"] = pd.to_numeric(val, errors="coerce")

    # Drop rows where we still couldn't read a number
    df = df[~df["amount_crore_bdt"].isna()]


    # Parse date
    if "month" in df.columns:
        df["date"] = pd.to_datetime(df["month"], errors="coerce", dayfirst=True)
    elif "year" in df.columns:
        df["date"] = pd.to_datetime(df["year"].astype(str) + "-01-01", errors="coerce")

    # Keep likely MFS rows
    df["category"] = df["category"].astype(str).str.strip()
    df = df[df["category"].str.contains("cash|p2p|utility|merchant|government|salary|others", case=False, na=False)]

    # Convert crore BDT -> BDT
    df["amount_bdt"] = df["amount_crore_bdt"] * 1e7

    out = df[["date", "category", "amount_bdt"]].dropna()
    return out


def fetch_and_tidy() -> pd.DataFrame:
    raw = fetch_raw()
    return tidy(raw)