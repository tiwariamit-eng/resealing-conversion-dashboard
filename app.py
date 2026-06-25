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

def process_data(df):
    # Rename columns
    cm = {'RC Name':'rc','Zone':'zone','Week':'week','Result':'result',
          'RTO / RVP':'type','RTO / RVP Status':'type',
          'QA remark':'reason','Vertical 1':'vert'}
    df = df.rename(columns={k:v for k,v in cm.items() if k in df.columns})
    if 'result' not in df.columns: return None

    df['result'] = df['result'].fillna('').astype(str).str.strip().str.lower()
    df = df[df['result'].isin(['pass','fail'])].copy()
    df['pass'] = df['result']=='pass'

    if 'type' in df.columns:
        df['type'] = df['type'].fillna('RTO').astype(str).str.strip().str.upper().str[:3]
        df['type'] = df['type'].where(df['type'].isin(['RTO','RVP']),'RTO')
    else:
        df['type'] = 'RTO'

    df['week'] = pd.to_numeric(df.get('week',0), errors='coerce').fillna(0).astype(int)
    df = df[df['week']>0]

    df['rc']   = df['rc'].fillna('').astype(str).str.strip().map(lambda x: REV.get(x,x))
    df['zone'] = df['zone'].fillna('').astype(str).str.strip()
    df['vert'] = df.get('vert', pd.Series(['Electronics']*len(df))).fillna('Electronics').astype(str).str.strip()
    df['vert'] = df['vert'].str.replace(r'^RTO[_ ]+','',regex=True).str.replace(r'^RVP[_ ]+','',regex=True).str.strip()
    df['reason'] = df.get('reason', pd.Series(['']*len(df))).fillna('').astype(str).str.strip()
    df.loc[df['reason'].str.lower().isin(['no issue','no issue.','']), 'reason'] = ''
    df['month'] = df['week'].map(wk2m)

    return df[df['rc']!=''].reset_index(drop=True)

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

# ── MAIN ───────────────────────────────────────────────────────────────────────
def main():
    # Load HTML template
    try:
        template = open('/app/dashboard_template.html').read()
    except:
        try:
            template = open('dashboard_template.html').read()
        except Exception as e:
            st.error(f"Template not found: {e}")
            return

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
