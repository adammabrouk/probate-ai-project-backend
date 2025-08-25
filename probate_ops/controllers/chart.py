from probate_ops.models.database import ProbateRecord
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query
from typing import List
import peewee
from peewee import fn, Case, SQL, Value
from typing import Any, Union

router = APIRouter(prefix="/charts", tags=["Charts"])


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


@router.get("/kpis")
def get_kpis():
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
        .where(ProbateRecord.property_class.is_null(False) & (ProbateRecord.property_class != ""))
        .group_by(ProbateRecord.property_class)
        .order_by(SQL("count").desc())
        .dicts()
    )
    return PropertyClassMixResponse(
        propertyClassMix=[PropertyClassCount(**row) for row in q]
    )
