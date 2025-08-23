import csv
from typing import TypedDict, List
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from probate_ops.core.registry import registry, ToolRegistry
from probate_ops.core.settings import settings


# ─────────────────── Models & State ───────────────────


class QuestionParserResponse(BaseModel):
    is_relevant: bool
    relevant_fields: List[str] = []


class State(TypedDict):
    question: str
    file: csv.DictReader
    file_schema: List[str]


# ─────────────────── Agent ───────────────────


class DataVizAgent:
    def __init__(self):
        self.tool_registry = ToolRegistry()
        self.llm = ChatOpenAI(
            api_key=settings.OPENAI_API_KEY, model="gpt-4o-mini", temperature=0
        )

    def parse_question(self, state: "State"):
        """Parse the user's question to extract relevant data (returns partial state)."""
        system_prompt = (
            "You are a data analyst who summarizes SQL/CSV tables and parses user questions "
            "about a dataset. You will be given the question and the table schema; identify "
            "the relevant fields. If the question is not relevant or lacks information, set "
            "is_relevant to False."
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "CSV schema: {file_schema}\nQuestion: {question}"),
            ]
        )

        chain = prompt | self.llm.with_structured_output(
            QuestionParserResponse
        )

        # Prefer explicit schema if present; otherwise try to read from DictReader
        schema = (
            state.get("file_schema")
            or getattr(state["file"], "fieldnames", None)
            or []
        )

        response: QuestionParserResponse = chain.invoke(
            {
                "file_schema": ", ".join(schema),
                "question": state["question"],
            }
        )

        # Return ONLY the updates to state
        return {"file_schema": response.relevant_fields}

    def create_workflow(self):
        """Create a workflow for data visualization tasks."""
        workflow = StateGraph(State)
        workflow.add_node("parse_question", self.parse_question)
        workflow.set_entry_point("parse_question")
        workflow.add_edge("parse_question", END)
        return workflow.compile()


graph = DataVizAgent().create_workflow()
