# Bangladesh Mobile Financial Services — Trends Dashboard

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-app-red.svg)
![Tests](https://github.com/<your-username>/mfs-trends-bd/actions/workflows/ci.yml/badge.svg)

An interactive **Streamlit** dashboard that ingests **Bangladesh Bank MFS** (Mobile Financial Services) tables (HTML/PDF), cleans them into monthly time series, and visualizes:

- **Amounts** by category (Cash In/Out, P2P, Merchant, Utility, Govt, Salary, Others)
- **MoM / YoY** growth
- **Seasonality & anomalies** (STL residuals)
- **Category mix** (donut + stacked area by %)
- **Downloadable CSV** of the cleaned data

> **Data mode:** the app automatically uses **live data** when available, and falls back to a **small sample dataset** if the source page/PDF is unavailable. You can force live-only mode with `MFS_ALLOW_SAMPLE=0`.

---

## 🚀 Live Demo

🔗 **App:** <https://<your-streamlit-url>>  
💻 **Code:** <https://github.com/Shamma-Samiha/mfs-trends-bd.git>

---

## 📸 Screenshots

Embed them like this:

<p align="center">
  <img src="assets/home1.png" alt="Home / Overview" width="49%"/>
  <img src="assets/home2.png" alt="" width="49%"/>
</p>
<p align="center">
  <img src="assets/category_mix.png" alt="Category Mix" width="49%"/>
  <img src="assets/category_mix2.png" alt="Category Mix" width="49%"/>
</p>

---

## 🧭 Table of Contents

- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Quickstart (Local)](#-quickstart-local)
- [Run Tests](#-run-tests)
- [Deploy (Streamlit Cloud)](#-deploy-streamlit-cloud)
- [Methodology](#-methodology)
- [Troubleshooting](#-troubleshooting)
- [Roadmap](#-roadmap)
- [License](#-license)

---

## ✨ Features

- **Robust ingestion**: tries HTML tables first; if structure changes, falls back to latest MFS PDF; if both fail, uses a **sample dataset** so the app still runs.
- **Clean ETL**: normalize headers, melt wide tables, parse dates, convert **crore BDT → BDT** (× 1e7).
- **Time-series analytics**: monthly aggregates, **MoM/YoY growth**, and **STL-based anomaly flags**.
- **Interactive UI**: category multiselect, moving-average smoothing, growth heatmap, donut chart, stacked area by share, CSV export.
- **CI-ready**: minimal **pytest** + **GitHub Actions** workflow.

---

## 🧰 Tech Stack

- **Python** · **pandas** · **numpy**
- **Streamlit** (UI)
- **plotly** (interactive charts)
- **statsmodels** (STL decomposition)
- **requests** · **BeautifulSoup** · **lxml** (HTML) · **pdfplumber** (PDF)

---

## 🗂 Project Structure

mfs-trends-bd/
├─ app/
│ └─ streamlit_app.py # Streamlit UI
├─ src/
│ ├─ init.py
│ ├─ fetch.py # fetch HTML/PDF (live) or sample data
│ ├─ etl.py # cleaning: tidy monthly format
│ └─ metrics.py # aggregates, growth, anomalies
├─ tests/
│ └─ test_metrics.py # tiny example test
├─ .github/workflows/ci.yml # GitHub Actions (pytest on push)
├─ .streamlit/config.toml # (optional) theme config
├─ requirements.txt
├─ README.md
├─ LICENSE
└─ assets/ # screenshots (not required but recommended)

---

## ⚡ Quickstart (Local)

> Use a virtual environment; run these **from the project root**.

**Windows (PowerShell)**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app\streamlit_app.py

## 📐 Methodology

- **Source:** Bangladesh Bank — Mobile Financial Services (MFS) monthly comparative statements (HTML/PDF).
- **Ingestion:** 
  - Try HTML tables first (`pandas.read_html` with `lxml`), 
  - fall back to the latest MFS PDF (`pdfplumber`), 
  - final fallback is a small **sample dataset** so the app always runs.
- **Cleaning (ETL):**
  - Normalize headers (handle `None` / “Unnamed” columns).
  - Reshape wide sheets to **long** format where needed.
  - Parse dates to pandas `datetime` (month start).
  - Convert **crore BDT → BDT** by multiplying **× 1e7**.
  - Keep standard categories: Cash In/Out, P2P, Merchant Payment, Utility Bill Payment (P2B), Government Payment, Salary Disbursement (B2P), Others.
- **KPIs:**
  - **MoM** = (current − previous month) / previous month.
  - **YoY** = (current − same month last year) / same month last year.
  - **Anomalies:** STL decomposition (statsmodels); flag residuals with |z| > 2.
- **Visualization:**
  - Amounts by category (line; auto-bar if only one month).
  - Growth lines (MoM/YoY) + YoY heatmap (when ≥ 13 months).
  - Donut for latest month mix + stacked area (share over time).
- **Export:** Download cleaned monthly CSV for audit/replication.
## 🙌 Acknowledgments

- **Bangladesh Bank** for publishing MFS statistics.
- **Streamlit**, **pandas**, **plotly**, **statsmodels**, **BeautifulSoup**, **lxml**, **pdfplumber** — the open-source tools powering this project.
- The broader Python community for documentation, examples, and packages that make data apps fast to build.
## 📫 Contact

- Author: **<Shamma Samiha>**
- LinkedIn: <https://www.linkedin.com/in/shamma-samiha-4b029b246/>
- GitHub: <https://github.com/Shamma-Samiha>
- Email: <shmmsamiha@gmail.com>


