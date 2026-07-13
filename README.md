# VC Ecosystem Explorer

A guided drill-down Streamlit app over a historical Crunchbase snapshot (~2013).
Walks from a world map of capital → a chosen country → a chosen sector → its
investors → a single company benchmarked against its cohort.

Two entry points:

- `app_v2.py` — the current, guided drill-down version (recommended)
- `app.py` — the earlier tabbed explorer (kept for reference)

## Quick start (local)

### 1. Prerequisites

- Python 3.10, 3.11, or 3.12 (matplotlib wheels for Python 3.14 are still
  patchy on Windows — pin to 3.11 if you hit install issues)
- `git`

### 2. Clone

```powershell
git clone https://github.com/Ell-29/VC_ecosystem.git
cd VC_ecosystem
```

### 3. Install Python dependencies

```powershell
pip install -r requirements.txt
```

### 4. Get the data

The CSVs (~200MB total) are **not** committed to this repo — GitHub's file
limit is 100MB. Download the zip from the shared link below and unzip it so
the folder ends up at `./data/` inside the repo root:

> **Data zip:** _<paste your Dropbox / Drive share link here>_

After unzipping you should have:

```
VC_ecosystem/
  data/
    objects.csv
    funding_rounds.csv
    investments.csv
    acquisitions.csv
    ipos.csv
    ... (11 CSVs total)
  app.py
  app_v2.py
  requirements.txt
```

### 5. Run

```powershell
streamlit run app_v2.py
```

Open http://localhost:8501 in a browser.

## What the app does

**Step 1 — World map.** Total capital raised by country, log-scaled. Click a
country (or use the Sankey jump control below) to drill in.

**Step 2 — Country view.** Funding + deal flow by year, a bubble cloud of
sectors (size = total funding), and two clickable sector bar charts (exit
rate, total funding). Pick a sector.

**Step 3 — Sector deep-dive.** Outcome mix, years-to-first-funding by
outcome, capital over time, and rounds by stage — all scoped to your chosen
country × sector.

**Step 4 — Investors.** Ranked bar + co-investment network for investors
active in this country × sector. Click one to open their scoped company
table.

**Step 5 — Company vs. cohort.** A cumulative funding curve for the selected
company against the median total raised of every funded peer in the same
country × sector, plus a bipartite Investor ↔ Company star explorer for
lateral exploration.

## Deploy to Streamlit Cloud (optional)

1. Push this repo to GitHub (already done if you're reading this on GitHub).
2. Go to https://share.streamlit.io, sign in with GitHub.
3. **New app** → pick this repo, set the entry point to `app_v2.py`.
4. Because the data isn't in the repo, the cloud runtime won't have it. Two
   ways to fix that:
   - Host the CSVs at a public URL and add a small download-on-first-run
     shim to `load_data()`, **or**
   - Attach the CSVs as a GitHub Release asset (2GB limit) and download
     them at startup.
   Say the word and this can be wired up.

## File overview

| File | Purpose |
|------|---------|
| `app_v2.py` | Main drill-down app |
| `app.py` | Original tabbed explorer |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Keeps CSVs and local tooling out of git |
