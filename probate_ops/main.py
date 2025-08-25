from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.registry import registry
from .tools.sql_tool import run_sql
from .tools.df_tool import run_df
from .tools.llm_score_tool import score_llm
from .controllers import ingest, analyze, ask, flows, chart

app = FastAPI(title="ProbateOps API", version="1.0.0")

# CORS middleware to allow requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# register tools
registry.register("run_sql", run_sql)
registry.register("run_df", run_df)
registry.register("score_llm", score_llm)

app.include_router(ingest.router)
app.include_router(analyze.router)
app.include_router(ask.router)
app.include_router(flows.router)
app.include_router(chart.router)

@app.get("/health")
def health():
    return {"ok": True}
