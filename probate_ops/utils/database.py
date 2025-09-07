import peewee
from probate_ops.models.database import ProbateRecord
from probate_ops.models.api import ChartFilters
from datetime import date
from typing import Optional, List
from fastapi import Query
from typing_extensions import Annotated
from peewee import fn, Value, SQL


def _apply_filters(q, f: ChartFilters) -> peewee.Query:

    if f.counties:
        q = q.where(ProbateRecord.county.in_(f.counties))

    if f.petition_types:
        q = q.where(ProbateRecord.petition_type.in_(f.petition_types))

    if f.tiers:
        tiers = [t if t != "med" else "medium" for t in f.tiers]
        q = q.where(
            (ProbateRecord.tier.in_(f.tiers)) | (ProbateRecord.tier.in_(tiers))
        )

    if f.absentee_only:
        q = q.where(_absentee_expr())

    if f.has_parcel:
        q = q.where(
            (ProbateRecord.parcel_number.is_null(False))
            & (ProbateRecord.parcel_number != "")
        )

    if f.has_qpublic:
        q = q.where(
            (ProbateRecord.qpublic_report_url.is_null(False))
            & (ProbateRecord.qpublic_report_url != "")
        )

    if f.min_value is not None:
        q = q.where(
            ProbateRecord.property_value.is_null(False)
            & (ProbateRecord.property_value >= f.min_value)
        )

    if f.max_value is not None:
        q = q.where(
            ProbateRecord.property_value.is_null(False)
            & (ProbateRecord.property_value <= f.max_value)
        )

    if f.month_from:
        q = q.where(
            ProbateRecord.petition_date.is_null(False)
            & (ProbateRecord.petition_date >= _first_of_month(f.month_from))
        )

    if f.month_to:
        q = q.where(
            ProbateRecord.petition_date.is_null(False)
            & (
                ProbateRecord.petition_date
                < _next_month(_first_of_month(f.month_to))
            )
        )
    if f.property_class:
        q = q.where(ProbateRecord.property_class == f.property_class)

    # Days since petition (CURRENT_DATE - petition_date)
    days_since_expr = (SQL('CURRENT_DATE') -  fn.DATE(ProbateRecord.petition_date))
    if f.days_since_petition_min:
        q = q.where(
            (ProbateRecord.petition_date.is_null(False)) &
            (days_since_expr >= f.days_since_petition_min)
        )
    if f.days_since_petition_max:
        q = q.where(
            (ProbateRecord.petition_date.is_null(False)) &
            (days_since_expr <= f.days_since_petition_max)
        )
    # Death to petition delay (petition_date - death_date)
    death_to_petition_expr = (fn.DATE(ProbateRecord.petition_date) - fn.DATE(ProbateRecord.death_date))
    if f.days_death_to_petition_min:
        q = q.where(
            (ProbateRecord.petition_date.is_null(False)) &
            (ProbateRecord.death_date.is_null(False)) &
            (death_to_petition_expr >= f.days_death_to_petition_min)
        )
    if f.days_death_to_petition_max:
        q = q.where(
            (ProbateRecord.petition_date.is_null(False)) &
            (ProbateRecord.death_date.is_null(False)) &
            (death_to_petition_expr <= f.days_death_to_petition_max)
        )
    if f.has_value:
        q = q.where(ProbateRecord.property_value.is_null(False))
    return q


def chart_filters_dep(
    counties: Annotated[Optional[List[str]], Query()] = None,
    petition_types: Annotated[Optional[List[str]], Query()] = None,
    tiers: Annotated[Optional[List[str]], Query()] = None,
    absentee_only: Annotated[Optional[bool], Query()] = None,
    has_parcel: Annotated[Optional[bool], Query()] = None,
    has_qpublic: Annotated[Optional[bool], Query()] = None,
    min_value: Annotated[Optional[float], Query()] = None,
    max_value: Annotated[Optional[float], Query()] = None,
    month_from: Annotated[Optional[str], Query()] = None,
    month_to: Annotated[Optional[str], Query()] = None,
    property_class: Annotated[Optional[str], Query()] = None,
    days_since_petition_min: Annotated[Optional[int], Query()] = None,
    days_since_petition_max: Annotated[Optional[int], Query()] = None,
    days_death_to_petition_min: Annotated[Optional[int], Query()] = None,
    days_death_to_petition_max: Annotated[Optional[int], Query()] = None,
    has_value: Annotated[Optional[bool], Query()] = None
) -> ChartFilters:
    return ChartFilters(
        counties=counties,
        petition_types=petition_types,
        tiers=tiers,
        absentee_only=absentee_only,
        has_parcel=has_parcel,
        has_qpublic=has_qpublic,
        min_value=min_value,
        max_value=max_value,
        month_from=month_from,
        month_to=month_to,
        property_class=property_class,
        days_since_petition_min=days_since_petition_min,
        days_since_petition_max=days_since_petition_max,
        days_death_to_petition_min=days_death_to_petition_min,
        days_death_to_petition_max=days_death_to_petition_max,
        has_value=has_value
    )


# 2) Absentee using 5-digit zip compare
def _five_zip(field):
    cleaned = fn.regexp_replace(field, Value(r"[^0-9]"), Value(""), Value("g"))
    return fn.nullif(fn.left(cleaned, 5), Value(""))


def _absentee_expr():
    return (
        (_five_zip(ProbateRecord.zip).is_null(False))
        & (_five_zip(ProbateRecord.party_zip).is_null(False))
        & (_five_zip(ProbateRecord.zip) != _five_zip(ProbateRecord.party_zip))
    )


# 3) Month helpers for range
def _first_of_month(ym: str) -> date:
    y, m = map(int, ym.split("-"))
    return date(y, m, 1)


def _next_month(d: date) -> date:
    y, m = d.year, d.month
    return date(y + (m // 12), (m % 12) + 1, 1)


_month_label = fn.to_char(
    fn.date_trunc("month", ProbateRecord.petition_date), Value("YYYY-MM")
)
