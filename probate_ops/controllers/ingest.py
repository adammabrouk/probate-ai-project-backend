import csv
from io import StringIO
from fastapi import APIRouter, UploadFile, File
from probate_ops.models.database import ProbateRecord

router = APIRouter()


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    content = await file.read()

    with StringIO(content.decode()) as data:
        reader = csv.DictReader(data)        
        records = [ProbateRecord.from_dict(row) for row in reader]

    from pprint import pprint;
    for record in records:
        pprint(
            { k : len(v) for k,v in record.items() if isinstance(v, str) and len(v) > 255 }
        )
    ProbateRecord.insert_many(records).on_conflict_ignore().execute()

    return {"status": "file processed", "filename": file.filename}