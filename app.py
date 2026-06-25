import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import warnings
warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="Flipkart — RTO/RVP Resealing Dashboard",
    page_icon="📦", layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"]{background:#0d0f14}
[data-testid="stSidebar"]{background:#13161e;border-right:1px solid rgba(255,255,255,0.07)}
[data-testid="stHeader"]{background:#0d0f14}
[data-testid="metric-container"]{background:#1e2230;border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:14px 18px}
[data-testid="stMetricValue"]{font-size:28px!important;font-weight:700!important}
h1,h2,h3{color:#f0f2f8!important}
.live-badge{display:inline-flex;align-items:center;gap:6px;background:rgba(54,217,164,0.12);
  border:1px solid rgba(54,217,164,0.3);color:#36d9a4;font-size:12px;font-weight:700;
  padding:4px 12px;border-radius:20px;letter-spacing:0.06em}
.live-dot{width:7px;height:7px;border-radius:50%;background:#36d9a4;display:inline-block;
  animation:pulse 1.5s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(54,217,164,0.7)}70%{box-shadow:0 0 0 6px rgba(54,217,164,0)}100%{box-shadow:0 0 0 0 rgba(54,217,164,0)}}
.sec-hdr{font-size:11px;font-weight:600;color:#8891a8;text-transform:uppercase;
  letter-spacing:0.09em;margin-bottom:8px;margin-top:4px}
</style>
""", unsafe_allow_html=True)

# ── SAME AUTH AS PV DASHBOARD ─────────────────────────────────────────────────
FOLDER_ID = st.secrets["GDRIVE_FOLDER_ID"]

FILE_IDS = [
    {"id": "1uHkOqI1xQ0vOdgORp0dHSrFgBda7XfkU", "label": "Wk 03-04"},
    {"id": "1uFFJVjMhM4a_LkdRHlfvYgnLynkVV97d", "label": "Wk 05-06"},
    {"id": "1XmXAve89lCtGVVLe6DHeLzIe6UwSJ4Tr", "label": "Wk 07-08"},
    {"id": "1Zhy7UQHvmRFcmmVS1csra1_FScbWC35v", "label": "Wk 09-10"},
    {"id": "1po7DG4keXC5Wscb6uWzCXOrPIyDwJXxA", "label": "Wk 11-13"},
]

def get_drive_service():
    creds = Credentials(
        token=None,
        refresh_token=st.secrets["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=st.secrets["GOOGLE_CLIENT_ID"],
        client_secret=st.secrets["GOOGLE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)

# ── CHART THEME ───────────────────────────────────────────────────────────────
BG="#1e2230";GRID="rgba(255,255,255,0.05)";MUTED="#8891a8"
GREEN="#36d9a4";RED="#f05050";BLUE="#4f8ef7";AMBER="#f5a623"

def base_layout():
    return dict(plot_bgcolor=BG, paper_bgcolor=BG,
        font=dict(color=MUTED, family="Inter,sans-serif", size=11),
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
        yaxis=dict(gridcolor=GRID, zerolinecolor=GRID))

# ── LOAD DATA ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_all_data():
    try:
        service = get_drive_service()
    except Exception as e:
        st.error(f"❌ Google Drive auth failed: {e}")
        return pd.DataFrame()

    dfs = []
    bar = st.progress(0, text="Loading data from Google Drive...")
    for i, f in enumerate(FILE_IDS):
        try:
            request = service.files().get_media(fileId=f["id"])
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            buf.seek(0)
            df = pd.read_csv(buf, low_memory=False, on_bad_lines="skip")
            df["_src"] = f["label"]
            dfs.append(df)
        except Exception as e:
            st.warning(f"Could not load {f['label']}: {e}")
        bar.progress(int((i+1)/len(FILE_IDS)*100), text=f"Loaded {f['label']} ({i+1}/{len(FILE_IDS)})")
    bar.empty()

    if not dfs:
        return pd.DataFrame()
    return clean_data(pd.concat(dfs, ignore_index=True))

def clean_data(df):
    # Rename columns safely - handle duplicate mappings
    for old_col, new_col in [
        ("RC Name","rc"),("Zone","zone"),("Week","week"),
        ("Result","result"),("QA remark","reason"),
        ("Vertical 1","vertical"),("Brand Name","brand"),
    ]:
        if old_col in df.columns:
            df = df.rename(columns={old_col: new_col})
    # Handle type column - pick first available
    if "RTO / RVP" in df.columns:
        df["type"] = df["RTO / RVP"]
    elif "RTO / RVP Status" in df.columns:
        df["type"] = df["RTO / RVP Status"]
    if "result" not in df.columns: return pd.DataFrame()
    df["result"] = df["result"].fillna("").astype(str).str.strip().str.lower()
    df = df[df["result"].isin(["pass","fail"])].copy()
    df["pass"] = df["result"] == "pass"
    if "type" in df.columns:
        df["type"] = df["type"].fillna("RTO").astype(str).str.strip().str.upper().str[:3]
        df["type"] = df["type"].where(df["type"].isin(["RTO","RVP"]), "RTO")
    if "week" in df.columns:
        df["week"] = pd.to_numeric(df["week"], errors="coerce").fillna(0).astype(int)
        df = df[df["week"] > 0]
    if "vertical" in df.columns:
        df["vertical"] = (df["vertical"].fillna("").astype(str)
            .str.replace(r"^RTO[_ ]+","",regex=True)
            .str.replace(r"^RVP[_ ]+","",regex=True).str.strip())
    if "reason" in df.columns:
        df["reason"] = df["reason"].fillna("").astype(str).str.strip()
        df["reason"] = df["reason"].str.replace(r"^\d+\.\s*","",regex=True).str.strip()
        df.loc[df["reason"].str.lower().isin(["no issue","no issue.","nan",""]), "reason"] = ""
    for col in ["rc","zone"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
            df = df[(df[col]!="") & (df[col]!="nan")]
    return df.reset_index(drop=True)

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
def render_sidebar(df):
    with st.sidebar:
        st.markdown("""
        <div style='text-align:center;padding:10px 0'>
          <div style='background:linear-gradient(135deg,#1d4ed8,#4f8ef7);color:#fff;
            font-size:11px;font-weight:700;padding:3px 12px;border-radius:4px;display:inline-block'>
            FLIPKART</div>
          <div style='font-size:14px;font-weight:600;color:#f0f2f8;margin-top:8px'>RTO / RVP Resealing</div>
          <div style='font-size:11px;color:#8891a8'>Live Dashboard 2026</div>
        </div>""", unsafe_allow_html=True)
        st.markdown('<div class="live-badge"><span class="live-dot"></span>&nbsp;LIVE</div>', unsafe_allow_html=True)
        st.caption(f"Updated: {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
        st.markdown("---")
        st.markdown("### 🔍 Filters")
        zones = ["All Zones"] + sorted(df["zone"].dropna().unique().tolist())
        sel_zone = st.selectbox("Zone", zones)
        df_z = df if sel_zone=="All Zones" else df[df["zone"]==sel_zone]
        rcs = ["All RC / Sites"] + sorted(df_z["rc"].dropna().unique().tolist())
        sel_rc = st.selectbox("RC / Site", rcs)
        weeks = ["All Weeks"] + [str(w) for w in sorted(df["week"].unique())]
        sel_week = st.selectbox("Week", weeks)
        verts = ["All Verticals"]
        if "vertical" in df.columns:
            verts += sorted(df["vertical"].dropna().unique().tolist())
        sel_vert = st.selectbox("Vertical", verts)
        sel_type = st.selectbox("Type", ["RTO + RVP","RTO only","RVP only"])
        st.markdown("---")
        st.markdown("### 📁 Upload New CSV")
        uploaded = st.file_uploader("Add new weekly file", type=["csv"])
        st.markdown("---")
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.caption("Auto-refreshes every 5 minutes")
    return sel_zone, sel_rc, sel_week, sel_vert, sel_type, uploaded

def apply_filters(df, sz, sr, sw, sv, stype):
    fd = df.copy()
    if sz != "All Zones":      fd = fd[fd["zone"]==sz]
    if sr != "All RC / Sites": fd = fd[fd["rc"]==sr]
    if sw != "All Weeks":      fd = fd[fd["week"]==int(sw)]
    if sv != "All Verticals" and "vertical" in fd.columns: fd = fd[fd["vertical"]==sv]
    if stype == "RTO only":    fd = fd[fd["type"]=="RTO"]
    elif stype == "RVP only":  fd = fd[fd["type"]=="RVP"]
    return fd

# ── KPIs ──────────────────────────────────────────────────────────────────────
def render_kpis(df, dff):
    t=len(df); p=int(df["pass"].sum()); f=t-p
    pct=round(p/t*100,1) if t else 0
    fpct=round(dff["pass"].sum()/len(dff)*100,1) if len(dff) else 0
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("📦 Total Records", f"{t:,}",  f"{df['week'].nunique()} weeks")
    c2.metric("✅ PV Pass",       f"{p:,}",   f"{pct}% pass rate")
    c3.metric("❌ PV Fail",       f"{f:,}",   f"{round(f/t*100,1) if t else 0}% fail rate")
    c4.metric("🎯 Pass %",        f"{pct}%",  f"{round(pct-fpct,1):+.1f}% vs overall", delta_color="normal")
    c5.metric("🏭 Active Sites",  f"{df['rc'].nunique()}", f"{df['zone'].nunique()} zones")
    c6.metric("📅 Weeks",         f"{df['week'].nunique()}", f"Wk {df['week'].min()}–{df['week'].max()}" if df['week'].nunique() else "")

# ── CHARTS ────────────────────────────────────────────────────────────────────
def chart_zone(df):
    g=df.groupby("zone").agg(t=("pass","count"),p=("pass","sum")).reset_index()
    g["pct"]=(g["p"]/g["t"]*100).round(1)
    g["c"]=g["pct"].apply(lambda x:GREEN if x>=85 else AMBER if x>=70 else RED)
    fig=go.Figure(go.Bar(x=g["zone"],y=g["pct"],marker_color=g["c"],
        text=g["pct"].astype(str)+"%",textposition="outside",marker_line_width=0))
    fig.update_layout(**base_layout(),yaxis_range=[0,110],yaxis_ticksuffix="%",height=240)
    return fig

def chart_week(df):
    g=df.groupby("week").agg(t=("pass","count"),p=("pass","sum")).reset_index().sort_values("week")
    g["pct"]=(g["p"]/g["t"]*100).round(1)
    fig=make_subplots(specs=[[{"secondary_y":True}]])
    fig.add_trace(go.Bar(x=g["week"].astype(str),y=g["t"],name="Volume",
        marker_color="rgba(79,142,247,0.25)",marker_line_width=0),secondary_y=True)
    fig.add_trace(go.Scatter(x=g["week"].astype(str),y=g["pct"],name="Pass %",
        line=dict(color=GREEN,width=2.5),mode="lines+markers",
        marker=dict(size=6,color=GREEN)),secondary_y=False)
    fig.update_layout(**base_layout(),height=240,showlegend=False)
    fig.update_yaxes(ticksuffix="%",range=[0,100],secondary_y=False,gridcolor=GRID)
    fig.update_yaxes(showgrid=False,secondary_y=True)
    return fig

def chart_donut(df):
    c=df["type"].value_counts().reset_index();c.columns=["type","count"]
    fig=px.pie(c,values="count",names="type",hole=0.66,color="type",
        color_discrete_map={"RTO":BLUE,"RVP":GREEN})
    fig.update_traces(textinfo="none")
    fig.update_layout(**base_layout(),height=200,
        legend=dict(orientation="h",y=-0.1,font=dict(color=MUTED,size=11)))
    return fig

def chart_type(df):
    g=df.groupby("type").agg(t=("pass","count"),p=("pass","sum")).reset_index()
    g["pct"]=(g["p"]/g["t"]*100).round(1);g["f"]=100-g["pct"]
    fig=go.Figure()
    fig.add_trace(go.Bar(name="Pass",x=g["type"],y=g["pct"],marker_color=[BLUE,GREEN],
        marker_line_width=0,text=g["pct"].astype(str)+"%",textposition="inside"))
    fig.add_trace(go.Bar(name="Fail",x=g["type"],y=g["f"],
        marker_color="rgba(240,80,80,0.35)",marker_line_width=0))
    fig.update_layout(**base_layout(),barmode="stack",height=240,
        yaxis_ticksuffix="%",yaxis_range=[0,100],showlegend=False)
    return fig

def chart_vert(df):
    if "vertical" not in df.columns: return None
    g=df.groupby("vertical").agg(t=("pass","count"),p=("pass","sum")).reset_index()
    g["pct"]=(g["p"]/g["t"]*100).round(1)
    g["c"]=g["pct"].apply(lambda x:GREEN if x>=85 else AMBER if x>=70 else RED)
    fig=go.Figure(go.Bar(x=g["vertical"],y=g["pct"],marker_color=g["c"],
        marker_line_width=0,text=g["pct"].astype(str)+"%",textposition="outside"))
    fig.update_layout(**base_layout(),height=240,yaxis_ticksuffix="%",yaxis_range=[0,110])
    return fig

def chart_zone_vol(df):
    g=df.groupby(["zone","pass"]).size().reset_index(name="count")
    g["label"]=g["pass"].map({True:"Pass",False:"Fail"})
    fig=px.bar(g,x="zone",y="count",color="label",
        color_discrete_map={"Pass":GREEN,"Fail":RED},barmode="stack")
    fig.update_layout(**base_layout(),height=260,
        legend=dict(orientation="h",y=1.1,font=dict(color=MUTED,size=11)))
    fig.update_traces(marker_line_width=0)
    return fig

def chart_reasons(df):
    if "reason" not in df.columns: return None
    fails=df[(df["pass"]==False)&(df["reason"]!="")]
    if fails.empty: return None
    top=fails["reason"].value_counts().head(8).reset_index()
    top.columns=["reason","count"]
    fig=go.Figure(go.Bar(y=top["reason"].str[:45],x=top["count"],orientation="h",
        marker_color=AMBER,marker_line_width=0,text=top["count"],textposition="outside"))
    fig.update_layout(**base_layout(),height=max(260,len(top)*38),
        yaxis=dict(autorange="reversed",gridcolor=GRID))
    return fig

def chart_heatmap(df):
    g=df.groupby(["rc","week"]).agg(t=("pass","count"),p=("pass","sum")).reset_index()
    g["pct"]=(g["p"]/g["t"]*100).round(1)
    pivot=g.pivot(index="rc",columns="week",values="pct").fillna(0)
    fig=go.Figure(go.Heatmap(z=pivot.values,
        x=["Wk "+str(c) for c in pivot.columns],y=pivot.index.tolist(),
        colorscale=[[0,RED],[0.7,AMBER],[1,GREEN]],zmin=0,zmax=100,
        hovertemplate="<b>%{y}</b><br>%{x}: %{z}%<extra></extra>",
        text=pivot.values.round(0).astype(int),texttemplate="%{text}%",
        textfont=dict(size=9)))
    fig.update_layout(**base_layout(),height=max(300,len(pivot)*28))
    return fig

def render_table(df):
    g=df.groupby(["rc","zone"]).agg(Total=("pass","count"),Pass=("pass","sum")).reset_index()
    g["Fail"]=g["Total"]-g["Pass"]
    g["Pass %"]=(g["Pass"]/g["Total"]*100).round(1)
    rto=df[df["type"]=="RTO"].groupby("rc").size().rename("RTO")
    rvp=df[df["type"]=="RVP"].groupby("rc").size().rename("RVP")
    g=g.merge(rto,left_on="rc",right_index=True,how="left")
    g=g.merge(rvp,left_on="rc",right_index=True,how="left")
    g[["RTO","RVP"]]=g[["RTO","RVP"]].fillna(0).astype(int)
    g=g.sort_values("Total",ascending=False).reset_index(drop=True)
    g.columns=["RC / Site","Zone","Total","Pass","Fail","Pass %","RTO","RVP"]
    st.dataframe(g.style.format({"Total":"{:,}","Pass":"{:,}","Fail":"{:,}",
        "Pass %":"{:.1f}%","RTO":"{:,}","RVP":"{:,}"}),
        use_container_width=True,height=380)

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    c1,c2=st.columns([4,1])
    with c1:
        st.markdown("""
        <h1 style='font-size:22px;font-weight:700;color:#f0f2f8;margin:0'>
        📦 RTO / RVP Resealing Dashboard</h1>
        <p style='font-size:12px;color:#8891a8;margin:2px 0 0'>
        All Zones · All Sites · Weeks 3–13 · Flipkart Internal · 2026</p>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown('<div style="text-align:right;padding-top:8px"><div class="live-badge"><span class="live-dot"></span>&nbsp;LIVE</div></div>',unsafe_allow_html=True)
    st.markdown("---")

    with st.spinner("🔄 Loading data from Google Drive..."):
        df_full = load_all_data()

    if df_full.empty:
        st.error("❌ No data loaded. Check Google Drive connection.")
        return

    sz,sr,sw,sv,stype,up = render_sidebar(df_full)

    if up:
        try:
            nd=pd.read_csv(up,low_memory=False,on_bad_lines="skip")
            nd=clean_data(nd)
            if not nd.empty:
                df_full=pd.concat([df_full,nd],ignore_index=True)
                st.sidebar.success(f"✅ Added {len(nd):,} rows from {up.name}")
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

    df=apply_filters(df_full,sz,sr,sw,sv,stype)
    if df.empty:
        st.warning("No records match current filters.")
        return

    render_kpis(df, df_full)
    st.markdown("---")

    st.markdown('<div class="sec-hdr">Zone Performance & Weekly Trend</div>',unsafe_allow_html=True)
    a,b=st.columns(2)
    with a: st.plotly_chart(chart_zone(df),use_container_width=True)
    with b: st.plotly_chart(chart_week(df),use_container_width=True)

    st.markdown('<div class="sec-hdr">Shipment Type & Vertical</div>',unsafe_allow_html=True)
    a,b,c=st.columns(3)
    with a: st.plotly_chart(chart_donut(df),use_container_width=True)
    with b: st.plotly_chart(chart_type(df),use_container_width=True)
    with c:
        vc=chart_vert(df)
        if vc: st.plotly_chart(vc,use_container_width=True)

    st.markdown('<div class="sec-hdr">Volume & Fail Analysis</div>',unsafe_allow_html=True)
    a,b=st.columns([3,2])
    with a: st.plotly_chart(chart_zone_vol(df),use_container_width=True)
    with b:
        fc=chart_reasons(df)
        if fc: st.plotly_chart(fc,use_container_width=True)
        else: st.info("No fail reason data.")

    st.markdown('<div class="sec-hdr">RC × Week Heatmap</div>',unsafe_allow_html=True)
    st.plotly_chart(chart_heatmap(df),use_container_width=True)

    st.markdown('<div class="sec-hdr">Site-level Breakdown</div>',unsafe_allow_html=True)
    render_table(df)

    st.markdown("---")
    st.caption(f"Showing {len(df):,} of {len(df_full):,} records · Updated: {datetime.now().strftime('%d %b %Y %H:%M:%S')} · Auto-refresh every 5 min")

if __name__=="__main__":
    main()
