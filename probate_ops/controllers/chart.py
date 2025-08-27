from probate_ops.models.database import ProbateRecord
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query
from typing import List
import peewee
from peewee import fn, Case, SQL, Value
from typing import Any, Union

router = APIRouter(prefix="/charts", tags=["Charts"])


_month_label = fn.to_char(
    fn.date_trunc("month", ProbateRecord.petition_date), Value("YYYY-MM")
)


def _absentee_expr():
    return (
        (ProbateRecord.zip.is_null(False))
        & (ProbateRecord.party_zip.is_null(False))
        & (ProbateRecord.zip != ProbateRecord.party_zip)
    )


def _apply_filters(q: peewee.Query, f: Any):
    # For now returning the query as is
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

@router.get("/kpis")
def get_kpis():
    absentee_case = Case(None, [(_absentee_expr(), 1)], 0)

    query = (
        ProbateRecord.select(
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
                value=f"$ {query['average_value']:.2f}",
            ),
            KPIValue(
                label="Average Property Acres",
                value=f"{query['average_acres']:.2f} acres",
            ),
            KPIValue(
                label="Absentee %",
                value=f"{((query['absentee_rate'] or 0)*100):.0f}%",
            ),
        ]
    )


@router.get("/property-class-mix")
def property_class_mix():
    q = (
        ProbateRecord.select(
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
def count_by_county():
    q = (
        ProbateRecord.select(
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
def average_value_by_county():
    q = (
        ProbateRecord.select(
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


# Binned days since petition
from peewee import fn, Case, Value, SQL


@router.get("/binned-days-since-petition")
def binned_days_since_petition():
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
        ProbateRecord.select(bin_cases, count_expr)
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
def binned_days_petition_to_death():
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
        ProbateRecord.select(bin_cases, count_expr)
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
def petition_type_mix():
    q = (
        ProbateRecord.select(
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
def petition_types():
    parties = (
        ProbateRecord.select(
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
def absentee_by_county():
    ae = _absentee_expr()
    absentee_sum = fn.sum(Case(None, [(ae, 1)], 0))
    total = fn.count(Value(1))
    local_cnt = total - absentee_sum

    q = (
        ProbateRecord
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