import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import networkx as nx
import pycountry
from pathlib import Path

# ==========================================================================
# VC Ecosystem Explorer — guided drill-down
#
# One continuous flow; every selection is made inside a chart and reshapes
# everything below it:
#   1. Where the money is  -> click a COUNTRY on the map
#   2. In <country>: funding by year, then exit rate & total funding by
#      sector -> click a SECTOR
#   3. Sector deep-dive: <category> in <country>  (trajectory)
#   4. Investors in the sector: ranked bar + co-investment network -> click
#      an INVESTOR; then a ranked company table -> pick a COMPANY
#   5. Company vs. its cohort (cumulative funding vs. peer median)
#
# Breadcrumb steps back up the funnel. Single file; data from data/*.csv.
# ==========================================================================

st.set_page_config(page_title="VC Ecosystem Explorer", layout="wide")
DATA_DIR = Path("data")

STATUS_COLORS = {"operating": "#64748B", "acquired": "#22C55E",
                 "ipo": "#F59E0B", "closed": "#94A3B8"}
EXIT_STATUSES = ["acquired", "ipo"]
CATEGORY_LABELS = {"games_video": "Games & Video", "photo_video": "Photo & Video",
                   "ecommerce": "E-Commerce"}

def category_label(code):
    if pd.isna(code):
        return code
    return CATEGORY_LABELS.get(code, str(code).replace("_", " ").title())

COUNTRY_NAMES = {c.alpha_3: c.name for c in pycountry.countries}
COUNTRY_NAMES.update({"KOR": "South Korea", "RUS": "Russia", "IRN": "Iran", "TWN": "Taiwan",
                      "VNM": "Vietnam", "VEN": "Venezuela", "PRK": "North Korea", "MDA": "Moldova",
                      "ROM": "Romania", "ANT": "Netherlands Antilles", "VGB": "British Virgin Islands"})

def country_label(code):
    if pd.isna(code):
        return code
    return COUNTRY_NAMES.get(code, code)

def bil(x):
    """Format a USD amount in billions."""
    b = x / 1e9
    return f"${b:,.0f}B" if abs(b) >= 1 else f"${b:,.2f}B"

def polish(fig):
    fig.update_layout(hoverlabel=dict(align="left"), margin=dict(l=40, r=30, t=50, b=40))
    return fig


# ------------------------------- data ------------------------------------
@st.cache_data
def load_data():
    return {f.stem: pd.read_csv(f, low_memory=False) for f in DATA_DIR.glob("*.csv")}

@st.cache_data
def build_companies(dfs):
    o = dfs["objects"]
    c = o[o["entity_type"] == "Company"].copy()
    for col in ["founded_at", "first_funding_at"]:
        c[col] = pd.to_datetime(c[col], errors="coerce")
    c["funding_total_usd"] = pd.to_numeric(c["funding_total_usd"], errors="coerce")
    c["founded_year"] = c["founded_at"].dt.year
    return c

@st.cache_data
def build_funding_rounds(dfs):
    fr = dfs["funding_rounds"].copy()
    fr["funded_at"] = pd.to_datetime(fr["funded_at"], errors="coerce")
    fr["funded_year"] = fr["funded_at"].dt.year
    fr["raised_amount_usd"] = pd.to_numeric(fr["raised_amount_usd"], errors="coerce")
    return fr

@st.cache_data
def funding_by_country(companies):
    g = (companies[companies["funding_total_usd"] > 0]
         .groupby("country_code")["funding_total_usd"].sum().reset_index())
    g.columns = ["country_code", "value"]
    return g

@st.cache_data
def investors_for_companies(dfs, company_ids):
    inv = dfs["investments"]
    sub = inv[inv["funded_object_id"].isin(company_ids)]
    counts = sub["investor_object_id"].value_counts()
    names = dfs["objects"].set_index("id")["name"]
    out = counts.reset_index()
    out.columns = ["investor_id", "deals_here"]
    out["name"] = out["investor_id"].map(lambda i: names.get(i, str(i)))
    return out

@st.cache_data
def scoped_network(dfs, company_ids, top_n=40):
    inv = dfs["investments"]
    sub = inv[inv["funded_object_id"].isin(company_ids)].dropna(subset=["funding_round_id", "investor_object_id"])
    counts = sub["investor_object_id"].value_counts()
    top = counts.head(top_n).index
    subt = sub[sub["investor_object_id"].isin(top)]
    ew = {}
    for _, g in subt.groupby("funding_round_id"):
        ids = g["investor_object_id"].unique()
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                p = tuple(sorted((ids[i], ids[j])))
                ew[p] = ew.get(p, 0) + 1
    min_w = 2 if len(company_ids) > 300 else 1     # relax threshold on small segments
    ew = {p: w for p, w in ew.items() if w >= min_w}
    names = dfs["objects"].set_index("id")["name"]
    G = nx.Graph()
    for iid in top:
        G.add_node(iid, name=names.get(iid, str(iid)), deals=int(counts[iid]))
    for (a, b), w in ew.items():
        G.add_edge(a, b, weight=w)
    k = 4 / (len(G) ** 0.5) if len(G) > 1 else 1
    pos = nx.spring_layout(G, seed=42, k=k, iterations=120)
    return G, pos, min_w

@st.cache_data
def companies_of_investor(dfs, investor_id):
    inv = dfs["investments"]
    return set(inv.loc[inv["investor_object_id"] == investor_id, "funded_object_id"].dropna())


dfs = load_data()
companies = build_companies(dfs)
funding_rounds = build_funding_rounds(dfs)
BASE_EXIT = companies["status"].isin(EXIT_STATUSES).mean() * 100


# --------------------------- drill-down state ----------------------------
ss = st.session_state
for k, v in {"sel_country": None, "sel_category": None,
             "sel_investor_id": None, "sel_investor_name": None,
             "sel_company": None, "nonce": 0,
             "bip_focus_type": None, "bip_focus_id": None, "bip_seed_company": None}.items():
    ss.setdefault(k, v)

def accept(**changes):
    ss.update(changes)
    ss["nonce"] += 1

def set_country(cc):
    accept(sel_country=cc, sel_category=None, sel_investor_id=None,
           sel_investor_name=None, sel_company=None)

def set_category(cat):
    accept(sel_category=cat, sel_investor_id=None, sel_investor_name=None, sel_company=None)

def set_investor(iid, name):
    accept(sel_investor_id=iid, sel_investor_name=name, sel_company=None)

def clicked_custom(sel):
    if sel and sel.get("selection", {}).get("points"):
        cd = sel["selection"]["points"][0].get("customdata")
        if cd is not None:
            return cd[0] if isinstance(cd, (list, tuple)) else cd
    return None

def reset_all():
    accept(sel_country=None, sel_category=None, sel_investor_id=None,
           sel_investor_name=None, sel_company=None)

K = lambda name: f"{name}_{ss['nonce']}"


# ------------------------------- header ----------------------------------
title_col, reset_col = st.columns([5, 1])
with title_col:
    st.title("VC Ecosystem Explorer")
    st.caption("A guided walk through a historical Crunchbase snapshot (~2013): start from where the "
               "capital is, drill into a country, a sector, its investors, and finally a single company. "
               "Every step is driven by clicking inside the charts.")
with reset_col:
    st.write("")  # vertical breathing room so the button lines up with the title
    st.button("↻ Start over", on_click=reset_all, use_container_width=True, key="reset_top")

# breadcrumb (no "World" crumb — the step-1 map is always on top; click a country to change it)
crumbs = []
if ss["sel_country"]:
    crumbs.append((country_label(ss["sel_country"]), lambda: set_category(None)))
if ss["sel_category"]:
    crumbs.append((category_label(ss["sel_category"]), lambda: set_investor(None, None)))
if ss["sel_investor_name"]:
    crumbs.append((ss["sel_investor_name"], lambda: accept(sel_company=None)))
if ss["sel_company"]:
    crumbs.append((ss["sel_company"], lambda: None))

if crumbs:
    bc = st.columns(len(crumbs) * 2 - 1)
    for i, (label, fn) in enumerate(crumbs):
        bc[i * 2].button(label, key=f"crumb_{i}", on_click=fn, use_container_width=True,
                         type="primary" if i == len(crumbs) - 1 else "secondary")
        if i < len(crumbs) - 1:
            bc[i * 2 + 1].markdown(
                "<div style='text-align:center;padding-top:6px;color:#94A3B8;'>›</div>",
                unsafe_allow_html=True)
st.divider()


# ==================== STEP 1 — WHERE THE MONEY IS ========================
st.header("1 · Where the money is")
st.write("Total capital raised by companies in each country (US$B). Click a country to drill in; "
         "click a different country any time to switch.")

fbc = funding_by_country(companies).copy()
fbc = fbc[fbc["value"] > 0]
fbc["log_value"] = np.log10(fbc["value"])
fbc["value_b"] = fbc["value"] / 1e9
fbc["country_name"] = fbc["country_code"].map(country_label)

fig_map = px.choropleth(
    fbc, locations="country_code", locationmode="ISO-3", color="log_value",
    color_continuous_scale="Blues", hover_name="country_name",
    custom_data=["country_code", "value_b"], projection="natural earth")
fig_map.update_traces(hovertemplate="<b>%{hovertext}</b><br>Total raised: $%{customdata[1]:,.2f}B<extra></extra>")
lo, hi = fbc["log_value"].min(), fbc["log_value"].max()
tp = np.linspace(lo, hi, 5)
fig_map.update_coloraxes(colorbar=dict(title="Total raised",
                         tickvals=tp, ticktext=[bil(10 ** v) for v in tp]))
fig_map.update_geos(showframe=False)
fig_map.update_layout(height=470, margin=dict(l=0, r=0, t=0, b=0))
if ss["sel_country"]:
    fig_map.add_trace(go.Choropleth(
        locations=[ss["sel_country"]], locationmode="ISO-3", z=[1],
        colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
        marker_line_color="#F59E0B", marker_line_width=2.5, hoverinfo="skip"))

sel = st.plotly_chart(fig_map, use_container_width=True, on_select="rerun",
                      selection_mode="points", key=K("map"))
cc = clicked_custom(sel)
if cc and cc != ss["sel_country"]:
    set_country(cc)
    st.rerun()

# --- Global flows Sankey: country -> sector -> outcome, band thickness = companies ---
with st.expander("Global flows: country → sector → outcome (top 6 × top 6)", expanded=False):
    _top_c = companies["country_code"].value_counts().head(6).index.tolist()
    _top_cat = companies["category_code"].value_counts().head(6).index.tolist()
    _sub = companies[companies["country_code"].isin(_top_c)
                     & companies["category_code"].isin(_top_cat)
                     & companies["status"].notna()]
    if len(_sub):
        _cc = _sub.groupby(["country_code", "category_code"]).size().reset_index(name="n")
        _cs = _sub.groupby(["category_code", "status"]).size().reset_index(name="n")
        _ctry_l = [country_label(x) for x in _top_c]
        _cat_l = [category_label(x) for x in _top_cat]
        _stat_c = ["operating", "acquired", "ipo", "closed"]
        _stat_l = [s.title() for s in _stat_c]
        _labels = _ctry_l + _cat_l + _stat_l
        _colors = (["#93C5FD"] * len(_ctry_l) + ["#C4B5FD"] * len(_cat_l)
                   + [STATUS_COLORS[s] for s in _stat_c])
        _idx = {**{n: i for i, n in enumerate(_ctry_l)},
                **{n: len(_ctry_l) + j for j, n in enumerate(_cat_l)},
                **{n: len(_ctry_l) + len(_cat_l) + k for k, n in enumerate(_stat_l)}}
        # Explicit hex palette so the rgba helper below can parse consistently
        # (px.colors.qualitative.Bold returns "rgb(...)" strings, not hex)
        _palette = ["#EF4444", "#F59E0B", "#EAB308", "#84CC16", "#22C55E",
                    "#14B8A6", "#0EA5E9", "#3B82F6", "#8B5CF6", "#EC4899"]
        _cat_col = {c: _palette[j % len(_palette)] for j, c in enumerate(_top_cat)}
        def _hexrgba(h, a=0.4):
            h = h.lstrip("#")
            return f"rgba({int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)},{a})"
        _src, _tgt, _val, _lc, _link_cd = [], [], [], [], []
        for r in _cc.itertuples():
            _src.append(_idx[country_label(r.country_code)])
            _tgt.append(_idx[category_label(r.category_code)])
            _val.append(int(r.n))
            _lc.append(_hexrgba(_cat_col[r.category_code]))
            _link_cd.append(["cc", r.country_code, r.category_code])
        for r in _cs.itertuples():
            _src.append(_idx[category_label(r.category_code)])
            _tgt.append(_idx[r.status.title()])
            _val.append(int(r.n))
            _lc.append(_hexrgba(STATUS_COLORS[r.status]))
            _link_cd.append(["cs", r.category_code, r.status])
        # Node customdata: (kind, code) — country / category / status
        _node_cd = (
            [["country", c] for c in _top_c]
            + [["category", c] for c in _top_cat]
            + [["status", s] for s in _stat_c]
        )
        fig_sk = go.Figure(go.Sankey(
            node=dict(label=_labels, color=_colors, pad=14, thickness=16,
                      customdata=_node_cd),
            link=dict(source=_src, target=_tgt, value=_val, color=_lc,
                      customdata=_link_cd)))
        fig_sk.update_layout(height=470, font=dict(size=11),
                             margin=dict(l=10, r=10, t=10, b=10))
        sel_sk = st.plotly_chart(fig_sk, use_container_width=True, on_select="rerun",
                                 selection_mode="points", key=K("sankey"))
        st.caption("Colored bands: purple links = country→sector (colored by sector); "
                   "status colors = sector→outcome. Band thickness = number of companies in that flow.")

        # Explicit jump controls — reliable path (Streamlit's Sankey click events are flaky)
        st.markdown("**Jump straight to a country / sector from the Sankey:**")
        _j1, _j2, _j3 = st.columns([3, 3, 1])
        with _j1:
            _pick_c = st.selectbox("Country", [None] + _top_c,
                                   format_func=lambda x: "— select —" if x is None else country_label(x),
                                   key=K("sk_pick_country"))
        with _j2:
            _pick_cat = st.selectbox("Sector (optional)", [None] + _top_cat,
                                     format_func=lambda x: "— select —" if x is None else category_label(x),
                                     key=K("sk_pick_cat"))
        with _j3:
            st.write("")  # align vertically with the selectboxes
            if st.button("Jump →", key=K("sk_jump"), use_container_width=True):
                if _pick_c:
                    if _pick_cat:
                        # Both picked → drill straight to Step 3
                        accept(sel_country=_pick_c, sel_category=_pick_cat,
                               sel_investor_id=None, sel_investor_name=None, sel_company=None)
                    else:
                        set_country(_pick_c)
                    st.rerun()

        # Sankey click handling — best-effort fallback (uses customdata OR label match)
        if sel_sk and sel_sk.get("selection", {}).get("points"):
            for _pt in sel_sk["selection"]["points"]:
                _cd = _pt.get("customdata")
                _label = _pt.get("label")
                # Node click via customdata
                if _cd and len(_cd) == 2:
                    _kind, _code = _cd
                    if _kind == "country" and _code != ss["sel_country"]:
                        set_country(_code); st.rerun()
                    if _kind == "category" and ss["sel_country"] and _code != ss["sel_category"]:
                        set_category(_code); st.rerun()
                    break
                # Link click via customdata
                if _cd and len(_cd) == 3:
                    _lt, _s, _t = _cd
                    if _lt == "cc":
                        accept(sel_country=_s, sel_category=_t, sel_investor_id=None,
                               sel_investor_name=None, sel_company=None)
                        st.rerun()
                    break
                # Fallback: no customdata came through, match by node label
                if _label:
                    if _label in _ctry_l:
                        _code = _top_c[_ctry_l.index(_label)]
                        if _code != ss["sel_country"]:
                            set_country(_code); st.rerun()
                        break
                    if _label in _cat_l and ss["sel_country"]:
                        _code = _top_cat[_cat_l.index(_label)]
                        if _code != ss["sel_category"]:
                            set_category(_code); st.rerun()
                        break

if not ss["sel_country"]:
    st.info("Click a country on the map to begin.")
    st.stop()


# ================ STEP 2 — THE CHOSEN COUNTRY ===========================
country_co = companies[companies["country_code"] == ss["sel_country"]]
country_ids = set(country_co["id"])
ctry_name = country_label(ss["sel_country"])
st.divider()
st.header(f"2 · {ctry_name}")

n = len(country_co)
er = country_co["status"].isin(EXIT_STATUSES).mean() * 100 if n else 0
funded_med = country_co.loc[country_co["funding_total_usd"] > 0, "funding_total_usd"].median()
m1, m2, m3 = st.columns(3)
m1.metric("Companies", f"{n:,}")
m2.metric("Exit rate", f"{er:.1f}%", f"{er - BASE_EXIT:+.1f} pp vs world")
m3.metric("Median funding (funded)", f"${funded_med:,.0f}" if pd.notna(funded_med) else "N/A")

# --- funding & deals by year ---
country_rounds = funding_rounds[funding_rounds["object_id"].isin(country_ids)]
by_year = (country_rounds.dropna(subset=["funded_year"])
           .groupby("funded_year")
           .agg(total=("raised_amount_usd", lambda s: s[s > 0].sum()), deals=("id", "size"))
           .reset_index().query("funded_year >= 1990").sort_values("funded_year"))
if len(by_year):
    by_year["total_b"] = by_year["total"] / 1e9
    fig_year = go.Figure()
    fig_year.add_trace(go.Bar(x=by_year["funded_year"], y=by_year["total_b"],
                              name="Total funding (US$B)", marker_color="#2563EB"))
    fig_year.add_trace(go.Scatter(x=by_year["funded_year"], y=by_year["deals"], name="Deals (rounds)",
                                  mode="lines+markers", yaxis="y2", line=dict(color="#F59E0B")))
    fig_year.update_layout(title=f"Funding and deal flow in {ctry_name} by year",
                           xaxis=dict(title="Year"), yaxis=dict(title="Total funding (US$B)"),
                           yaxis2=dict(title="Deals", overlaying="y", side="right", showgrid=False),
                           legend=dict(orientation="h", yanchor="bottom", y=1.02), height=380)
    st.plotly_chart(polish(fig_year), use_container_width=True)

st.write("Pick a sector to study — click a **bubble**, or a bar in either chart below.")
MIN_CO = 15
cat_stats = (country_co.groupby("category_code")
             .agg(companies=("id", "size"),
                  exit_rate=("status", lambda s: s.isin(EXIT_STATUSES).mean() * 100),
                  total=("funding_total_usd", lambda s: s[s > 0].sum()))
             .reset_index())
cat_stats = cat_stats[cat_stats["companies"] >= MIN_CO]

if len(cat_stats):
    # --- Bubble cloud: one bubble per sector, area = total funding, unique color per sector ---
    dbub = cat_stats.sort_values("total", ascending=False).reset_index(drop=True).copy()
    dbub["label"] = dbub["category_code"].map(category_label)
    dbub["total_b"] = dbub["total"] / 1e9
    # Fibonacci-sunflower disk packing: evenly spreads points across the whole disk
    # instead of the ring you get from an edgeless spring layout.
    # Biggest bubble (index 0) lands near the center, smaller ones spiral outward.
    n_bub = len(dbub)
    idx = np.arange(n_bub, dtype=float)
    golden = np.pi * (3 - np.sqrt(5))          # ~137.5° — packs points evenly on a disk
    radii = np.sqrt((idx + 0.5) / n_bub)
    theta = idx * golden
    dbub["px"] = radii * np.cos(theta)
    dbub["py"] = radii * np.sin(theta)
    # sqrt sizing so a $100B semiconductor sector doesn't make $1B ones invisible
    dbub["bsize"] = np.sqrt(dbub["total_b"].clip(lower=0.05))
    # label the top ~8 bubbles inside; the rest get names on hover only
    dbub["text_in"] = dbub["label"].where(dbub.index < 8, "")

    palette = (px.colors.qualitative.Bold + px.colors.qualitative.Set3 +
               px.colors.qualitative.Pastel + px.colors.qualitative.Vivid)
    fig_bub = px.scatter(
        dbub, x="px", y="py", size="bsize", color="label", text="text_in",
        hover_name="label", custom_data=["category_code", "total_b", "companies", "exit_rate"],
        color_discrete_sequence=palette, size_max=95,
        title=f"Sectors in {ctry_name} — bubble size = total funding")
    fig_bub.update_traces(
        textposition="middle center", textfont=dict(size=11, color="#0F172A"),
        hovertemplate=("<b>%{hovertext}</b><br>Total funding: $%{customdata[1]:,.2f}B<br>"
                       "Companies: %{customdata[2]}<br>Exit rate: %{customdata[3]:.1f}%<extra></extra>"),
    )
    fig_bub.update_xaxes(visible=False, range=[-1.4, 1.4])
    fig_bub.update_yaxes(visible=False, range=[-1.4, 1.4])
    fig_bub.update_layout(showlegend=False, height=470,
                          margin=dict(l=10, r=10, t=50, b=10),
                          plot_bgcolor="rgba(0,0,0,0)")
    sb = st.plotly_chart(polish(fig_bub), use_container_width=True, on_select="rerun",
                         selection_mode="points", key=K("catbub"))
    c = clicked_custom(sb)
    if c and c != ss["sel_category"]:
        set_category(c); st.rerun()

    col_er, col_tf = st.columns(2)
    with col_er:
        d = cat_stats.sort_values("exit_rate", ascending=False).head(12).copy()
        d["label"] = d["category_code"].map(category_label)
        f = px.bar(d.sort_values("exit_rate"), x="exit_rate", y="label", orientation="h",
                   custom_data=["category_code"], color="exit_rate", color_continuous_scale="Tealgrn",
                   labels={"exit_rate": "Exit rate (%)", "label": "Sector"},
                   title=f"Exit rate by sector (≥{MIN_CO} companies)")
        f.update_layout(coloraxis_showscale=False, height=430)
        s1 = st.plotly_chart(polish(f), use_container_width=True, on_select="rerun",
                             selection_mode="points", key=K("catbar_er"))
        c = clicked_custom(s1)
        if c and c != ss["sel_category"]:
            set_category(c); st.rerun()
    with col_tf:
        d = cat_stats.sort_values("total", ascending=False).head(12).copy()
        d["label"] = d["category_code"].map(category_label)
        d["total_b"] = d["total"] / 1e9
        f = px.bar(d.sort_values("total_b"), x="total_b", y="label", orientation="h",
                   custom_data=["category_code"], color="total_b", color_continuous_scale="Blues",
                   labels={"total_b": "Total funding (US$B)", "label": "Sector"},
                   title=f"Total funding by sector (≥{MIN_CO} companies)")
        f.update_layout(coloraxis_showscale=False, height=430)
        s2 = st.plotly_chart(polish(f), use_container_width=True, on_select="rerun",
                             selection_mode="points", key=K("catbar_tf"))
        c = clicked_custom(s2)
        if c and c != ss["sel_category"]:
            set_category(c); st.rerun()
else:
    st.info(f"Not enough companies in {ctry_name} to break down by sector (need ≥{MIN_CO} each).")

if not ss["sel_category"]:
    st.info("Click a sector bar above to go deeper.")
    st.stop()


# ============ STEP 3 — SECTOR DEEP-DIVE (country + category) =============
seg = country_co[country_co["category_code"] == ss["sel_category"]]
seg_ids = set(seg["id"])
cat_name = category_label(ss["sel_category"])
st.divider()
st.header(f"3 · {cat_name} in {ctry_name} — sector deep-dive")

seg_er = seg["status"].isin(EXIT_STATUSES).mean() * 100 if len(seg) else 0
seg_med = seg.loc[seg["funding_total_usd"] > 0, "funding_total_usd"].median()
d1, d2, d3 = st.columns(3)
d1.metric("Companies", f"{len(seg):,}")
d2.metric("Exit rate", f"{seg_er:.1f}%", f"{seg_er - BASE_EXIT:+.1f} pp vs world")
d3.metric("Median funding (funded)", f"${seg_med:,.0f}" if pd.notna(seg_med) else "N/A")

c1, c2 = st.columns(2)
with c1:
    sc = seg["status"].value_counts()
    f = px.bar(x=sc.index, y=sc.values, color=sc.index, color_discrete_map=STATUS_COLORS,
               labels={"x": "Status", "y": "Companies"}, title="Outcome mix")
    f.update_layout(showlegend=False, height=340)
    st.plotly_chart(polish(f), use_container_width=True)
with c2:
    seg2 = seg.copy()
    seg2["years"] = (seg2["first_funding_at"] - seg2["founded_at"]).dt.days / 365.25
    vd = seg2[(seg2["years"] >= 0) & (seg2["years"] < 10)]
    if len(vd) >= 5:
        f = px.violin(vd, x="status", y="years", color="status", color_discrete_map=STATUS_COLORS,
                      box=True, points=False,
                      labels={"years": "Years to first funding", "status": "Status"},
                      title="Years from founding to first funding, by outcome")
        f.update_layout(showlegend=False, height=340)
        st.plotly_chart(polish(f), use_container_width=True)
    else:
        st.info("Too few dated companies here to show a funding-timing breakdown.")

seg_rounds = funding_rounds[funding_rounds["object_id"].isin(seg_ids)]
c3, c4 = st.columns(2)
with c3:
    yr = (seg_rounds.dropna(subset=["funded_year", "raised_amount_usd"]).query("raised_amount_usd > 0")
          .groupby("funded_year")["raised_amount_usd"].sum().reset_index())
    if len(yr):
        yr["total_b"] = yr["raised_amount_usd"] / 1e9
        f = px.area(yr, x="funded_year", y="total_b",
                    labels={"funded_year": "Year", "total_b": "Total raised (US$B)"},
                    title="Capital raised over time")
        f.update_traces(line_color="#2563EB")
        f.update_layout(height=340)
        st.plotly_chart(polish(f), use_container_width=True)
    else:
        st.info("No dated funding rounds recorded for this sector here.")
with c4:
    if len(seg_rounds.dropna(subset=["funding_round_type"])):
        rc = seg_rounds["funding_round_type"].value_counts()
        f = px.bar(x=rc.index, y=rc.values, labels={"x": "Round type", "y": "Rounds"},
                   title="Funding rounds by stage")
        f.update_layout(height=340)
        st.plotly_chart(polish(f), use_container_width=True)
    else:
        st.info("No round-type data for this sector here.")


# =============== STEP 4 — INVESTORS IN THE SECTOR =======================
st.divider()
st.header(f"4 · Investors backing {cat_name} in {ctry_name}")
st.write("The most active investors here, and how they co-invest. Click an investor in **either** the "
         "bar or the network to pull up their companies.")

inv_here = investors_for_companies(dfs, tuple(seg_ids)) if seg_ids else pd.DataFrame()
col_bar, col_net = st.columns(2)

with col_bar:
    if len(inv_here):
        top_inv = inv_here.head(15).sort_values("deals_here")
        f = px.bar(top_inv, x="deals_here", y="name", orientation="h", custom_data=["investor_id"],
                   labels={"deals_here": "Deals in this country + sector", "name": "Investor"},
                   title="Most active investors")
        f.update_traces(marker_color="#2563EB")
        f.update_layout(height=460)
        sb = st.plotly_chart(polish(f), use_container_width=True, on_select="rerun",
                             selection_mode="points", key=K("invbar"))
        iid = clicked_custom(sb)
        if iid and iid != ss["sel_investor_id"]:
            set_investor(iid, inv_here.set_index("investor_id")["name"].get(iid, "Investor")); st.rerun()
    else:
        st.info("No recorded investors for this country + sector.")

with col_net:
    G, pos, min_w = scoped_network(dfs, tuple(seg_ids)) if seg_ids else (nx.Graph(), {}, 1)
    if G.number_of_nodes() >= 2:
        tiers = [(lambda w: w < 3, "rgba(148,163,184,0.20)", 1),
                 (lambda w: 3 <= w < 6, "rgba(100,116,139,0.35)", 1.6),
                 (lambda w: w >= 6, "rgba(37,99,235,0.6)", 2.6)]
        etr = []
        for pred, color, width in tiers:
            xs, ys = [], []
            for a, b, dd in G.edges(data=True):
                if not pred(dd["weight"]):
                    continue
                x0, y0 = pos[a]; x1, y1 = pos[b]
                xs += [x0, x1, None]; ys += [y0, y1, None]
            etr.append(go.Scatter(x=xs, y=ys, mode="lines", line=dict(width=width, color=color),
                                  hoverinfo="none", showlegend=False))
        labeled = {nid for nid, _ in sorted(G.nodes(data=True), key=lambda x: -x[1]["deals"])[:8]}
        nx_, ny_, nsz, nhov, nids, anns = [], [], [], [], [], []
        for nid, dd in G.nodes(data=True):
            x, y = pos[nid]
            nx_.append(x); ny_.append(y)
            # Stronger scaling so top-N hubs read as hubs at a glance:
            #   sqrt gave ~2× spread; ^0.75 * 3.5 gives ~5-6× spread top vs. bottom.
            nsz.append(11 + dd["deals"] ** 0.75 * 3.5)
            nhov.append(f"{dd['name']} ({dd['deals']} deals here)"); nids.append(nid)
            if nid in labeled:
                anns.append(dict(x=x, y=y, text=dd["name"], showarrow=False, yshift=18,
                                 font=dict(size=10, color="#0F172A"), bgcolor="rgba(255,255,255,0.92)",
                                 bordercolor="rgba(37,99,235,0.6)", borderwidth=1, borderpad=3))
        ntr = go.Scatter(x=nx_, y=ny_, mode="markers", showlegend=False,
                         marker=dict(size=nsz, color="#2563EB",
                                     line=dict(width=1, color="#FFF")),
                         hovertext=nhov, hoverinfo="text", customdata=nids)
        fig_net = go.Figure(data=etr + [ntr])
        fig_net.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False),
                              margin=dict(l=0, r=0, t=40, b=0), height=460, annotations=anns,
                              dragmode="pan", title=f"Co-investment network (edges ≥{min_w} shared round)")
        sn = st.plotly_chart(fig_net, use_container_width=True, on_select="rerun",
                             selection_mode="points", key=K("invnet"), config={"scrollZoom": True})
        pts = [p for p in (sn or {}).get("selection", {}).get("points", []) if p.get("customdata") is not None]
        if pts:
            iid = pts[0]["customdata"]
            if iid != ss["sel_investor_id"]:
                set_investor(iid, dfs["objects"].set_index("id")["name"].get(iid, "Investor")); st.rerun()
    else:
        st.info("Too few co-investing investors here to draw a network.")

if not ss["sel_investor_id"]:
    st.info("Click an investor to see their companies.")
    st.stop()


# ---- investor's companies as a ranked table (replaces the footprint map) ----
st.subheader(f"{ss['sel_investor_name']} — companies in {ctry_name} · {cat_name}")
inv_co_ids = companies_of_investor(dfs, ss["sel_investor_id"])
pool = companies[(companies["id"].isin(inv_co_ids)) &
                 (companies["category_code"] == ss["sel_category"]) &
                 (companies["country_code"] == ss["sel_country"])].copy()

if len(pool):
    last = (funding_rounds[funding_rounds["object_id"].isin(pool["id"])]
            .dropna(subset=["funded_at"]).sort_values("funded_at")
            .groupby("object_id").tail(1).set_index("object_id"))
    pool["last_type"] = pool["id"].map(last["funding_round_type"])
    pool["last_date"] = pool["id"].map(last["funded_at"])
    tbl = pd.DataFrame({
        "Company": pool["name"].values,
        "Status": pool["status"].values,
        "Total raised (US$M)": (pool["funding_total_usd"] / 1e6).values,
        "Last round": pool["last_type"].values,
        "Last round date": pd.to_datetime(pool["last_date"]).dt.date.values,
        "Founded": pool["founded_year"].values,
    }).sort_values("Total raised (US$M)", ascending=False, na_position="last").reset_index(drop=True)

    def _status_bg(v):
        return f"background-color: {STATUS_COLORS.get(v, '#EEEEEE')}33"
    sty = (tbl.style
           .background_gradient(subset=["Total raised (US$M)"], cmap="Blues")
           .map(_status_bg, subset=["Status"])
           .format({"Total raised (US$M)": "{:,.1f}", "Founded": "{:.0f}"}, na_rep="—"))

    st.caption("Ranked by total raised (darker = more). Click a row to open the comparison, "
               "or use the dropdown below.")
    ev = st.dataframe(sty, use_container_width=True, hide_index=True,
                      on_select="rerun", selection_mode="single-row", key=K("cotable"))
    rows = ev.selection.rows if hasattr(ev, "selection") else ev.get("selection", {}).get("rows", [])
    if rows:
        picked_name = tbl.iloc[rows[0]]["Company"]
        if picked_name != ss["sel_company"]:
            accept(sel_company=picked_name); st.rerun()

    names = sorted(pool["name"].dropna().unique())
    chosen = st.selectbox("Or pick a company", [None] + names,
                          index=([None] + names).index(ss["sel_company"]) if ss["sel_company"] in names else 0,
                          format_func=lambda x: "— select —" if x is None else x)
    if chosen != ss["sel_company"]:
        accept(sel_company=chosen); st.rerun()
else:
    st.info(f"{ss['sel_investor_name']} has no {cat_name} companies recorded in {ctry_name}. "
            "Pick another investor above.")

if not ss["sel_company"]:
    st.stop()


# ================= STEP 5 — COMPANY VS. ITS COHORT ======================
st.divider()
st.header(f"5 · {ss['sel_company']} vs. its cohort")
row = companies[companies["name"] == ss["sel_company"]].iloc[0]
_s = lambda v: "—" if pd.isna(v) else v
e1, e2, e3, e4 = st.columns(4)
e1.metric("Sector", _s(category_label(row["category_code"])))
e2.metric("Country", _s(country_label(row["country_code"])))
e3.metric("Status", _s(row["status"]))
e4.metric("Founded", int(row["founded_year"]) if pd.notna(row["founded_year"]) else "—")

cohort = companies[(companies["country_code"] == ss["sel_country"]) &
                   (companies["category_code"] == ss["sel_category"]) &
                   (companies["funding_total_usd"] > 0)]["funding_total_usd"]
med = cohort.median()
st.caption(f"The **cohort** is every funded {cat_name} company in {ctry_name} "
           f"({cohort.shape[0]:,} companies). The dashed line is that group's median total raised "
           f"({bil(med) if pd.notna(med) else 'N/A'}); the curve is this company's funding accumulating "
           "round by round, so you can read directly whether it ends up above or below a typical funded peer.")

cr = funding_rounds[funding_rounds["object_id"] == row["id"]].dropna(subset=["funded_at"]).sort_values("funded_at")
if not cr.empty:
    cr = cr.copy()
    cr["cum"] = cr["raised_amount_usd"].fillna(0).cumsum()
    f = go.Figure()
    f.add_trace(go.Scatter(x=cr["funded_at"], y=cr["cum"], mode="lines+markers",
                           fill="tozeroy", line=dict(color="#2563EB"),
                           name="Cumulative raised",
                           hovertext=[f"{t}: +${a:,.0f}" for t, a in
                                      zip(cr["funding_round_type"], cr["raised_amount_usd"].fillna(0))],
                           hoverinfo="text+y"))
    if pd.notna(med):
        f.add_hline(y=med, line_dash="dash", line_color="#F59E0B",
                    annotation_text=f"{ctry_name} · {cat_name} median (funded): {bil(med)}")
    f.update_layout(title=f"Cumulative funding — {ss['sel_company']}",
                    xaxis=dict(title="Date"), yaxis=dict(title="Cumulative raised (USD)"), height=430)
    st.plotly_chart(polish(f), use_container_width=True)
else:
    st.info("No dated funding-round records for this company.")


# --- Bipartite investor <-> company explorer (star layout, click to re-center) ---
st.divider()
st.subheader("Investor ↔ Company explorer")
st.caption("Star layout — the amber/blue center is the currently focused node; its direct "
           "connections radiate around it. **Click any circle to re-center on it** and explore "
           "laterally through the investor/company graph.")

# Seed the bipartite focus when the user first arrives in step 5 for this company
if ss.get("bip_seed_company") != ss["sel_company"]:
    ss["bip_focus_type"] = "company"
    ss["bip_focus_id"] = row["id"]
    ss["bip_seed_company"] = ss["sel_company"]

focus_type = ss["bip_focus_type"]
focus_id = ss["bip_focus_id"]
inv_df = dfs["investments"]
names_by_id = dfs["objects"].set_index("id")["name"]

if focus_type == "company":
    neighbor_ids = (inv_df.loc[inv_df["funded_object_id"] == focus_id, "investor_object_id"]
                    .dropna().unique().tolist())
    neighbor_type = "investor"
    focus_color = "#F59E0B"
    neighbor_color = "#93C5FD"
    focus_kind, neighbor_kind = "Company", "Investor"
else:
    neighbor_ids = (inv_df.loc[inv_df["investor_object_id"] == focus_id, "funded_object_id"]
                    .dropna().unique().tolist())
    neighbor_type = "company"
    focus_color = "#2563EB"
    neighbor_color = "#BBF7D0"
    focus_kind, neighbor_kind = "Investor", "Company"

CAP = 18
total_neighbors = len(neighbor_ids)
if total_neighbors > CAP:
    neighbor_ids = neighbor_ids[:CAP]
    st.caption(f"Showing first {CAP} of {total_neighbors} neighbors. Click one to re-center and drill further.")

focus_name = str(names_by_id.get(focus_id, "?"))
neighbor_names = [str(names_by_id.get(nid, "?")) for nid in neighbor_ids]

if neighbor_ids:
    theta = np.linspace(0, 2 * np.pi, len(neighbor_ids), endpoint=False)
    nxp = np.cos(theta)
    nyp = np.sin(theta)

    edge_x, edge_y = [], []
    for xn, yn in zip(nxp, nyp):
        edge_x += [0, float(xn), None]
        edge_y += [0, float(yn), None]
    edge_tr = go.Scatter(x=edge_x, y=edge_y, mode="lines",
                         line=dict(color="rgba(148,163,184,0.45)", width=1.5),
                         hoverinfo="none", showlegend=False)
    focus_tr = go.Scatter(
        x=[0], y=[0], mode="markers+text",
        marker=dict(size=56, color=focus_color, line=dict(width=2, color="#FFF")),
        text=[focus_name], textposition="middle center",
        textfont=dict(size=10, color="#FFF"),
        hovertext=[f"{focus_kind}: {focus_name}"], hoverinfo="text",
        customdata=[[focus_type, focus_id]], showlegend=False)
    neighbor_tr = go.Scatter(
        x=nxp, y=nyp, mode="markers+text",
        marker=dict(size=38, color=neighbor_color, line=dict(width=1, color="#FFF")),
        text=neighbor_names, textposition="middle center",
        textfont=dict(size=8, color="#0F172A"),
        hovertext=[f"{neighbor_kind}: {n}" for n in neighbor_names], hoverinfo="text",
        customdata=[[neighbor_type, nid] for nid in neighbor_ids],
        showlegend=False)

    fig_bip = go.Figure(data=[edge_tr, focus_tr, neighbor_tr])
    fig_bip.update_xaxes(visible=False, range=[-1.35, 1.35])
    fig_bip.update_yaxes(visible=False, scaleanchor="x", scaleratio=1, range=[-1.35, 1.35])
    fig_bip.update_layout(height=540, margin=dict(l=0, r=0, t=10, b=0),
                          plot_bgcolor="rgba(0,0,0,0)")
    sel_b = st.plotly_chart(fig_bip, use_container_width=True, on_select="rerun",
                            selection_mode="points", key=K("bipartite"))
    if sel_b and sel_b.get("selection", {}).get("points"):
        for pt in sel_b["selection"]["points"]:
            cd = pt.get("customdata")
            if cd and len(cd) == 2:
                new_type, new_id = cd
                if new_type != focus_type or new_id != focus_id:
                    accept(bip_focus_type=new_type, bip_focus_id=new_id)
                    st.rerun()
                break
else:
    st.info(f"{focus_kind} `{focus_name}` has no linked {neighbor_kind.lower()}s in the data.")

st.success("End of the walkthrough. Use the breadcrumb up top to back out and explore another "
           "country, sector, or investor.")
