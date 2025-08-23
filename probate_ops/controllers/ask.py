# import the UploadFile class for handling file uploads
import csv
from fastapi import UploadFile, APIRouter, WebSocket, File, Form
from pydantic import BaseModel
from probate_ops.flows.dataviz import graph

router = APIRouter()


class AskReq(BaseModel):
    thread_id: str
    question: str
    file: UploadFile  # Uncomment if you want to handle file uploads


@router.post("/ask")
async def ask(
    question: str = Form(...),
    file: UploadFile = File(
        ...
    ),  # Uncomment if you want to handle file uploads
    thread_id: str = Form(...),
):
    # Minimal heuristic: prefer SQL for counts/group-bys; otherwise DF

    state = {
        "question": question,
        "file": csv.DictReader(
            (await file.read()).decode("utf-8").splitlines()
        ),
    }

    # Execute the workflow

    result = await graph.ainvoke(state, config={"thread_id": thread_id})
    return result["file_schema"]


@router.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        async for event in graph.astream(
            {"file_schema": [data]}, config=config, stream_mode="messages"
        ):
            await websocket.send_text(event[0].content)
