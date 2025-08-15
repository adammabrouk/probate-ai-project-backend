import pandas as pd
from typing import Literal


def run_df(
    df: pd.DataFrame,
    op: Literal["count_by", "sum_by"],
    by: str,
    col: str | None = None,
) -> dict:
    if op == "count_by":
        out = (
            df.groupby(by)
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
    elif op == "sum_by" and col:
        out = (
            df.groupby(by)[col]
            .sum(numeric_only=True)
            .reset_index()
            .sort_values(col, ascending=False)
        )
    else:
        raise ValueError("unsupported op")
    return {"rows": out.head(100).to_dict(orient="records")}
