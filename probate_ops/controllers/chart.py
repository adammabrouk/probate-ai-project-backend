from probate_ops.models.database import ProbateRecord
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query
from typing import List
from datetime import date
from peewee import fn, Case, SQL, Value
from typing_extensions import Annotated
from typing import Union, Optional
from peewee import fn, Case, Value, SQL
import peewee
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/charts", tags=["Charts"])

class ChartFilters(BaseModel):
    counties: Optional[List[str]] = Query(None)      
    petition_types: Optional[List[str]] = Query(None)
    tiers: Optional[List[str]] = Query(None)         
    absentee_only: Optional[bool] = Query(None)      
    has_parcel: Optional[bool] = Query(None)         
    has_qpublic: Optional[bool] = Query(None)        
    min_value: Optional[float] = Query(None)         
    max_value: Optional[float] = Query(None)         
    month_from: Optional[str] = Query(None)          
    month_to: Optional[str] = Query(None)

def chart_filters_dep(
    counties:       Annotated[Optional[List[str]], Query()] = None,
    petition_types: Annotated[Optional[List[str]], Query()] = None,
    tiers:          Annotated[Optional[List[str]], Query()] = None,
    absentee_only:  Annotated[Optional[bool],      Query()] = None,
    has_parcel:     Annotated[Optional[bool],      Query()] = None,
    has_qpublic:    Annotated[Optional[bool],      Query()] = None,
    min_value:      Annotated[Optional[float],     Query()] = None,
    max_value:      Annotated[Optional[float],     Query()] = None,
    month_from:     Annotated[Optional[str],       Query()] = None,
    month_to:       Annotated[Optional[str],       Query()] = None,
) -> ChartFilters:
    return ChartFilters(
        counties=counties, petition_types=petition_types, tiers=tiers,
        absentee_only=absentee_only, has_parcel=has_parcel, has_qpublic=has_qpublic,
        min_value=min_value, max_value=max_value, month_from=month_from, month_to=month_to,
    )            

# 2) Absentee using 5-digit zip compare
def _five_zip(field):
    cleaned = fn.regexp_replace(field, Value(r"[^0-9]"), Value(""), Value("g"))
    return fn.nullif(fn.left(cleaned, 5), Value(""))

def _absentee_expr():
    return (
        (_five_zip(ProbateRecord.zip).is_null(False)) &
        (_five_zip(ProbateRecord.party_zip).is_null(False)) &
        (_five_zip(ProbateRecord.zip) != _five_zip(ProbateRecord.party_zip))
    )

# 3) Month helpers for range
def _first_of_month(ym: str) -> date:
    y, m = map(int, ym.split("-")); return date(y, m, 1)

def _next_month(d: date) -> date:
    y, m = d.year, d.month; return date(y + (m // 12), (m % 12) + 1, 1)

_month_label = fn.to_char(
    fn.date_trunc("month", ProbateRecord.petition_date), Value("YYYY-MM")
)

# ---- Parse query params into ChartFilters

def _apply_filters(q, f: ChartFilters) -> peewee.Query:

    if f.counties:
        q = q.where(ProbateRecord.county.in_(f.counties))
    if f.petition_types:
        q = q.where(ProbateRecord.petition_type.in_(f.petition_types))
    if f.tiers:
        tiers = [t if t != "med" else "medium" for t in f.tiers]
        q = q.where((ProbateRecord.tier.in_(f.tiers)) | (ProbateRecord.tier.in_(tiers)))
    if f.absentee_only:
        q = q.where(_absentee_expr())
    if f.has_parcel:
        q = q.where((ProbateRecord.parcel_number.is_null(False)) & (ProbateRecord.parcel_number != ""))
    if f.has_qpublic:
        q = q.where((ProbateRecord.qpublic_report_url.is_null(False)) & (ProbateRecord.qpublic_report_url != ""))
    if f.min_value is not None:
        q = q.where(ProbateRecord.property_value.is_null(False) & (ProbateRecord.property_value >= f.min_value))
    if f.max_value is not None:
        q = q.where(ProbateRecord.property_value.is_null(False) & (ProbateRecord.property_value <= f.max_value))
    if f.month_from:
        q = q.where(ProbateRecord.petition_date.is_null(False) & (ProbateRecord.petition_date >= _first_of_month(f.month_from)))
    if f.month_to:
        q = q.where(ProbateRecord.petition_date.is_null(False) & (ProbateRecord.petition_date < _next_month(_first_of_month(f.month_to))))
    return q



class KPIValue(BaseModel):
    label: str
    value: Union[int, float, str]

class KPIResponse(BaseModel):
    kpis: List[KPIValue]

class PropertyClassCount(BaseModel):
    property_class: str
    count: int

class PropertyClassMixResponse(BaseModel):
    propertyClassMix: List[PropertyClassCount]

class CountyCount(BaseModel):
    county: str
    count: int

class CountyCountResponse(BaseModel):
    countByCounty: List[CountyCount]

class CountyAverageValue(BaseModel):
    county: str
    average_value: float

class CountyAverageValueResponse(BaseModel):
    averageValueByCounty: List[CountyAverageValue]

class BinnedDaysCount(BaseModel):
    bin: str
    count: int

class BinnedDaysSincePetitionResponse(BaseModel):
    daysSincePetitionHist: List[BinnedDaysCount]

class BinnedDaysDeathToPetitionResponse(BaseModel):
    daysDeathToPetitionHist: List[BinnedDaysCount]

# Add Petition Types
class PetitionTypeCount(BaseModel):
    petition_type: str
    count: int

class PetitionTypeResponse(BaseModel):
    petitionTypes: List[PetitionTypeCount]

class PartyCount(BaseModel):
    party: str
    count: int

class PartiesResponse(BaseModel):
    parties: List[PartyCount]

class AbsCountyItem(BaseModel):
    county: str
    absentee: int
    local: int

class AbsCountyResp(BaseModel):
    absenteeByCounty: List[AbsCountyItem]

class FilingsMonthItem(BaseModel):
    month: str
    count: int

class FilingsMonthResp(BaseModel):
    filingsByMonth: List[FilingsMonthItem]

class AbsRateItem(BaseModel):
    month: str
    rate: float

class AbsRateResp(BaseModel):
    absenteeRateTrend: List[AbsRateItem]

class ValueBucket(BaseModel):
    bucket: str
    count: int

class ValueHistResp(BaseModel):
    valueHist: List[ValueBucket]

@router.get("/kpis")
def get_kpis(f: Annotated[ChartFilters, Depends(chart_filters_dep)]):
    absentee_case = Case(None, [(_absentee_expr(), 1)], 0)
    base = _apply_filters(ProbateRecord.select(), f)
    query = (
        base.select(
            fn.COUNT(fn.DISTINCT(ProbateRecord.id)).alias("total_records"),
            fn.COUNT(fn.DISTINCT(ProbateRecord.county)).alias(
                "total_counties"
            ),
            fn.AVG(
                Case(
                    None,
                    [
                        (
                            (ProbateRecord.parcel_number.is_null(False))
                            & (ProbateRecord.parcel_number != ""),
                            1,
                        )
                    ],
                    0,
                )
            ).alias("with_parcel"),
            fn.AVG(
                Case(
                    None,
                    [
                        (
                            ProbateRecord.property_value.is_null(False),
                            ProbateRecord.property_value,
                        )
                    ],
                )
            ).alias("average_value"),
            fn.AVG(
                Case(
                    None,
                    [
                        (
                            ProbateRecord.property_acres.is_null(False),
                            ProbateRecord.property_acres,
                        )
                    ],
                )
            ).alias("average_acres"),
            fn.AVG(absentee_case).alias("absentee_rate"),
        )
        .dicts()
        .first()
    )

    return KPIResponse(
        kpis=[
            KPIValue(label="Total Records", value=query["total_records"]),
            KPIValue(label="Counties", value=query["total_counties"]),
            KPIValue(
                label="With Parcel", value=f"{query['with_parcel']*100:.2f}%"
            ),
            KPIValue(
                label="Average Property Value",
                value=f"$ {query['average_value']:.2f}" if query['average_value'] else "N/A",
            ),
            KPIValue(
                label="Average Property Acres",
                value=f"{query['average_acres']:.2f} acres" if query['average_acres'] else "N/A",
            ),
            KPIValue(
                label="Absentee %",
                value=f"{((query['absentee_rate'] or 0)*100):.0f}%" if query['absentee_rate'] is not None else "N/A",
            ),
        ]
    )


@router.get("/property-class-mix")
def property_class_mix(f: Annotated[ChartFilters, Depends(chart_filters_dep)]):
    base = _apply_filters(ProbateRecord.select(), f)

    q = (
        base.select(
            fn.coalesce(ProbateRecord.property_class, Value("Unknown")).alias(
                "property_class"
            ),
            fn.count(Value(1)).alias("count"),
        )
        .where(
            ProbateRecord.property_class.is_null(False)
            & (ProbateRecord.property_class != "")
        )
        .group_by(ProbateRecord.property_class)
        .order_by(SQL("count").desc())
        .dicts()
    )
    return PropertyClassMixResponse(
        propertyClassMix=[PropertyClassCount(**row) for row in q]
    )


@router.get("/count-by-county")
def count_by_county(f: Annotated[ChartFilters, Depends(chart_filters_dep)]):
    base = _apply_filters(ProbateRecord.select(), f)
    q = (
        base.select(
            fn.coalesce(ProbateRecord.county, Value("Unknown")).alias(
                "county"
            ),
            fn.count(Value(1)).alias("count"),
        )
        .where(
            ProbateRecord.county.is_null(False) & (ProbateRecord.county != "")
        )
        .group_by(ProbateRecord.county)
        .order_by(SQL("count").desc())
        .dicts()
    )

    return CountyCountResponse(countByCounty=[CountyCount(**row) for row in q])


@router.get("/average-value-by-county")
def average_value_by_county(f: Annotated[ChartFilters, Depends(chart_filters_dep)]):
    base = _apply_filters(ProbateRecord.select(), f)
    q = (
        base.select(
            fn.coalesce(ProbateRecord.county, Value("Unknown")).alias(
                "county"
            ),
            fn.AVG(
                Case(
                    None,
                    [
                        (
                            ProbateRecord.property_value.is_null(False),
                            ProbateRecord.property_value,
                        )
                    ],
                )
            ).alias("average_value"),
        )
        .where(
            ProbateRecord.county.is_null(False)
            & (ProbateRecord.county != "")
            & (ProbateRecord.property_value.is_null(False))
        )
        .group_by(ProbateRecord.county)
        .order_by(SQL("average_value").desc())
        .dicts()
    )

    return [
        CountyAverageValueResponse(
            averageValueByCounty=[CountyAverageValue(**row) for row in q]
        )
    ]


@router.get("/binned-days-since-petition")
def binned_days_since_petition(f: Annotated[ChartFilters, Depends(chart_filters_dep)]):
    base = _apply_filters(ProbateRecord.select(), f)
    bins = [
        (0, 30, "0-30 days"),
        (31, 60, "31-60 days"),
        (61, 90, "61-90 days"),
        (91, 180, "91-180 days"),
        (181, 365, "181-365 days"),
        (366, 10**6, "> 1 year"),
    ]

    # Postgres: days since = date_part('day', age(CURRENT_DATE, petition_date))
    days_since = SQL("CURRENT_DATE") - fn.DATE(ProbateRecord.petition_date)

    # CASE expression for binning
    bin_cases = Case(
        None,
        [
            ((days_since >= low) & (days_since <= high), Value(label))
            for (low, high, label) in bins
        ],
        Value("Unknown"),
    ).alias("bin")

    count_expr = fn.COUNT(1).alias("count")

    q = (
        base.select(bin_cases, count_expr)
        .where(ProbateRecord.petition_date.is_null(False))
        .group_by(bin_cases)  # reuse the same expression you selected
        .order_by(count_expr.desc())  # reuse the same count expression
        .dicts()
    )

    return BinnedDaysSincePetitionResponse(
        daysSincePetitionHist=[BinnedDaysCount(**row) for row in q]
    )


# Same graph but with difference between petition date and death date
@router.get("/binned-days-petition-to-death")
def binned_days_petition_to_death(f: Annotated[ChartFilters, Depends(chart_filters_dep)]):
    base = _apply_filters(ProbateRecord.select(), f)
    bins = [
        (0, 30, "0-30 days"),
        (31, 60, "31-60 days"),
        (61, 90, "61-90 days"),
        (91, 180, "91-180 days"),
        (181, 365, "181-365 days"),
        (366, 10**6, "> 1 year"),
    ]

    # Postgres: days since = date_part('day', age(petition_date, death_date))
    days_between = fn.DATE(ProbateRecord.petition_date) - fn.DATE(
        ProbateRecord.death_date
    )

    # CASE expression for binning
    bin_cases = Case(
        None,
        [
            ((days_between >= low) & (days_between <= high), Value(label))
            for (low, high, label) in bins
        ],
        Value("Unknown"),
    ).alias("bin")

    count_expr = fn.COUNT(1).alias("count")

    q = (
        base.select(bin_cases, count_expr)
        .where(
            (ProbateRecord.petition_date.is_null(False))
            & (ProbateRecord.death_date.is_null(False))
        )
        .group_by(bin_cases)  # reuse the same expression you selected
        .order_by(count_expr.desc())  # reuse the same count expression
        .dicts()
    )

    return BinnedDaysDeathToPetitionResponse(
        daysDeathToPetitionHist=[BinnedDaysCount(**row) for row in q]
    )


@router.get("/petition-types")
def petition_type_mix(f: Annotated[ChartFilters, Depends(chart_filters_dep)]):
    base = _apply_filters(ProbateRecord.select(), f)
    q = (
        base.select(
            fn.coalesce(ProbateRecord.petition_type, Value("Unknown")).alias(
                "petition_type"
            ),
            fn.count(Value(1)).alias("count"),
        )
        .where(
            ProbateRecord.petition_type.is_null(False)
            & (ProbateRecord.petition_type != "")
        )
        .group_by(ProbateRecord.petition_type)
        .order_by(SQL("count").desc())
        .dicts()
    )

    return PetitionTypeResponse(
        petitionTypes=[PetitionTypeCount(**row) for row in q]
    )


@router.get("/get-parties")
def petition_types(f: Annotated[ChartFilters, Depends(chart_filters_dep)]):
    base = _apply_filters(ProbateRecord.select(), f)
    parties = (
        base.select(
            ProbateRecord.party, fn.count(Value(1)).alias("count")
        )
        .where(
            ProbateRecord.party.is_null(False) & (ProbateRecord.party != "")
        )
        .group_by(ProbateRecord.party)
        .order_by(SQL("count").desc())
        .dicts()
    )

    return PartiesResponse(parties=[PartyCount(**row) for row in parties])

@router.get("/absentee-by-county", response_model=AbsCountyResp)
def absentee_by_county(f: Annotated[ChartFilters, Depends(chart_filters_dep)]):
    ae = _absentee_expr()
    absentee_sum = fn.sum(Case(None, [(ae, 1)], 0))
    total = fn.count(Value(1))
    local_cnt = total - absentee_sum

    base = _apply_filters(ProbateRecord.select(), f)
    q = (
        base
        .select(
            ProbateRecord.county,
            absentee_sum.alias("absentee"),
            local_cnt.alias("local"),
        )
        .where(ProbateRecord.county.is_null(False) & (ProbateRecord.county != ""))
        .group_by(ProbateRecord.county)
        .order_by(SQL("absentee DESC"))
        .dicts()
    )

    
    return AbsCountyResp(
        absenteeByCounty=[AbsCountyItem(**row) for row in q]
    )

@router.get("/filings-by-month", response_model=FilingsMonthResp)
def filings_by_month(f: Annotated[ChartFilters, Depends(chart_filters_dep)]):
    base = _apply_filters(ProbateRecord.select(), f)
    q = (
        base
        .select(_month_label.alias("month"), fn.count(Value(1)).alias("count"))
        .where(ProbateRecord.petition_date.is_null(False))
        .group_by(SQL("month"))
        .order_by(SQL("month"))
        .dicts()
    )
    
    return FilingsMonthResp(
        filingsByMonth=[FilingsMonthItem(**row) for row in q]
    )

@router.get("/absentee-rate-trend", response_model=AbsRateResp)
def absentee_rate_trend(f: Annotated[ChartFilters, Depends(chart_filters_dep)]):
    ae = _absentee_expr()
    rate = fn.avg(Case(None, [(ae, 1)], 0))
    base = _apply_filters(ProbateRecord.select(), f)
    q = (
        base
        .select(_month_label.alias("month"), rate.alias("rate"))
        .where(ProbateRecord.petition_date.is_null(False))
        .group_by(SQL("month"))
        .order_by(SQL("month"))
        .dicts()
    )

    return AbsRateResp(
        absenteeRateTrend=[AbsRateItem(month=row["month"], rate=float(row["rate"] or 0)) for row in q]
    )


@router.get("/value-hist", response_model=ValueHistResp)
def value_hist(f: Annotated[ChartFilters, Depends(chart_filters_dep)]):
    base = _apply_filters(ProbateRecord.select(), f)
    pv = ProbateRecord.property_value

    # [low, high) bins; last bin is 1M+ (no upper bound)
    bins = [
        (0,        100_000,  "<100k"),
        (100_000,  250_000,  "100–250k"),
        (250_000,  500_000,  "250–500k"),
        (500_000, 1_000_000, "500k–1M"),
        (1_000_000, None,    "1M+"),
    ]

    # Build CASE WHEN comparisons (wrap numeric literals in Value(...))
    cases = []
    for low, high, label in bins:
        low_v = Value(low)
        if high is None:
            cond = (pv.is_null(False)) & (pv >= low_v)
        else:
            high_v = Value(high)
            cond = (pv.is_null(False)) & (pv >= low_v) & (pv < high_v)  # half-open interval
        cases.append((cond, Value(label)))

    bucket_expr = Case(None, cases, Value("Unknown")).alias("bucket")
    count_expr = fn.COUNT(1).alias("count")

    # Query without SQL ordering on alias (avoid "column 'bucket' does not exist")
    q = (
        base
        .select(bucket_expr, count_expr)
        .where(ProbateRecord.property_value.is_null(False))
        .group_by(bucket_expr)
        .dicts()
    )

    rows = [{"bucket": r["bucket"], "count": int(r["count"] or 0)} for r in q]

    # Order in Python (stable and simple)
    order = {label: i for i, (_, _, label) in enumerate(bins, start=1)}
    rows.sort(key=lambda r: order.get(r["bucket"], 999))


    return ValueHistResp(valueHist=[ValueBucket(**row) for row in rows])
