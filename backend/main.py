from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
import requests
import io
import os
from typing import Optional
from pdf_generator import generate_pdf
from docx_generator import generate_docx
from pydantic import BaseModel

app = FastAPI(title="MedElite Facility Report Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CMS_BASE = "https://data.cms.gov/provider-data/api/1/datastore/query"

# CMS PDC dataset IDs. Each key has a list of IDs to try in order.
# CMS occasionally retires and replaces dataset resource IDs, so the extras
# are known alternates that have worked in the past.
# Verified against NH Data Dictionary (February 2026):
#   provider_info  -> NH_ProviderInfo
#   claims_qm      -> NH_QualityMsr_Claims  (fields: cms_certification_number_ccn, measure_description, resident_type, adjusted_score)
#   state_averages -> NH_StateUSAverages    (fields: state_or_nation, percentage_of_short_stay...)
DATASETS = {
    "provider_info":  ["v22b-55vb", "4pq5-n9py"],
    "claims_qm":      ["ijh5-nb2v", "cbce-6mv8", "mq3g-4f8z", "ynj2-r877"],
    "state_averages": ["xcdc-v8bm", "axe5-jnby", "xcdc-v9qx", "s2uc-8wxp"],
}

CMS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://data.cms.gov/",
}


def cms_fetch(dataset_key: str, conditions: list = None, limit: int = 500):
    """Try each dataset ID in order until one returns a 200. Raise 502 if all fail."""
    ids = DATASETS[dataset_key]
    params = {"limit": limit}
    if conditions:
        for i, c in enumerate(conditions):
            for k, v in c.items():
                params[f"conditions[{i}][{k}]"] = v

    last_error = None
    for dataset_id in ids:
        url = f"{CMS_BASE}/{dataset_id}/0"
        try:
            r = requests.get(url, params=params, headers=CMS_HEADERS, timeout=25)
            if r.status_code == 200:
                return r.json(), dataset_id
            last_error = f"HTTP {r.status_code} on {dataset_id}"
        except requests.Timeout:
            last_error = f"Timeout on {dataset_id}"
        except Exception as e:
            last_error = str(e)

    raise HTTPException(
        status_code=502,
        detail=f"CMS API unavailable for {dataset_key}. Last error: {last_error}"
    )


def get_rows(response: dict) -> list:
    return response.get("results") or response.get("data") or []


def is_dict_format(row: dict) -> bool:
    # The NH_QualityMsr_Claims CSV uses cms_certification_number_ccn and measure_description.
    # An older Care Compare display dataset used facility_id and measure_name instead.
    # This check tells us which format we got so we can read the right fields.
    return "cms_certification_number_ccn" in row or "measure_description" in row


@app.get("/api/facility/{ccn}")
def get_facility(ccn: str):
    ccn = ccn.strip().lstrip("0")
    if not ccn.isdigit():
        raise HTTPException(status_code=400, detail="CCN must be numeric (e.g. 686123)")
    ccn = ccn.zfill(6)

    # Pull facility name, address, star ratings, and bed count
    pinfo, _ = cms_fetch("provider_info", conditions=[
        {"property": "cms_certification_number_ccn", "value": ccn, "operator": "="}
    ])
    rows = get_rows(pinfo)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No facility found for CCN {ccn}. Please double-check the number."
        )
    p = rows[0]
    state = (p.get("state") or "").strip().upper()

    # Pull the 4 claims-based quality measures for this facility.
    # STR = Short Stay, LT = Long Stay (per NH Data Dictionary Table 12).
    # We filter by CCN after fetching since some API versions don't support server-side CCN filtering.
    hosp_data = {}
    try:
        claims_resp, _ = cms_fetch("claims_qm", conditions=[
            {"property": "cms_certification_number_ccn", "value": ccn, "operator": "="}
        ])
        facility_claims = get_rows(claims_resp)

        if facility_claims and not is_dict_format(facility_claims[0]):
            # Older Care Compare format uses measure_name and score
            for row in facility_claims:
                name  = (row.get("measure_name") or "").lower()
                score = row.get("score") or ""
                if ("re-hospitalized" in name or "rehospitalized" in name) and "short" in name:
                    hosp_data["str_hosp"] = score
                elif "emergency department" in name and "short" in name:
                    hosp_data["str_ed"] = score
                elif "hospitalizations per 1,000" in name or "hospitalizations per 1000" in name:
                    hosp_data["lt_hosp"] = score
                elif "emergency department" in name and ("per 1,000" in name or "per 1000" in name):
                    hosp_data["lt_ed"] = score
        else:
            # Standard dictionary format uses measure_description and resident_type
            for row in facility_claims:
                desc  = (row.get("measure_description") or "").lower()
                rtype = (row.get("resident_type") or "").lower()
                score = row.get("adjusted_score") or row.get("observed_score") or ""
                if "rehospitalized" in desc and "short" in rtype:
                    hosp_data["str_hosp"] = score
                elif "emergency department" in desc and "short" in rtype and "per 1000" not in desc:
                    hosp_data["str_ed"] = score
                elif "hospitalizations per 1000" in desc and "long" in rtype:
                    hosp_data["lt_hosp"] = score
                elif "emergency department" in desc and "per 1000" in desc and "long" in rtype:
                    hosp_data["lt_ed"] = score

    except HTTPException:
        # CCN filter returned 400/404 - fetch all rows and filter in Python instead
        try:
            claims_resp, _ = cms_fetch("claims_qm", limit=500)
            all_claims = get_rows(claims_resp)

            if all_claims and is_dict_format(all_claims[0]):
                facility_claims = [
                    r for r in all_claims
                    if str(r.get("cms_certification_number_ccn", "")).zfill(6) == ccn
                ]
                for row in facility_claims:
                    desc  = (row.get("measure_description") or "").lower()
                    rtype = (row.get("resident_type") or "").lower()
                    score = row.get("adjusted_score") or row.get("observed_score") or ""
                    if "rehospitalized" in desc and "short" in rtype:
                        hosp_data["str_hosp"] = score
                    elif "emergency department" in desc and "short" in rtype and "per 1000" not in desc:
                        hosp_data["str_ed"] = score
                    elif "hospitalizations per 1000" in desc and "long" in rtype:
                        hosp_data["lt_hosp"] = score
                    elif "emergency department" in desc and "per 1000" in desc and "long" in rtype:
                        hosp_data["lt_ed"] = score
            else:
                facility_claims = [
                    r for r in all_claims
                    if str(r.get("facility_id", "")).zfill(6) == ccn
                ]
                for row in facility_claims:
                    name  = (row.get("measure_name") or "").lower()
                    score = row.get("score") or ""
                    if ("re-hospitalized" in name or "rehospitalized" in name) and "short" in name:
                        hosp_data["str_hosp"] = score
                    elif "emergency department" in name and "short" in name:
                        hosp_data["str_ed"] = score
                    elif "hospitalizations per 1,000" in name or "hospitalizations per 1000" in name:
                        hosp_data["lt_hosp"] = score
                    elif "emergency department" in name and ("per 1,000" in name or "per 1000" in name):
                        hosp_data["lt_ed"] = score
        except HTTPException:
            pass

    # State and national averages for benchmark comparisons.
    # Only ~57 rows total (one per state/territory + NATION) so fetching all is fast.
    state_avg = {}
    nat_avg = {}
    try:
        savg_resp, _ = cms_fetch("state_averages", limit=65)
        for row in get_rows(savg_resp):
            row_geo = (
                row.get("state_or_nation") or row.get("state") or ""
            ).strip().upper()
            if row_geo == state and not state_avg:
                state_avg = row
            if row_geo in ("NATION", "US", "UNITED STATES") and not nat_avg:
                nat_avg = row
            if state_avg and nat_avg:
                break
    except HTTPException:
        pass

    def fmt_pct(v):
        if v is None or v == "":
            return ""
        try:
            return f"{float(v):.1f}%"
        except Exception:
            return str(v)

    def fmt_rate(v):
        if v is None or v == "":
            return ""
        try:
            return f"{float(v):.2f}"
        except Exception:
            return str(v)

    # These field names are truncated by the CMS API - confirmed from live debug output.
    # The NH Data Dictionary shows the full names; the API cuts them and adds a hash suffix.
    STR_HOSP_KEY = "percentage_of_short_stay_residents_who_were_rehospitalized__1d02"
    STR_ED_KEY   = "percentage_of_short_stay_residents_who_had_an_outpatient_em_d911"
    LT_HOSP_KEY  = "number_of_hospitalizations_per_1000_longstay_resident_days"
    LT_ED_KEY    = "number_of_outpatient_emergency_department_visits_per_1000_l_de9d"

    return {
        "ccn":    ccn,
        "name":   p.get("provider_name") or "",
        "address": p.get("provider_address") or "",
        "city":   p.get("citytown") or p.get("city_town") or "",
        "state":  state,
        "zip":    str(p.get("zip_code") or ""),
        "certified_beds":           str(p.get("number_of_certified_beds") or ""),
        "overall_rating":           str(p.get("overall_rating") or ""),
        "health_inspection_rating": str(p.get("health_inspection_rating") or ""),
        "staffing_rating":          str(p.get("staffing_rating") or ""),
        "qm_rating":                str(p.get("qm_rating") or ""),
        "str_hosp":       fmt_pct(hosp_data.get("str_hosp")),
        "str_hosp_nat":   fmt_pct(nat_avg.get(STR_HOSP_KEY)),
        "str_hosp_state": fmt_pct(state_avg.get(STR_HOSP_KEY)),
        "str_ed":         fmt_pct(hosp_data.get("str_ed")),
        "str_ed_nat":     fmt_pct(nat_avg.get(STR_ED_KEY)),
        "str_ed_state":   fmt_pct(state_avg.get(STR_ED_KEY)),
        "lt_hosp":        fmt_rate(hosp_data.get("lt_hosp")),
        "lt_hosp_nat":    fmt_rate(nat_avg.get(LT_HOSP_KEY)),
        "lt_hosp_state":  fmt_rate(state_avg.get(LT_HOSP_KEY)),
        "lt_ed":          fmt_rate(hosp_data.get("lt_ed")),
        "lt_ed_nat":      fmt_rate(nat_avg.get(LT_ED_KEY)),
        "lt_ed_state":    fmt_rate(state_avg.get(LT_ED_KEY)),
    }


class ReportRequest(BaseModel):
    ccn: str
    name: str
    name_override: Optional[str] = ""
    address: str
    city: str
    state: str
    zip: str
    emr: Optional[str] = ""
    certified_beds: Optional[str] = ""
    current_census: Optional[str] = ""
    patient_type: Optional[str] = ""
    prev_coverage: Optional[str] = ""
    prev_performance: Optional[str] = ""
    medical_coverage: Optional[str] = ""
    overall_rating: Optional[str] = ""
    health_inspection_rating: Optional[str] = ""
    staffing_rating: Optional[str] = ""
    qm_rating: Optional[str] = ""
    str_hosp: Optional[str] = ""
    str_hosp_nat: Optional[str] = ""
    str_hosp_state: Optional[str] = ""
    str_ed: Optional[str] = ""
    str_ed_nat: Optional[str] = ""
    str_ed_state: Optional[str] = ""
    lt_hosp: Optional[str] = ""
    lt_hosp_nat: Optional[str] = ""
    lt_hosp_state: Optional[str] = ""
    lt_ed: Optional[str] = ""
    lt_ed_nat: Optional[str] = ""
    lt_ed_state: Optional[str] = ""


@app.post("/api/report/pdf")
def download_pdf(req: ReportRequest):
    buf = io.BytesIO()
    generate_pdf(req.model_dump(), buf)
    buf.seek(0)
    safe_name = (req.name_override or req.name or "facility").replace(" ", "_")[:60]
    filename = f"MedElite_Assessment_{safe_name}_{req.ccn}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/report/docx")
def download_docx(req: ReportRequest):
    buf = io.BytesIO()
    generate_docx(req.model_dump(), buf)
    buf.seek(0)
    safe_name = (req.name_override or req.name or "facility").replace(" ", "_")[:60]
    filename = f"MedElite_Assessment_{safe_name}_{req.ccn}.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/debug/{ccn}")
def debug_facility(ccn: str):
    """Returns raw CMS API responses - useful for checking field names when CMS updates datasets."""
    ccn = ccn.strip().zfill(6)
    result = {"ccn": ccn}

    try:
        pinfo, pid = cms_fetch("provider_info", conditions=[
            {"property": "cms_certification_number_ccn", "value": ccn, "operator": "="}
        ])
        rows = get_rows(pinfo)
        result["provider_info_dataset_id"] = pid
        result["provider_info_row_count"] = len(rows)
        result["provider_info_fields"] = list(rows[0].keys()) if rows else []
    except Exception as e:
        result["provider_info_error"] = str(e)

    try:
        claims, cid = cms_fetch("claims_qm", conditions=[
            {"property": "cms_certification_number_ccn", "value": ccn, "operator": "="}
        ])
        facility_rows = get_rows(claims)
        result["claims_qm_dataset_id"] = cid
        result["claims_qm_facility_row_count"] = len(facility_rows)
        result["claims_qm_sample_fields"] = list(facility_rows[0].keys()) if facility_rows else []
        result["claims_qm_facility_rows"] = facility_rows[:5]
        result["claims_qm_format"] = "dictionary" if (facility_rows and is_dict_format(facility_rows[0])) else "care_compare"
    except Exception as e:
        result["claims_qm_with_filter_error"] = str(e)
        try:
            claims2, cid2 = cms_fetch("claims_qm", limit=5)
            all_rows = get_rows(claims2)
            result["claims_qm_no_filter_dataset_id"] = cid2
            result["claims_qm_no_filter_sample_fields"] = list(all_rows[0].keys()) if all_rows else []
            result["claims_qm_format"] = "dictionary" if (all_rows and is_dict_format(all_rows[0])) else "care_compare"
        except Exception as e2:
            result["claims_qm_no_filter_error"] = str(e2)

    try:
        savg, sid = cms_fetch("state_averages", limit=65)
        rows = get_rows(savg)
        result["state_avg_dataset_id"] = sid
        result["state_avg_total_rows"] = len(rows)
        result["state_avg_sample_fields"] = list(rows[0].keys()) if rows else []
        result["state_avg_has_state_or_nation"] = "state_or_nation" in (rows[0] if rows else {})
        hosp_key = "percentage_of_short_stay_residents_who_were_rehospitalized__1d02"
        result["state_avg_has_hosp_benchmark"] = hosp_key in (rows[0] if rows else {})
        for row in rows:
            geo = (row.get("state_or_nation") or row.get("state") or "").upper()
            if geo in ("NATION", "US"):
                result["state_avg_nation_row_keys"] = list(row.keys())
                result["state_avg_has_nation_row"] = True
                break
        else:
            result["state_avg_has_nation_row"] = False
    except Exception as e:
        result["state_avg_error"] = str(e)

    return result


@app.get("/health")
def health():
    return {"status": "ok", "service": "MedElite Facility Report Generator"}


# Frontend is mounted last so all /api/* routes are matched first
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
