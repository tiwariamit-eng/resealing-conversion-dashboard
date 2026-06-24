import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import time
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

# ─── PAGE CONFIG ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Flipkart — RTO/RVP Resealing Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── CUSTOM CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Dark theme overrides */
[data-testid="stAppViewContainer"] { background-color: #0d0f14; }
[data-testid="stSidebar"] { background-color: #13161e; border-right: 1px solid rgba(255,255,255,0.07); }
[data-testid="stHeader"] { background-color: #0d0f14; }

/* Metric cards */
[data-testid="metric-container"] {
    background: #1e2230;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
    padding: 14px 18px;
}
[data-testid="stMetricValue"] { font-size: 28px !important; font-weight: 700 !important; }
[data-testid="stMetricDelta"] { font-size: 12px !important; }

/* Headers */
h1, h2, h3 { color: #f0f2f8 !important; }
p, li { color: #8891a8; }

/* Selectbox */
[data-testid="stSelectbox"] > div > div {
    background: #1a1e29;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 6px;
}

/* Live badge */
.live-badge {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(54,217,164,0.12);
    border: 1px solid rgba(54,217,164,0.3);
    color: #36d9a4; font-size: 12px; font-weight: 700;
    padding: 4px 12px; border-radius: 20px;
    letter-spacing: 0.06em;
}
.live-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: #36d9a4; display: inline-block;
    animation: pulse 1.5s infinite;
}
@keyframes pulse {
    0%   { box-shadow: 0 0 0 0 rgba(54,217,164,0.7); }
    70%  { box-shadow: 0 0 0 6px rgba(54,217,164,0); }
    100% { box-shadow: 0 0 0 0 rgba(54,217,164,0); }
}

/* KPI row colors */
.kpi-pass  { color: #36d9a4 !important; }
.kpi-fail  { color: #f05050 !important; }
.kpi-warn  { color: #f5a623 !important; }

/* Section header */
.section-header {
    font-size: 11px; font-weight: 600; color: #8891a8;
    text-transform: uppercase; letter-spacing: 0.09em;
    margin-bottom: 8px; margin-top: 4px;
}

/* Divider */
hr { border-color: rgba(255,255,255,0.07) !important; }

/* Scrollable table */
.dataframe-container { max-height: 400px; overflow-y: auto; }
</style>
""", unsafe_allow_html=True)

# ─── GOOGLE DRIVE AUTH ────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://spreadsheets.google.com/feeds",
]

FOLDER_ID = "1wfyMOkNiJGYYIcu9L2IYS-k6Yi-Z6MgL"  # Your Resealing Conversion folder

@st.cache_resource(show_spinner=False)
def get_drive_service():
    """Authenticate with Google Drive using service account credentials."""
    try:
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=SCOPES
        )
        service = build("drive", "v3", credentials=creds)
        return service, creds
    except Exception as e:
        st.error(f"❌ Google Drive auth failed: {e}")
        st.info("👉 Make sure you added your service account JSON to Streamlit secrets. See setup guide below.")
        return None, None

# ─── DATA LOADING ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)  # Cache for 5 minutes
def load_all_data():
    """Scan Drive folder, download all CSVs, combine into one DataFrame."""
    service, creds = get_drive_service()
    if not service:
        return pd.DataFrame()

    # List all CSV files in the folder
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and mimeType='text/csv' and trashed=false",
        fields="files(id, name, modifiedTime)",
        orderBy="modifiedTime desc"
    ).execute()
    files = results.get("files", [])

    if not files:
        st.warning("No CSV files found in the Google Drive folder.")
        return pd.DataFrame()

    dfs = []
    progress = st.progress(0, text="Loading data from Google Drive...")

    for i, f in enumerate(files):
        try:
            request = service.files().get_media(fileId=f["id"])
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            buf.seek(0)
            df = pd.read_csv(buf, low_memory=False, on_bad_lines="skip")
            df["_source_file"] = f["name"]
            dfs.append(df)
            progress.progress(
                int((i + 1) / len(files) * 100),
                text=f"Loaded {f['name']} ({i+1}/{len(files)})"
            )
        except Exception as e:
            st.warning(f"Skipped {f['name']}: {e}")

    progress.empty()

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)
    return clean_data(df)


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names and types."""
    # Rename columns to standard names
    col_map = {
        "RC Name": "rc",
        "Zone": "zone",
        "Week": "week",
        "RTO / RVP": "type",
        "RTO / RVP Status": "type",
        "Result": "result",
        "QA remark": "reason",
        "RC QC Remarks": "reason_raw",
        "Vertical 1": "vertical",
        "Vertical": "vertical_base",
        "Brand Name": "brand",
        "Timestamp": "timestamp",
        "Final Bulk Movement": "final_status",
        "Final PV remarks": "final_status",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # Normalize result
    if "result" in df.columns:
        df["result"] = df["result"].str.strip().str.lower()
        df = df[df["result"].isin(["pass", "fail"])].copy()
        df["pass"] = df["result"] == "pass"
    else:
        return pd.DataFrame()

    # Normalize type
    if "type" in df.columns:
        df["type"] = df["type"].str.strip().str.upper().str[:3]
        df["type"] = df["type"].where(df["type"].isin(["RTO", "RVP"]), "RTO")

    # Normalize week
    if "week" in df.columns:
        df["week"] = pd.to_numeric(df["week"], errors="coerce").fillna(0).astype(int)
        df = df[df["week"] > 0]

    # Normalize vertical
    if "vertical" in df.columns:
        df["vertical"] = (df["vertical"]
            .str.replace(r"^RTO[_ ]+", "", regex=True)
            .str.replace(r"^RVP[_ ]+", "", regex=True)
            .str.strip())

    # Normalize reason
    if "reason" in df.columns:
        df["reason"] = df["reason"].fillna("").str.strip()
        df["reason"] = df["reason"].where(
            ~df["reason"].str.lower().isin(["no issue", "no issue.", ""]), ""
        )
        # Clean numeric prefix like "1. No Issues"
        df["reason"] = df["reason"].str.replace(r"^\d+\.\s*", "", regex=True).str.strip()

    # Drop rows with missing critical fields
    for col in ["rc", "zone", "type"]:
        if col in df.columns:
            df = df[df[col].notna() & (df[col] != "")]

    df = df.reset_index(drop=True)
    return df


# ─── PLOTLY THEME ─────────────────────────────────────────────────────────────
PLOT_BG    = "#1e2230"
PAPER_BG   = "#1e2230"
FONT_COLOR = "#8891a8"
GRID_COLOR = "rgba(255,255,255,0.05)"
GREEN = "#36d9a4"
RED   = "#f05050"
BLUE  = "#4f8ef7"
AMBER = "#f5a623"
PURPLE= "#a78bfa"

def base_layout(title=""):
    return dict(
        plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG,
        font=dict(color=FONT_COLOR, family="Inter, sans-serif", size=11),
        margin=dict(l=10, r=10, t=30 if title else 10, b=10),
        title=dict(text=title, font=dict(color="#f0f2f8", size=13)) if title else None,
        xaxis=dict(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR),
        yaxis=dict(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR),
    )


# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
def render_sidebar(df: pd.DataFrame):
    with st.sidebar:
        st.markdown("""
        <div style='text-align:center;padding:12px 0'>
          <div style='background:linear-gradient(135deg,#1d4ed8,#4f8ef7);color:#fff;
            font-size:11px;font-weight:700;letter-spacing:.08em;
            padding:4px 14px;border-radius:4px;display:inline-block'>FLIPKART</div>
          <div style='font-size:14px;font-weight:600;color:#f0f2f8;margin-top:8px'>
            RTO / RVP Resealing
          </div>
          <div style='font-size:11px;color:#8891a8'>Live Dashboard</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="live-badge"><span class="live-dot"></span> LIVE</div>',
                    unsafe_allow_html=True)
        st.caption(f"Last loaded: {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
        st.markdown("---")

        st.markdown("### 🔍 Filters")

        zones = ["All Zones"] + sorted(df["zone"].dropna().unique().tolist())
        sel_zone = st.selectbox("Zone", zones)

        # Filter RC list by zone
        df_zone = df if sel_zone == "All Zones" else df[df["zone"] == sel_zone]
        rcs = ["All RC / Sites"] + sorted(df_zone["rc"].dropna().unique().tolist())
        sel_rc = st.selectbox("RC / Site", rcs)

        weeks = ["All Weeks"] + [str(w) for w in sorted(df["week"].unique())]
        sel_week = st.selectbox("Week", weeks)

        verts = ["All Verticals"] + sorted(df["vertical"].dropna().unique().tolist()) if "vertical" in df.columns else ["All Verticals"]
        sel_vert = st.selectbox("Vertical", verts)

        sel_type = st.selectbox("Type", ["RTO + RVP", "RTO only", "RVP only"])

        st.markdown("---")
        st.markdown("### 📁 Add New Data")
        uploaded = st.file_uploader(
            "Upload new weekly CSV",
            type=["csv"],
            help="Upload a new weekly CSV file — same column format as existing files"
        )

        st.markdown("---")
        st.caption("Auto-refreshes every 5 minutes")
        if st.button("🔄 Refresh Now", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    return sel_zone, sel_rc, sel_week, sel_vert, sel_type, uploaded


# ─── APPLY FILTERS ────────────────────────────────────────────────────────────
def apply_filters(df, sel_zone, sel_rc, sel_week, sel_vert, sel_type):
    fd = df.copy()
    if sel_zone != "All Zones":
        fd = fd[fd["zone"] == sel_zone]
    if sel_rc != "All RC / Sites":
        fd = fd[fd["rc"] == sel_rc]
    if sel_week != "All Weeks":
        fd = fd[fd["week"] == int(sel_week)]
    if sel_vert != "All Verticals" and "vertical" in fd.columns:
        fd = fd[fd["vertical"] == sel_vert]
    if sel_type == "RTO only":
        fd = fd[fd["type"] == "RTO"]
    elif sel_type == "RVP only":
        fd = fd[fd["type"] == "RVP"]
    return fd


# ─── KPI ROW ──────────────────────────────────────────────────────────────────
def render_kpis(df: pd.DataFrame, df_full: pd.DataFrame):
    total  = len(df)
    passes = df["pass"].sum()
    fails  = total - passes
    pct    = round(passes / total * 100, 1) if total else 0
    sites  = df["rc"].nunique()
    weeks  = df["week"].nunique()

    # Compare pass% to full dataset
    full_pct = round(df_full["pass"].sum() / len(df_full) * 100, 1) if len(df_full) else 0
    delta = round(pct - full_pct, 1)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("📦 Total Records",  f"{total:,}",    f"{weeks} weeks")
    c2.metric("✅ PV Pass",        f"{passes:,}",   f"{pct}% pass rate")
    c3.metric("❌ PV Fail",        f"{fails:,}",    f"{round(fails/total*100,1) if total else 0}% fail rate")
    c4.metric("🎯 Pass %",         f"{pct}%",       f"{delta:+.1f}% vs overall", delta_color="normal")
    c5.metric("🏭 Active Sites",   f"{sites}",      f"{df['zone'].nunique()} zones")
    c6.metric("📅 Weeks",          f"{weeks}",      f"Wk {df['week'].min()}–{df['week'].max()}" if weeks else "")


# ─── CHARTS ───────────────────────────────────────────────────────────────────
def chart_zone_pass(df):
    grp = df.groupby("zone").agg(
        total=("pass","count"), passes=("pass","sum")
    ).reset_index()
    grp["pass_pct"] = (grp["passes"] / grp["total"] * 100).round(1)
    grp["color"] = grp["pass_pct"].apply(
        lambda x: GREEN if x >= 85 else AMBER if x >= 70 else RED
    )
    fig = go.Figure(go.Bar(
        x=grp["zone"], y=grp["pass_pct"],
        marker_color=grp["color"], text=grp["pass_pct"].astype(str) + "%",
        textposition="outside", marker_line_width=0,
        customdata=grp[["total","passes"]],
        hovertemplate="<b>%{x}</b><br>Pass: %{y}%<br>Total: %{customdata[0]:,}<extra></extra>"
    ))
    fig.update_layout(**base_layout(), yaxis_range=[0, 110],
                      yaxis_ticksuffix="%", height=240)
    return fig


def chart_week_trend(df):
    grp = df.groupby("week").agg(
        total=("pass","count"), passes=("pass","sum")
    ).reset_index().sort_values("week")
    grp["pass_pct"] = (grp["passes"] / grp["total"] * 100).round(1)

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=grp["week"].astype(str), y=grp["total"], name="Volume",
        marker_color="rgba(79,142,247,0.25)", marker_line_width=0
    ), secondary_y=True)
    fig.add_trace(go.Scatter(
        x=grp["week"].astype(str), y=grp["pass_pct"], name="Pass %",
        line=dict(color=GREEN, width=2.5), mode="lines+markers",
        marker=dict(size=6, color=GREEN),
        hovertemplate="Week %{x}: %{y}%<extra></extra>"
    ), secondary_y=False)
    fig.update_layout(**base_layout(), height=240, showlegend=False,
                      xaxis_title="Week")
    fig.update_yaxes(ticksuffix="%", range=[0,100], secondary_y=False,
                     gridcolor=GRID_COLOR)
    fig.update_yaxes(showgrid=False, secondary_y=True)
    return fig


def chart_donut(df):
    counts = df["type"].value_counts().reset_index()
    counts.columns = ["type", "count"]
    fig = px.pie(counts, values="count", names="type",
                 hole=0.66, color="type",
                 color_discrete_map={"RTO": BLUE, "RVP": GREEN})
    fig.update_traces(textinfo="none",
                      hovertemplate="<b>%{label}</b><br>%{value:,} records<br>%{percent}<extra></extra>")
    fig.update_layout(**base_layout(), height=200, showlegend=True,
                      legend=dict(orientation="h", y=-0.1,
                                  font=dict(color=FONT_COLOR, size=11)))
    return fig


def chart_type_pass(df):
    grp = df.groupby("type").agg(
        total=("pass","count"), passes=("pass","sum")
    ).reset_index()
    grp["pass_pct"] = (grp["passes"] / grp["total"] * 100).round(1)
    grp["fail_pct"] = 100 - grp["pass_pct"]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Pass %", x=grp["type"], y=grp["pass_pct"],
                         marker_color=[BLUE, GREEN], marker_line_width=0,
                         text=grp["pass_pct"].astype(str)+"%", textposition="inside"))
    fig.add_trace(go.Bar(name="Fail %", x=grp["type"], y=grp["fail_pct"],
                         marker_color="rgba(240,80,80,0.35)", marker_line_width=0))
    fig.update_layout(**base_layout(), barmode="stack", height=240,
                      yaxis_ticksuffix="%", yaxis_range=[0,100], showlegend=False)
    return fig


def chart_vertical(df):
    if "vertical" not in df.columns:
        return None
    grp = df.groupby("vertical").agg(
        total=("pass","count"), passes=("pass","sum")
    ).reset_index()
    grp["pass_pct"] = (grp["passes"] / grp["total"] * 100).round(1)
    grp["color"] = grp["pass_pct"].apply(
        lambda x: GREEN if x >= 85 else AMBER if x >= 70 else RED
    )
    fig = go.Figure(go.Bar(
        x=grp["vertical"], y=grp["pass_pct"],
        marker_color=grp["color"], marker_line_width=0,
        text=grp["pass_pct"].astype(str)+"%", textposition="outside",
        hovertemplate="<b>%{x}</b><br>Pass: %{y}%<extra></extra>"
    ))
    fig.update_layout(**base_layout(), height=240,
                      yaxis_ticksuffix="%", yaxis_range=[0,110])
    return fig


def chart_zone_volume(df):
    grp = df.groupby(["zone","pass"]).size().reset_index(name="count")
    grp["label"] = grp["pass"].map({True: "Pass", False: "Fail"})
    fig = px.bar(grp, x="zone", y="count", color="label",
                 color_discrete_map={"Pass": GREEN, "Fail": RED},
                 barmode="stack")
    fig.update_layout(**base_layout(), height=260, showlegend=True,
                      legend=dict(orientation="h", y=1.1,
                                  font=dict(color=FONT_COLOR, size=11)),
                      xaxis_title="", yaxis_title="Records")
    fig.update_traces(marker_line_width=0)
    return fig


def chart_fail_reasons(df):
    fails = df[df["pass"] == False].copy()
    if "reason" not in fails.columns:
        return None
    fails = fails[fails["reason"] != ""]
    if fails.empty:
        return None
    top = (fails["reason"].value_counts()
           .head(8).reset_index())
    top.columns = ["reason", "count"]
    top["short"] = top["reason"].str[:45]
    fig = go.Figure(go.Bar(
        y=top["short"], x=top["count"], orientation="h",
        marker_color=AMBER, marker_line_width=0,
        text=top["count"], textposition="outside",
        customdata=top["reason"],
        hovertemplate="%{customdata}<br>Count: %{x:,}<extra></extra>"
    ))
    fig.update_layout(**base_layout(), height=max(260, len(top)*38),
                      xaxis_title="", yaxis_title="",
                      yaxis=dict(autorange="reversed",
                                 gridcolor=GRID_COLOR))
    return fig


def chart_rc_heatmap(df):
    """Pass rate heatmap: RC × Week"""
    grp = df.groupby(["rc","week"]).agg(
        total=("pass","count"), passes=("pass","sum")
    ).reset_index()
    grp["pass_pct"] = (grp["passes"] / grp["total"] * 100).round(1)
    pivot = grp.pivot(index="rc", columns="week", values="pass_pct").fillna(0)
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=["Wk "+str(c) for c in pivot.columns],
        y=pivot.index.tolist(),
        colorscale=[[0,"#f05050"],[0.7,"#f5a623"],[1,"#36d9a4"]],
        zmin=0, zmax=100,
        hovertemplate="<b>%{y}</b><br>%{x}: %{z}%<extra></extra>",
        text=pivot.values.round(0).astype(int),
        texttemplate="%{text}%",
        textfont=dict(size=9)
    ))
    fig.update_layout(**base_layout(), height=max(300, len(pivot)*28),
                      xaxis_title="", yaxis_title="")
    return fig


# ─── RC TABLE ─────────────────────────────────────────────────────────────────
def render_rc_table(df):
    grp = df.groupby(["rc","zone"]).agg(
        Total=("pass","count"),
        Pass=("pass","sum")
    ).reset_index()
    grp["Fail"]    = grp["Total"] - grp["Pass"]
    grp["Pass %"]  = (grp["Pass"] / grp["Total"] * 100).round(1)
    grp["RTO"]     = df[df["type"]=="RTO"].groupby("rc")["pass"].count().reindex(grp["rc"]).fillna(0).astype(int).values
    grp["RVP"]     = df[df["type"]=="RVP"].groupby("rc")["pass"].count().reindex(grp["rc"]).fillna(0).astype(int).values

    grp = grp.sort_values("Total", ascending=False).reset_index(drop=True)
    grp.columns = ["RC / Site", "Zone", "Total", "Pass", "Fail", "Pass %", "RTO", "RVP"]

    def color_pct(val):
        color = "#36d9a4" if val >= 85 else "#f5a623" if val >= 70 else "#f05050"
        return f"color: {color}; font-weight: 700"

    styled = (grp.style
              .applymap(color_pct, subset=["Pass %"])
              .format({"Total":"{:,}", "Pass":"{:,}", "Fail":"{:,}",
                       "Pass %":"{:.1f}%", "RTO":"{:,}", "RVP":"{:,}"})
              .set_properties(**{"background-color":"#1e2230","color":"#f0f2f8",
                                 "border":"1px solid rgba(255,255,255,0.05)"})
              .set_table_styles([{
                  "selector":"thead th",
                  "props":[("background-color","#13161e"),("color","#8891a8"),
                           ("font-size","11px"),("text-transform","uppercase"),
                           ("letter-spacing","0.07em")]
              }]))
    st.dataframe(grp, use_container_width=True, height=380)


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    # Header
    col_title, col_live = st.columns([4, 1])
    with col_title:
        st.markdown("""
        <h1 style='font-size:22px;font-weight:700;color:#f0f2f8;margin:0;padding:0'>
        📦 RTO / RVP Resealing Dashboard
        </h1>
        <p style='font-size:12px;color:#8891a8;margin:2px 0 0'>
        All Zones · All Sites · Weeks 3–13 · 2026
        </p>
        """, unsafe_allow_html=True)
    with col_live:
        st.markdown("""
        <div style='text-align:right;padding-top:8px'>
          <div class="live-badge"><span class="live-dot"></span>&nbsp;LIVE</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Load data
    with st.spinner("🔄 Fetching data from Google Drive..."):
        df_full = load_all_data()

    if df_full.empty:
        st.error("No data loaded. Check Google Drive connection and folder permissions.")
        render_setup_guide()
        return

    # Sidebar filters
    sel_zone, sel_rc, sel_week, sel_vert, sel_type, uploaded = render_sidebar(df_full)

    # Handle uploaded file
    if uploaded:
        try:
            new_df = pd.read_csv(uploaded, low_memory=False, on_bad_lines="skip")
            new_df = clean_data(new_df)
            if not new_df.empty:
                df_full = pd.concat([df_full, new_df], ignore_index=True)
                st.sidebar.success(f"✅ Added {len(new_df):,} rows from {uploaded.name}")
        except Exception as e:
            st.sidebar.error(f"Error reading file: {e}")

    # Apply filters
    df = apply_filters(df_full, sel_zone, sel_rc, sel_week, sel_vert, sel_type)

    if df.empty:
        st.warning("No records match the current filters.")
        return

    # KPIs
    render_kpis(df, df_full)
    st.markdown("---")

    # Row 1: Zone pass rate + Week trend
    st.markdown('<div class="section-header">Zone Performance & Weekly Trend</div>',
                unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(chart_zone_pass(df), use_container_width=True, key="zone_pass")
    with c2:
        st.plotly_chart(chart_week_trend(df), use_container_width=True, key="week_trend")

    # Row 2: Donut + Type + Vertical
    st.markdown('<div class="section-header">Shipment Type & Vertical Breakdown</div>',
                unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.plotly_chart(chart_donut(df), use_container_width=True, key="donut")
    with c2:
        st.plotly_chart(chart_type_pass(df), use_container_width=True, key="type_pass")
    with c3:
        vc = chart_vertical(df)
        if vc:
            st.plotly_chart(vc, use_container_width=True, key="vertical")

    # Row 3: Zone volume + Fail reasons
    st.markdown('<div class="section-header">Volume Analysis & Fail Reasons</div>',
                unsafe_allow_html=True)
    c1, c2 = st.columns([3, 2])
    with c1:
        st.plotly_chart(chart_zone_volume(df), use_container_width=True, key="zone_vol")
    with c2:
        fc = chart_fail_reasons(df)
        if fc:
            st.plotly_chart(fc, use_container_width=True, key="fail_reasons")
        else:
            st.info("No fail reason data available for this filter.")

    # RC Heatmap
    st.markdown('<div class="section-header">RC × Week Pass Rate Heatmap</div>',
                unsafe_allow_html=True)
    st.plotly_chart(chart_rc_heatmap(df), use_container_width=True, key="heatmap")

    # RC Table
    st.markdown('<div class="section-header">Site-level Breakdown</div>',
                unsafe_allow_html=True)
    render_rc_table(df)

    # Footer
    st.markdown("---")
    st.caption(
        f"📊 Showing {len(df):,} of {len(df_full):,} total records · "
        f"Last refreshed: {datetime.now().strftime('%d %b %Y %H:%M:%S')} · "
        f"Auto-refresh every 5 minutes"
    )

    # Auto-refresh every 5 minutes
    time.sleep(0)  # Yield to Streamlit
    st.markdown("""
    <script>
    setTimeout(function(){ window.location.reload(); }, 300000);
    </script>
    """, unsafe_allow_html=True)


# ─── SETUP GUIDE (shown when not configured) ──────────────────────────────────
def render_setup_guide():
    st.markdown("---")
    st.markdown("## 📋 Setup Guide")
    st.markdown("""
    ### Step 1 — Create Google Service Account
    1. Go to [Google Cloud Console](https://console.cloud.google.com)
    2. Create a new project → Enable **Google Drive API**
    3. Go to **IAM & Admin → Service Accounts → Create**
    4. Download the JSON key file

    ### Step 2 — Share your Drive folder with the service account
    1. Copy the service account email (looks like `xxx@project.iam.gserviceaccount.com`)
    2. In Google Drive, right-click your **Resealing Conversion** folder
    3. Click **Share** → paste the service account email → **Viewer** access

    ### Step 3 — Add secrets to Streamlit Cloud
    In Streamlit Cloud dashboard → your app → **Settings → Secrets**, paste:
    ```toml
    [gcp_service_account]
    type = "service_account"
    project_id = "your-project-id"
    private_key_id = "..."
    private_key = "-----BEGIN RSA PRIVATE KEY-----\\n...\\n-----END RSA PRIVATE KEY-----\\n"
    client_email = "your-service-account@project.iam.gserviceaccount.com"
    client_id = "..."
    auth_uri = "https://accounts.google.com/o/oauth2/auth"
    token_uri = "https://oauth2.googleapis.com/token"
    ```

    ### Step 4 — Deploy
    Push to GitHub → Streamlit Cloud auto-deploys!
    """)


if __name__ == "__main__":
    main()
