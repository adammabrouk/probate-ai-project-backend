from probate_ops.models.database import ProbateRecord
from fastapi import APIRouter
from peewee import fn, Value

router = APIRouter()

def _absentee_expr():
    return (
        (ProbateRecord.zip.is_null(False))
        & (ProbateRecord.party_zip.is_null(False))
        & (ProbateRecord.zip != ProbateRecord.party_zip)
    )

@router.get("/shortlist")
def shortlist():
    ae = _absentee_expr()
    mailing = fn.concat_ws(
        Value(", "),
        ProbateRecord.party_address,
        ProbateRecord.party_city,
        ProbateRecord.party_state,
        ProbateRecord.party_zip,
    ).alias("mailing_address")

    q = ProbateRecord.select(
            ProbateRecord.score,
            ProbateRecord.tier,
            ProbateRecord.county,
            ProbateRecord.case_no,
            ProbateRecord.owner_name,
            ProbateRecord.property_address,
            ProbateRecord.city,
            ProbateRecord.property_value.alias("property_value_2025"),
            fn.to_char(ProbateRecord.petition_date, Value("YYYY-MM-DD")).alias("petition_date"),
            ae.alias("absentee_flag"),
            ProbateRecord.parcel_number,
            ProbateRecord.qpublic_report_url,
            ProbateRecord.rationale,
            ProbateRecord.source_url,
            ProbateRecord.state,
            ProbateRecord.zip,
            ProbateRecord.party,
            mailing,
            ProbateRecord.petition_type,
            fn.to_char(ProbateRecord.death_date, Value("YYYY-MM-DD")).alias("death_date"),
        ).dicts()

    return {"shortlist": list(q)}