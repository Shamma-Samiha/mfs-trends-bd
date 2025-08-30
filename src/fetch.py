# src/fetch.py
from __future__ import annotations

import io
import os
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

# --- Source endpoints ---------------------------------------------------------
# Official landing page (update here if the site structure moves)
BB_MFS_PAGE = "https://www.bb.org.bd/en/index.php/financialactivity/mfsdata"
# Known "latest trend" PDF (fallback if discovery fails)
BB_MFS_TREND_PDF = "https://www.bb.org.bd/fnansys/paymentsys/mfstrend_latest.pdf"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

# Project root (…/repo), so we can find data/mfs_manual.csv reliably
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# --- Optional: merge extra manual history if present -------------------------
def _append_manual_if_present(df: pd.DataFrame) -> pd.DataFrame:
    """
    If data/mfs_manual.csv exists, merge it with the raw dataframe and keep the
    *latest* value for each (month, category). The manual file should be in one of:
      - month,category,amount_bdt
      - month,category,amount_crore_bdt   (will be converted to amount_bdt)
    """
    manual_path = os.path.join(ROOT, "data", "mfs_manual.csv")
    if not os.path.exists(manual_path):
        return df

    try:
        manual = pd.read_csv(manual_path, parse_dates=["month"])
    except Exception as e:
        print(f"[manual] Could not read {manual_path}: {e}")
        return df

    # Normalize manual columns → amount_bdt
    cols = {c.lower().strip(): c for c in manual.columns}
    if "amount_bdt" in cols:
        manual["amount_bdt"] = pd.to_numeric(
            manual[cols["amount_bdt"]], errors="coerce"
        ).fillna(0)
    elif "amount_crore_bdt" in cols:
        manual["amount_bdt"] = pd.to_numeric(
            manual[cols["amount_crore_bdt"]], errors="coerce"
        ).fillna(0) * 1e7  # crore → BDT
    else:
        print("[manual] No amount_bdt/amount_crore_bdt column found; skipping merge.")
        return df

    manual["category"] = manual[cols.get("category", "category")].astype(str)
    manual["month"] = pd.to_datetime(manual[cols.get("month", "month")])

    manual = manual[["month", "category", "amount_bdt"]].copy()

    # Append and keep the latest value per (month, category)
    try:
        merged = pd.concat([df, manual], ignore_index=True)
        merged = (
            merged.drop_duplicates(subset=["month", "category"], keep="last")
            .sort_values(["month", "category"])
            .reset_index(drop=True)
        )
        return merged
    except Exception as e:
        # If the raw df doesn't yet have month/category columns (e.g., pre-tidy HTML),
        # it's still ok to return the original df; we'll merge post-tidy in the app.
        print(f"[manual] Merge failed (non-fatal): {e}")
        return df


# --- Fetch helpers -----------------------------------------------------------
def get_html() -> str:
    r = requests.get(BB_MFS_PAGE, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def read_html_tables(html: str) -> list[pd.DataFrame]:
    """Try pandas.read_html; if nothing found, parse each <table> with BeautifulSoup."""
    tables: list[pd.DataFrame] = []
    try:
        tables = pd.read_html(html)  # requires lxml
    except Exception:
        pass
    if not tables:
        soup = BeautifulSoup(html, "html.parser")
        for t in soup.find_all("table"):
            try:
                tables.append(pd.read_html(str(t))[0])
            except Exception:
                continue
    return tables


def discover_pdf_url(html: str) -> str | None:
    """Find a likely MFS PDF link on the page."""
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        low = href.lower()
        if "pdf" in low and "mfs" in low:
            candidates.append(href)
    if candidates:
        return urljoin(BB_MFS_PAGE, candidates[0])
    return None


def get_pdf_table(pdf_url: str) -> pd.DataFrame:
    import pdfplumber

    r = requests.get(pdf_url, headers=HEADERS, timeout=30)
    r.raise_for_status()

    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        # Find the first page that actually has a table
        table = None
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                break

    if not table:
        raise RuntimeError("No table found in PDF.")

    df = pd.DataFrame(table[1:], columns=table[0])
    return df


# --- Sample for resilience ----------------------------------------------------
def sample_raw() -> pd.DataFrame:
    """Small synthetic long-format sample so the app still runs during source outages."""
    rows = []
    months = pd.period_range("2024-01", "2024-12", freq="M").to_timestamp()
    cats = [
        "P2P",
        "Merchant Payment",
        "Cash In",
        "Cash Out",
        "Utility Bill Payment (P2B)",
        "Government Payment",
        "Salary Disbursement (B2P)",
        "Others",
    ]
    import numpy as np

    rng = np.random.default_rng(42)
    for m in months:
        for i, c in enumerate(cats):
            base = [8, 4, 20, 19, 2, 1, 1.5, 0.5][i]  # crore BDT
            noise = rng.normal(0, base * 0.08)
            rows.append(
                {
                    "month": m.strftime("%Y-%m-01"),
                    "category": c,
                    "amount_crore_bdt": max(base + noise, 0.1),
                }
            )
    return pd.DataFrame(rows)


# --- Public API ---------------------------------------------------------------
def fetch_raw() -> pd.DataFrame:
    """
    Return the widest useful raw table:
      - Try HTML tables from the landing page.
      - Else try a discovered PDF (or known latest-trend PDF).
      - Else fall back to a small synthetic sample (unless MFS_ALLOW_SAMPLE=0).
    Regardless of the branch, we then append manual history if present.
    """
    allow_sample = os.environ.get("MFS_ALLOW_SAMPLE", "1") != "0"
    df: pd.DataFrame | None = None

    try:
        html = get_html()
        tables = read_html_tables(html)
        if tables:
            # prefer the table with the most columns
            df = max(tables, key=lambda d: d.shape[1]).copy()
            df["source"] = "html"
        else:
            pdf_url = discover_pdf_url(html) or BB_MFS_TREND_PDF
            df = get_pdf_table(pdf_url)
            df["source"] = "pdf"
    except Exception as e:
        print(f"[fetch_raw] WARNING: {e}")
        if allow_sample:
            df = sample_raw()
            df["source"] = "sample"
        else:
            raise

    # Append manual history if available (non-fatal if shapes differ)
    df = _append_manual_if_present(df)
    return df
