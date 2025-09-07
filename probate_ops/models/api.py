from pydantic import BaseModel
from fastapi import Query
from typing import Optional, List


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
    property_class: Optional[str] = Query(None)
    days_since_petition_min: Optional[int] = Query(None)
    days_since_petition_max: Optional[int] = Query(None)
    days_death_to_petition_min: Optional[int] = Query(None)
    days_death_to_petition_max: Optional[int] = Query(None)
    has_value: Optional[bool] = Query(None)
