# VC Ecosystem Explorer — Project Context

This document summarizes the background, decisions, and current state of this project for
anyone (or any AI assistant) picking up the work. It captures reasoning that isn't visible
just from reading the code.

## 1. Project background

This is a course assignment for a Data Visualization class. The assignment requires:
- **Problem Definition** — define a data science/analytics problem, target users, and how an
  interactive app helps solve it.
- **Data Understanding** — data source/structure, EDA (trends, outliers, patterns), visual
  summaries.
- **Data Processing** — cleaning, transformations, feature engineering, and justification.
- **Visualization & Interaction Design** — explain visualization choices, interactions, user
  flow, and justify design decisions.
- **AI Usage Documentation** — list AI tools used, prompts, which AI capabilities were used
  (code generation, debugging, UI design, data analysis, visualization suggestions,
  refactoring, documentation, idea generation), and how outputs were validated.
- **Evaluation & Reflection** — strengths/limitations, what AI helped with vs. human
  decisions, lessons learned.
- **Deliverables** — report, source code, AI prompt appendix, working demo (10–15 min
  presentation).

**Dataset**: Kaggle "Startup Investments" by Justinas Cirtautas
(https://www.kaggle.com/datasets/justinas/startup-investments) — an 11-file CSV export of a
2013 Crunchbase snapshot: `objects`, `funding_rounds`, `people`, `funds`, `degrees`, `ipos`,
`relationships`, `offices`, `investments`, `milestones`, `acquisitions`.

**Team**: This is a group project. A teammate started the repo and did the initial EDA
(`eda.ipynb`); the user (not the teammate) is now building the Streamlit app (`app.py`) and
has been iterating on the notebook too.

**Repo**: https://github.com/Ell-29/VC_ecosystem — local folder name `VC_ecosystem/`.

## 2. Problem definition (as drafted for the report)

**Problem**: Startup funding data is fragmented and hard to interpret in raw form. The app
turns a large historical dataset into explorable visualizations of funding concentration,
outcome patterns, and investor activity.

**Target users**: (1) early-stage VC analysts screening markets/sectors, (2) founders
benchmarking their funding trajectory, (3) students/analysts studying startup financing
trends.

**Core decision-support question the app answers**: "Given a category, geography, or funding
stage, what does the historical funding and outcome pattern actually look like?"

**Important caveat to keep visible in the report/app**: this is a static 2013 snapshot, not
live data — should be framed as a historical/educational analytics tool, not a
predictive/live investment tool. Recent-year uptick in funding activity in the data partly
reflects Crunchbase's own data-recency/coverage improving over time, not pure market growth —
this nuance should not be overstated as a clean trend.

## 3. Dataset structure notes

- `objects` (462,651 rows, 40 cols) is the core table containing multiple entity types
  (companies, people, financial orgs). Filtered to `entity_type == "Company"` →
  `companies` (196,553 rows). This is the primary working table.
- Key columns on `companies`: `id`, `name`, `category_code`, `status` (operating/acquired/
  closed/ipo), `country_code`, `state_code`, `city`, `founded_at`, `closed_at`,
  `first_funding_at`, `last_funding_at`, `funding_rounds`, `funding_total_usd`.
- `funding_rounds` (52,928 rows): `object_id`, `funded_at`, `funding_round_type` (seed,
  angel, series-a/b/c...), `raised_amount_usd`.
- `investments` (80,902 rows): links `funding_round_id` → `investor_object_id`. Investor
  names can be recovered by mapping `investor_object_id` to `objects["name"]` via `id`.
- `acquisitions` (9,562 rows), `ipos` (1,259 rows): event-level tables for M&A / IPO timing.
- **Not yet used**: `people`, `degrees`, `relationships`, `offices`, `milestones`, `funds`.
  Considered but deprioritized — `people`/`relationships` could support a "founder
  background" angle (e.g. serial founders, education) as a future extension, not required.

### Data quality notes (from missing-value analysis)
- `objects.closed_at` (99.4% missing), `offices.created_at`/`updated_at` (100% missing),
  `people.birthplace` (87.6% missing) are effectively unusable.
- `funding_total_usd` is heavily right-skewed — log scale needed on funding-amount axes.
- No hard filtering of IPO'd/incumbent companies (e.g. Facebook, Twitter, Verizon
  Communications) was applied in the EDA or app data layer — see design decision below.

## 4. Key EDA findings (already validated, worth preserving/surfacing in the app)

1. **Category predicts exit type, not just company count.** Biotech has the highest overall
   exit rate (~18%) and uniquely leans toward IPO. Enterprise, software, and web lean toward
   acquisition as the dominant exit path. Consulting and "other" have the lowest exit rates,
   staying almost entirely "operating." (Chart: outcome rate % by category, stacked bar,
   normalized — NOT raw counts, which hide this pattern.)
2. **Time-to-first-funding differs by eventual outcome.** Companies that eventually "closed"
   got funded fastest (median ~300 days post-founding); companies that reached "ipo" took
   longest (median ~1,050 days). Caveat: likely partly a timeline-length artifact (IPO
   requires a longer overall company lifecycle to occur at all), not proof that slow funding
   causes success — frame as correlation, not causation.
3. Funding amounts are heavily right-skewed (log scale needed).
4. USA dominates by ~7x over the next-largest country (UK) in company count.
5. Software/web/"other" dominate by category count; funding-by-category (median) tells a
   different, complementary story (worth showing both count and $ dimensions).
6. Funding round size and count both grow with round stage (seed → later rounds), as
   expected.
7. Total funding and round count both show a sharp rise in the years leading up to 2013 in
   this dataset (recency-artifact caveat applies, see above).
8. Top investors by number of investments: Intel Capital, New Enterprise Associates, Sequoia
   Capital, SV Angel, Accel Partners, etc. — each with 450+ recorded investments.

## 5. Key design decisions (with reasoning — important not to silently reverse these)

- **IPO'd / already-public companies (e.g. Facebook, Twitter, Verizon Communications) are
  NOT filtered out anywhere in the data layer.** We explicitly decided against a hardcoded
  "startup" filter. Instead, `status` (including `ipo`) is exposed as an **interactive
  filter** in the app so users can toggle between "all entities," "startups only," etc.
  themselves. This was a deliberate choice to keep the data layer neutral and put the
  judgment call in the user's hands via the UI, rather than baking in an assumption.
- **Status filter defaults to ALL statuses selected** (not empty), consistent with the above
  — the first view a user sees should be the full picture, not a pre-filtered one.
- **Category and Country filters default to empty `[]`**, which the app logic interprets as
  "no filter applied" (show all) — chosen because pre-selecting specific values would be
  arbitrary given hundreds of possible options.
- Log scale on funding-amount axes is a **visualization-only** choice (does not transform
  underlying data) — this distinction matters for the "Data Processing" vs. "Visualization
  Design" report sections; log scale belongs in the latter.
- Correlation heatmap should only include meaningful numeric columns (funding_total_usd,
  funding_rounds, investment_rounds, invested_companies, milestones, relationships,
  founded_year) — NOT raw identifier/UI columns like entity_id, parent_id, logo_width/height,
  which dilute the heatmap.
- User-facing tables/displays should exclude internal/meaningless columns: `id`,
  `entity_id`, `parent_id`, `normalized_name`, `permalink`, `logo_url`, `logo_width`,
  `logo_height`, `created_by`, `created_at`, `updated_at`, `tag_list`. Long free-text fields
  (`overview`, `short_description`, `description`) should only appear in a future
  company-detail drill-down view, not in list/table views.
- Core columns worth showing in a clean summary table: `name`, `category_code`,
  `country_code`, `status`, `founded_year`, `funding_total_usd`, `funding_rounds` — displayed
  with human-readable renamed headers (e.g. "Total Funding (USD)" not `funding_total_usd`),
  via a `column_labels` dict + `.rename(columns=...)`, applied only to a display copy of the
  dataframe (never rename the working `filtered`/`companies` dataframes in place, since later
  charts/filters depend on the original column names).

## 6. Design/theme decisions

- Aesthetic direction: modeled on Crunchbase/PitchBook/CB Insights — calm, trustworthy,
  financial-data look, NOT a bright/playful palette. Originally a dark neutral background;
  switched to a light/white background on request (dark theme did not fit user preference).
- Theme file at `.streamlit/config.toml`:
  ```toml
  [theme]
  primaryColor="#2563EB"
  backgroundColor="#FFFFFF"
  secondaryBackgroundColor="#F1F3F6"
  textColor="#0E1117"
  font="sans serif"
  ```
  (Blue accent chosen over Streamlit's default red — reads as "finance/trust" and is more
  fitting for a VC analytics tool. Theme changes require a Streamlit server restart, not just
  a script rerun, to take effect.)
- Any chart that hardcodes a color assuming the background (e.g. marker border colors meant
  to blend into the page) needs to be checked against the current theme — the investor
  network's node border color in `app.py` was originally `#0E1117` to blend into the dark
  background and had to be changed to `#FFFFFF` when the theme flipped to light.
- **Planned but not yet implemented**: consistent status-based color coding across ALL charts
  (e.g. operating=neutral blue/gray, acquired=green, ipo=gold/amber, closed=muted
  red/gray — avoid harsh red for "closed" since it's an outcome, not necessarily framed as
  failure). Currently each matplotlib/seaborn chart in the notebook uses default colors
  inconsistently — this should be unified when porting charts into the app.
- Card-style metric summaries (`st.metric()`) at the top of the app are planned but not yet
  built (e.g. Total Companies / Total Funding / Avg Funding as headline numbers, in the style
  of PitchBook/Crunchbase dashboard headers).

## 7. Current state of `app.py`

Implemented so far, in this order in the file:
1. Imports (`streamlit`, `pandas`, `numpy`, `pathlib.Path`) + `st.set_page_config(layout="wide")`.
2. `load_data()` — cached (`@st.cache_data`), reads all CSVs from `data/` into a `dfs` dict.
3. `build_companies(dfs)` — cached, filters `objects` to `entity_type == "Company"`, parses
   date columns (`founded_at`, `closed_at`, `first_funding_at`, `last_funding_at`) to
   datetime, coerces `funding_total_usd`/`funding_rounds` to numeric, derives `founded_year`.
4. `dfs = load_data()`, `companies = build_companies(dfs)` called.
5. Title + a one-line `st.caption()` subtitle (carries the "historical snapshot, not live
   data" caveat). The earlier "Loaded N companies from M tables" debug line and the "Main
   questions" numbered list were both removed on request — they read as dev/notebook
   artifacts rather than product UI; the 5 guiding questions still belong in the written
   report's Problem Definition section, just not rendered in the live app.
6. `reset_filters()` callback function defined (sets all filter session_state keys back to
   defaults: empty category/country, all statuses, full year range).
7. Default session_state initialization (`if "key" not in st.session_state: ...`) for
   `selected_categories`, `selected_countries`, `selected_statuses`, `year_range`.
8. Sidebar filter form (`st.sidebar.form("filter_form")`) containing category/country/status
   multiselects and a founded-year range slider, each bound via `key=` directly to
   `session_state` (critical — this is what makes Reset work correctly; do NOT revert to
   manually copying widget values into session_state after the button, that pattern caused a
   `StreamlitAPIException` because Streamlit disallows modifying a widget's session_state key
   after that widget has been instantiated in the same run). Ends with
   `st.form_submit_button("Apply Filters")`.
9. `st.sidebar.button("Reset Filters", on_click=reset_filters)` — uses the `on_click` callback
   pattern specifically because callbacks run BEFORE widgets are re-instantiated in the next
   script run, avoiding the session_state conflict above. Do not replace this with a plain
   `if reset: ...` block followed by `st.rerun()` — that was the original broken approach.
10. Filtering logic: builds `filtered` from `companies.copy()`, applying category/country
    filters only `if` the list is non-empty, and always applying status + year range filters
    (since those always have valid defaults).
11. `st.write(f"Showing {len(filtered):,} companies after filters.")`.
12. Display table: `display_cols` list of 7 clean columns, `column_labels` rename dict, build
    `display_df = filtered[display_cols].rename(columns=column_labels)`, then
    `st.dataframe(display_df.head(20))`. (A currency-formatting step for
    `Total Funding (USD)` using `f"${x:,.0f}"` was suggested but may not yet be applied —
    check current file state.)

**Important ordering bug already encountered and fixed once**: the display table code was
briefly pasted BEFORE the filter section existed in the file, causing
`NameError: name 'filtered' is not defined`. Streamlit/Python execute top-to-bottom — any
reference to `filtered` must come after the full filter-building block. Watch for this
recurring if more sections get added/reordered.

**Not yet built**:
- Any actual charts in `app.py` (everything so far is data loading + filters + one table).
- `st.metric()` summary cards.
- Status-based consistent color palette applied to charts.
- Any of the 7 report-recommended charts (see below) ported into the app as interactive
  Plotly/Altair versions.
- A company-detail drill-down view.

## 8. `requirements.txt` notes

Was originally exported from a conda environment and contained several broken/nonexistent
pinned versions (e.g. a local `rattler-build` file path, `altair==6.2.2`, `anyio==4.14.1` —
none of which exist on PyPI). Resolved by stripping all version pins
(`sed -i '' -E 's/==[0-9a-zA-Z\.\-]+//' requirements.txt`) and letting pip resolve current
compatible versions. If `requirements.txt` is regenerated in the future, prefer doing so from
a plain `venv` (not conda) to avoid this recurring.

Key libraries available: `streamlit`, `pandas`, `plotly`, `matplotlib`, `seaborn`, `altair`,
`scikit-learn`, `pydeck`, `pyarrow`. Plotly/Altair/pydeck are available but not yet used in
`app.py` — worth switching to Plotly for the ported charts since it's natively interactive
(vs. static matplotlib) and fits the "Visualization & Interaction Design" assignment
requirement better.

## 9. `eda.ipynb` — current state and recommended charts for the report

Notebook is in good shape: sequential clean execution (`In[1]` through `In[36]`), all major
charts have descriptive captions written in plain language (not headers — team preference).

**7 charts recommended for the written report** (out of ~13 total in the notebook — the rest
support the narrative but aren't standalone report material):
1. Startup Status Distribution (bar)
2. Top 15 Startup Categories (bar)
3. Top 15 Countries by Number of Startups (bar)
4. Distribution of Total Funding (log-scale histogram)
5. Outcome Rate by Category (%) — stacked bar, normalized (strongest original insight)
6. Days to First Funding by Outcome (boxplot) — second-strongest original insight
7. Most Active Investors (horizontal bar)

**Known remaining cleanup items in the notebook** (may or may not be done yet — check current
file):
- A duplicate/redundant reload of `funding_rounds` (re-loads from `dfs.get("funding_rounds")`
  and re-parses dates/numerics that were already done earlier in the notebook) — should be
  deleted, just reuse the earlier `funding_rounds` variable.
- One caption ("Funding amounts are not evenly distributed... log scale") was misplaced
  earlier (sitting before the wrong chart) — should sit right before the "Distribution of
  Total Funding" histogram specifically.
- No closing "Key Takeaways" summary cell yet — recommended addition, pulling together the
  biggest findings for easy reuse in the report's Data Understanding section.
- No duplicate-row check yet in the missing-values section — recommended addition:
  `companies.duplicated().sum()` and `companies["id"].duplicated().sum()`.

## 10. Git workflow being used

Standard clone → branch → edit → commit → push → PR → merge workflow, since the user is new
to collaborative Git. Currently working on a personal branch (not `main`) inside a Python
`venv` (not conda) with `ipykernel` registered as `"Python (vc_ecosystem)"` for Jupyter.

## 11. Suggested next steps (as of this handoff)

1. Fix any remaining ordering issues in `app.py` (see section 7 caveat).
2. Add `st.metric()` summary cards near the top (Total Companies, Total Funding, Avg Funding
   — computed from `filtered`, not `companies`, so they respond to filters).
3. Port the 7 recommended charts into `app.py` using Plotly, driven by `filtered`, with a
   consistent status color palette (see section 6).
4. Apply the `.streamlit/config.toml` theme (create if not already present) and confirm it
   renders (blue accents instead of default red).
5. Consider adding a company-detail drill-down (search/select a company by name, show its
   full timeline).
6. Once app charts are stable, revisit and finalize the written report sections (Problem
   Definition, Data Understanding, Data Processing, Visualization & Interaction Design,
   Evaluation & Reflection) — drafts for Problem Definition, Data Understanding, and Data
   Processing already exist from this conversation and can be requested/reconstructed if
   needed.
