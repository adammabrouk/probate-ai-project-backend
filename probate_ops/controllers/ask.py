from fastapi import APIRouter
from pydantic import BaseModel
from ..core.registry import registry
from ..core.storage import sqlstore

router = APIRouter()

class AskReq(BaseModel):
    question: str
    mode: str | None = None   # "sql" | "df" | None (let LLM choose)

@router.post("/ask")
def ask(req: AskReq):
    # Minimal heuristic: prefer SQL for counts/group-bys; otherwise DF
    if req.mode == "sql" or ("count" in req.question.lower() or "top" in req.question.lower()):
        sql = "SELECT county, COUNT(*) AS n FROM records GROUP BY county ORDER BY n DESC LIMIT 10"
        res = registry.call("run_sql", query=sql)
        return {"answer": "Top counties by record count", "sql_used": sql, **res}
    # Demo DF op
    import pandas as pd
    df = sqlstore.query("SELECT * FROM records")
    res = registry.call("run_df", df=df, op="count_by", by="petition_type")
    return {"answer": "Count by petition type", "data": res["rows"]}
