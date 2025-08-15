from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
import pandas as pd
from ..utils.normalize import read_table, normalize
from ..tools.llm_score_tool import score_llm

router = APIRouter()


@router.post("/analyze")
async def analyze(file: UploadFile = File(...), max_records: int = 200):
    content = await file.read()
    df = normalize(read_table(content, file.filename)).head(max_records)
    scored = []
    for _, row in df.iterrows():
        rec = row.to_dict()
        rec.update(score_llm(rec))
        scored.append(rec)
    out = pd.DataFrame(scored)

    # charts
    tiers = out["tier"].value_counts().to_dict()
    counties = (
        out["county"].replace("", "Unknown").value_counts().head(10).to_dict()
    )
    petition_types = (
        out["petition_type"]
        .replace("", "Unknown")
        .value_counts()
        .head(8)
        .to_dict()
    )
    by_month = (
        out["petition_date"]
        .dropna()
        .dt.to_period("M")
        .astype(str)
        .value_counts()
        .sort_index()
    )
    charts = {
        "tiers": tiers,
        "top_counties": counties,
        "petition_types": petition_types,
        "by_month": [
            {"month": k, "count": int(v)} for k, v in by_month.items()
        ],
        "absentee_rate": (
            float((out["absentee_flag"] == True).mean()) if len(out) else 0.0
        ),
    }

    keep = [
        "county",
        "source_url",
        "case_no",
        "owner_name",
        "property_address",
        "city",
        "state",
        "zip",
        "party",
        "mailing_address",
        "petition_type",
        "petition_date",
        "death_date",
        "absentee_flag",
        "days_since_petition",
        "days_since_death",
        "holdings_in_file",
        "score",
        "tier",
        "rationale",
    ]
    for k in keep:
        if k not in out.columns:
            out[k] = ""
    for dc in ["petition_date", "death_date"]:
        out[dc] = (
            pd.to_datetime(out[dc], errors="coerce")
            .dt.strftime("%Y-%m-%d")
            .fillna("")
        )
    return JSONResponse(
        {
            "records": out[keep].fillna("").to_dict(orient="records"),
            "charts": charts,
            "sample_size": len(out),
        }
    )
