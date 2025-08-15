from fastapi import APIRouter, UploadFile, File
from ..utils.normalize import read_table, normalize
from ..core.storage import sqlstore, blobstore

router = APIRouter()


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    content = await file.read()
    path = blobstore.save(content, suffix="." + file.filename.split(".")[-1])
    import pandas as pd

    df = read_table(content, file.filename)
    df = normalize(df)
    sqlstore.write_df(df, table="records")
    return {"ok": True, "blob": path, "rows": int(len(df))}
