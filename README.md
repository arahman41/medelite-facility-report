# MedElite Facility Assessment Report Generator

A web app built for the MedElite Product Strategy and AI team. A director types a facility's CCN, the app pulls live data from the CMS Provider Data Catalog, they fill in a few internal fields, and download a PDF. No spreadsheets, no copy-paste, no manual formatting.

---

## Live Demo

**App URL:** `https://medelite-facility-report.onrender.com`  
**GitHub:** `https://github.com/arahman41/medelite-facility-report`  
**Test CCN:** `686123` (Kendall Lakes Healthcare and Rehab Center, Miami FL)

---

## What it does

**Core (required)**

- Enter any valid CCN to fetch live facility data from CMS
- Pulls location, all four star ratings, and certified bed count from the CMS Provider Data Catalog API
- Optional name override field: replaces the CMS legal name on the output without touching the INFINITE branding
- Manual input fields for EMR, current census, patient type, Medelite coverage history, and medical coverage
- One button downloads a PDF with the correct INFINITE/MEDELITE header and a clickable Medicare Care Compare link
- Live preview updates as you type, so you see what you are getting before downloading

**Bonus (all four implemented)**

- All 12 hospitalization and ED visit metrics from the CMS Claims-Based Quality Measures dataset, with state and national benchmarks
- Color-coded above/below-national-average labels on each hospitalization metric
- Summary metric cards at the top of the preview for quick visual comparison
- Word document export (.docx) for cases where the director wants to edit the output before sharing

---

## Data mapping

| Report field | Source | CMS field |
|---|---|---|
| Name of Facility | CMS API + name override | `provider_name` |
| Location | CMS API | `provider_address`, `city_town`, `state`, `zip_code` |
| EMR | Manual input | text field |
| Census Capacity | CMS API | `number_of_certified_beds` |
| Current Census | Manual input | numeric field |
| Type of Patient | Manual input | text field |
| Previous Coverage from Medelite | Manual input | Yes/No dropdown |
| Previous Provider Performance | Manual input | text field |
| Medical Coverage | Manual input | text field |
| Overall Star Rating | CMS API | `overall_rating` |
| Health Inspection | CMS API | `health_inspection_rating` |
| Staffing | CMS API | `staffing_rating` |
| Quality of Resident Care | CMS API | `qm_rating` |
| Short Term Hospitalization | CMS Claims QMs | short-stay rehospitalization rate |
| STR National/State Avg. | CMS State Averages | `percentage_of_short_stay_residents_who_were_rehospitalized_after_a_nursing_home_admission` |
| STR ED Visit | CMS Claims QMs | short-stay ED visit rate |
| STR ED National/State Avg. | CMS State Averages | `percentage_of_short_stay_residents_who_had_an_outpatient_emergency_department_visit` |
| LT Hospitalization | CMS Claims QMs | long-stay hospitalizations per 1000 resident days |
| LT National/State Avg. | CMS State Averages | `number_of_hospitalizations_per_1000_long_stay_resident_days` |
| ED Visit (LT) | CMS Claims QMs | long-stay ED visits per 1000 resident days |
| LT ED National/State Avg. | CMS State Averages | `number_of_outpatient_emergency_department_visits_per_1000_long_stay_resident_days` |

**Dataset IDs**

| Dataset | Primary ID | Fallback ID |
|---|---|---|
| Provider Information | `v22b-55vb` | `4pq5-n9py` |
| Medicare Claims Quality Measures | `ijh5-nb2v` | `cbce-6mv8` |
| State and US Averages | `xcdc-v8bm` | `axe5-jnby` |

The app tries the primary ID first and falls back automatically if CMS retires it. All IDs were verified against the live API during development.

---

## Project structure

```
medelite-facility-report/
├── backend/
│   ├── main.py            # FastAPI app, API routes, static file serving
│   ├── pdf_generator.py   # ReportLab PDF builder
│   ├── docx_generator.py  # python-docx Word export
│   └── requirements.txt
├── frontend/
│   └── index.html         # single HTML file, no build step
├── render.yaml            # Render deployment config
└── README.md
```

**Stack**

- Backend: Python 3.11, FastAPI, Uvicorn
- PDF: ReportLab (programmatic layout, not template-based)
- Word export: python-docx
- Frontend: plain HTML/CSS/JS, no framework
- Hosting: Render free tier
- Data: CMS Provider Data Catalog public API, no key required

---

## Running locally

```bash
git clone https://github.com/arahman41/medelite-facility-report
cd medelite-facility-report

pip install -r backend/requirements.txt

cd backend
uvicorn main:app --reload --port 8000
# open http://localhost:8000
```

---

## Engineering decisions

**Why ReportLab instead of WeasyPrint or pdfkit?**  
I needed pixel-level control over the layout to match the reference document exactly. WeasyPrint works fine for HTML-to-PDF but fights you when you need precise table cell padding and programmatic color logic. ReportLab lets you place every element exactly where you want it. I had also already used it in a previous project (InternTrack) so I knew how to handle the edge cases.

**Why a single HTML file for the frontend?**  
The brief called this a "micro-app." Adding React means a build step, Node.js, npm, and a separate deployment pipeline for a form with two buttons. The single file is served directly by FastAPI and works fine. It also makes the code walkthrough easier since everything is visible in one place.

**Why proxy the CMS API through the backend instead of calling it from the browser?**  
The CMS API blocks direct browser requests because of CORS policy. The FastAPI server makes the request server-side, where CORS does not apply, and returns the result to the browser.

**What happens if CMS changes a dataset resource ID?**  
The `DATASETS` dict in `main.py` has fallback IDs for each dataset. If the primary ID returns an error, the code tries the next one before giving up. Most apps would just break. Updating the list takes about thirty seconds.

**What if claims data is missing for a CCN?**  
Some facilities have too few residents to meet CMS reporting thresholds. If the claims quality measures API returns nothing for a CCN, the hospitalization section is skipped entirely. The star ratings and facility info still show up correctly.

**CCN formatting**  
CMS CCNs are stored as 6-character strings. The input field accepts formats like `686123`, `"686123"`, or `0686123` and normalizes them before querying.

---

## Test case

Input CCN `686123`. The values below are from the original case materials (an older CMS snapshot). The live app pulls current data, so numbers will differ. CMS refreshes quarterly. That's expected and correct behavior.

| Field | Reference value (case materials) |
|---|---|
| Name | Kendall Lakes Healthcare and Rehab Center |
| Location | 5280 SW 157th Ave, Miami, FL |
| Census Capacity | 120 |
| Overall Star Rating | 1 |
| Health Inspection | 1 |
| Staffing | 2 |
| Quality of Resident Care | 4 |
| STR Hospitalization | 18.7% |
| STR National Avg. | 21.5% |
| STR State Avg. | 23.8% |
| STR ED Visit | 13.9% |
| LT Hospitalization | 1.86 |
| LT ED Visit | 6.94 |
