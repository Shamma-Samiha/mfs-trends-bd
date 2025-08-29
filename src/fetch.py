from __future__ import annotations
import io, os, re, requests, pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Official landing page; if this ever moves, update here
BB_MFS_PAGE = "https://www.bb.org.bd/en/index.php/financialactivity/mfsdata"
# A known "latest trend" PDF path (used as a fallback if discovery fails)
BB_MFS_TREND_PDF = "https://www.bb.org.bd/fnansys/paymentsys/mfstrend_latest.pdf"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36"
}

def get_html() -> str:
    r = requests.get(BB_MFS_PAGE, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def read_html_tables(html: str) -> list[pd.DataFrame]:
    """Use pandas.read_html (requires lxml). Falls back to parsing <table> tags if needed."""
    tables = []
    try:
        tables = pd.read_html(html)  # needs lxml
    except Exception:
        pass
    if not tables:
        soup = BeautifulSoup(html, "html.parser")
        raw_tables = soup.find_all("table")
        for t in raw_tables:
            try:
                tables.append(pd.read_html(str(t))[0])
            except Exception:
                continue
    return tables

def discover_pdf_url(html: str) -> str | None:
    """Find a likely MFS PDF link on the page."""
    soup = BeautifulSoup(html, "html.parser")
    cands = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        low = href.lower()
        if "pdf" in low and "mfs" in low:   # heuristic
            cands.append(href)
    if cands:
        return urljoin(BB_MFS_PAGE, cands[0])
    return None

def get_pdf_table(pdf_url: str) -> pd.DataFrame:
    import pdfplumber
    r = requests.get(pdf_url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        # try first page; some PDFs hold the summary there
        page = pdf.pages[0]
        table = page.extract_table()
    if not table:
        raise RuntimeError("No table on first PDF page.")
    df = pd.DataFrame(table[1:], columns=table[0])
    return df

def sample_raw() -> pd.DataFrame:
    """Small synthetic long-format sample so the app still runs during source outages."""
    rows = []
    months = pd.period_range("2024-01", "2024-12", freq="M").to_timestamp()
    cats = [
        "P2P","Merchant Payment","Cash In","Cash Out",
        "Utility Bill Payment (P2B)","Government Payment","Salary Disbursement (B2P)","Others"
    ]
    import numpy as np
    rng = np.random.default_rng(42)
    for m in months:
        for i, c in enumerate(cats):
            base = [8, 4, 20, 19, 2, 1, 1.5, 0.5][i]  # crore BDT
            noise = rng.normal(0, base*0.08)
            rows.append({"month": m.strftime("%Y-%m-01"), "category": c, "amount_crore_bdt": max(base+noise, 0.1)})
    return pd.DataFrame(rows)

def fetch_raw() -> pd.DataFrame:
    """Return the widest useful table (HTML preferred) else a PDF, else a small sample."""
    # allow disabling sample fallback: set env var MFS_ALLOW_SAMPLE=0
    allow_sample = os.environ.get("MFS_ALLOW_SAMPLE", "1") != "0"
    try:
        html = get_html()
        tables = read_html_tables(html)
        if tables:
            # prefer the table with the most columns
            df = max(tables, key=lambda d: d.shape[1])
            df["source"] = "html"
            return df
        # try a discovered PDF on the page
        pdf_url = discover_pdf_url(html) or BB_MFS_TREND_PDF
        df = get_pdf_table(pdf_url)
        df["source"] = "pdf"
        return df
    except Exception as e:
        print(f"[fetch_raw] WARNING: {e}")
        if allow_sample:
            df = sample_raw()
            df["source"] = "sample"
            return df
        # no fallback; propagate error
        raise
