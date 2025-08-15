from fastapi import APIRouter
from pydantic import BaseModel
from ..flows.full_enrich import build_graph

router = APIRouter()
graph = build_graph()

class FlowReq(BaseModel):
    records: list[dict]

@router.post("/flows/score")
def run_flow(req: FlowReq):
    state = {"records": req.records, "i": 0}
    result = graph.invoke(state)
    return {"records": result["records"], "count": len(result["records"])}
