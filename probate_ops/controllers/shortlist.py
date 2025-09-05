from probate_ops.models.api import ChartFilters
from probate_ops.models.database import ProbateRecord
from probate_ops.utils.database import _apply_filters, chart_filters_dep
from fastapi import APIRouter, Depends
from peewee import fn, Value
from typing_extensions import Annotated

router = APIRouter()


def _absentee_expr():
    return (
        (ProbateRecord.zip.is_null(False))
        & (ProbateRecord.party_zip.is_null(False))
        & (ProbateRecord.zip != ProbateRecord.party_zip)
    )


@router.get("/shortlist")
def shortlist(f: Annotated[ChartFilters, Depends(chart_filters_dep)]):
    base = _apply_filters(ProbateRecord.select(), f)    
    ae = _absentee_expr()
    mailing = fn.concat_ws(
        Value(", "),
        ProbateRecord.party_address,
        ProbateRecord.party_city,
        ProbateRecord.party_state,
        ProbateRecord.party_zip,
    ).alias("mailing_address")

    q = base.select(
        ProbateRecord.score,
        ProbateRecord.tier,
        ProbateRecord.county,
        ProbateRecord.case_no,
        ProbateRecord.owner_name,
        ProbateRecord.property_address,
        ProbateRecord.city,
        ProbateRecord.property_value.alias("property_value_2025"),
        fn.to_char(ProbateRecord.petition_date, Value("YYYY-MM-DD")).alias(
            "petition_date"
        ),
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
        fn.to_char(ProbateRecord.death_date, Value("YYYY-MM-DD")).alias(
            "death_date"
        ),
    ).dicts()

    return {"shortlist": list(q)}
