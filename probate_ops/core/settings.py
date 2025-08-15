import os
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"
    DB_URL: str = "duckdb:///probate_ops/data/duckdb.db"
    BLOB_DIR: str = "./_blobs"
import os
print("ENV seen by Python?", "OPENAI_API_KEY" in os.environ)  # should be True
settings = Settings()

print(settings)
