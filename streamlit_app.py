import streamlit as st
import pandas as pd
import plotly.express as px
import os, io
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

st.set_page_config(page_title="Flipkart FC PV Dashboard", layout="wide", page_icon="📊")

# ── SITE → ZONE MAP ────────────────────────────────────────────────────────────
SITE_ZONE = {
    'frk_bts_RC':'North','malur_bts_RC':'West','Sanpka RC':'North',
    'nad_har_wh_kl_nl_01nl_RC':'East','Bhiwandi_BTS_RC':'West',
    'kol_uluberia_bts_RC':'East','Amd_khd_BTS':'West','Indore_02_FC':'West',
    'hyderabad_medchal_01':'South','Jaipur NLFC':'North',
    'guw_kam_wh_nl_02nl_RC':'East','cbe_oth_01_RC':'South','Patna FC 02':'East',
    'chn_tvr_04_RC':'South','Hubli_01_RC':'East',
    'Vijayawada  (vij_ved_wh_nl_01nl_RC)':'South','jal_bin_wh_nl_01nl':'East',
    'Nagpur_01':'West','Bhuneshwar BTS 01':'East','Lucknow_BTS_RC':'North',
    'Nagpur_01_RC':'West','rai_dha_wh_nl_02nl_RC':'East',
    'rai_dha_wh_nl_02nl':'East','lud_kha_wh_nl_01nl':'North',
}
ALLOWED_SITES = set(SITE_ZONE.keys())
ML = {'1':'Jan','2':'Feb','3':'Mar','4':'Apr','5':'May','6':'Jun',
      '7':'Jul','8':'Aug','9':'Sep','10':'Oct','11':'Nov','12':'Dec'}

# ── CUSTOM CSS (matches HTML dashboard) ───────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');

* { font-family: 'Inter', sans-serif !important; }
[data-testid="stAppViewContainer"] { background: #1e2130 !important; }
[data-testid="stHeader"] { background: #1e2130 !important; }
[data-testid="stSidebar"] { display: none !important; }
.block-container { padding: 3.5rem 1.5rem 1rem 1.5rem !important; max-width: 100% !important; }

/* Header */
.dash-header {
    background: linear-gradient(135deg, #2c3e6b 0%, #1a2a4a 100%);
    border-bottom: 3px solid #F8CA00;
    padding: 14px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 0rem -1.5rem 1rem -1.5rem;
}
.dash-title { color: #F8CA00; font-size: 26px; font-weight: 800; margin: 0; letter-spacing: 0.5px; }
.dash-subtitle { color: #cbd5e1; font-size: 12px; margin: 4px 0 0 0; }

/* Filter bar */
.filter-bar {
    background: #2a2f45;
    border: 1px solid #3a4060;
    border-radius: 10px;
    padding: 10px 16px;
    margin-bottom: 14px;
}
.filter-label { color: #94a3b8; font-size: 10px; font-weight: 600; text-transform: uppercase; margin-bottom: 3px; }

/* KPI Cards */
.kpi-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 14px; }
.kpi-card {
    background: #2a2f45;
    border: 1px solid #3a4060;
    border-radius: 12px;
    padding: 16px 20px;
    text-align: center;
}
.kpi-label { color: #94a3b8; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
.kpi-value { font-size: 32px; font-weight: 800; margin: 4px 0 0 0; }
.kpi-green { color: #16a34a; }
.kpi-yellow { color: #d97706; }
.kpi-red { color: #dc2626; }
.kpi-blue { color: #2563eb; }

/* Section headers */
.section-title {
    color: #F8CA00;
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    border-left: 3px solid #F8CA00;
    padding-left: 10px;
    margin: 16px 0 8px 0;
}

/* Tables */
.stDataFrame { border-radius: 8px; overflow: hidden; }
div[data-testid="stDataFrame"] > div { border-radius: 8px; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { background: #2a2f45; border-radius: 8px; padding: 4px; gap: 4px; }
.stTabs [data-baseweb="tab"] { background: transparent; color: #94a3b8; border-radius: 6px; font-size: 12px; font-weight: 600; padding: 6px 16px; }
.stTabs [aria-selected="true"] { background: #F8CA00 !important; color: #1a1a1a !important; }

/* Selectbox */
.stSelectbox > div > div { background: #2a2f45 !important; border: 1px solid #3a4060 !important; border-radius: 6px !important; color: #e2e8f0 !important; font-size: 12px !important; }

div[data-testid="metric-container"] { display: none; }
</style>
""", unsafe_allow_html=True)

# ── LOAD DATA ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Loading latest data from Google Drive...")
def load_data():
    folder_id = st.secrets["GDRIVE_FOLDER_ID"]
    creds = Credentials(
        token=None,
        refresh_token=st.secrets["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=st.secrets["GOOGLE_CLIENT_ID"],
        client_secret=st.secrets["GOOGLE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    files, token = [], None
    while True:
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false and (mimeType='text/csv' or name contains '.csv')",
            orderBy="modifiedTime desc", pageSize=100, pageToken=token,
            fields="nextPageToken, files(id, name, modifiedTime)"
        ).execute()
        files += results.get("files", [])
        token = results.get("nextPageToken")
        if not token: break
    if not files:
        st.error("No CSV file found in your Google Drive folder.")
        st.stop()
    frames = []
    for f in files:
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, service.files().get_media(fileId=f["id"]))
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buf.seek(0)
        frames.append(pd.read_csv(buf, low_memory=False))
    df = pd.concat(frames, ignore_index=True).drop_duplicates()
    df = df[df['Site: Site Name'].isin(ALLOWED_SITES)].copy()
    df['Zone'] = df['Site: Site Name'].map(SITE_ZONE)
    def parse_month(v):
        if pd.isna(v): return None
        p = str(v).split('/')
        return (p[2] + '-' + p[1].zfill(2)) if len(p) == 3 else None
    df['MonthKey'] = df['Month'].apply(parse_month)
    def month_label(k):
        if not k: return ''
        y, m = k.split('-')
        return ML.get(str(int(m)), m) + ' ' + y[2:]
    df['MonthLabel'] = df['MonthKey'].apply(month_label)
    return df

try:
    df_raw = load_data()
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

# ── HELPERS ────────────────────────────────────────────────────────────────────
def pv_acc(df):
    no  = (df['Wrong PV'] == 'No').sum()
    yes = (df['Wrong PV'] == 'Yes').sum()
    t   = no + yes
    return round((no / t) * 100, 2) if t > 0 else None

def sample_size(df):
    return df['WSN'].count()

def fmt(v):
    return f"{v:.2f}%" if v is not None else "—"

def fmt_with_n(v, n):
    if v is None or n == 0: return "—"
    return f"{v:.2f}%\n{int(n)}"

def kpi_color_class(v):
    if v is None: return "kpi-blue"
    if v >= 98.5: return "kpi-green"
    if v >= 97:   return "kpi-yellow"
    return "kpi-red"

def style_acc(val):
    if val == "—" or val is None: return "color: #4a5568"
    try:
        v = float(str(val).split('%')[0])
        if v >= 98.5: return "color: #22c55e; font-weight:bold"
        if v >= 97:   return "color: #F8CA00; font-weight:bold"
        return "color: #ef4444; font-weight:bold"
    except: return ""

def style_n(val):
    if val == "—" or val == 0: return "color: #4a5568; font-size:11px"
    return "color: #94a3b8; font-size:11px"

# ── HEADER ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="dash-header">
  <div>
    <div class="dash-title">PV Accuracy Dashboard Pan India</div>
    <div class="dash-subtitle">Flipkart FC · Physical Verification Accuracy Tracker · {len(df_raw):,} records loaded</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── FILTERS IN ONE ROW ─────────────────────────────────────────────────────────
months_sorted = sorted(df_raw['MonthKey'].dropna().unique())
month_opts    = {k: df_raw[df_raw['MonthKey']==k]['MonthLabel'].iloc[0] for k in months_sorted}

st.markdown('<div class="filter-bar">', unsafe_allow_html=True)
c1,c2,c3,c4,c5,c6,c7 = st.columns(7)
with c1:
    st.markdown('<div class="filter-label">Month</div>', unsafe_allow_html=True)
    sel_month = st.selectbox("Month", ["All"]+[month_opts[k] for k in months_sorted], label_visibility="collapsed")
with c2:
    st.markdown('<div class="filter-label">Week</div>', unsafe_allow_html=True)
    sel_week = st.selectbox("Week", ["All"]+sorted(df_raw['Week Number'].dropna().unique(), key=lambda x: int(x)), label_visibility="collapsed")
with c3:
    st.markdown('<div class="filter-label">Zone</div>', unsafe_allow_html=True)
    sel_zone = st.selectbox("Zone", ["All","North","South","East","West"], label_visibility="collapsed")
with c4:
    st.markdown('<div class="filter-label">Site</div>', unsafe_allow_html=True)
    sel_site = st.selectbox("Site", ["All"]+sorted(df_raw['Site: Site Name'].dropna().unique()), label_visibility="collapsed")
with c5:
    st.markdown('<div class="filter-label">Business Unit</div>', unsafe_allow_html=True)
    sel_bu = st.selectbox("BU", ["All"]+sorted(df_raw['Business unit'].dropna().unique()), label_visibility="collapsed")
with c6:
    st.markdown('<div class="filter-label">CMS Vertical</div>', unsafe_allow_html=True)
    sel_vert = st.selectbox("Vertical", ["All"]+sorted(df_raw['CMS Vertical'].dropna().unique()), label_visibility="collapsed")
with c7:
    st.markdown('<div class="filter-label">Location</div>', unsafe_allow_html=True)
    sel_loc = st.selectbox("Location", ["All"]+sorted(df_raw['Location'].dropna().unique()), label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

# ── APPLY FILTERS ──────────────────────────────────────────────────────────────
df = df_raw.copy()
if sel_month != "All":
    mk = [k for k,v in month_opts.items() if v == sel_month]
    if mk: df = df[df['MonthKey'] == mk[0]]
if sel_week  != "All": df = df[df['Week Number']     == sel_week]
if sel_zone  != "All": df = df[df['Zone']            == sel_zone]
if sel_site  != "All": df = df[df['Site: Site Name'] == sel_site]
if sel_bu    != "All": df = df[df['Business unit']   == sel_bu]
if sel_vert  != "All": df = df[df['CMS Vertical']    == sel_vert]
if sel_loc   != "All": df = df[df['Location']        == sel_loc]

pass_df = df[df['Audit Type'] == 'PV Pass Audit']
fail_df = df[df['Audit Type'] == 'PV Fail Audit']

# ── KPI CARDS ──────────────────────────────────────────────────────────────────
ov  = pv_acc(df)
pv  = pv_acc(pass_df)
fv  = pv_acc(fail_df)
wrong_yes = int((df['Wrong PV']=='Yes').sum())

st.markdown(f"""
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">Overall PV Accuracy</div>
    <div class="kpi-value {kpi_color_class(ov)}">{fmt(ov)}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">PV Pass Accuracy</div>
    <div class="kpi-value {kpi_color_class(pv)}">{fmt(pv)}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">PV Fail Accuracy</div>
    <div class="kpi-value {kpi_color_class(fv)}">{fmt(fv)}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── MONTH-WISE TABLE ───────────────────────────────────────────────────────────
st.markdown('<div class="section-title">📅 PV Accuracy — Month Wise</div>', unsafe_allow_html=True)
months = sorted(df['MonthKey'].dropna().unique())
if months:
    rows = []
    for label, flt in [("Overall PV Accuracy", df),
                        ("PV Pass Accuracy",    pass_df),
                        ("PV Fail Accuracy",    fail_df)]:
        row = {"Metric": label}
        for mk in months:
            ml = month_opts.get(mk, mk)
            sub = flt[flt['MonthKey'] == mk]
            row[ml] = fmt(pv_acc(sub))
        rows.append(row)
    mdf = pd.DataFrame(rows).set_index("Metric")
    st.dataframe(mdf.style.map(style_acc), use_container_width=True, height=140)
else:
    st.info("No data available")

# ── SITE-WISE TABLE ────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">🏭 Site-wise PV Accuracy</div>', unsafe_allow_html=True)

mj_weeks = sorted(
    df[df['MonthKey'] == (months[-1] if months else None)]['Week Number'].dropna().unique(),
    key=lambda x: int(x)
)
ZONE_ORDER = {'North':1,'East':2,'West':3,'South':4}

def build_site_table(src_df):
    zones = ['North', 'East', 'West', 'South']
    sites_all = sorted(df['Site: Site Name'].dropna().unique(),
                       key=lambda s: (ZONE_ORDER.get(SITE_ZONE.get(s,''),9), s))
    rows = []
    for zone in zones:
        zone_sites = [s for s in sites_all if SITE_ZONE.get(s,'') == zone]
        if not zone_sites: continue
        # Zone subtotal row
        zone_src = src_df[src_df['Zone'] == zone]
        zrow = {"Site": f"▶ {zone} Zone", "Zone": zone}
        for mk in months:
            ml = month_opts.get(mk, mk)
            sub = zone_src[zone_src['MonthKey'] == mk]
            zrow[ml] = fmt(pv_acc(sub))
        for wk in mj_weeks:
            sub = zone_src[zone_src['Week Number'] == wk]
            zrow[f"Wk {wk}"] = fmt(pv_acc(sub))
        rows.append(zrow)
        # Individual sites
        for site in zone_sites:
            row = {"Site": f"  {site}", "Zone": ""}
            site_src = src_df[src_df['Site: Site Name'] == site]
            for mk in months:
                ml = month_opts.get(mk, mk)
                sub = site_src[site_src['MonthKey'] == mk]
                row[ml] = fmt(pv_acc(sub))
            for wk in mj_weeks:
                sub = site_src[site_src['Week Number'] == wk]
                row[f"Wk {wk}"] = fmt(pv_acc(sub))
            rows.append(row)
    return pd.DataFrame(rows).set_index("Site")

def build_sample_table(src_df):
    zones = ['North', 'East', 'West', 'South']
    sites_all = sorted(df['Site: Site Name'].dropna().unique(),
                       key=lambda s: (ZONE_ORDER.get(SITE_ZONE.get(s,''),9), s))
    rows = []
    for zone in zones:
        zone_sites = [s for s in sites_all if SITE_ZONE.get(s,'') == zone]
        if not zone_sites: continue
        # Zone subtotal row
        zone_src = src_df[src_df['Zone'] == zone]
        zrow = {"Site": f"▶ {zone} Zone", "Zone": zone}
        for mk in months:
            ml = month_opts.get(mk, mk)
            sub = zone_src[zone_src['MonthKey'] == mk]
            n = sample_size(sub)
            zrow[ml] = str(int(n)) if n > 0 else "—"
        for wk in mj_weeks:
            sub = zone_src[zone_src['Week Number'] == wk]
            n = sample_size(sub)
            zrow[f"Wk {wk}"] = str(int(n)) if n > 0 else "—"
        rows.append(zrow)
        # Individual sites
        for site in zone_sites:
            row = {"Site": f"  {site}", "Zone": ""}
            site_src = src_df[src_df['Site: Site Name'] == site]
            for mk in months:
                ml = month_opts.get(mk, mk)
                sub = site_src[site_src['MonthKey'] == mk]
                n = sample_size(sub)
                row[ml] = str(int(n)) if n > 0 else "—"
            for wk in mj_weeks:
                sub = site_src[site_src['Week Number'] == wk]
                n = sample_size(sub)
                row[f"Wk {wk}"] = str(int(n)) if n > 0 else "—"
            rows.append(row)
    return pd.DataFrame(rows).set_index("Site")

acc_cols = [month_opts.get(mk,mk) for mk in months] + [f"Wk {w}" for w in mj_weeks]

tab1, tab2, tab3 = st.tabs(["📊 Overall", "✅ PV Pass", "❌ PV Fail"])
def style_acc_zone(val): return style_acc(val)

def style_site_full(df_s):
    styles = pd.DataFrame('', index=df_s.index, columns=df_s.columns)
    for idx in df_s.index:
        is_zone = str(idx).startswith("▶")
        for col in df_s.columns:
            val = df_s.loc[idx, col]
            if is_zone:
                base = style_acc(val)
                styles.loc[idx, col] = base + "; background-color:#2e3a2e;" if "22c55e" in base else \
                                        base + "; background-color:#3a3520;" if "F8CA00" in base else \
                                        base + "; background-color:#3a2020;" if "ef4444" in base else \
                                        "color:#F8CA00; font-weight:800; background-color:#2a2f45;"
            else:
                styles.loc[idx, col] = style_acc(val)
    return styles

def style_sample_full(df_s):
    styles = pd.DataFrame('', index=df_s.index, columns=df_s.columns)
    for idx in df_s.index:
        is_zone = str(idx).startswith("▶")
        for col in df_s.columns:
            val = df_s.loc[idx, col]
            try:
                v = int(val)
                if v >= 500:   c = "color:#22c55e; font-weight:bold"
                elif v >= 100: c = "color:#F8CA00; font-weight:bold"
                else:          c = "color:#ef4444; font-weight:bold"
            except: c = "color:#4a5568"
            styles.loc[idx, col] = c + ("; background-color:#2a2f45; font-weight:800;" if is_zone else "")
    return styles

for tab, src in [(tab1, df), (tab2, pass_df), (tab3, fail_df)]:
    with tab:
        sdf = build_site_table(src)
        st.markdown("**PV Accuracy % — Zone Subtotal + Site Wise**")
        st.dataframe(sdf.style.apply(style_site_full, axis=None, subset=acc_cols), use_container_width=True, height=650)
        st.markdown('<div class="section-title" style="margin-top:12px">📊 Sample Count (WSN) — Zone Subtotal + Site Wise</div>', unsafe_allow_html=True)
        ndf = build_sample_table(src)
        st.dataframe(ndf.style.apply(style_sample_full, axis=None, subset=acc_cols), use_container_width=True, height=650)

# ── LOCATION TABLE (PV Fail) ───────────────────────────────────────────────────
st.markdown('<div class="section-title">📍 Location-wise PV Accuracy — PV Fail Audit</div>', unsafe_allow_html=True)
locs = sorted(fail_df['Location'].dropna().unique())
if locs:
    loc_rows = []
    for loc in locs:
        row = {"Location": loc}
        loc_src = fail_df[fail_df['Location'] == loc]
        for mk in months:
            ml = month_opts.get(mk, mk)
            sub = loc_src[loc_src['MonthKey'] == mk]
            row[ml] = fmt(pv_acc(sub))
        for wk in mj_weeks:
            sub = loc_src[loc_src['Week Number'] == wk]
            row[f"Wk {wk}"] = fmt(pv_acc(sub))
        loc_rows.append(row)
    ldf = pd.DataFrame(loc_rows).set_index("Location")
    st.dataframe(ldf.style.map(style_acc, subset=acc_cols), use_container_width=True, height=400)
else:
    st.info("No data")

# ── TOP 10 CMS VERTICALS ───────────────────────────────────────────────────────
st.markdown('<div class="section-title">📦 Top 10 CMS Verticals by Wrong PV</div>', unsafe_allow_html=True)
vert_data = fail_df[fail_df['Wrong PV']=='Yes']['CMS Vertical'].value_counts().head(10).reset_index()
vert_data.columns = ['CMS Vertical','Wrong PV Count']
if not vert_data.empty:
    fig = px.bar(vert_data, x='Wrong PV Count', y='CMS Vertical', orientation='h',
                 color_discrete_sequence=['#F8CA00'])
    fig.update_layout(
        paper_bgcolor='#2a2f45', plot_bgcolor='#2a2f45',
        font_color='#e2e8f0',
        yaxis={'categoryorder':'total ascending', 'tickfont':{'color':'#e2e8f0','size':12}},
        xaxis={'tickfont':{'color':'#e2e8f0'}},
        margin=dict(l=0,r=0,t=10,b=0), height=320
    )
    st.plotly_chart(fig, use_container_width=True)

# ── FAILURE REASON ANALYSIS ────────────────────────────────────────────────────
st.markdown('<div class="section-title">🔍 Failure Reason Analysis — Issue Type / Checkpoint</div>', unsafe_allow_html=True)

ISSUE_COL = 'Issue Type / Checkpoint'

# Common sub-filters for this section
fr_c1, fr_c2, fr_c3 = st.columns([2, 2, 2])
with fr_c1:
    fr_sites = ["All"] + sorted(df['Site: Site Name'].dropna().unique())
    fr_site = st.selectbox("Filter by Site", fr_sites, key="fr_site")
with fr_c2:
    fr_zone = st.selectbox("Filter by Zone", ["All","North","South","East","West"], key="fr_zone")
with fr_c3:
    fr_weeks_list = ["All"] + sorted(df['Week Number'].dropna().unique(), key=lambda x: int(x))
    fr_week = st.selectbox("Filter by Week", fr_weeks_list, key="fr_week")

def apply_fr_filters(src):
    d = src.copy()
    if fr_site != "All": d = d[d['Site: Site Name'] == fr_site]
    if fr_zone != "All": d = d[d['Zone'] == fr_zone]
    if fr_week != "All": d = d[d['Week Number'] == fr_week]
    return d

def render_reason_section(src_df, color_scale, bar_color):
    if ISSUE_COL not in src_df.columns or src_df.empty:
        st.info("No data for selected filters.")
        return
    col_left, col_right = st.columns([1, 1])
    with col_left:
        st.markdown("**Count & % Contribution**")
        rc = src_df[ISSUE_COL].value_counts().reset_index()
        rc.columns = ['Issue Type', 'Count']
        total = rc['Count'].sum()
        rc['%'] = (rc['Count'] / total * 100).round(1)
        rc['Label'] = rc.apply(lambda r: f"{r['Count']} ({r['%']}%)", axis=1)
        fig = px.bar(rc.head(15), x='Count', y='Issue Type', orientation='h',
                     text='Label', color='Count', color_continuous_scale=color_scale)
        fig.update_traces(textposition='outside', textfont_size=10, textfont_color='#e2e8f0')
        fig.update_layout(
            paper_bgcolor='#2a2f45', plot_bgcolor='#2a2f45', font_color='#e2e8f0',
            yaxis={'categoryorder':'total ascending', 'tickfont':{'color':'#e2e8f0','size':11}},
            xaxis={'tickfont':{'color':'#e2e8f0'}},
            coloraxis_showscale=False,
            margin=dict(l=0, r=90, t=10, b=0), height=420
        )
        st.plotly_chart(fig, use_container_width=True)
        if not rc.empty:
            top1 = rc.iloc[0]
            st.info(f"**Top Issue:** '{top1['Issue Type']}' — **{top1['%']}%** ({top1['Count']:,} cases)")

    with col_right:
        st.markdown("**Week-wise Breakdown**")
        wk_list = sorted(src_df['Week Number'].dropna().unique(), key=lambda x: int(x))
        top_reasons = src_df[ISSUE_COL].value_counts().head(10).index.tolist()
        wk_rows = []
        for reason in top_reasons:
            row = {'Issue Type': reason}
            r_df = src_df[src_df[ISSUE_COL] == reason]
            for wk in wk_list:
                cnt = int((r_df['Week Number'] == wk).sum())
                row[f'Wk {wk}'] = cnt if cnt > 0 else '—'
            row['Total'] = int((src_df[ISSUE_COL] == reason).sum())
            wk_rows.append(row)
        wk_df = pd.DataFrame(wk_rows).set_index('Issue Type')

        def highlight_high(val):
            if val == '—' or val == 0: return 'color: #9ca3af'
            try:
                v = int(val)
                if v >= 50: return 'background-color: #fee2e2; color: #dc2626; font-weight:bold'
                if v >= 20: return 'background-color: #fef9c3; color: #d97706; font-weight:bold'
                return 'color: #374151'
            except: return ''

        st.dataframe(wk_df.style.map(highlight_high), use_container_width=True, height=420)

fr_tab1, fr_tab2 = st.tabs(["❌ PV Fail — Wrong PV", "✅ PV Pass — Wrong PV"])

with fr_tab1:
    fail_wrong = apply_fr_filters(df[(df['Audit Type'] == 'PV Fail Audit') & (df['Wrong PV'] == 'Yes')])
    render_reason_section(fail_wrong, ['#fecaca','#dc2626'], '#dc2626')

with fr_tab2:
    pass_wrong = apply_fr_filters(df[(df['Audit Type'] == 'PV Pass Audit') & (df['Wrong PV'] == 'Yes')])
    render_reason_section(pass_wrong, ['#bbf7d0','#16a34a'], '#16a34a')

st.markdown("<div style='color:#6b7280;font-size:11px;text-align:center;margin-top:20px'>Flipkart FC PV Audit Dashboard · Data refreshes every hour</div>", unsafe_allow_html=True)
