# 📦 Flipkart RTO/RVP Resealing Dashboard

Live 24/7 dashboard — Streamlit + Google Drive + GitHub

---

## ⚡ Quick Deploy (15 minutes)

### STEP 1 — Upload this code to GitHub

1. Go to [github.com](https://github.com) → Sign in (or create free account)
2. Click **New repository** → Name it `flipkart-dashboard`
3. Set to **Private** (recommended) → Click **Create repository**
4. Upload all these files:
   - `app.py`
   - `requirements.txt`
   - `.streamlit/config.toml`
   - `.gitignore`
   > ⚠️ Do NOT upload `secrets.toml` — keep it private

---

### STEP 2 — Create Google Service Account

This is how the app reads your Google Drive files securely.

1. Go to → https://console.cloud.google.com
2. Click **Select a project** → **New Project** → Name: `flipkart-dashboard` → **Create**
3. In the left menu → **APIs & Services** → **Enable APIs and Services**
4. Search **"Google Drive API"** → Click it → **Enable**
5. Go to **APIs & Services** → **Credentials** → **Create Credentials** → **Service Account**
6. Fill:
   - Name: `flipkart-dashboard-sa`
   - Click **Create and Continue** → **Done**
7. Click the service account you just created
8. Go to **Keys** tab → **Add Key** → **Create new key** → **JSON** → **Create**
9. A JSON file downloads — **keep this safe, do not share**

---

### STEP 3 — Share your Google Drive folder with the Service Account

1. Open the downloaded JSON file
2. Find the line: `"client_email": "flipkart-dashboard-sa@YOUR-PROJECT.iam.gserviceaccount.com"`
3. Copy that email address
4. Go to **Google Drive** → Find your **"Resealing Conversion"** folder
5. Right-click → **Share** → Paste the service account email → Set to **Viewer** → **Send**

✅ The app can now read your CSV files!

---

### STEP 4 — Deploy on Streamlit Cloud (Free)

1. Go to → https://streamlit.io/cloud → **Sign in with GitHub**
2. Click **New app**
3. Select your repository: `flipkart-dashboard`
4. Main file path: `app.py`
5. Click **Advanced settings** → **Secrets**
6. Paste this (replace with values from your JSON file):

```toml
[gcp_service_account]
type = "service_account"
project_id = "YOUR_PROJECT_ID"
private_key_id = "YOUR_PRIVATE_KEY_ID"
private_key = "-----BEGIN RSA PRIVATE KEY-----\nPASTE_YOUR_KEY_HERE\n-----END RSA PRIVATE KEY-----\n"
client_email = "flipkart-dashboard-sa@YOUR_PROJECT.iam.gserviceaccount.com"
client_id = "YOUR_CLIENT_ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "YOUR_CERT_URL"
```

7. Click **Deploy!**

In ~2 minutes your dashboard is live at:
`https://YOUR-APP-NAME.streamlit.app`

---

### STEP 5 — Keep it awake 24/7 (Free with UptimeRobot)

Streamlit free tier sleeps after 7 days of no visits. Fix this in 2 minutes:

1. Go to → https://uptimerobot.com → Create free account
2. Click **Add New Monitor**
3. Monitor Type: **HTTP(s)**
4. Friendly Name: `Flipkart Dashboard`
5. URL: `https://YOUR-APP-NAME.streamlit.app`
6. Monitoring Interval: **5 minutes**
7. Click **Create Monitor**

✅ Dashboard now stays awake 24/7 — UptimeRobot pings it every 5 minutes for free!

---

## 🔄 Adding New Weekly Data

Just drop new CSV files into your **"Resealing Conversion"** Google Drive folder.

- Same column format required:
  `Timestamp, RC Name, Type, Scan WSN, Vertical, Brand Name, FSN, FSP, RC QC Remarks, Final Bulk Movement, Week, Zone, RTO / RVP, Result, QA remark, Resealing, Vertical 1`

- The dashboard **auto-detects and loads new files** on next refresh (every 5 minutes)
- You can also use the **"Upload new weekly CSV"** button in the sidebar for instant loading

---

## 👥 Sharing with your team

Once deployed, share the URL:
`https://YOUR-APP-NAME.streamlit.app`

- Anyone with the link can view the dashboard
- No login required (public URL)
- To restrict access: In Streamlit Cloud → App settings → **Viewers** → add specific email addresses

---

## 📊 Dashboard Features

| Feature | Details |
|---|---|
| **Filters** | Zone, RC/Site, Week, Vertical, RTO/RVP |
| **KPI Cards** | Total records, Pass, Fail, Pass %, Sites, Weeks |
| **Zone tiles** | Pass rate per zone with color coding |
| **Week trend** | Pass % + volume combined chart |
| **RTO vs RVP** | Donut chart + pass rate comparison |
| **Vertical breakdown** | Electronics vs Mobile pass rates |
| **Fail reasons** | Top 8 fail reasons ranked |
| **RC × Week heatmap** | Site performance across weeks |
| **Site table** | All RCs with pass %, RTO, RVP counts |
| **Upload button** | Add new CSVs instantly via sidebar |
| **Auto-refresh** | Every 5 minutes, no manual action needed |

---

## 🆘 Troubleshooting

**"No data loaded"**
→ Check that you shared the Google Drive folder with the service account email

**"API error 403"**
→ Google Drive API is not enabled. Go to Cloud Console → APIs → Enable Drive API

**App is sleeping / shows "Zzz"**
→ Set up UptimeRobot (Step 5 above)

**Data not updating**
→ Click "Refresh Now" in sidebar, or wait 5 minutes for auto-refresh

**New CSV not showing**
→ Make sure the file is in the correct Drive folder and has the correct column names

---

## 📁 File Structure

```
flipkart-dashboard/
├── app.py                          ← Main dashboard (edit this)
├── requirements.txt                ← Python packages
├── .gitignore                      ← Protects secrets from GitHub
├── .streamlit/
│   ├── config.toml                 ← Dark theme + server settings
│   └── secrets.toml.template       ← Secret template (DO NOT upload actual secrets)
└── README.md                       ← This file
```

---

*Built for Flipkart RTO/RVP Resealing quality tracking · 2026*
