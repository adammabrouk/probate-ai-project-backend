import os, uuid, duckdb, pandas as pd
from .settings import settings

os.makedirs(settings.BLOB_DIR, exist_ok=True)


class BlobStore:
    def save(self, bytes_: bytes, suffix: str) -> str:
        name = f"{uuid.uuid4().hex}{suffix}"
        path = os.path.join(settings.BLOB_DIR, name)
        with open(path, "wb") as f:
            f.write(bytes_)
        return path


blobstore = BlobStore()


class SQLStore:
    def __init__(self):
        self.con = duckdb.connect(
            settings.DB_URL.replace("duckdb:///", "")
        )  # dev default
        self.con.execute("PRAGMA threads=4")

    def write_df(self, df: pd.DataFrame, table: str):
        self.con.execute(
            f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM df LIMIT 0"
        )
        self.con.register("df", df)
        self.con.execute(f"INSERT INTO {table} SELECT * FROM df")
        self.con.unregister("df")

    def query(self, sql: str) -> pd.DataFrame:
        return self.con.execute(sql).df()
