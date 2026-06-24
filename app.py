import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import io
from datetime import datetime
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

# ── CONFIG FROM STREAMLIT SECRETS ─────────────────────────────────────────────
CLIENT_ID     = st.secrets["oauth"]["client_id"]
CLIENT_SECRET = st.secrets["oauth"]["client_secret"]
FILE_IDS      = st.secrets["drive"]["file_ids"].split(",")
FILE_LABELS   = ["Wk 03-04","Wk 05-06","Wk 07-08","Wk 09-10","Wk 11-13"]
REDIRECT_URI  = "https://resealing-dashboard-fk.streamlit.app"
TOKEN_URL     = "https://oauth2.googleapis.com/token"
SCOPE         = "https://www.googleapis.com/auth/drive.readonly"
BG="#1e2230";GRID="rgba(255,255,255,0.05)";MUTED="#8891a8"
GREEN="#36d9a4";RED="#f05050";BLUE="#4f8ef7";AMBER="#f5a623"

def base_layout():
    return dict(plot_bgcolor=BG,paper_bgcolor=BG,
        font=dict(color=MUTED,family="Inter,sans-serif",size=11),
        margin=dict(l=10,r=10,t=30,b=10),
        xaxis=dict(gridcolor=GRID,zerolinecolor=GRID),
        yaxis=dict(gridcolor=GRID,zerolinecolor=GRID))

# ── OAUTH ─────────────────────────────────────────────────────────────────────
def get_auth_url():
    import urllib.parse
    params = {"client_id":CLIENT_ID,"redirect_uri":REDIRECT_URI,
              "response_type":"code","scope":SCOPE,
              "access_type":"offline","prompt":"consent","hd":"flipkart.com"}
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

def exchange_code(code):
    r = requests.post(TOKEN_URL,data={"code":code,"client_id":CLIENT_ID,
        "client_secret":CLIENT_SECRET,"redirect_uri":REDIRECT_URI,
        "grant_type":"authorization_code"})
    return r.json()

# ── DATA ──────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300,show_spinner=False)
def load_file(fid,token):
    r = requests.get(f"https://www.googleapis.com/drive/v3/files/{fid}?alt=media",
        headers={"Authorization":f"Bearer {token}"},timeout=60)
    if r.status_code==200 and len(r.text)>100:
        return pd.read_csv(io.StringIO(r.text),low_memory=False,on_bad_lines="skip")
    return pd.DataFrame()

def load_all(token):
    dfs=[]
    bar=st.progress(0,text="Loading from Google Drive...")
    for i,(fid,lbl) in enumerate(zip(FILE_IDS,FILE_LABELS)):
        df=load_file(fid.strip(),token)
        if not df.empty:
            df["_src"]=lbl;dfs.append(df)
        bar.progress(int((i+1)/len(FILE_IDS)*100),text=f"Loaded {lbl}")
    bar.empty()
    if not dfs: return pd.DataFrame()
    return clean(pd.concat(dfs,ignore_index=True))

def clean(df):
    cm={"RC Name":"rc","Zone":"zone","Week":"week","RTO / RVP":"type",
        "RTO / RVP Status":"type","Result":"result","QA remark":"reason",
        "Vertical 1":"vertical","Brand Name":"brand"}
    df=df.rename(columns={k:v for k,v in cm.items() if k in df.columns})
    if "result" not in df.columns: return pd.DataFrame()
    df["result"]=df["result"].str.strip().str.lower()
    df=df[df["result"].isin(["pass","fail"])].copy()
    df["pass"]=df["result"]=="pass"
    if "type" in df.columns:
        df["type"]=df["type"].str.strip().str.upper().str[:3]
        df["type"]=df["type"].where(df["type"].isin(["RTO","RVP"]),"RTO")
    if "week" in df.columns:
        df["week"]=pd.to_numeric(df["week"],errors="coerce").fillna(0).astype(int)
        df=df[df["week"]>0]
    if "vertical" in df.columns:
        df["vertical"]=(df["vertical"].str.replace(r"^RTO[_ ]+","",regex=True)
            .str.replace(r"^RVP[_ ]+","",regex=True).str.strip())
    if "reason" in df.columns:
        df["reason"]=df["reason"].fillna("").str.strip()
        df["reason"]=df["reason"].str.replace(r"^\d+\.\s*","",regex=True).str.strip()
        df.loc[df["reason"].str.lower().isin(["no issue","no issue.",""]), "reason"]=""
    for col in ["rc","zone","type"]:
        if col in df.columns: df=df[df[col].notna()&(df[col]!="")]
    return df.reset_index(drop=True)

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
def sidebar(df):
    with st.sidebar:
        st.markdown("<div style='text-align:center;padding:10px 0'><div style='background:linear-gradient(135deg,#1d4ed8,#4f8ef7);color:#fff;font-size:11px;font-weight:700;padding:3px 12px;border-radius:4px;display:inline-block'>FLIPKART</div><div style='font-size:14px;font-weight:600;color:#f0f2f8;margin-top:8px'>RTO / RVP Resealing</div><div style='font-size:11px;color:#8891a8'>Live Dashboard 2026</div></div>",unsafe_allow_html=True)
        st.markdown('<div class="live-badge"><span class="live-dot"></span>&nbsp;LIVE</div>',unsafe_allow_html=True)
        st.caption(f"Updated: {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
        st.markdown("---")
        st.markdown("### 🔍 Filters")
        zones=["All Zones"]+sorted(df["zone"].dropna().unique().tolist())
        sz=st.selectbox("Zone",zones)
        dfz=df if sz=="All Zones" else df[df["zone"]==sz]
        rcs=["All RC / Sites"]+sorted(dfz["rc"].dropna().unique().tolist())
        sr=st.selectbox("RC / Site",rcs)
        weeks=["All Weeks"]+[str(w) for w in sorted(df["week"].unique())]
        sw=st.selectbox("Week",weeks)
        verts=["All Verticals"]+( sorted(df["vertical"].dropna().unique().tolist()) if "vertical" in df.columns else [])
        sv=st.selectbox("Vertical",verts)
        stype=st.selectbox("Type",["RTO + RVP","RTO only","RVP only"])
        st.markdown("---")
        st.markdown("### 📁 Upload New CSV")
        up=st.file_uploader("Add new weekly file",type=["csv"])
        st.markdown("---")
        if st.button("🔄 Refresh Data",use_container_width=True):
            st.cache_data.clear();st.rerun()
        st.caption("Auto-refreshes every 5 minutes")
        if st.button("🚪 Logout",use_container_width=True):
            for k in ["access_token","refresh_token"]:
                if k in st.session_state: del st.session_state[k]
            st.rerun()
    return sz,sr,sw,sv,stype,up

def filt(df,sz,sr,sw,sv,stype):
    fd=df.copy()
    if sz!="All Zones": fd=fd[fd["zone"]==sz]
    if sr!="All RC / Sites": fd=fd[fd["rc"]==sr]
    if sw!="All Weeks": fd=fd[fd["week"]==int(sw)]
    if sv!="All Verticals" and "vertical" in fd.columns: fd=fd[fd["vertical"]==sv]
    if stype=="RTO only": fd=fd[fd["type"]=="RTO"]
    elif stype=="RVP only": fd=fd[fd["type"]=="RVP"]
    return fd

# ── KPIs ──────────────────────────────────────────────────────────────────────
def kpis(df,dff):
    t=len(df);p=int(df["pass"].sum());f=t-p
    pct=round(p/t*100,1) if t else 0
    fpct=round(dff["pass"].sum()/len(dff)*100,1) if len(dff) else 0
    c1,c2,c3,c4,c5,c6=st.columns(6)
    c1.metric("📦 Total",f"{t:,}",f"{df['week'].nunique()} weeks")
    c2.metric("✅ Pass",f"{p:,}",f"{pct}% rate")
    c3.metric("❌ Fail",f"{f:,}",f"{round(f/t*100,1) if t else 0}%")
    c4.metric("🎯 Pass %",f"{pct}%",f"{round(pct-fpct,1):+.1f}% vs overall",delta_color="normal")
    c5.metric("🏭 Sites",f"{df['rc'].nunique()}",f"{df['zone'].nunique()} zones")
    c6.metric("📅 Weeks",f"{df['week'].nunique()}",f"Wk {df['week'].min()}–{df['week'].max()}" if df['week'].nunique() else "")

# ── CHARTS ────────────────────────────────────────────────────────────────────
def c_zone(df):
    g=df.groupby("zone").agg(t=("pass","count"),p=("pass","sum")).reset_index()
    g["pct"]=(g["p"]/g["t"]*100).round(1)
    g["c"]=g["pct"].apply(lambda x:GREEN if x>=85 else AMBER if x>=70 else RED)
    fig=go.Figure(go.Bar(x=g["zone"],y=g["pct"],marker_color=g["c"],text=g["pct"].astype(str)+"%",textposition="outside",marker_line_width=0))
    fig.update_layout(**base_layout(),yaxis_range=[0,110],yaxis_ticksuffix="%",height=240)
    return fig

def c_week(df):
    g=df.groupby("week").agg(t=("pass","count"),p=("pass","sum")).reset_index().sort_values("week")
    g["pct"]=(g["p"]/g["t"]*100).round(1)
    fig=make_subplots(specs=[[{"secondary_y":True}]])
    fig.add_trace(go.Bar(x=g["week"].astype(str),y=g["t"],name="Vol",marker_color="rgba(79,142,247,0.25)",marker_line_width=0),secondary_y=True)
    fig.add_trace(go.Scatter(x=g["week"].astype(str),y=g["pct"],name="Pass %",line=dict(color=GREEN,width=2.5),mode="lines+markers",marker=dict(size=6,color=GREEN)),secondary_y=False)
    fig.update_layout(**base_layout(),height=240,showlegend=False)
    fig.update_yaxes(ticksuffix="%",range=[0,100],secondary_y=False,gridcolor=GRID)
    fig.update_yaxes(showgrid=False,secondary_y=True)
    return fig

def c_donut(df):
    c=df["type"].value_counts().reset_index();c.columns=["type","count"]
    fig=px.pie(c,values="count",names="type",hole=0.66,color="type",color_discrete_map={"RTO":BLUE,"RVP":GREEN})
    fig.update_traces(textinfo="none")
    fig.update_layout(**base_layout(),height=200,legend=dict(orientation="h",y=-0.1,font=dict(color=MUTED,size=11)))
    return fig

def c_type(df):
    g=df.groupby("type").agg(t=("pass","count"),p=("pass","sum")).reset_index()
    g["pct"]=(g["p"]/g["t"]*100).round(1);g["f"]=100-g["pct"]
    fig=go.Figure()
    fig.add_trace(go.Bar(name="Pass",x=g["type"],y=g["pct"],marker_color=[BLUE,GREEN],marker_line_width=0,text=g["pct"].astype(str)+"%",textposition="inside"))
    fig.add_trace(go.Bar(name="Fail",x=g["type"],y=g["f"],marker_color="rgba(240,80,80,0.35)",marker_line_width=0))
    fig.update_layout(**base_layout(),barmode="stack",height=240,yaxis_ticksuffix="%",yaxis_range=[0,100],showlegend=False)
    return fig

def c_vert(df):
    if "vertical" not in df.columns: return None
    g=df.groupby("vertical").agg(t=("pass","count"),p=("pass","sum")).reset_index()
    g["pct"]=(g["p"]/g["t"]*100).round(1);g["c"]=g["pct"].apply(lambda x:GREEN if x>=85 else AMBER if x>=70 else RED)
    fig=go.Figure(go.Bar(x=g["vertical"],y=g["pct"],marker_color=g["c"],marker_line_width=0,text=g["pct"].astype(str)+"%",textposition="outside"))
    fig.update_layout(**base_layout(),height=240,yaxis_ticksuffix="%",yaxis_range=[0,110])
    return fig

def c_zvol(df):
    g=df.groupby(["zone","pass"]).size().reset_index(name="count")
    g["label"]=g["pass"].map({True:"Pass",False:"Fail"})
    fig=px.bar(g,x="zone",y="count",color="label",color_discrete_map={"Pass":GREEN,"Fail":RED},barmode="stack")
    fig.update_layout(**base_layout(),height=260,legend=dict(orientation="h",y=1.1,font=dict(color=MUTED,size=11)))
    fig.update_traces(marker_line_width=0)
    return fig

def c_reasons(df):
    if "reason" not in df.columns: return None
    fails=df[(df["pass"]==False)&(df["reason"]!="")]
    if fails.empty: return None
    top=fails["reason"].value_counts().head(8).reset_index();top.columns=["reason","count"]
    fig=go.Figure(go.Bar(y=top["reason"].str[:45],x=top["count"],orientation="h",marker_color=AMBER,marker_line_width=0,text=top["count"],textposition="outside"))
    fig.update_layout(**base_layout(),height=max(260,len(top)*38),yaxis=dict(autorange="reversed",gridcolor=GRID))
    return fig

def c_heat(df):
    g=df.groupby(["rc","week"]).agg(t=("pass","count"),p=("pass","sum")).reset_index()
    g["pct"]=(g["p"]/g["t"]*100).round(1)
    pivot=g.pivot(index="rc",columns="week",values="pct").fillna(0)
    fig=go.Figure(go.Heatmap(z=pivot.values,x=["Wk "+str(c) for c in pivot.columns],y=pivot.index.tolist(),
        colorscale=[[0,RED],[0.7,AMBER],[1,GREEN]],zmin=0,zmax=100,
        hovertemplate="<b>%{y}</b><br>%{x}: %{z}%<extra></extra>",
        text=pivot.values.round(0).astype(int),texttemplate="%{text}%",textfont=dict(size=9)))
    fig.update_layout(**base_layout(),height=max(300,len(pivot)*28))
    return fig

def tbl(df):
    g=df.groupby(["rc","zone"]).agg(Total=("pass","count"),Pass=("pass","sum")).reset_index()
    g["Fail"]=g["Total"]-g["Pass"];g["Pass %"]=(g["Pass"]/g["Total"]*100).round(1)
    rto=df[df["type"]=="RTO"].groupby("rc").size().rename("RTO")
    rvp=df[df["type"]=="RVP"].groupby("rc").size().rename("RVP")
    g=g.merge(rto,left_on="rc",right_index=True,how="left")
    g=g.merge(rvp,left_on="rc",right_index=True,how="left")
    g[["RTO","RVP"]]=g[["RTO","RVP"]].fillna(0).astype(int)
    g=g.sort_values("Total",ascending=False).reset_index(drop=True)
    g.columns=["RC / Site","Zone","Total","Pass","Fail","Pass %","RTO","RVP"]
    st.dataframe(g.style.format({"Total":"{:,}","Pass":"{:,}","Fail":"{:,}","Pass %":"{:.1f}%","RTO":"{:,}","RVP":"{:,}"}),use_container_width=True,height=380)

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    # Handle OAuth callback
    params=st.query_params
    if "code" in params and "access_token" not in st.session_state:
        with st.spinner("Logging you in..."):
            td=exchange_code(params["code"])
            if "access_token" in td:
                st.session_state["access_token"]=td["access_token"]
                st.session_state["refresh_token"]=td.get("refresh_token","")
                st.query_params.clear();st.rerun()
            else:
                st.error(f"Login failed: {td}");return

    # Show login if not authenticated
    if "access_token" not in st.session_state:
        st.markdown("""
        <div style='text-align:center;padding:60px 20px'>
          <div style='background:linear-gradient(135deg,#1d4ed8,#4f8ef7);color:#fff;font-size:13px;font-weight:700;padding:5px 16px;border-radius:4px;display:inline-block;margin-bottom:16px'>FLIPKART</div>
          <h1 style='font-size:26px;font-weight:700;color:#f0f2f8;margin-bottom:8px'>📦 RTO / RVP Resealing Dashboard</h1>
          <p style='font-size:14px;color:#8891a8;margin-bottom:32px'>Sign in with your Flipkart Google account to view the dashboard</p>
        </div>""",unsafe_allow_html=True)
        _,c,_=st.columns([2,1,2])
        with c:
            st.markdown(f'<a href="{get_auth_url()}" target="_self"><div style="background:#4f8ef7;color:#fff;font-size:14px;font-weight:600;padding:12px 24px;border-radius:8px;text-align:center;cursor:pointer">🔐 Sign in with Flipkart Google</div></a>',unsafe_allow_html=True)
        return

    # Dashboard
    token=st.session_state["access_token"]
    c1,c2=st.columns([4,1])
    with c1:
        st.markdown("<h1 style='font-size:22px;font-weight:700;color:#f0f2f8;margin:0'>📦 RTO / RVP Resealing Dashboard</h1><p style='font-size:12px;color:#8891a8;margin:2px 0 0'>All Zones · All Sites · Weeks 3–13 · Flipkart Internal · 2026</p>",unsafe_allow_html=True)
    with c2:
        st.markdown('<div style="text-align:right;padding-top:8px"><div class="live-badge"><span class="live-dot"></span>&nbsp;LIVE</div></div>',unsafe_allow_html=True)
    st.markdown("---")

    with st.spinner("🔄 Loading data from Google Drive..."):
        dff=load_all(token)

    if dff.empty:
        st.error("❌ Could not load data. Session may have expired.")
        if st.button("🔄 Login Again"):
            for k in ["access_token","refresh_token"]:
                if k in st.session_state: del st.session_state[k]
            st.rerun()
        return

    sz,sr,sw,sv,stype,up=sidebar(dff)

    if up:
        try:
            nd=pd.read_csv(up,low_memory=False,on_bad_lines="skip")
            nd=clean(nd)
            if not nd.empty:
                dff=pd.concat([dff,nd],ignore_index=True)
                st.sidebar.success(f"✅ Added {len(nd):,} rows from {up.name}")
        except Exception as e: st.sidebar.error(f"Error: {e}")

    df=filt(dff,sz,sr,sw,sv,stype)
    if df.empty: st.warning("No records match the current filters.");return

    kpis(df,dff);st.markdown("---")

    st.markdown('<div class="sec-hdr">Zone Performance & Weekly Trend</div>',unsafe_allow_html=True)
    a,b=st.columns(2)
    with a: st.plotly_chart(c_zone(df),use_container_width=True)
    with b: st.plotly_chart(c_week(df),use_container_width=True)

    st.markdown('<div class="sec-hdr">Shipment Type & Vertical</div>',unsafe_allow_html=True)
    a,b,c=st.columns(3)
    with a: st.plotly_chart(c_donut(df),use_container_width=True)
    with b: st.plotly_chart(c_type(df),use_container_width=True)
    with c:
        vc=c_vert(df)
        if vc: st.plotly_chart(vc,use_container_width=True)

    st.markdown('<div class="sec-hdr">Volume & Fail Analysis</div>',unsafe_allow_html=True)
    a,b=st.columns([3,2])
    with a: st.plotly_chart(c_zvol(df),use_container_width=True)
    with b:
        fc=c_reasons(df)
        if fc: st.plotly_chart(fc,use_container_width=True)
        else: st.info("No fail reason data.")

    st.markdown('<div class="sec-hdr">RC × Week Heatmap</div>',unsafe_allow_html=True)
    st.plotly_chart(c_heat(df),use_container_width=True)

    st.markdown('<div class="sec-hdr">Site-level Breakdown</div>',unsafe_allow_html=True)
    tbl(df)

    st.markdown("---")
    st.caption(f"Showing {len(df):,} of {len(dff):,} records · Updated: {datetime.now().strftime('%d %b %Y %H:%M:%S')} · Auto-refresh every 5 min")

if __name__=="__main__":
    main()
