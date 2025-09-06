from probate_ops.models.api import ChartFilters
from probate_ops.models.database import ProbateRecord
from probate_ops.utils.database import _apply_filters, chart_filters_dep
from fastapi import APIRouter, Depends, Query, Request
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
    page_size: int = Query(25, ge=1, le=2000),
    sort: str = Query(None, description="Sort columns, e.g. 'score:desc,county:asc'")
    ):

    # Start with a select query
    base = ProbateRecord.select()
    base = _apply_filters(base, f)
    ae = _absentee_expr()
    mailing = fn.concat_ws(
        Value(", "),
        ProbateRecord.party_address,
        ProbateRecord.party_city,
        ProbateRecord.party_state,
        ProbateRecord.party_zip,
    ).alias("mailing_address")

    # --- Sorting ---
    if sort:
        order_by = []
        for part in sort.split(","):
            if not part.strip():
                continue
            col, *dir_part = part.split(":")
            direction = dir_part[0] if dir_part else "asc"
            col_map = {
                "score": ProbateRecord.score,
                "tier": ProbateRecord.tier,
                "county": ProbateRecord.county,
                "case_no": ProbateRecord.case_no,
                "owner_name": ProbateRecord.owner_name,
                "property_address": ProbateRecord.property_address,
                "city": ProbateRecord.city,
                "property_value_2025": ProbateRecord.property_value,
                "property_value": ProbateRecord.property_value,
                "petition_date": ProbateRecord.petition_date,
                # Note: absentee_flag is not a real column, skip for sorting
                "parcel_number": ProbateRecord.parcel_number,
                "qpublic_report_url": ProbateRecord.qpublic_report_url,
                "rationale": ProbateRecord.rationale,
            }
            field = col_map.get(col)
            if field is not None:
                if direction == "desc":
                    order_by.append(field.desc())
                else:
                    order_by.append(field.asc())
        if order_by:
            base = base.order_by(*order_by)

    total = base.count()

    q = base.paginate(page, page_size).dicts()

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
    # Compose output dicts with aliases
    result = []
    for row in q:
        row["property_value_2025"] = row.get("property_value")
        row["absentee_flag"] = bool(ae)
        result.append(row)
    return {"shortlist": result, "meta": meta}
