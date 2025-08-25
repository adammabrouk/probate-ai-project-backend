import csv
from io import StringIO
from fastapi import APIRouter, UploadFile, File
from probate_ops.models.database import ProbateRecord

router = APIRouter()


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    content = await file.read()

    records = []
    with StringIO(content.decode()) as data:
        reader = csv.DictReader(data)
        for row in reader:
            try:
                records.append(ProbateRecord.from_dict(row))
            except Exception as e:
                print(f"Error processing row {row}: {e}")

    ProbateRecord.insert_many(records).on_conflict_ignore().execute()

    return {"status": "file processed", "filename": file.filename}
