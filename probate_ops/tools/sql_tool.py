import pandas as pd
from probate_ops.core.storage import SQLStore

SAFE = (
    "select",
    "with",
    "from",
    "where",
    "group",
    "order",
    "limit",
    "offset",
    "join",
    "on",
    "having",
)


def _safe(sql: str) -> str:
    s = sql.strip().lower()
    if not any(s.startswith(k) for k in ("select", "with")):
        raise ValueError("Only SELECT/CTE queries allowed")
    return sql


def run_sql(query: str) -> dict:
    df: pd.DataFrame = SQLStore().query(_safe(query))
    preview = df.head(50).to_dict(orient="records")
    return {"rows": preview, "row_count": len(df)}
