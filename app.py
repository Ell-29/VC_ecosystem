import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import networkx as nx
import pycountry
from pathlib import Path

st.set_page_config(
    page_title="VC Ecosystem Explorer",
    layout="wide"
)

DATA_DIR = Path("data")

STATUS_COLORS = {
    "operating": "#64748B",
    "acquired": "#22C55E",
    "ipo": "#F59E0B",
    "closed": "#94A3B8",
}

# category_code is raw Crunchbase data (snake_case) and stays that way in filtering logic —
# this only controls how it's displayed. Most codes are fine with underscore-to-space plus
# title case; a few need an explicit override to read naturally ("Games & Video" rather than
# the literal "Games Video", "E-Commerce" rather than "Ecommerce").
CATEGORY_LABELS = {
    "games_video": "Games & Video",
    "photo_video": "Photo & Video",
    "ecommerce": "E-Commerce",
}

def category_label(code):
    if pd.isna(code):
        return code
    return CATEGORY_LABELS.get(code, str(code).replace("_", " ").title())

# country_code is ISO-3 (e.g. "USA") and stays that way in filtering logic and in the
# choropleth's `locations` (required for the map to place countries correctly) — this only
# controls display text. pycountry resolves most codes to their official ISO name, but a) a
# few of those official names are unnecessarily formal for a dashboard ("Korea, Republic of",
# "Russian Federation") so we override with the common name, and b) a handful of codes in this
# Crunchbase export are deprecated or non-standard and aren't in pycountry at all — for those,
# fall back to the raw code rather than guessing.
COUNTRY_NAMES = {country.alpha_3: country.name for country in pycountry.countries}
COUNTRY_NAMES.update({
    "BOL": "Bolivia",
    "IRN": "Iran",
    "KOR": "South Korea",
    "MDA": "Moldova",
    "PRK": "North Korea",
    "RUS": "Russia",
    "TWN": "Taiwan",
    "TZA": "Tanzania",
    "VEN": "Venezuela",
    "VGB": "British Virgin Islands",
    "VIR": "U.S. Virgin Islands",
    "VNM": "Vietnam",
    "ROM": "Romania",              # deprecated ISO code, not in pycountry
    "ANT": "Netherlands Antilles", # deprecated ISO code, not in pycountry
})

def country_label(code):
    if pd.isna(code):
        return code
    return COUNTRY_NAMES.get(code, code)

# Regional bucket for "zoom the map to this country" — Plotly's geo `scope` only supports
# continent-level regions (no true single-country zoom without a separate lat/lon centroid
# table), so clicking a country zooms to its region rather than a tight box around just it.
# Not exhaustive — codes missing here just leave the map at the world view.
COUNTRY_SCOPES = {
    **{c: "north america" for c in [
        "USA", "CAN", "MEX", "ATG", "BHS", "BLZ", "BMU", "BRB", "CRI", "CUB", "CYM", "DMA",
        "DOM", "GRD", "GTM", "HND", "HTI", "JAM", "NIC", "PAN", "PRI", "SLV", "TTO", "VCT",
        "VGB", "VIR", "AIA", "ANT", "GLP", "MTQ",
    ]},
    **{c: "south america" for c in [
        "ARG", "BOL", "BRA", "CHL", "COL", "ECU", "PER", "PRY", "SUR", "URY", "VEN",
    ]},
    **{c: "europe" for c in [
        "ALB", "AND", "AUT", "BEL", "BGR", "BIH", "BLR", "CHE", "CYP", "CZE", "DEU", "DNK",
        "ESP", "EST", "FIN", "FRA", "GBR", "GIB", "GRC", "HRV", "HUN", "IRL", "ISL", "ITA",
        "LIE", "LTU", "LUX", "LVA", "MCO", "MDA", "MKD", "MLT", "NLD", "NOR", "POL", "PRT",
        "ROM", "RUS", "SMR", "SVK", "SVN", "SWE", "TUR", "UKR", "GEO",
    ]},
    **{c: "africa" for c in [
        "AGO", "BDI", "BEN", "BWA", "CIV", "CMR", "DZA", "EGY", "ETH", "GHA", "GIN", "KEN",
        "LSO", "MAR", "MDG", "MUS", "NAM", "NER", "NGA", "REU", "RWA", "SDN", "SEN", "SLE",
        "SOM", "SWZ", "SYC", "TUN", "TZA", "UGA", "ZAF", "ZMB", "ZWE",
    ]},
    **{c: "asia" for c in [
        "AFG", "ARE", "ARM", "AZE", "BGD", "BHR", "BRN", "CHN", "HKG", "IDN", "IND", "IOT",
        "IRN", "IRQ", "ISR", "JOR", "JPN", "KAZ", "KGZ", "KHM", "KOR", "KWT", "LAO", "LBN",
        "LKA", "MAC", "MDV", "MMR", "MYS", "NPL", "OMN", "PAK", "PHL", "PRK", "QAT", "SAU",
        "SGP", "SYR", "TJK", "THA", "TWN", "UZB", "VNM", "YEM",
    ]},
    **{c: "oceania" for c in [
        "AUS", "NZL", "NCL", "NFK", "NRU", "PCN", "UMI",
    ]},
}

def polish(fig):
    # Plotly's default hoverlabel alignment ("auto") flips to right-aligned text when the
    # tooltip renders to the left of the cursor, which breaks the key/value column layout.
    # Force left alignment so hover text reads consistently regardless of tooltip position.
    fig.update_layout(hoverlabel=dict(align="left"))
    return fig

@st.cache_data
def load_data():
    dfs = {}
    for file in DATA_DIR.glob("*.csv"):
        dfs[file.stem] = pd.read_csv(file, low_memory=False)
    return dfs

@st.cache_data
def build_companies(dfs):
    objects = dfs["objects"]
    companies = objects[objects["entity_type"] == "Company"].copy()

    date_cols = ["founded_at", "closed_at", "first_funding_at", "last_funding_at"]
    for col in date_cols:
        companies[col] = pd.to_datetime(companies[col], errors="coerce")

    num_cols = ["funding_total_usd", "funding_rounds"]
    for col in num_cols:
        companies[col] = pd.to_numeric(companies[col], errors="coerce")

    companies["founded_year"] = companies["founded_at"].dt.year
    return companies

@st.cache_data
def build_funding_rounds(dfs):
    funding_rounds = dfs["funding_rounds"].copy()
    funding_rounds["funded_at"] = pd.to_datetime(funding_rounds["funded_at"], errors="coerce")
    funding_rounds["funded_year"] = funding_rounds["funded_at"].dt.year
    funding_rounds["raised_amount_usd"] = pd.to_numeric(funding_rounds["raised_amount_usd"], errors="coerce")
    return funding_rounds

@st.cache_data
def build_investor_network(dfs, top_n=40, min_edge_weight=2):
    investments = dfs["investments"].dropna(subset=["funding_round_id", "investor_object_id"])
    investor_counts = investments["investor_object_id"].value_counts()
    top_investors = investor_counts.head(top_n).index

    inv_subset = investments[investments["investor_object_id"].isin(top_investors)]

    edge_weights = {}
    for _, group in inv_subset.groupby("funding_round_id"):
        investors = group["investor_object_id"].unique()
        if len(investors) < 2:
            continue
        for i in range(len(investors)):
            for j in range(i + 1, len(investors)):
                pair = tuple(sorted((investors[i], investors[j])))
                edge_weights[pair] = edge_weights.get(pair, 0) + 1

    # Only keep edges backed by repeated co-investment — a single shared round is common
    # noise at this scale and is what turns the layout into an unreadable hairball.
    edge_weights = {pair: w for pair, w in edge_weights.items() if w >= min_edge_weight}

    names = dfs["objects"].set_index("id")["name"]

    graph = nx.Graph()
    for investor_id in top_investors:
        graph.add_node(
            investor_id,
            name=names.get(investor_id, str(investor_id)),
            investments=int(investor_counts[investor_id]),
        )
    for (a, b), weight in edge_weights.items():
        graph.add_edge(a, b, weight=weight)

    # Wider spacing than the default (roughly 1/sqrt(n)) so labels and nodes don't overlap.
    k = 4 / (len(graph) ** 0.5)
    pos = nx.spring_layout(graph, seed=42, k=k, iterations=150)
    return graph, pos

dfs = load_data()
companies = build_companies(dfs)
funding_rounds = build_funding_rounds(dfs)

st.title("VC Ecosystem Explorer")
st.caption(
    "Explore startup funding, outcomes, and investor activity across a historical "
    "Crunchbase snapshot (2013) — a research and benchmarking tool, not a live feed."
)

def reset_filters():
    st.session_state["selected_categories"] = []
    st.session_state["selected_countries"] = []
    st.session_state["selected_statuses"] = []
    min_year = int(companies["founded_year"].min(skipna=True))
    max_year = int(companies["founded_year"].max(skipna=True))
    st.session_state["year_range"] = (min_year, max_year)

# --- defaults, only set once ---
if "selected_categories" not in st.session_state:
    st.session_state["selected_categories"] = []
if "selected_countries" not in st.session_state:
    st.session_state["selected_countries"] = []
if "selected_statuses" not in st.session_state:
    # Empty means "no filter" (same convention as category/country below), not "show nothing" —
    # keeps the sidebar clean by default while every chart still includes all statuses.
    st.session_state["selected_statuses"] = []
if "year_range" not in st.session_state:
    min_year = int(companies["founded_year"].min(skipna=True))
    max_year = int(companies["founded_year"].max(skipna=True))
    st.session_state["year_range"] = (min_year, max_year)

# Resolve any pending click-to-filter request (e.g. from the outcome-by-category chart)
# BEFORE the sidebar widgets are instantiated below, since Streamlit disallows writing to a
# widget's session_state key after that widget has already been instantiated in the same run.
if st.session_state.get("pending_category_click"):
    st.session_state["selected_categories"] = [st.session_state.pop("pending_category_click")]

st.markdown("""
<style>
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    font-size: 12px;
    color: #8A94A3;
}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondaryFormSubmit"] {
    width: 100%;
    border-radius: 8px;
}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
    width: 100%;
    border: none;
    background: transparent;
    color: #8A94A3;
    font-size: 12px;
    box-shadow: none;
}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
    color: #2563EB;
    background: transparent;
}
</style>
""", unsafe_allow_html=True)

with st.sidebar.container(border=True):
    st.markdown(
        "<p style='font-size:13px; font-weight:500; color:#5F6B7A; margin-bottom:0.5rem;'>Filters</p>",
        unsafe_allow_html=True,
    )

    with st.form("filter_form"):
        all_categories = sorted(companies["category_code"].dropna().unique())
        st.multiselect(
            "Category", options=all_categories, key="selected_categories",
            format_func=category_label,
        )

        all_countries = sorted(companies["country_code"].dropna().unique(), key=country_label)
        st.multiselect(
            "Country", options=all_countries, key="selected_countries",
            format_func=country_label,
        )

        all_statuses = sorted(companies["status"].dropna().unique())
        st.multiselect("Status", options=all_statuses, key="selected_statuses")

        min_year = int(companies["founded_year"].min(skipna=True))
        max_year = int(companies["founded_year"].max(skipna=True))
        st.slider("Founded year", min_value=min_year, max_value=max_year, key="year_range")

        submitted = st.form_submit_button("Apply Filters")

    st.button("Reset Filters", on_click=reset_filters)
# --- Apply filters (always reads current session_state, no separate "submitted" branching needed) ---
filtered = companies.copy()

if st.session_state["selected_categories"]:
    filtered = filtered[filtered["category_code"].isin(st.session_state["selected_categories"])]

if st.session_state["selected_countries"]:
    filtered = filtered[filtered["country_code"].isin(st.session_state["selected_countries"])]

if st.session_state["selected_statuses"]:
    filtered = filtered[filtered["status"].isin(st.session_state["selected_statuses"])]

filtered = filtered[
    filtered["founded_year"].isna() |
    (
        (filtered["founded_year"] >= st.session_state["year_range"][0]) &
        (filtered["founded_year"] <= st.session_state["year_range"][1])
    )
]

display_cols = ["name", "category_code", "country_code", "status", "founded_year", "funding_total_usd", "funding_rounds"]

column_labels = {
    "name": "Name",
    "category_code": "Category",
    "country_code": "Country",
    "status": "Status",
    "founded_year": "Founded Year",
    "funding_total_usd": "Total Funding (USD)",
    "funding_rounds": "Funding Rounds"
}

display_df = filtered[display_cols].rename(columns=column_labels)
display_df["Category"] = display_df["Category"].map(category_label)
display_df["Country"] = display_df["Country"].map(country_label)

# --- KPI summary cards (driven by `filtered`, so they respond to the sidebar filters) ---
total_funding = filtered["funding_total_usd"].sum(skipna=True)
# Most companies in this dataset never raised recorded funding, so a median across ALL
# companies is trivially $0 — median over funded companies only is the informative number.
median_funding = filtered.loc[filtered["funding_total_usd"] > 0, "funding_total_usd"].median()
exit_rate = filtered["status"].isin(["acquired", "ipo"]).mean() * 100 if len(filtered) else 0

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Companies", f"{len(filtered):,}")
kpi2.metric("Total Funding", f"${total_funding:,.0f}" if pd.notna(total_funding) else "N/A")
kpi3.metric("Median Funding (funded)", f"${median_funding:,.0f}" if pd.notna(median_funding) else "N/A")
kpi4.metric("Exit Rate", f"{exit_rate:.1f}%")

tab_overview, tab_trends, tab_categories, tab_geo, tab_network, tab_explorer = st.tabs(
    ["Overview", "Funding Trends", "Categories & Outcomes", "Geography", "Investor Network", "Company Explorer"]
)

# ============================== Overview tab ==============================
with tab_overview:
    col1, col2 = st.columns(2)

    with col1:
        status_counts = filtered["status"].value_counts()
        fig_status = px.bar(
            x=status_counts.index, y=status_counts.values,
            color=status_counts.index, color_discrete_map=STATUS_COLORS,
            labels={"x": "Status", "y": "Number of Startups"},
            title="Startup Status Distribution",
        )
        fig_status.update_layout(showlegend=False)
        st.plotly_chart(polish(fig_status), use_container_width=True)

    with col2:
        cat_counts = filtered["category_code"].value_counts().head(15).sort_values()
        fig_cats = px.bar(
            x=cat_counts.values, y=[category_label(c) for c in cat_counts.index], orientation="h",
            labels={"x": "Number of Startups", "y": "Category"},
            title="Top 15 Startup Categories",
        )
        st.plotly_chart(polish(fig_cats), use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        funded = filtered[(filtered["funding_total_usd"] > 0) & np.isfinite(filtered["funding_total_usd"])].copy()
        # Plotly Express's histogram `log_x=True` bins on the linear scale then only
        # relabels the axis, which truncates the visible range on data this skewed.
        # Binning the log10-transformed values directly avoids that and is the
        # statistically correct way to build a log-scale histogram.
        funded["log_funding"] = np.log10(funded["funding_total_usd"])
        fig_dist = px.histogram(
            funded, x="log_funding", nbins=50,
            labels={"log_funding": "Total Funding USD (log scale)"},
            title="Distribution of Total Funding",
        )
        fig_dist.update_xaxes(
            tickvals=[3, 4, 5, 6, 7, 8, 9],
            ticktext=["$1K", "$10K", "$100K", "$1M", "$10M", "$100M", "$1B"],
        )
        st.plotly_chart(polish(fig_dist), use_container_width=True)

    with col4:
        funding_dates = filtered.copy()
        funding_dates["days_to_first_funding"] = (
            funding_dates["first_funding_at"] - funding_dates["founded_at"]
        ).dt.days
        valid_days = funding_dates[
            (funding_dates["days_to_first_funding"] >= 0) &
            (funding_dates["days_to_first_funding"] < 3650)
        ]
        fig_violin = px.violin(
            valid_days, x="status", y="days_to_first_funding", color="status",
            color_discrete_map=STATUS_COLORS, box=True, points=False,
            labels={"days_to_first_funding": "Days to First Funding", "status": "Status"},
            title="Days from Founding to First Funding, by Outcome",
        )
        fig_violin.update_layout(showlegend=False)
        st.plotly_chart(polish(fig_violin), use_container_width=True)

    with st.expander("View filtered company data"):
        st.dataframe(display_df.head(20))

# ============================== Funding Trends tab ==============================
with tab_trends:
    funding_rounds_filtered = funding_rounds[funding_rounds["object_id"].isin(filtered["id"])]

    funding_by_year = (
        funding_rounds_filtered
        .dropna(subset=["funded_year", "raised_amount_usd"])
        .query("funded_year >= 1990 and raised_amount_usd > 0")
        .groupby("funded_year")
        .agg(total_raised=("raised_amount_usd", "sum"), num_rounds=("raised_amount_usd", "size"))
        .reset_index()
        .sort_values("funded_year")
    )

    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(
        x=funding_by_year["funded_year"], y=funding_by_year["total_raised"],
        name="Total Funding (USD)", mode="lines+markers", yaxis="y1",
    ))
    fig_trend.add_trace(go.Scatter(
        x=funding_by_year["funded_year"], y=funding_by_year["num_rounds"],
        name="Number of Rounds", mode="lines+markers", yaxis="y2",
        line=dict(dash="dot"),
    ))
    fig_trend.update_layout(
        title="Total Funding and Round Count Over Time",
        xaxis=dict(title="Year"),
        yaxis=dict(title="Total Funding (USD)"),
        yaxis2=dict(title="Number of Rounds", overlaying="y", side="right"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(polish(fig_trend), use_container_width=True)
    st.caption(
        "This is a static 2013 snapshot. The rise in recent years partly reflects Crunchbase's "
        "own data coverage improving over time, not pure market growth — read the recent-year "
        "uptick as a coverage artifact, not a clean trend."
    )

    col1, col2 = st.columns(2)

    round_stage_order = (
        funding_rounds_filtered
        .dropna(subset=["funding_round_type", "raised_amount_usd"])
        .groupby("funding_round_type")["raised_amount_usd"]
        .median()
        .sort_values()
        .index
    )

    with col1:
        round_type_counts = funding_rounds_filtered["funding_round_type"].value_counts()
        round_type_counts = round_type_counts.reindex(round_stage_order).dropna()
        fig_round_counts = px.bar(
            x=round_type_counts.index, y=round_type_counts.values,
            labels={"x": "Funding Round Type", "y": "Number of Rounds"},
            title="Funding Rounds by Type (ordered by typical size)",
        )
        st.plotly_chart(polish(fig_round_counts), use_container_width=True)

    with col2:
        avg_funding_type = (
            funding_rounds_filtered
            .dropna(subset=["funding_round_type", "raised_amount_usd"])
            .groupby("funding_round_type")["raised_amount_usd"]
            .mean()
            .reindex(round_stage_order)
            .dropna()
        )
        fig_avg_type = px.bar(
            x=avg_funding_type.index, y=avg_funding_type.values,
            labels={"x": "Funding Round Type", "y": "Average Raised Amount USD"},
            title="Average Funding Amount by Round Type (ordered by typical size)",
        )
        st.plotly_chart(polish(fig_avg_type), use_container_width=True)

# ============================== Categories & Outcomes tab ==============================
with tab_categories:
    top10_cats = filtered["category_code"].value_counts().head(10).index
    cat_subset = filtered[filtered["category_code"].isin(top10_cats)]

    status_by_category = (
        cat_subset.groupby(["category_code", "status"]).size().unstack(fill_value=0)
    )
    status_pct = status_by_category.div(status_by_category.sum(axis=1), axis=0) * 100
    status_pct_long = status_pct.reset_index().melt(
        id_vars="category_code", var_name="status", value_name="pct"
    )

    fig_outcome = px.bar(
        status_pct_long, x="category_code", y="pct", color="status",
        color_discrete_map=STATUS_COLORS,
        labels={"category_code": "Category", "pct": "% of Companies", "status": "Status"},
        title="Outcome Rate by Category (% of Companies, Top 10 Categories) — click a bar to filter",
    )
    fig_outcome.update_layout(barmode="stack")
    # Keep the plotted x values as raw category_code (so click-to-filter below still matches
    # the sidebar's session_state values) and only relabel the tick text shown to the user.
    fig_outcome.update_xaxes(
        tickvals=list(top10_cats), ticktext=[category_label(c) for c in top10_cats]
    )
    outcome_selection = st.plotly_chart(
        polish(fig_outcome), use_container_width=True, on_select="rerun",
        selection_mode="points", key="outcome_chart",
    )
    if outcome_selection and outcome_selection.get("selection", {}).get("points"):
        clicked_category = outcome_selection["selection"]["points"][0].get("x")
        if clicked_category:
            st.session_state["pending_category_click"] = clicked_category
            st.rerun()

    category_order = filtered["category_code"].value_counts().head(15).index
    category_order_labels = [category_label(c) for c in category_order]

    col1, col2 = st.columns(2)
    with col1:
        cat_count_series = filtered["category_code"].value_counts().reindex(category_order)
        fig_cat_count = px.bar(
            x=category_order_labels, y=cat_count_series.values,
            labels={"x": "Category", "y": "Number of Startups"},
            title="Startups by Category (Count)",
        )
        fig_cat_count.update_xaxes(tickangle=45)
        st.plotly_chart(polish(fig_cat_count), use_container_width=True)

    with col2:
        cat_median_series = (
            filtered[filtered["funding_total_usd"] > 0]
            .groupby("category_code")["funding_total_usd"]
            .median()
            .reindex(category_order)
        )
        fig_cat_median = px.bar(
            x=category_order_labels, y=cat_median_series.values,
            labels={"x": "Category", "y": "Median Funding USD"},
            title="Median Funding by Category ($)",
        )
        fig_cat_median.update_xaxes(tickangle=45)
        st.plotly_chart(polish(fig_cat_median), use_container_width=True)

    st.caption(
        "Same category order and axis on both charts — categories that dominate by company "
        "count are not always the ones that raise the most money per company."
    )

# ============================== Geography tab ==============================
with tab_geo:
    metric_col, reset_col = st.columns([5, 1])
    with metric_col:
        geo_metric = st.radio(
            "Metric", ["Count", "Total Funding (USD)", "Median Funding (USD)"],
            horizontal=True, key="geo_metric",
        )
    focus_country = st.session_state.get("map_focus_country")
    with reset_col:
        if focus_country:
            st.button("Reset map view", on_click=lambda: st.session_state.pop("map_focus_country", None))

    if geo_metric == "Count":
        country_series = filtered["country_code"].value_counts()
    else:
        geo_funded = filtered[filtered["funding_total_usd"] > 0]
        grouped = geo_funded.groupby("country_code")["funding_total_usd"]
        country_series = grouped.sum() if geo_metric == "Total Funding (USD)" else grouped.median()
        country_series = country_series.sort_values(ascending=False)

    country_df = country_series.reset_index()
    country_df.columns = ["country_code", "value"]
    # USA outweighs the next-biggest country (UK) by ~7x, so a linear color scale makes
    # every other country read as nearly-blank white next to it. Color by log10(value) —
    # same fix as the funding histogram — so mid-tier countries stay visually distinguishable,
    # then relabel the colorbar with real values instead of raw log numbers.
    country_df["log_value"] = np.log10(country_df["value"])
    # `locations` must stay ISO-3 codes (that's what locationmode="ISO-3" matches against) —
    # only the hover label shows the full country name.
    country_df["country_name"] = country_df["country_code"].map(country_label)

    fig_map = px.choropleth(
        country_df, locations="country_code", locationmode="ISO-3", color="log_value",
        color_continuous_scale="Blues",
        hover_name="country_name",
        hover_data={"log_value": False, "value": ":,.0f", "country_code": False, "country_name": False},
        title=f"Companies by Country — {geo_metric}",
        projection="natural earth",
    )
    log_lo, log_hi = country_df["log_value"].min(), country_df["log_value"].max()
    tick_positions = np.linspace(log_lo, log_hi, 5)
    tick_values = 10 ** tick_positions
    is_currency = geo_metric != "Count"
    tick_labels = (
        [f"${v:,.0f}" for v in tick_values] if is_currency
        else [f"{v:,.0f}" for v in tick_values]
    )
    fig_map.update_coloraxes(
        colorbar=dict(title=geo_metric, tickvals=tick_positions, ticktext=tick_labels)
    )
    fig_map.update_layout(height=600)
    map_scope = COUNTRY_SCOPES.get(focus_country) if focus_country else None
    if map_scope:
        fig_map.update_geos(showframe=False, scope=map_scope)
        st.caption(f"Zoomed to {country_label(focus_country)}'s region ({map_scope.title()}).")
    else:
        fig_map.update_geos(showframe=False)
    st.plotly_chart(polish(fig_map), use_container_width=True)

    top15_countries = country_series.head(15).sort_values()
    # Keep the plotted y values as raw country_code (so a click below reports a code we can
    # look up in COUNTRY_SCOPES) and only relabel the tick text shown to the user — same
    # approach used for the category outcome chart's click-to-filter.
    fig_country_bar = px.bar(
        x=top15_countries.values, y=top15_countries.index, orientation="h",
        labels={"x": geo_metric, "y": "Country"},
        title=f"Top 15 Countries — {geo_metric} — click a bar to zoom the map",
    )
    fig_country_bar.update_yaxes(
        tickvals=list(top15_countries.index),
        ticktext=[country_label(c) for c in top15_countries.index],
    )
    country_bar_selection = st.plotly_chart(
        polish(fig_country_bar), use_container_width=True, on_select="rerun",
        selection_mode="points", key="country_bar_chart",
    )
    if country_bar_selection and country_bar_selection.get("selection", {}).get("points"):
        clicked_country = country_bar_selection["selection"]["points"][0].get("y")
        if clicked_country and clicked_country != focus_country:
            st.session_state["map_focus_country"] = clicked_country
            st.rerun()

# ============================== Investor Network tab ==============================
with tab_network:
    st.caption(
        "Nodes are the top 40 investors by number of investments; an edge connects two "
        "investors who co-invested together in at least 2 funding rounds (one-off overlaps "
        "are hidden to keep this readable). Line darkness shows how often a pair "
        "co-invested — the elite VC tier is genuinely this densely connected, so edge "
        "strength is what carries the signal here, not sparseness. Labeled nodes are the "
        "10 most active investors. Layout is a force-directed (Fruchterman-Reingold) spring "
        "layout — scroll to zoom, drag to pan, click a node to see that investor's portfolio."
    )

    graph, pos = build_investor_network(dfs, top_n=40, min_edge_weight=2)

    # Split edges into weight tiers so co-investment strength reads visually — a single line
    # trace can't vary width per-segment, so each tier is its own trace, faintest first so
    # the strongest ties draw on top and stand out. Dimmer overall than a first pass so the
    # nodes/labels read clearly against the dense core.
    edge_tiers = [
        ("weak", lambda w: w < 4, "rgba(148, 163, 184, 0.12)", 1),
        ("medium", lambda w: 4 <= w < 8, "rgba(100, 116, 139, 0.25)", 1.5),
        ("strong", lambda w: w >= 8, "rgba(37, 99, 235, 0.55)", 2.5),
    ]
    edge_traces = []
    for _, predicate, color, width in edge_tiers:
        tier_x, tier_y = [], []
        for a, b, data in graph.edges(data=True):
            if not predicate(data["weight"]):
                continue
            x0, y0 = pos[a]
            x1, y1 = pos[b]
            tier_x += [x0, x1, None]
            tier_y += [y0, y1, None]
        edge_traces.append(go.Scatter(
            x=tier_x, y=tier_y, mode="lines",
            line=dict(width=width, color=color),
            hoverinfo="none", showlegend=False,
        ))

    # Label only the most active investors — labeling all nodes at this density just
    # recreates the clutter problem, so the label itself acts as a "top investor" cue.
    # Fewer than before (10, not 15) since the dense core left little room to read them.
    label_rank = sorted(graph.nodes(data=True), key=lambda n: -n[1]["investments"])
    labeled_ids = {node_id for node_id, _ in label_rank[:10]}

    node_x, node_y, node_size, node_hover, node_ids = [], [], [], [], []
    label_annotations = []
    for node_id, data in graph.nodes(data=True):
        x, y = pos[node_id]
        node_x.append(x)
        node_y.append(y)
        node_size.append(8 + data["investments"] ** 0.5 * 2)
        node_hover.append(f"{data['name']} ({data['investments']} investments)")
        node_ids.append(node_id)
        if node_id in labeled_ids:
            # Plain text labels got lost in the dense core, so labels are a background
            # "chip" instead — stays legible no matter how many edges cross behind it.
            label_annotations.append(dict(
                x=x, y=y, text=data["name"], showarrow=False, yshift=16,
                font=dict(size=10, color="#1E293B"),
                bgcolor="rgba(255, 255, 255, 0.9)", bordercolor="rgba(148, 163, 184, 0.6)",
                borderwidth=1, borderpad=2,
            ))

    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers", showlegend=False,
        marker=dict(size=node_size, color="#2563EB", line=dict(width=1, color="#FFFFFF")),
        hovertext=node_hover, hoverinfo="text", customdata=node_ids,
    )

    fig_network = go.Figure(data=edge_traces + [node_trace])
    fig_network.update_layout(
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        margin=dict(l=0, r=0, t=20, b=0), height=600,
        annotations=label_annotations,
        dragmode="pan",
    )
    network_selection = st.plotly_chart(
        polish(fig_network), use_container_width=True, on_select="rerun",
        selection_mode="points", key="network_chart",
        config={"scrollZoom": True},
    )

    selected_points = (network_selection or {}).get("selection", {}).get("points", [])
    # Node-trace points carry customdata (the investor id); edge-trace points never do —
    # checking for that is more robust than a hardcoded curve index now that edges are
    # split across multiple weight-tier traces.
    investor_points = [p for p in selected_points if p.get("customdata") is not None]
    if investor_points:
        selected_investor_id = investor_points[0].get("customdata")
        investor_names = dfs["objects"].set_index("id")["name"]
        selected_investor_name = investor_names.get(selected_investor_id, "Unknown investor")
        st.write(f"**Portfolio companies for {selected_investor_name}:**")
        portfolio_ids = dfs["investments"].loc[
            dfs["investments"]["investor_object_id"] == selected_investor_id, "funded_object_id"
        ]
        portfolio = companies[companies["id"].isin(portfolio_ids)][display_cols].rename(columns=column_labels)
        portfolio["Category"] = portfolio["Category"].map(category_label)
        portfolio["Country"] = portfolio["Country"].map(country_label)
        st.dataframe(portfolio.head(50))

# ============================== Company Explorer tab ==============================
with tab_explorer:
    company_query = st.text_input("Search for a company by name", placeholder="e.g. Facebook")

    selected_company = None
    if company_query:
        matches = sorted(
            companies.loc[
                companies["name"].str.contains(company_query, case=False, na=False), "name"
            ].dropna().unique()
        )[:50]
        if matches:
            selected_company = st.selectbox("Select a match", options=matches)
        else:
            st.write("No companies match that search.")

    if selected_company:
        company_row = companies[companies["name"] == selected_company].iloc[0]

        def _safe(val):
            return "—" if pd.isna(val) else val

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Category", _safe(category_label(company_row["category_code"])))
        col2.metric("Country", _safe(country_label(company_row["country_code"])))
        col3.metric("Status", _safe(company_row["status"]))
        founded_year = company_row["founded_year"]
        col4.metric("Founded", int(founded_year) if pd.notna(founded_year) else "—")

        company_rounds = funding_rounds[funding_rounds["object_id"] == company_row["id"]].sort_values("funded_at")
        if not company_rounds.empty:
            fig_company = px.bar(
                company_rounds, x="funded_at", y="raised_amount_usd", color="funding_round_type",
                labels={"funded_at": "Date", "raised_amount_usd": "Raised Amount (USD)", "funding_round_type": "Round Type"},
                title=f"Funding Timeline — {selected_company}",
            )
            cat_median = filtered.loc[
                filtered["category_code"] == company_row["category_code"], "funding_total_usd"
            ].median()
            if pd.notna(cat_median):
                fig_company.add_hline(
                    y=cat_median, line_dash="dash",
                    annotation_text="Category median total funding",
                )
            st.plotly_chart(polish(fig_company), use_container_width=True)
        else:
            st.write("No funding round records for this company.")