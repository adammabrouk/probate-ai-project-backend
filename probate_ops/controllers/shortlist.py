from probate_ops.models.api import ChartFilters
from probate_ops.models.database import ProbateRecord
from probate_ops.utils.database import _apply_filters, chart_filters_dep
from fastapi import APIRouter, Depends, Query
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
def shortlist(
    f: Annotated[ChartFilters, Depends(chart_filters_dep)],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200)
    ):

    base = _apply_filters(ProbateRecord.select(), f)    
    ae = _absentee_expr()
    mailing = fn.concat_ws(
        Value(", "),
        ProbateRecord.party_address,
        ProbateRecord.party_city,
        ProbateRecord.party_state,
        ProbateRecord.party_zip,
    ).alias("mailing_address")

    total = base.count()

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
    ).paginate(page, page_size).dicts()

    # Meta
    total_pages = (total + page_size - 1) // page_size if page_size else 1
    meta = {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
    return {"shortlist": list(q), "meta": meta}
