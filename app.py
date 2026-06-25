import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import io, json, re
from collections import defaultdict, Counter
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

st.set_page_config(
    page_title="Flipkart Resealing Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Hide streamlit chrome
st.markdown("""
<style>
#MainMenu{visibility:hidden}
footer{visibility:hidden}
header{visibility:hidden}
.block-container{padding:0!important;max-width:100%!important}
iframe{border:none!important}
</style>
""", unsafe_allow_html=True)

# ── CONSTANTS ──────────────────────────────────────────────────────────────────
FILE_IDS = [
    "1C56nffAx64Nb-n_evj6Dvg0ENq_B9ocJ",  # Wk 01-02
    "1uHkOqI1xQ0vOdgORp0dHSrFgBda7XfkU",  # Wk 03-04
    "1uFFJVjMhM4a_LkdRHlfvYgnLynkVV97d",  # Wk 05-06
    "1XmXAve89lCtGVVLe6DHeLzIe6UwSJ4Tr",  # Wk 07-08
    "1Zhy7UQHvmRFcmmVS1csra1_FScbWC35v",  # Wk 09-10
    "1po7DG4keXC5Wscb6uWzCXOrPIyDwJXxA",  # Wk 11-13
    "1JET6E2XUd15MhsH_eve3H9dRcdKTU-HO",  # Wk 14-15
    "10u01FaIrZAXyyrHqpST5UTGTD-S-m4bp",  # Wk 16-17
    "1U1i8ZJNOrzrBH-g21zMU5qEJHTbV877k",  # Wk 18-20
    "1IdtZA1eLualeJmIkWIrObfqoKY7ngdtq",  # Wk 21-23
]

MERGE = {
    'Frk_bts':      ['Frk_bts','Frk_bts_RC'],
    'Sanpka':       ['Sanpka','Sanpka RC'],
    'Bhiwandi BTS': ['Bhiwandi BTS','Bhiwandi BTS RC'],
    'Ahm_Kheda':    ['Ahm_ Kheda','Ahm_Kheda','Ahm_kheda'],
    'Indore_02':    ['Indore_02','Indore_ 02'],
    'Nagpur_01':    ['Nagpur_01','Nagpur_01_RC','Nagpur_02'],
}
REV = {n:c for c,ns in MERGE.items() for n in ns}

MONTHS    = ['Jan26','Feb26','Mar26','Apr26','May26','Jun26']
MLABELS   = ['Jan 26','Feb 26','Mar 26','Apr 26','May 26','Jun 26']
LAST7WKS  = [17,18,19,20,21,22,23]
ALL_WKS   = [1,2,3,4,5,6,7,8,9,10,11,12,13,16,17,18,19,20,21,22,23]

def wk2m(wk):
    m={1:'Jan26',2:'Jan26',3:'Jan26',4:'Jan26',
       5:'Feb26',6:'Feb26',7:'Feb26',8:'Feb26',
       9:'Mar26',10:'Mar26',11:'Apr26',12:'Apr26',
       13:'May26',16:'May26',17:'Jun26',18:'Jun26',
       19:'Jun26',20:'Jun26',21:'Jun26',22:'Jun26',23:'Jun26'}
    return m.get(wk,'Unknown')

# ── GOOGLE DRIVE AUTH ──────────────────────────────────────────────────────────
def get_drive_service():
    creds = Credentials(
        token=None,
        refresh_token=st.secrets["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=st.secrets["GOOGLE_CLIENT_ID"],
        client_secret=st.secrets["GOOGLE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive","v3",credentials=creds,cache_discovery=False)

# ── LOAD & PROCESS DATA ────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_all_data():
    try:
        svc = get_drive_service()
    except Exception as e:
        st.error(f"Drive auth failed: {e}")
        return None

    all_rows = []
    for fid in FILE_IDS:
        try:
            req = svc.files().get_media(fileId=fid)
            buf = io.BytesIO()
            dl  = MediaIoBaseDownload(buf, req)
            done = False
            while not done: _, done = dl.next_chunk()
            buf.seek(0)
            df = pd.read_csv(buf, low_memory=False, on_bad_lines='skip')
            all_rows.append(df)
        except Exception:
            pass

    if not all_rows:
        return None
    return pd.concat(all_rows, ignore_index=True)

def get_col(df, names):
    """Safely get first matching column as a flat Series"""
    for n in names:
        if n in df.columns:
            c = df[n]
            # Handle duplicate column names returning a DataFrame
            if isinstance(c, pd.DataFrame):
                c = c.iloc[:, 0]
            # Ensure it's a proper 1D Series
            if hasattr(c, 'squeeze'):
                c = c.squeeze()
            if not isinstance(c, pd.Series):
                c = pd.Series(c)
            return c.reset_index(drop=True)
    return pd.Series([''] * len(df))

def process_data(df):
    # Build clean dataframe column by column - never rename to avoid duplicates
    out = pd.DataFrame()
    out['rc']     = get_col(df, ['RC Name'])
    out['zone']   = get_col(df, ['Zone'])
    out['week']   = get_col(df, ['Week'])
    out['result'] = get_col(df, ['Result'])
    out['type']   = get_col(df, ['RTO / RVP', 'RTO / RVP Status'])
    out['reason'] = get_col(df, ['QA remark'])
    out['vert']   = get_col(df, ['Vertical 1'])

    # Clean result
    out['result'] = out['result'].fillna('').astype(str).str.strip().str.lower()
    out = out[out['result'].isin(['pass','fail'])].copy()
    if len(out)==0: return None
    out['pass'] = out['result']=='pass'

    # Clean type
    out['type'] = out['type'].fillna('RTO').astype(str).str.strip().str.upper().str[:3]
    out['type'] = out['type'].where(out['type'].isin(['RTO','RVP']), 'RTO')

    # Clean week
    # Extra safe week conversion
    wk_col = out['week']
    if isinstance(wk_col, pd.DataFrame): wk_col = wk_col.iloc[:,0]
    out['week'] = pd.to_numeric(wk_col.squeeze(), errors='coerce').fillna(0).astype(int)
    out = out[out['week']>0]

    # Clean rc
    out['rc'] = out['rc'].fillna('').astype(str).str.strip().map(lambda x: REV.get(x,x))
    out = out[out['rc']!='']

    # Clean zone
    out['zone'] = out['zone'].fillna('').astype(str).str.strip()
    out = out[out['zone']!='']

    # Clean vert
    out['vert'] = out['vert'].fillna('Electronics').astype(str).str.strip()
    out['vert'] = out['vert'].str.replace(r'^RTO[_ ]+','',regex=True).str.replace(r'^RVP[_ ]+','',regex=True).str.strip()
    out.loc[out['vert']=='', 'vert'] = 'Electronics'

    # Clean reason
    out['reason'] = out['reason'].fillna('').astype(str).str.strip()
    out.loc[out['reason'].str.lower().isin(['no issue','no issue.','']), 'reason'] = ''

    # Month mapping
    out['month'] = out['week'].map(wk2m)

    return out.reset_index(drop=True)

def build_js_data(df):
    rc_zones = dict(df.groupby('rc')['zone'].first())
    stats    = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0,0])))
    rd       = defaultdict(list)  # reason detail
    reasons_overall = Counter()
    reasons_rto     = Counter()
    reasons_rvp     = Counter()
    reasons_by_zone = {'overall':defaultdict(Counter),'rto':defaultdict(Counter),'rvp':defaultdict(Counter)}
    reasons_by_rc   = {'overall':defaultdict(Counter),'rto':defaultdict(Counter),'rvp':defaultdict(Counter)}

    for _, row in df.iterrows():
        rc, zone, wk, typ, res, vert, reason, month = (
            row['rc'], row['zone'], row['week'], row['type'],
            row['result'], row['vert'], row['reason'], row['month']
        )
        p = 1 if res=='pass' else 0
        for key in [wk, month]:
            stats[rc][key][typ][0]      += 1
            stats[rc][key]['overall'][0] += 1
            stats[rc][key][typ][1]       += p
            stats[rc][key]['overall'][1] += p

        if res=='fail' and reason:
            reasons_overall[reason] += 1
            rk = 'rto' if typ=='RTO' else 'rvp'
            (reasons_rto if typ=='RTO' else reasons_rvp)[reason] += 1
            reasons_by_zone['overall'][zone][reason] += 1
            reasons_by_zone[rk][zone][reason]         += 1
            reasons_by_rc['overall'][rc][reason]       += 1
            reasons_by_rc[rk][rc][reason]              += 1
            rd[rc].append({'m':month,'w':int(wk),'t':typ,'v':vert,'r':reason,'c':1})

    def gs(rc,key,typ):
        return stats.get(rc,{}).get(key,{}).get(typ,[0,0])
    def gbl(key,typ):
        t,p=0,0
        for rc in stats:
            v=stats[rc].get(key,{}).get(typ,[0,0]); t+=v[0]; p+=v[1]
        return [t,p]
    def mf(d): return ','.join(k+':'+json.dumps(v) for k,v in d.items() if v[0]>0)
    def wf(d): return ','.join(str(k)+':'+json.dumps(v) for k,v in d.items() if v[0]>0)

    # Collapse rd: aggregate per (rc, month, wk, type, vert, reason)
    rd_agg = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: 0)))))
    for rc, entries in rd.items():
        for e in entries:
            rd_agg[rc][e['m']][e['w']][e['t']][e['v']+'\x00'+e['r']] += e['c']

    reason_objs = []
    for rc in rd_agg:
        flat = []
        for m, wks_d in rd_agg[rc].items():
            for wk, typs in wks_d.items():
                for typ, vr in typs.items():
                    for vr_key, cnt in vr.items():
                        v, r = vr_key.split('\x00',1)
                        flat.append({'m':m,'w':wk,'t':typ,'v':v,'r':r,'c':cnt})
        reason_objs.append('{rc:'+json.dumps(rc)+',d:'+json.dumps(flat)+'}')

    # RC objects
    rc_objs = []
    for rc, zone in sorted(rc_zones.items(), key=lambda x:(x[1],x[0])):
        wo = {w:gs(rc,w,'overall') for w in LAST7WKS}
        if sum(v[0] for v in wo.values())==0: continue
        mo = {m:gs(rc,m,'overall') for m in MONTHS}
        mr = {m:gs(rc,m,'RTO')     for m in MONTHS}
        mv = {m:gs(rc,m,'RVP')     for m in MONTHS}
        wr = {w:gs(rc,w,'RTO')     for w in LAST7WKS}
        wv = {w:gs(rc,w,'RVP')     for w in LAST7WKS}
        rr = dict(reasons_by_rc['overall'].get(rc,Counter()).most_common(8))
        s  = '{rc:'+json.dumps(rc)+',zone:'+json.dumps(zone)
        s += ',mth:{overall:{'+mf(mo)+'},rto:{'+mf(mr)+'},rvp:{'+mf(mv)+'}}'
        s += ',wk:{overall:{'+wf(wo)+'},rto:{'+wf(wr)+'},rvp:{'+wf(wv)+'}}'
        s += ',reasons:'+json.dumps(rr)+'}'
        rc_objs.append(s)

    # Global stats
    wko={w:gbl(w,'overall') for w in ALL_WKS}
    wkr={w:gbl(w,'RTO')     for w in ALL_WKS}
    wkv={w:gbl(w,'RVP')     for w in ALL_WKS}
    mto={m:gbl(m,'overall') for m in MONTHS}
    mtr={m:gbl(m,'RTO')     for m in MONTHS}
    mtv={m:gbl(m,'RVP')     for m in MONTHS}

    # Trend / declining
    def get_dec():
        dec = []
        seen = set()
        for rc, zone in rc_zones.items():
            for typ in ['overall','RTO','RVP']:
                wk_vals = {}
                for w in LAST7WKS:
                    v = stats[rc].get(w,{}).get(typ,[0,0])
                    if v[0]>0: wk_vals[w] = round(v[1]/v[0]*100,1)
                if len(wk_vals)<3: continue
                early = [wk_vals[w] for w in LAST7WKS[:3] if w in wk_vals]
                late  = [wk_vals[w] for w in LAST7WKS[4:] if w in wk_vals]
                if not early or not late: continue
                ae,al = sum(early)/len(early), sum(late)/len(late)
                drop  = round(ae-al,1)
                if drop<=1.5 or (rc,typ) in seen: continue
                seen.add((rc,typ))
                top_r = list(reasons_by_rc['overall'].get(rc,Counter()).keys())
                top_r = top_r[0] if top_r else ''
                obs = ('🔴 Critical drop.' if drop>15 else '🟠 Significant decline.' if drop>7 else '🟡 Moderate decline.')
                obs += f' {typ} down {drop}% (Wk17→Wk23).'
                dec.append({'rc':rc,'zone':zone,'type':typ,
                            'avg_early':round(ae,1),'avg_late':round(al,1),'drop':drop,
                            'wk_vals':{str(w):v for w,v in wk_vals.items()},
                            'top_reason':top_r[:60],'obs':obs})
        return sorted(dec, key=lambda x:-x['drop'])[:25]

    declining = get_dec()
    top6 = [r for r,_ in reasons_overall.most_common(6)]
    chart_data = {r:[0]*len(LAST7WKS) for r in top6}
    for rc, entries in rd.items():
        for e in entries:
            if e['w'] in LAST7WKS and e['r'] in chart_data:
                chart_data[e['r']][LAST7WKS.index(e['w'])] += e['c']

    all_verts = sorted(set(df['vert'].dropna().unique()) - {''})

    lines = [
        'const MONTHS='+json.dumps(MONTHS)+';',
        'const MLABELS='+json.dumps(MLABELS)+';',
        'const LAST7WKS='+json.dumps(LAST7WKS)+';',
        'const ALL_WKS='+json.dumps(ALL_WKS)+';',
        'const ALL_VERTS='+json.dumps(all_verts)+';',
        'const REASONS_OVERALL='+json.dumps(dict(reasons_overall.most_common(12)))+';',
        'const REASONS_RTO='+json.dumps(dict(reasons_rto.most_common(12)))+';',
        'const REASONS_RVP='+json.dumps(dict(reasons_rvp.most_common(12)))+';',
        'const REASONS_BY_ZONE='+json.dumps({'overall':{z:dict(c.most_common(8)) for z,c in reasons_by_zone['overall'].items()},'rto':{z:dict(c.most_common(8)) for z,c in reasons_by_zone['rto'].items()},'rvp':{z:dict(c.most_common(8)) for z,c in reasons_by_zone['rvp'].items()}})+';',
        'const REASONS_BY_RC='+json.dumps({'overall':{rc:dict(c.most_common(8)) for rc,c in reasons_by_rc['overall'].items()},'rto':{rc:dict(c.most_common(8)) for rc,c in reasons_by_rc['rto'].items()},'rvp':{rc:dict(c.most_common(8)) for rc,c in reasons_by_rc['rvp'].items()}})+';',
        'const WK_OV={'+','.join(str(k)+':'+json.dumps(v) for k,v in wko.items() if v[0]>0)+'};',
        'const WK_RTO={'+','.join(str(k)+':'+json.dumps(v) for k,v in wkr.items() if v[0]>0)+'};',
        'const WK_RVP={'+','.join(str(k)+':'+json.dumps(v) for k,v in wkv.items() if v[0]>0)+'};',
        'const MTH_OV={'+','.join('"'+k+'":'+json.dumps(v) for k,v in mto.items() if v[0]>0)+'};',
        'const MTH_RTO={'+','.join('"'+k+'":'+json.dumps(v) for k,v in mtr.items() if v[0]>0)+'};',
        'const MTH_RVP={'+','.join('"'+k+'":'+json.dumps(v) for k,v in mtv.items() if v[0]>0)+'};',
        'const DECLINING='+json.dumps(declining)+';',
        'const TOP6_REASONS='+json.dumps(top6)+';',
        'const CHART_DATA='+json.dumps(chart_data)+';',
        'const TREND_WKS='+json.dumps(LAST7WKS)+';',
        'const RC_DATA=[\n'+',\n'.join(rc_objs)+'\n];',
        'const REASON_DATA=[\n'+',\n'.join(reason_objs)+'\n];',
    ]
    return '\n'.join(lines), len(df)

# ── EMBEDDED HTML TEMPLATE ────────────────────────────────────────────────────
DASHBOARD_TEMPLATE = "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\"/>\n<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"/>\n<title>Flipkart Resealing Conversion Dashboard</title>\n<script src=\"https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js\"></script>\n<style>\n@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');\n*{box-sizing:border-box;margin:0;padding:0;font-family:'Inter',sans-serif}\nbody{background:#1e2130;color:#e2e8f0;min-height:100vh}\n.hdr{background:linear-gradient(135deg,#2c3e6b,#1a2a4a);border-bottom:3px solid #F8CA00;padding:12px 24px;display:flex;align-items:center;justify-content:space-between}\n.htitle{color:#F8CA00;font-size:20px;font-weight:800}\n.hsub{color:#cbd5e1;font-size:11px;margin-top:2px}\n.live{display:flex;align-items:center;gap:6px;font-size:10px;font-weight:700;color:#4ade80;background:rgba(74,222,128,.1);border:1px solid rgba(74,222,128,.3);padding:4px 12px;border-radius:20px}\n.ld{width:6px;height:6px;border-radius:50%;background:#4ade80;animation:lp 1.5s infinite;display:inline-block}\n@keyframes lp{0%{box-shadow:0 0 0 0 rgba(74,222,128,.7)}70%{box-shadow:0 0 0 5px rgba(74,222,128,0)}100%{box-shadow:0 0 0 0 rgba(74,222,128,0)}}\n\n/* FILTER BAR */\n.fbar{background:#2a2f45;border-bottom:1px solid #3a4060;padding:10px 24px;display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}\n.fg{display:flex;flex-direction:column;gap:3px}\n.fl{color:#94a3b8;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}\nselect{background:#1e2130;border:1px solid #3a4060;color:#e2e8f0;font-size:12px;padding:5px 26px 5px 9px;border-radius:6px;cursor:pointer;appearance:none;background-image:url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2394a3b8'/%3E%3C/svg%3E\");background-repeat:no-repeat;background-position:right 7px center;min-width:130px}\nselect:focus{outline:none;border-color:#F8CA00}\n.frec{margin-left:auto;font-size:11px;color:#94a3b8;align-self:center;white-space:nowrap}\n.frec b{color:#F8CA00;font-family:monospace}\n.main{padding:14px 24px 48px}\n\n/* KPI */\n.krow{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px}\n.kc{background:#2a2f45;border:1px solid #3a4060;border-radius:12px;padding:16px 20px;text-align:center}\n.kl{color:#94a3b8;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.4px}\n.kv{font-size:34px;font-weight:800;margin-top:5px}\n\n/* OBSERVATION BOX */\n.obs{background:linear-gradient(135deg,rgba(248,202,0,.08),rgba(59,130,246,.06));border:1px solid rgba(248,202,0,.25);border-radius:10px;padding:14px 18px;margin-bottom:14px}\n.obs-title{color:#F8CA00;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px;display:flex;align-items:center;gap:6px}\n.obs-body{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}\n.obs-item{background:rgba(255,255,255,.04);border-radius:8px;padding:10px 12px;border-left:3px solid var(--oc)}\n.obs-item h4{font-size:11px;font-weight:700;color:var(--oc);margin-bottom:4px}\n.obs-item p{font-size:11px;color:#94a3b8;line-height:1.5}\n\n/* SECTION */\n.sec{color:#F8CA00;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;border-left:3px solid #F8CA00;padding-left:10px;margin:16px 0 8px}\n\n/* CARD */\n.card{background:#2a2f45;border:1px solid #3a4060;border-radius:10px;overflow:hidden;margin-bottom:12px}\n\n/* TABLE */\n.tw{overflow-x:auto}\n.tw::-webkit-scrollbar{height:4px}\n.tw::-webkit-scrollbar-thumb{background:#3a4060;border-radius:2px}\ntable{width:100%;border-collapse:collapse;font-size:12px}\nthead th{background:#1e2130;color:#94a3b8;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;padding:8px 12px;border-bottom:1px solid #3a4060;white-space:nowrap;text-align:center}\nthead th:first-child{text-align:left;min-width:155px;position:sticky;left:0;background:#1e2130;z-index:2}\nthead th:nth-child(2){text-align:left;min-width:65px}\nthead th.ov{background:rgba(248,202,0,.1);color:#F8CA00}\nthead th.tgt{background:rgba(74,222,128,.08);color:#4ade80}\ntbody tr{border-bottom:1px solid rgba(255,255,255,.04)}\ntbody tr:hover{background:rgba(255,255,255,.03)}\ntbody td{padding:7px 12px;text-align:center;font-size:12px}\ntbody td:first-child{text-align:left;font-weight:600;color:#e2e8f0;position:sticky;left:0;background:#2a2f45;z-index:1}\ntbody tr:hover td:first-child{background:#323754}\ntbody td:nth-child(2){text-align:left;font-size:11px;color:#94a3b8}\ntbody td.ov{background:rgba(248,202,0,.05);font-weight:700}\ntbody td.tgt{background:rgba(74,222,128,.05);font-size:10px;color:#4ade80}\n.sep td{background:#1a1e2e!important;padding:1px!important}\n\n/* REASONS */\n.reasons-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}\n.reason-card{background:#2a2f45;border:1px solid #3a4060;border-radius:10px;padding:14px 16px}\n.reason-card h3{font-size:10px;font-weight:700;color:#F8CA00;text-transform:uppercase;letter-spacing:.7px;margin-bottom:10px}\n.ritem{margin-bottom:8px}\n.rheader{display:flex;justify-content:space-between;align-items:center;margin-bottom:3px}\n.rname{font-size:11px;color:#e2e8f0;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:8px}\n.rpct{font-size:10px;font-weight:700;color:#F8CA00;font-family:monospace;white-space:nowrap}\n.rbw{height:3px;background:rgba(255,255,255,.06);border-radius:2px}\n.rb{height:100%;background:#F8CA00;border-radius:2px;transition:width .5s}\n\n/* TABS */\n.tabs{display:flex;gap:4px;padding:10px 14px 0}\n.tab{background:transparent;border:1px solid #3a4060;color:#94a3b8;font-size:11px;font-weight:600;padding:5px 14px;border-radius:6px 6px 0 0;cursor:pointer;transition:all .15s}\n.tab.active{background:#F8CA00;color:#1a1a1a;border-color:#F8CA00}\n\n.footer{text-align:center;color:#64748b;font-size:10px;padding:14px;border-top:1px solid #2a2f45;margin-top:4px}\n\n/* REASON FILTER BAR */\n.rfbar{background:#1e2130;border:1px solid #3a4060;border-radius:10px;padding:10px 14px;\n  margin-bottom:10px;display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}\n.rtbl-wrap{overflow-x:auto;max-height:420px;overflow-y:auto}\n.rtbl-wrap::-webkit-scrollbar{width:3px;height:3px}\n.rtbl-wrap::-webkit-scrollbar-thumb{background:#3a4060;border-radius:2px}\n\n/* TREND TABLE */\n.trend-badge{display:inline-flex;padding:2px 8px;border-radius:20px;font-size:10px;font-weight:700}\n.drop-high{background:rgba(239,68,68,.15);color:#ef4444}\n.drop-med{background:rgba(245,166,35,.15);color:#f5a623}\n.drop-low{background:rgba(248,202,0,.15);color:#F8CA00}\n.mini-spark{display:flex;align-items:flex-end;gap:2px;height:28px}\n.spark-bar{width:8px;border-radius:2px 2px 0 0;min-height:2px;background:#4f8ef7;transition:height .3s}\n/* CHART CONTAINER */\n.chart-card{background:#2a2f45;border:1px solid #3a4060;border-radius:10px;padding:16px 18px;margin-bottom:12px}\n.chart-card h3{font-size:10px;font-weight:700;color:#F8CA00;text-transform:uppercase;letter-spacing:.7px;margin-bottom:12px}\n\n/* Sticky first 2 columns in site table */\n#sBody tr:hover td:nth-child(1),\n#sBody tr:hover td:nth-child(2){background:#323754!important;}\n#smpBody tr:hover td:nth-child(1),\n#smpBody tr:hover td:nth-child(2){background:#323754!important;}\ntbody td {padding:5px 6px;}\n</style>\n</head>\n<body>\n\n<div class=\"hdr\">\n  <div>\n    <div class=\"htitle\">\ud83d\udce6 Resealing Conversion Dashboard \u2014 Pan India</div>\n    <div class=\"hsub\">Flipkart FC \u00b7 RTO/RVP Resealing Conversion Tracker \u00b7 <span id=\"recLbl\">1,27,871</span> records \u00b7 Target: &gt;90%</div>\n  </div>\n  <div style=\"display:flex;align-items:center;gap:10px\">\n    <div class=\"live\"><div class=\"ld\"></div>LIVE</div>\n    <div style=\"font-size:10px;color:#94a3b8\" id=\"clock\"></div>\n  </div>\n</div>\n\n<!-- FILTER BAR -->\n<div class=\"fbar\">\n  <div class=\"fg\"><div class=\"fl\">Zone</div>\n    <select id=\"fZone\" onchange=\"render()\"><option value=\"\">All Zones</option><option>East</option><option>North</option><option>South</option><option>West</option></select>\n  </div>\n  <div class=\"fg\"><div class=\"fl\">RC / Site</div>\n    <select id=\"fRC\" onchange=\"render()\"><option value=\"\">All Sites</option></select>\n  </div>\n  <div class=\"fg\"><div class=\"fl\">Month</div>\n    <select id=\"fMonth\" onchange=\"render()\"><option value=\"\">All Months</option></select>\n  </div>\n  <div class=\"fg\"><div class=\"fl\">Week</div>\n    <select id=\"fWeek\" onchange=\"render()\"><option value=\"\">All Weeks</option></select>\n  </div>\n  <div class=\"fg\"><div class=\"fl\">Vertical</div>\n    <select id=\"fVert\" onchange=\"render()\"><option value=\"\">All Verticals</option></select>\n  </div>\n  <div class=\"fg\"><div class=\"fl\">Type</div>\n    <select id=\"fType\" onchange=\"render()\"><option value=\"\">RTO + RVP</option><option value=\"rto\">RTO only</option><option value=\"rvp\">RVP only</option></select>\n  </div>\n  <div class=\"frec\">Showing <b id=\"recCount\">1,27,871</b> records</div>\n</div>\n\n<div class=\"main\">\n\n  <!-- KPI -->\n  <div class=\"krow\">\n    <div class=\"kc\"><div class=\"kl\">Overall Resealing Conversion</div><div class=\"kv\" id=\"kOv\">\u2014</div></div>\n    <div class=\"kc\"><div class=\"kl\">RTO Resealing Conversion</div><div class=\"kv\" id=\"kRTO\">\u2014</div></div>\n    <div class=\"kc\"><div class=\"kl\">RVP Resealing Conversion</div><div class=\"kv\" id=\"kRVP\">\u2014</div></div>\n  </div>\n\n  <!-- OBSERVATION BOX -->\n  <div class=\"obs\">\n    <div class=\"obs-title\">\ud83d\udccb Key Observations &amp; Target Analysis</div>\n    <div class=\"obs-body\" id=\"obsBody\"></div>\n  </div>\n\n  <!-- MONTH WISE -->\n  <div class=\"sec\">\ud83d\udcc5 Conversion \u2014 Month Wise</div>\n  <div class=\"card\"><div class=\"tw\"><table><thead><tr id=\"mHead\"></tr></thead><tbody id=\"mBody\"></tbody></table></div></div>\n\n  <!-- WEEK WISE -->\n  <div class=\"sec\">\ud83d\udcca Conversion \u2014 Last 7 Weeks</div>\n  <div class=\"card\"><div class=\"tw\"><table><thead><tr id=\"wHead\"></tr></thead><tbody id=\"wBody\"></tbody></table></div></div>\n\n  <!-- FAILURE REASONS - 3 PANELS -->\n  <div class=\"sec\">\ud83d\udd0d Failure Reason Analysis \u2014 QA Remark (Excl. No Issue)</div>\n  <div style=\"display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:12px\">\n    <div class=\"reason-card\">\n      <h3 style=\"color:#e2e8f0\">\ud83d\udcca Overall (RTO + RVP)</h3>\n      <div id=\"reasonOverall\"></div>\n    </div>\n    <div class=\"reason-card\">\n      <h3 style=\"color:#4f8ef7\">\ud83d\udd35 RTO Only</h3>\n      <div id=\"reasonRTO\"></div>\n    </div>\n    <div class=\"reason-card\">\n      <h3 style=\"color:#36d9a4\">\ud83d\udfe2 RVP Only</h3>\n      <div id=\"reasonRVP\"></div>\n    </div>\n  </div>\n\n\n  <!-- SITE TABLE -->\n  <div class=\"sec\">\ud83c\udfed Site-wise Resealing Conversion</div>\n  <div style=\"display:flex;gap:4px;margin-bottom:0\">\n    <button class=\"tab active\" onclick=\"setTab('overall',this)\">\ud83d\udcca Overall</button>\n    <button class=\"tab\" onclick=\"setTab('rto',this)\">\ud83d\udd35 RTO</button>\n    <button class=\"tab\" onclick=\"setTab('rvp',this)\">\ud83d\udfe2 RVP</button>\n  </div>\n  <div class=\"card\"><div class=\"tw\" style=\"overflow-x:auto\"><table style=\"min-width:max-content\"><thead><tr id=\"sHead\"></tr></thead><tbody id=\"sBody\"></tbody></table></div></div>\n\n</div>\n\n\n    <!-- SAMPLE SIZE TABLE \u2014 inserted after site-wise conversion -->\n  <div class=\"sec\">\ud83d\udd2c Sample Size Monitor \u2014 Weekly Audit Count per Site (Ov / RTO / RVP)</div>\n  <div style=\"background:#2a2f45;border:1px solid #3a4060;border-radius:10px;overflow:hidden;margin-bottom:14px\">\n    <div style=\"padding:7px 14px;border-bottom:1px solid #3a4060;display:flex;gap:16px;flex-wrap:wrap;font-size:10px;color:#94a3b8;align-items:center\">\n      <span style=\"font-weight:600;color:#f0f2f8\">Color guide:</span>\n      <span style=\"color:#22c55e\">\u25cf \u2265200 (healthy)</span>\n      <span style=\"color:#f5a623\">\u25cf 100\u2013199 (watch)</span>\n      <span style=\"color:#ef4444\">\u25cf &lt;100 (low \u2014 not filling data)</span>\n      <span style=\"color:#ef4444\">\ud83d\udd34 = dropped \u226550% vs prev week</span>\n      <span style=\"color:#5a6278;margin-left:4px\">Each cell shows: Overall / RTO / RVP</span>\n    </div>\n    <div style=\"overflow-x:auto\">\n      <table style=\"width:100%;border-collapse:collapse;font-size:11px\">\n        <thead><tr id=\"smpHead\" style=\"background:#1e2130\"></tr></thead>\n        <tbody id=\"smpBody\"></tbody>\n      </table>\n    </div>\n  </div>\n\n  <!-- SITE FAILURE REASON TABLE -->\n  <div class=\"sec\">\ud83d\udccb Site-level Failure Reason Analysis (QA Remark)</div>\n\n  <!-- Reason filters -->\n  <div class=\"rfbar\" style=\"padding:8px 14px;gap:8px\">\n    <div class=\"fg\"><div class=\"fl\">Site</div>\n      <select id=\"rSite\" onchange=\"renderReasonTable();renderReasonCharts()\"><option value=\"\">All Sites</option></select>\n    </div>\n    <div class=\"fg\"><div class=\"fl\">Month</div>\n      <select id=\"rMonth\" onchange=\"renderReasonTable();renderReasonCharts()\"><option value=\"\">All Months</option></select>\n    </div>\n    <div class=\"fg\"><div class=\"fl\">Week</div>\n      <select id=\"rWeek\" onchange=\"renderReasonTable();renderReasonCharts()\"><option value=\"\">All Weeks</option></select>\n    </div>\n    <div class=\"fg\"><div class=\"fl\">Vertical 1</div>\n      <select id=\"rVert\" onchange=\"renderReasonTable();renderReasonCharts()\"><option value=\"\">All Verticals</option></select>\n    </div>\n    <div class=\"frec\">Total failures: <b id=\"rCount\">\u2014</b></div>\n  </div>\n\n  <!-- 3 panels: Overall / RTO / RVP -->\n  <div style=\"display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:14px\">\n    <div class=\"reason-card\">\n      <h3 id=\"rPanelTitle1\" style=\"color:#e2e8f0\">All Sites \u2014 Overall</h3>\n      <div id=\"rPanelBody1\"></div>\n    </div>\n    <div class=\"reason-card\">\n      <h3 id=\"rPanelTitle2\" style=\"color:#4f8ef7\">All Sites \u2014 RTO Only</h3>\n      <div id=\"rPanelBody2\"></div>\n    </div>\n    <div class=\"reason-card\">\n      <h3 id=\"rPanelTitle3\" style=\"color:#36d9a4\">All Sites \u2014 RVP Only</h3>\n      <div id=\"rPanelBody3\"></div>\n    </div>\n  </div>\n  <!-- Hidden tbody needed for JS compatibility -->\n  <tbody id=\"reasonBody\" style=\"display:none\"></tbody>\n  <tbody id=\"trendBody\" style=\"display:none\"></tbody>\n\n  <!-- FAILURE REASON BAR CHART - WEEK ON WEEK -->\n  <div class=\"sec\">\ud83d\udcca Failure Reason Trend \u2014 Week on Week Contribution</div>\n  <div class=\"chart-card\">\n    <h3>Top 6 Failure Reasons \u2014 Weekly Count (Wk 17 to 23, excl. No Issue)</h3>\n    <div style=\"display:flex;gap:12px;flex-wrap:wrap;margin-bottom:10px;font-size:11px;color:#94a3b8\" id=\"chartLegend\"></div>\n    <div style=\"position:relative;height:300px\">\n      <canvas id=\"reasonTrendChart\" role=\"img\" aria-label=\"Weekly failure reason trend bar chart\"></canvas>\n    </div>\n  </div>\n\n  <!-- REASON STACKED % CHART -->\n  <div class=\"chart-card\">\n    <h3>Failure Reason % Contribution per Week \u2014 Stacked (Wk 17 to 23)</h3>\n    <div style=\"position:relative;height:260px\">\n      <canvas id=\"reasonPctChart\" role=\"img\" aria-label=\"Weekly failure reason percentage stacked chart\"></canvas>\n    </div>\n  </div>\n\n\n<div class=\"footer\">Resealing Conversion % = Pass \u00f7 (Pass + Fail) \u00d7 100 \u00b7 Target &gt;90% \u00b7 resealing-dashboard-fk.streamlit.app \u00b7 Wks 1\u201323 \u00b7 2026</div>\n\n<script>\nDATABLOCK\nlet sTab='overall', trendChart=null, pctChart=null;\nconst REASON_COLORS=['#ef4444','#f5a623','#F8CA00','#4ade80','#4f8ef7','#a78bfa'];\nconst pct=(p,t)=>t>0?(p/t*100).toFixed(2)+'%':'\u2014';\nconst conv=(p,t)=>t>0?Math.round(p/t*1000)/10:0;\nconst fmtN=n=>n.toLocaleString('en-IN');\nfunction cc(v){if(v==='\u2014')return'color:#4a5568';const n=parseFloat(v);if(isNaN(n))return'color:#4a5568';if(n>=90)return'color:#22c55e;font-weight:700';if(n>=85)return'color:#4ade80;font-weight:700';if(n>=80)return'color:#F8CA00;font-weight:700';return'color:#ef4444;font-weight:700';}\nfunction kc(v){return v>=90?'#22c55e':v>=85?'#4ade80':v>=80?'#F8CA00':'#ef4444';}\nsetInterval(()=>{const c=document.getElementById('clock');if(c)c.textContent=new Date().toLocaleString('en-IN');},1000);\n\nfunction populateFilters(){\n  const ms=document.getElementById('fMonth'); ms.innerHTML='<option value=\"\">All Months</option>';\n  MLABELS.forEach((l,i)=>ms.add(new Option(l,MONTHS[i])));\n  const ws=document.getElementById('fWeek'); ws.innerHTML='<option value=\"\">All Weeks</option>';\n  ALL_WKS.forEach(w=>ws.add(new Option('Wk '+w,w)));\n  const vs=document.getElementById('fVert'); vs.innerHTML='<option value=\"\">All Verticals</option>';\n  ALL_VERTS.forEach(v=>vs.add(new Option(v,v)));\n  populateRC();\n  populateReasonFilters();\n}\nfunction populateRC(){\n  const zone=document.getElementById('fZone').value;\n  const sel=document.getElementById('fRC'); const cur=sel.value;\n  sel.innerHTML='<option value=\"\">All Sites</option>';\n  [...RC_DATA].filter(r=>!zone||r.zone===zone).sort((a,b)=>a.rc.localeCompare(b.rc))\n    .forEach(r=>{const o=new Option(r.rc,r.rc);if(r.rc===cur)o.selected=true;sel.add(o);});\n}\nfunction populateReasonFilters(){\n  const rs=document.getElementById('rSite'); rs.innerHTML='<option value=\"\">All Sites</option>';\n  [...RC_DATA].sort((a,b)=>a.rc.localeCompare(b.rc)).forEach(r=>rs.add(new Option(r.rc,r.rc)));\n  const rm=document.getElementById('rMonth'); rm.innerHTML='<option value=\"\">All Months</option>';\n  MLABELS.forEach((l,i)=>rm.add(new Option(l,MONTHS[i])));\n  const rw=document.getElementById('rWeek'); rw.innerHTML='<option value=\"\">All Weeks</option>';\n  ALL_WKS.forEach(w=>rw.add(new Option('Wk '+w,w)));\n  const rv=document.getElementById('rVert'); rv.innerHTML='<option value=\"\">All Verticals</option>';\n  ALL_VERTS.forEach(v=>rv.add(new Option(v,v)));\n}\n\nfunction getFiltered(){\n  const zone=document.getElementById('fZone').value;\n  const rc=document.getElementById('fRC').value;\n  const type=document.getElementById('fType').value||'overall';\n  let d=[...RC_DATA];\n  if(zone) d=d.filter(r=>r.zone===zone);\n  if(rc)   d=d.filter(r=>r.rc===rc);\n  return {data:d,type};\n}\n\nfunction render(){\n  populateRC();\n  const {data,type}=getFiltered();\n  const fWeek=parseInt(document.getElementById('fWeek').value)||0;\n  const fMth=document.getElementById('fMonth').value;\n  let tot=0; data.forEach(r=>ALL_WKS.forEach(w=>{const v=r.wk.overall?.[w];if(v)tot+=v[0];}));\n  document.getElementById('recCount').textContent=fmtN(tot||127871);\n  const sum=(src)=>Object.values(src).reduce((a,v)=>[a[0]+v[0],a[1]+v[1]],[0,0]);\n  const [oT,oP]=sum(WK_OV), [rT,rP]=sum(WK_RTO), [vT,vP]=sum(WK_RVP);\n  const oC=conv(oP,oT), rC=conv(rP,rT), vC=conv(vP,vT);\n  const setel=(id,v)=>{const e=document.getElementById(id);if(e){e.textContent=v+'%';e.style.color=kc(v);}};\n  setel('kOv',oC); setel('kRTO',rC); setel('kRVP',vC);\n  renderObs(oC,rC,vC);\n  renderMonthTable(data,type,fMth);\n  renderWeekTable(data,type,fWeek);\n  renderReasons(data);\n  renderSiteTable(data,sTab);\n}\n\nfunction renderObs(oC,rC,vC){\n  const gap=(90-oC).toFixed(1);\n  const w23=WK_OV[23]?conv(WK_OV[23][1],WK_OV[23][0]):0;\n  const w17=WK_OV[17]?conv(WK_OV[17][1],WK_OV[17][0]):0;\n  const trend=w23-w17;\n  const top=TOP6_REASONS[0]||'Physical Product Damages';\n  const items=[\n    {c:'#F8CA00',t:'\ud83d\udcca vs Target (>90%)',\n     b:oC>=90?`\u2705 Target achieved! Overall ${oC}%. Both types ${rC>=90&&vC>=90?'above':'near'} 90%.`\n            :`\u26a0\ufe0f ${gap}% gap to 90% target. RTO: ${rC}%, RVP: ${vC}%. Focus on ${rC<vC?'RTO':'RVP'}.`},\n    {c:'#ef4444',t:'\ud83d\udd0d Top Fail Drivers',\n     b:`#1: ${(top||'').substring(0,45)}. This + packaging damage = ~70% of all failures. Priority action area.`},\n    {c:'#4ade80',t:'\ud83d\udcc8 Wk17\u219223 Trend',\n     b:trend>=0?`\u2705 +${Math.abs(trend).toFixed(1)}% improvement. Wk23: ${w23}%. Keep momentum going.`\n              :`\u26a0\ufe0f ${Math.abs(trend).toFixed(1)}% decline. Wk23: ${w23}%. Review QA process urgently.`},\n  ];\n  const el=document.getElementById('obsBody');\n  if(el) el.innerHTML=items.map(i=>`<div class=\"obs-item\" style=\"--oc:${i.c}\"><h4>${i.t}</h4><p>${i.b}</p></div>`).join('');\n}\n\nfunction renderMonthTable(data,type,fMth){\n  const months=MONTHS.filter(m=>{let t=0;RC_DATA.forEach(r=>{const v=r.mth.overall?.[m];if(v)t+=v[0];});return t>0;});\n  const mlbls=months.map(m=>MLABELS[MONTHS.indexOf(m)]);\n  const mh=document.getElementById('mHead'); const mb=document.getElementById('mBody');\n  if(!mh||!mb) return;\n  mh.innerHTML='<th>Metric</th>'+mlbls.map((l,i)=>`<th${fMth===months[i]?' style=\"background:rgba(248,202,0,.15)\"':''}>${l}</th>`).join('')+'<th class=\"ov\">Overall</th><th class=\"tgt\">Target</th>';\n  const rows=[{l:'Overall Conversion %',k:'overall'},{l:'RTO Conversion %',k:'rto'},{l:'RVP Conversion %',k:'rvp'}];\n  let tbl='';\n  rows.forEach((r,i)=>{\n    if(i>0) tbl+=`<tr class=\"sep\"><td colspan=\"${months.length+3}\"></td></tr>`;\n    let tT=0,tP=0;\n    const cells=months.map(m=>{let t=0,p=0;data.forEach(d=>{const v=d.mth[r.k]?.[m];if(v){t+=v[0];p+=v[1];}});tT+=t;tP+=p;const v=pct(p,t);return`<td style=\"${cc(v)}\">${v}</td>`;}).join('');\n    const ov=pct(tP,tT);\n    tbl+=`<tr><td>${r.l}</td>${cells}<td class=\"ov\" style=\"${cc(ov)}\">${ov}</td><td class=\"tgt\">>90%</td></tr>`;\n  });\n  mb.innerHTML=tbl;\n}\n\nfunction renderWeekTable(data,type,fWeek){\n  const wks=LAST7WKS;\n  const wh=document.getElementById('wHead'); const wb=document.getElementById('wBody');\n  if(!wh||!wb) return;\n  wh.innerHTML='<th>Metric</th>'+wks.map(w=>`<th${fWeek===w?' style=\"background:rgba(248,202,0,.15)\"':''}>Wk ${w}</th>`).join('')+'<th class=\"ov\">Overall</th><th class=\"tgt\">Target</th>';\n  const rows=[{l:'Overall Conversion %',k:'overall'},{l:'RTO Conversion %',k:'rto'},{l:'RVP Conversion %',k:'rvp'}];\n  let tbl='';\n  rows.forEach((r,i)=>{\n    if(i>0) tbl+=`<tr class=\"sep\"><td colspan=\"${wks.length+3}\"></td></tr>`;\n    let tT=0,tP=0;\n    const cells=wks.map(w=>{let t=0,p=0;data.forEach(d=>{const v=d.wk[r.k]?.[w];if(v){t+=v[0];p+=v[1];}});tT+=t;tP+=p;const v=pct(p,t);return`<td style=\"${cc(v)}\">${v}</td>`;}).join('');\n    const ov=pct(tP,tT);\n    tbl+=`<tr><td>${r.l}</td>${cells}<td class=\"ov\" style=\"${cc(ov)}\">${ov}</td><td class=\"tgt\">>90%</td></tr>`;\n  });\n  wb.innerHTML=tbl;\n}\n\nfunction renderReasons(data){\n  function buildList(reasons,elId,clr){\n    const el=document.getElementById(elId); if(!el) return;\n    const tot=Object.values(reasons).reduce((s,v)=>s+v,0);\n    const mx=Math.max(...Object.values(reasons));\n    el.innerHTML=Object.entries(reasons).slice(0,8).map(([r,cnt])=>{\n      const p=(cnt/tot*100).toFixed(1);\n      return`<div class=\"ritem\"><div class=\"rheader\"><span class=\"rname\" title=\"${r}\">${r.length>45?r.slice(0,43)+'\u2026':r}</span><span class=\"rpct\">${fmtN(cnt)} (${p}%)</span></div><div class=\"rbw\"><div class=\"rb\" style=\"width:${Math.round(cnt/mx*100)}%;background:${clr}\"></div></div></div>`;\n    }).join('');\n  }\n  buildList(REASONS_OVERALL,'reasonOverall','#F8CA00');\n  buildList(REASONS_RTO,'reasonRTO','#4f8ef7');\n  buildList(REASONS_RVP,'reasonRVP','#36d9a4');\n}\n\nfunction setTab(tab,el){\n  sTab=tab;\n  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));\n  el.classList.add('active');\n  const {data}=getFiltered();\n  renderSiteTable(data,tab);\n}\n\nfunction renderSiteTable(data,typ){\n  var wks    = LAST7WKS;\n  var months = MONTHS.filter(function(m){\n    var t=0; RC_DATA.forEach(function(r){var v=r.mth.overall?.[m];if(v)t+=v[0];}); return t>0;\n  });\n  var mlbls = months.map(function(m){return MLABELS[MONTHS.indexOf(m)];});\n  var sh=document.getElementById('sHead'), sb=document.getElementById('sBody');\n  if(!sh||!sb) return;\n\n  sh.innerHTML=\n    '<th style=\"text-align:left;width:150px;min-width:150px;position:sticky;left:0;background:#1e2130;z-index:3;white-space:nowrap\">Site</th>'+\n    '<th style=\"text-align:left;width:58px;min-width:58px;position:sticky;left:150px;background:#1e2130;z-index:3\">Zone</th>'+\n    mlbls.map(function(l){return '<th style=\"width:58px;min-width:58px;white-space:nowrap;font-size:10px\">'+l+'</th>';}).join('')+\n    wks.map(function(w){return '<th style=\"width:44px;min-width:44px;font-size:10px\">Wk'+w+'</th>';}).join('')+\n    '<th class=\"ov\" style=\"width:60px;min-width:60px\">Overall</th>'+\n    '<th class=\"tgt\" style=\"width:46px;min-width:46px\">Gap</th>'+\n    '<th style=\"width:260px;min-width:260px;text-align:left;color:#F8CA00\">Observation</th>';\n\n  var tbl=''; var pz='';\n  var PRIORITY_ORDER=['Frk_bts','Haringhata NLFC 01','Malur_bts','Patna FC 02',\n    'Bhiwandi BTS','Hyderabad_medchal_01','Raipur 3pl 01','Ahm_Kheda',\n    'Guwahati_BTS_01','Nagpur_01','Lucknow FC 02','Bhuneshwar BTS 01','Sanpka'];\n  var sorted=[...data].sort(function(a,b){\n    var ai=PRIORITY_ORDER.indexOf(a.rc), bi=PRIORITY_ORDER.indexOf(b.rc);\n    if(ai>=0&&bi>=0) return ai-bi;          // both priority: keep order\n    if(ai>=0) return -1;                     // a priority, b not: a first\n    if(bi>=0) return 1;                      // b priority, a not: b first\n    return a.zone.localeCompare(b.zone)||a.rc.localeCompare(b.rc); // rest: zone then alpha\n  });\n\n  sorted.forEach(function(r){\n    if(r.zone!==pz&&pz!==''&&PRIORITY_ORDER.indexOf(r.rc)<0&&PRIORITY_ORDER.indexOf(r.rc)<0) tbl+='<tr class=\"sep\"><td colspan=\"'+(months.length+wks.length+6)+'\"></td></tr>';\n    pz=r.zone;\n    var tT=0,tP=0;\n\n    var mc=months.map(function(m){\n      var v=r.mth[typ]?.[m];\n      if(!v) return '<td style=\"color:#4a5568;font-size:10px;padding:5px 2px;text-align:center\">\u2014</td>';\n      tT+=v[0]; tP+=v[1];\n      var pv=pct(v[1],v[0]);\n      return '<td style=\"'+cc(pv)+';font-size:10px;padding:5px 2px;text-align:center\">'+pv+'</td>';\n    }).join('');\n\n    var wc=wks.map(function(w){\n      var v=r.wk[typ]?.[w];\n      if(!v) return '<td style=\"color:#4a5568;font-size:10px;padding:5px 2px;text-align:center\">\u2014</td>';\n      tT+=v[0]; tP+=v[1];\n      var pv=pct(v[1],v[0]);\n      return '<td style=\"'+cc(pv)+';font-size:10px;padding:5px 2px;text-align:center\">'+pv+'</td>';\n    }).join('');\n\n    var ov  = pct(tP,tT);\n    var gap = tT>0?(90-tP/tT*100).toFixed(1):null;\n    var gt  = gap!==null?(parseFloat(gap)<=0?'\u2705':gap+'%'):'\u2014';\n    var obs = buildSiteObs(r);\n\n    tbl+='<tr>'+\n      '<td style=\"font-size:11px;font-weight:600;padding:5px 8px;position:sticky;left:0;background:#2a2f45;z-index:2;white-space:nowrap;width:150px\">'+r.rc+'</td>'+\n      '<td style=\"font-size:10px;color:#94a3b8;padding:5px 6px;position:sticky;left:150px;background:#2a2f45;z-index:2;width:58px\">'+r.zone+'</td>'+\n      mc+wc+\n      '<td class=\"ov\" style=\"'+cc(ov)+';font-size:11px;padding:5px 4px;text-align:center;font-weight:700\">'+ov+'</td>'+\n      '<td style=\"font-size:10px;padding:5px 4px;text-align:center;'+(parseFloat(gap)<=0?'color:#22c55e':'color:#f5a623')+'\">'+gt+'</td>'+\n      '<td style=\"font-size:10px;line-height:1.6;padding:5px 8px;width:260px;vertical-align:top\">'+obs+'</td>'+\n    '</tr>';\n  });\n  sb.innerHTML=tbl||'<tr><td colspan=\"20\" style=\"text-align:center;color:#94a3b8;padding:12px\">No data</td></tr>';\n}\n\n\nfunction buildSiteObs(r){\n  var obs=[];\n  var wks=LAST7WKS;\n\n  // Helper: get conversion for a type over last N weeks\n  function getWkConv(typ,wList){\n    var t=0,p=0;\n    wList.forEach(function(w){var v=r.wk[typ]?.[w];if(v){t+=v[0];p+=v[1];}});\n    return t>0?Math.round(p/t*1000)/10:null;\n  }\n  function getWkSample(typ,wList){\n    var t=0; wList.forEach(function(w){var v=r.wk[typ]?.[w];if(v)t+=v[0];}); return t;\n  }\n\n  var early=wks.slice(0,3), late=wks.slice(4);\n\n  // Overall conversion trend\n  var ovE=getWkConv('overall',early), ovL=getWkConv('overall',late);\n  var rtoE=getWkConv('rto',early),    rtoL=getWkConv('rto',late);\n  var rvpE=getWkConv('rvp',early),    rvpL=getWkConv('rvp',late);\n\n  if(ovE!==null&&ovL!==null){\n    var drop=Math.round((ovE-ovL)*10)/10;\n    if(drop>10)      obs.push('<span style=\"color:#ef4444\">\ud83d\udd34 Conv dropped '+drop+'% ('+ovE+'\u2192'+ovL+'%)</span>');\n    else if(drop>5)  obs.push('<span style=\"color:#f5a623\">\ud83d\udfe0 Conv down '+drop+'% ('+ovE+'\u2192'+ovL+'%)</span>');\n    else if(drop<-3) obs.push('<span style=\"color:#22c55e\">\u2705 Conv improved '+(Math.abs(drop))+'%</span>');\n  }\n  if(rtoE!==null&&rtoL!==null){\n    var rdrop=Math.round((rtoE-rtoL)*10)/10;\n    if(rdrop>8) obs.push('<span style=\"color:#ef4444\">\ud83d\udd34 RTO \u2193'+rdrop+'% ('+rtoE+'\u2192'+rtoL+'%)</span>');\n    else if(rdrop>4) obs.push('<span style=\"color:#f5a623\">\ud83d\udfe0 RTO \u2193'+rdrop+'%</span>');\n  }\n  if(rvpE!==null&&rvpL!==null){\n    var vdrop=Math.round((rvpE-rvpL)*10)/10;\n    if(vdrop>8) obs.push('<span style=\"color:#ef4444\">\ud83d\udd34 RVP \u2193'+vdrop+'% ('+rvpE+'\u2192'+rvpL+'%)</span>');\n    else if(vdrop>4) obs.push('<span style=\"color:#f5a623\">\ud83d\udfe0 RVP \u2193'+vdrop+'%</span>');\n  }\n\n  // Sample drop check: last 2 weeks\n  var lastWk=wks[wks.length-1], prevWk=wks[wks.length-2];\n  ['overall','rto','rvp'].forEach(function(typ){\n    var lv=r.wk[typ]?.[lastWk]?r.wk[typ][lastWk][0]:0;\n    var pv=r.wk[typ]?.[prevWk]?r.wk[typ][prevWk][0]:0;\n    var lbl=typ==='overall'?'Overall':typ==='rto'?'RTO':'RVP';\n    if(lv<100&&lv>0) obs.push('<span style=\"color:#ef4444\">\u26a0\ufe0f '+lbl+' Wk23 sample='+lv+' (low)</span>');\n    else if(pv>0&&lv===0) obs.push('<span style=\"color:#ef4444\">\u26a0\ufe0f '+lbl+' no data Wk23</span>');\n    else if(pv>50&&lv>0&&lv/pv<0.5) obs.push('<span style=\"color:#ef4444\">\u26a0\ufe0f '+lbl+' sample dropped '+(100-Math.round(lv/pv*100))+'% ('+pv+'\u2192'+lv+')</span>');\n  });\n\n  if(obs.length===0){\n    var ovCurr=getWkConv('overall',[wks[wks.length-1]]);\n    if(ovCurr!==null&&ovCurr>=90) return '<span style=\"color:#22c55e;font-size:10px\">\u2705 On track \u2014 Conv '+ovCurr+'% (\u226590%)</span>';\n    return '<span style=\"color:#94a3b8;font-size:10px\">No major issues</span>';\n  }\n  return obs.join('<br>');\n}\n\n\nfunction renderReasonTable(){\n  var fSite  = document.getElementById('rSite').value;\n  var fMonth = document.getElementById('rMonth').value;\n  var fWeek  = parseInt(document.getElementById('rWeek').value)||0;\n  var fVert  = document.getElementById('rVert').value;\n  var zone   = document.getElementById('fZone').value;\n\n  // Filter sites\n  var sites = REASON_DATA.slice();\n  if(fSite)  sites = sites.filter(function(s){return s.rc===fSite;});\n  else if(zone) sites = sites.filter(function(s){\n    var r=RC_DATA.find(function(x){return x.rc===s.rc;});\n    return r&&r.zone===zone;\n  });\n\n  // Aggregate by reason, split by type\n  var agg_ov={}, agg_rto={}, agg_rvp={};\n  var tot_ov=0, tot_rto=0, tot_rvp=0;\n\n  sites.forEach(function(s){\n    s.d.forEach(function(e){\n      if(fMonth && e.m!==fMonth) return;\n      if(fWeek  && e.w!==fWeek)  return;\n      if(fVert  && e.v!==fVert)  return;\n      var r=e.r;\n      // Overall\n      agg_ov[r]=(agg_ov[r]||0)+e.c; tot_ov+=e.c;\n      // RTO / RVP\n      if(e.t==='RTO'){ agg_rto[r]=(agg_rto[r]||0)+e.c; tot_rto+=e.c; }\n      else            { agg_rvp[r]=(agg_rvp[r]||0)+e.c; tot_rvp+=e.c; }\n    });\n  });\n\n  var rce=document.getElementById('rCount');\n  if(rce) rce.textContent=fmtN(tot_ov);\n\n  function buildPanel(agg, tot, clr){\n    if(!tot) return '<p style=\"color:#4a5568;font-size:12px;padding:8px 0\">No data</p>';\n    var entries=Object.entries(agg).sort(function(a,b){return b[1]-a[1];}).slice(0,10);\n    var mx=entries[0]?entries[0][1]:1;\n    return entries.map(function(e){\n      var r=e[0], cnt=e[1];\n      var p=(cnt/tot*100).toFixed(1);\n      var bw=Math.round(cnt/mx*100);\n      return '<div class=\"ritem\">'+\n        '<div class=\"rheader\">'+\n          '<span class=\"rname\" title=\"'+r+'\">'+(r.length>46?r.slice(0,44)+'\u2026':r)+'</span>'+\n          '<span class=\"rpct\">'+fmtN(cnt)+' ('+p+'%)</span>'+\n        '</div>'+\n        '<div class=\"rbw\"><div class=\"rb\" style=\"width:'+bw+'%;background:'+clr+'\"></div></div>'+\n      '</div>';\n    }).join('');\n  }\n\n  var label = fSite ? fSite : (zone ? 'Zone: '+zone : 'All Sites');\n  var suffix = (fMonth?' \u00b7 '+MLABELS[MONTHS.indexOf(fMonth)]:'')+(fWeek?' \u00b7 Wk '+fWeek:'')+(fVert?' \u00b7 '+fVert:'');\n\n  // Update panel titles\n  var t1=document.getElementById('rPanelTitle1');\n  var t2=document.getElementById('rPanelTitle2');\n  var t3=document.getElementById('rPanelTitle3');\n  if(t1) t1.textContent = label+' \u2014 Overall'+suffix;\n  if(t2) t2.textContent = label+' \u2014 RTO Only'+suffix;\n  if(t3) t3.textContent = label+' \u2014 RVP Only'+suffix;\n\n  var p1=document.getElementById('rPanelBody1');\n  var p2=document.getElementById('rPanelBody2');\n  var p3=document.getElementById('rPanelBody3');\n  if(p1) p1.innerHTML=buildPanel(agg_ov,tot_ov,'#F8CA00');\n  if(p2) p2.innerHTML=buildPanel(agg_rto,tot_rto,'#4f8ef7');\n  if(p3) p3.innerHTML=buildPanel(agg_rvp,tot_rvp,'#36d9a4');\n}\n\n\nfunction renderSampleTable(){\n  var sh=document.getElementById('smpHead');\n  var sb=document.getElementById('smpBody');\n  if(!sh||!sb) return;\n\n  var wks=LAST7WKS;\n  sh.innerHTML='<th style=\"text-align:left;position:sticky;left:0;background:#1e2130;z-index:3;min-width:140px\">Site</th>'+\n    '<th style=\"text-align:left;position:sticky;left:140px;background:#1e2130;z-index:3;min-width:55px\">Zone</th>'+\n    wks.map(function(w){return '<th>Wk '+w+'<br><span style=\"font-size:9px;color:#5a6278;font-weight:400\">Ov/RTO/RVP</span></th>';}).join('')+\n    '<th class=\"ov\">Wk23 Alert</th>';\n\n  var tbl=''; var pz='';\n  var sorted=[...RC_DATA].sort(function(a,b){return a.zone.localeCompare(b.zone)||a.rc.localeCompare(b.rc);});\n\n  sorted.forEach(function(r){\n    if(r.zone!==pz && pz!=='')\n      tbl+='<tr class=\"sep\"><td colspan=\"'+(wks.length+3)+'\"></td></tr>';\n    pz=r.zone;\n\n    // Build week cells\n    var prevOv=null, prevRto=null, prevRvp=null;\n    var alerts=[];\n\n    var wc=wks.map(function(w,wi){\n      var ov  = r.wk.overall?.[w]?r.wk.overall[w][0]:0;\n      var rto = r.wk.rto?.[w]?r.wk.rto[w][0]:0;\n      var rvp = r.wk.rvp?.[w]?r.wk.rvp[w][0]:0;\n\n      // Color coding for sample size\n      function smpColor(n){\n        if(n===0)  return 'color:#3a4060';\n        if(n<100)  return 'color:#ef4444;font-weight:700';\n        if(n<200)  return 'color:#f5a623';\n        return 'color:#4ade80';\n      }\n      function smpFlag(n,prev){\n        if(!prev||prev===0||n===0) return '';\n        var drop=(prev-n)/prev*100;\n        return drop>=50?'\ud83d\udd34':'';\n      }\n\n      var ovF  = smpFlag(ov, prevOv);\n      var rtoF = smpFlag(rto,prevRto);\n      var rvpF = smpFlag(rvp,prevRvp);\n\n      // Track alerts for last week (wk23)\n      if(wi===wks.length-1){\n        if(ov<100 && ov>0)   alerts.push('Low sample: Ov='+ov);\n        if(rto<100 && rto>0) alerts.push('RTO='+rto+'<100');\n        if(rvp<100 && rvp>0) alerts.push('RVP='+rvp+'<100');\n        if(ovF==='\ud83d\udd34')  alerts.push('Ov dropped 50%+');\n        if(rtoF==='\ud83d\udd34') alerts.push('RTO dropped 50%+');\n        if(rvpF==='\ud83d\udd34') alerts.push('RVP dropped 50%+');\n      }\n\n      prevOv=ov; prevRto=rto; prevRvp=rvp;\n\n      return '<td style=\"padding:5px 8px\">'+\n        '<div style=\"font-size:10px;'+smpColor(ov)+'\">'+ovF+(ov||'\u2014')+'</div>'+\n        '<div style=\"font-size:10px;'+smpColor(rto)+';margin-top:1px\">'+rtoF+(rto||'\u2014')+'</div>'+\n        '<div style=\"font-size:10px;'+smpColor(rvp)+';margin-top:1px\">'+rvpF+(rvp||'\u2014')+'</div>'+\n      '</td>';\n    }).join('');\n\n    var alertCell='<td style=\"font-size:10px;max-width:180px\">';\n    if(alerts.length===0){\n      alertCell+='<span style=\"color:#22c55e\">\u2705 Normal</span>';\n    } else {\n      alertCell+=alerts.map(function(a){return '<div style=\"color:#ef4444\">\u26a0\ufe0f '+a+'</div>';}).join('');\n    }\n    alertCell+='</td>';\n\n    tbl+='<tr>'+\n      '<td style=\"font-size:11px;font-weight:600;position:sticky;left:0;background:#2a2f45;z-index:2;white-space:nowrap;padding:5px 8px\">'+r.rc+'</td>'+\n      '<td style=\"font-size:10px;color:#94a3b8;position:sticky;left:140px;background:#2a2f45;z-index:2;padding:5px 6px\">'+r.zone+'</td>'+\n      wc+alertCell+\n    '</tr>';\n  });\n  sb.innerHTML=tbl||'<tr><td colspan=\"12\" style=\"text-align:center;color:#94a3b8;padding:12px\">No data</td></tr>';\n}\n\n\nfunction renderTrendTable(){\n  const tb=document.getElementById('trendBody'); if(!tb) return;\n  const rows=DECLINING.slice(0,25).map(d=>{\n    const dc=d.drop>15?'drop-high':d.drop>7?'drop-med':'drop-low';\n    const di=d.drop>15?'\ud83d\udd34':d.drop>7?'\ud83d\udfe0':'\ud83d\udfe1';\n    const vals=Object.values(d.wk_vals).filter(v=>v!==null&&v!==undefined);\n    const mx=vals.length?Math.max(...vals):100, mn=vals.length?Math.min(...vals):0;\n    const sp=TREND_WKS.map(w=>{\n      const v=d.wk_vals[w]!==undefined?d.wk_vals[w]:d.wk_vals[String(w)];\n      if(v===undefined||v===null) return'<div class=\"spark-bar\" style=\"height:2px;background:#3a4060\"></div>';\n      const h=mx>mn?Math.max(2,Math.round((v-mn)/(mx-mn)*26)):14;\n      const c=v>=90?'#22c55e':v>=85?'#4ade80':v>=80?'#F8CA00':'#ef4444';\n      return`<div class=\"spark-bar\" title=\"Wk${w}:${v}%\" style=\"height:${h}px;background:${c}\"></div>`;\n    }).join('');\n    const tb2=d.type==='overall'?'<span style=\"color:#e2e8f0\">Overall</span>':d.type==='RTO'?'<span style=\"color:#4f8ef7\">RTO</span>':'<span style=\"color:#36d9a4\">RVP</span>';\n    return`<tr><td>${d.rc}</td><td>${d.zone}</td><td>${tb2}</td><td style=\"color:#4ade80;font-family:monospace\">${d.avg_early}%</td><td style=\"color:#ef4444;font-family:monospace\">${d.avg_late}%</td><td><span class=\"trend-badge ${dc}\">${di} -${d.drop}%</span></td><td><div class=\"mini-spark\">${sp}</div></td><td style=\"font-size:11px;color:#94a3b8;max-width:180px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis\" title=\"${d.top_reason}\">${d.top_reason.substring(0,50)}</td><td style=\"font-size:11px;color:#94a3b8\">${d.obs}</td></tr>`;\n  }).join('');\n  tb.innerHTML=rows||'<tr><td colspan=\"9\" style=\"text-align:center;color:#94a3b8;padding:16px\">No declining sites</td></tr>';\n}\n\nfunction renderReasonCharts(){\n  var BG='#2a2f45', GRID='rgba(255,255,255,0.05)', FONT='#94a3b8';\n  var labels=TREND_WKS.map(function(w){return 'Wk '+w;});\n\n  // \u2500\u2500 Use site-level filters if set \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n  var fSite  = document.getElementById('rSite').value;\n  var fMonth = document.getElementById('rMonth').value;\n  var fVert  = document.getElementById('rVert').value;\n  var fType  = document.getElementById('rType') ? document.getElementById('rType').value : '';\n  var zone   = document.getElementById('fZone').value;\n\n  var useReasons = TOP6_REASONS;\n  var useData    = CHART_DATA; // default: all sites global\n\n  // If site or zone filter applied, rebuild from REASON_DATA\n  if(fSite || zone){\n    var sites = REASON_DATA.slice();\n    if(fSite) sites = sites.filter(function(s){return s.rc===fSite;});\n    else if(zone) sites = sites.filter(function(s){\n      var r=RC_DATA.find(function(x){return x.rc===s.rc;}); return r&&r.zone===zone;\n    });\n\n    // Aggregate by reason per week\n    var wkR={};\n    TREND_WKS.forEach(function(w){wkR[w]={};});\n    sites.forEach(function(s){\n      s.d.forEach(function(e){\n        if(!TREND_WKS.includes(e.w)) return;\n        if(fVert && e.v!==fVert) return;\n        if(fType && e.t!==fType) return;\n        wkR[e.w][e.r]=(wkR[e.w][e.r]||0)+e.c;\n      });\n    });\n\n    // Get top 6 reasons across filtered data\n    var totals={};\n    TREND_WKS.forEach(function(w){\n      Object.entries(wkR[w]).forEach(function(kv){totals[kv[0]]=(totals[kv[0]]||0)+kv[1];});\n    });\n    useReasons = Object.entries(totals).sort(function(a,b){return b[1]-a[1];}).slice(0,6).map(function(e){return e[0];});\n    useData={};\n    useReasons.forEach(function(r){useData[r]=TREND_WKS.map(function(w){return wkR[w][r]||0;});});\n  }\n\n  // Chart title\n  var label = fSite?fSite:(zone?'Zone: '+zone:'All Sites');\n  var suffix = (fVert?' \u00b7 '+fVert:'')+(fType?' \u00b7 '+fType:'');\n  var c1title = document.querySelector('.chart-card h3');\n  if(c1title) c1title.innerHTML='Top 6 Failure Reasons \u2014 Weekly Count &nbsp;<span style=\"color:#94a3b8;font-weight:400;font-size:10px\">'+label+suffix+' \u00b7 Wk 17\u201323 \u00b7 excl. No Issue</span>';\n\n  // Legend\n  var lg=document.getElementById('chartLegend');\n  if(lg) lg.innerHTML=useReasons.map(function(r,i){\n    return '<span style=\"display:flex;align-items:center;gap:4px;font-size:10px\">'+\n      '<span style=\"width:10px;height:10px;border-radius:2px;background:'+REASON_COLORS[i%6]+';flex-shrink:0;display:inline-block\"></span>'+\n      r.substring(0,32)+(r.length>32?'\u2026':'')+\n    '</span>';\n  }).join('');\n\n  // \u2500\u2500 GROUPED BAR CHART with % labels \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n  var c1=document.getElementById('reasonTrendChart');\n  if(c1){\n    if(trendChart) trendChart.destroy();\n\n    // Pre-compute weekly totals for % calculation\n    var wkTotals=TREND_WKS.map(function(_,wi){\n      return useReasons.reduce(function(s,r){return s+((useData[r]||[])[wi]||0);},0);\n    });\n\n    trendChart=new Chart(c1,{\n      type:'bar',\n      data:{\n        labels:labels,\n        datasets:useReasons.map(function(r,i){\n          return {\n            label:r.substring(0,30),\n            data:useData[r]||TREND_WKS.map(function(){return 0;}),\n            backgroundColor:REASON_COLORS[i%6]+'cc',\n            borderColor:REASON_COLORS[i%6],\n            borderWidth:1,\n            borderRadius:3,\n          };\n        })\n      },\n      options:{\n        responsive:true, maintainAspectRatio:false,\n        plugins:{\n          legend:{display:false},\n          tooltip:{\n            callbacks:{\n              title:function(c){return 'Wk '+TREND_WKS[c[0].dataIndex];},\n              label:function(c){\n                var wi=c.dataIndex;\n                var tot=wkTotals[wi];\n                var p=tot>0?Math.round(c.raw/tot*1000)/10:0;\n                return '  '+c.dataset.label.substring(0,28)+': '+c.raw+' ('+p+'%)';\n              },\n              afterBody:function(c){\n                var wi=c[0].dataIndex;\n                return ['','Total failures: '+fmtN(wkTotals[wi])];\n              }\n            }\n          },\n          datalabels:{display:false}\n        },\n        scales:{\n          x:{ticks:{color:FONT,font:{size:11}},grid:{color:GRID}},\n          y:{ticks:{color:FONT,font:{size:10}},grid:{color:GRID},\n             title:{display:true,text:'Count',color:FONT,font:{size:10}}}\n        }\n      }\n    });\n  }\n\n  // \u2500\u2500 STACKED % CHART \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n  var c2=document.getElementById('reasonPctChart');\n  if(c2){\n    if(pctChart) pctChart.destroy();\n    var wkT2=TREND_WKS.map(function(_,wi){\n      return useReasons.reduce(function(s,r){return s+((useData[r]||[])[wi]||0);},0);\n    });\n    pctChart=new Chart(c2,{\n      type:'bar',\n      data:{\n        labels:labels,\n        datasets:useReasons.map(function(r,i){\n          return {\n            label:r.substring(0,30),\n            data:(useData[r]||[]).map(function(v,wi){return wkT2[wi]>0?Math.round(v/wkT2[wi]*1000)/10:0;}),\n            backgroundColor:REASON_COLORS[i%6]+'cc',\n            borderColor:REASON_COLORS[i%6],\n            borderWidth:0\n          };\n        })\n      },\n      options:{\n        responsive:true, maintainAspectRatio:false,\n        plugins:{\n          legend:{\n            display:true,\n            position:'bottom',\n            labels:{color:FONT,font:{size:10},boxWidth:10,padding:10,\n              generateLabels:function(chart){\n                return useReasons.map(function(r,i){\n                  return {text:r.length>35?r.substring(0,33)+'\u2026':r, fillStyle:REASON_COLORS[i%6], strokeStyle:REASON_COLORS[i%6], lineWidth:0, hidden:false, index:i};\n                });\n              }\n            }\n          },\n          tooltip:{\n            callbacks:{\n              title:function(c){return 'Wk '+TREND_WKS[c[0].dataIndex];},\n              label:function(c){return '  '+c.dataset.label.substring(0,28)+': '+c.raw+'%';}\n            }\n          }\n        },\n        scales:{\n          x:{stacked:true,ticks:{color:FONT,font:{size:11}},grid:{color:GRID}},\n          y:{stacked:true,min:0,max:100,\n             ticks:{callback:function(v){return v+'%';},color:FONT,font:{size:10}},\n             grid:{color:GRID},\n             title:{display:true,text:'% Contribution',color:FONT,font:{size:10}}}\n        }\n      }\n    });\n  }\n}\n\n\nwindow.onload=initDashboard;\n// Filter change handler\nfunction onFilterChange(id){\n  if(['fZone','fRC','fMonth','fWeek','fVert','fType'].indexOf(id)>=0){populateRC();render();}\n}\n\nfunction initDashboard(){\n  populateFilters();\n  render();\n  renderReasonTable();\n  renderReasonCharts();\n  renderSampleTable();\n}\nwindow.onload = initDashboard;\n\n\n\n\n\n</script>\n</body>\n</html>\n"

# ── MAIN ───────────────────────────────────────────────────────────────────────
def main():
    template = DASHBOARD_TEMPLATE

    with st.spinner("🔄 Loading data from Google Drive..."):
        raw_df = load_all_data()

    if raw_df is None:
        st.error("❌ Could not load data from Google Drive.")
        return

    with st.spinner("⚙️ Processing data..."):
        df = process_data(raw_df)

    if df is None or len(df)==0:
        st.error("❌ No valid data found.")
        return

    with st.spinner("📊 Building dashboard..."):
        js_data, total = build_js_data(df)

    # Inject data into template
    html = template.replace('DATABLOCK', js_data)

    # Update record count in header
    html = html.replace('>1,27,871<', '>'+f"{total:,}"+'<')

    # Render full-page dashboard
    components.html(html, height=4000, scrolling=True)

if __name__ == "__main__":
    main()
